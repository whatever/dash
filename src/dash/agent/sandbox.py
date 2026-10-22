"""Shell commands in the dash-sandbox pod, run over ssh with the system client."""

import asyncio
import contextlib
import re
import shlex
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

WORKSPACE = "/config/workspace"
TIMEOUT_SECONDS = 90
OUTPUT_CHARS = 20_000
CONNECT_TIMEOUT_SECONDS = 10
GITHUB_TOKEN_PATH = "/run/secrets/github/token"  # noqa: S105 — a file path, not a secret
GITHUB_TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")
MASK = "***"
EXPORT_GITHUB_TOKEN = (
    f"[ -r {GITHUB_TOKEN_PATH} ] && "
    f'export GITHUB_TOKEN="$(cat {GITHUB_TOKEN_PATH})" GH_TOKEN="$(cat {GITHUB_TOKEN_PATH})"; '
)


class CommandResult(BaseModel):
    """What a sandbox command printed and how it ended."""

    exit_code: int | None
    output: str
    output_cut: bool = False
    timed_out: bool = False


def private_key_copy(key_path: Path) -> Path:
    """Copy the given key into a new directory only this process can read, and return the copy."""
    copy = Path(tempfile.mkdtemp(prefix="dash-ssh-")) / "id"
    copy.write_bytes(key_path.read_bytes())
    copy.chmod(0o600)
    return copy


@dataclass(frozen=True)
class Sandbox:
    """Where the sandbox listens and the key that opens it."""

    host: str
    port: int
    user: str
    key: Path

    def argv(self, command: str) -> list[str]:
        """Return the ssh command line that runs the given command in the workspace."""
        remote = (
            f"{EXPORT_GITHUB_TOKEN}cd {WORKSPACE} && "
            f"timeout -s KILL {TIMEOUT_SECONDS} sh -c {shlex.quote(command)}"
        )
        return [
            "ssh",
            "-i",
            str(self.key),
            "-p",
            str(self.port),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={self.key.parent / 'known_hosts'}",
            "-o",
            f"ConnectTimeout={CONNECT_TIMEOUT_SECONDS}",
            f"{self.user}@{self.host}",
            remote,
        ]

    async def run(self, command: str) -> CommandResult:
        """Run the given command in the sandbox and return its result."""
        process = await asyncio.create_subprocess_exec(
            *self.argv(command),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            out, _ = await asyncio.wait_for(
                process.communicate(), TIMEOUT_SECONDS + CONNECT_TIMEOUT_SECONDS
            )
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            return CommandResult(exit_code=None, output="", timed_out=True)
        text = GITHUB_TOKEN.sub(MASK, out.decode(errors="replace"))
        code = process.returncode
        return CommandResult(
            exit_code=code,
            output=text[:OUTPUT_CHARS],
            output_cut=len(text) > OUTPUT_CHARS,
            timed_out=code == 137,
        )
