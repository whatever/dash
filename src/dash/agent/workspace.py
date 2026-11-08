"""Per-conversation sandbox workspaces: profiles of mounts and the script that sets one up."""

import posixpath
import re
import shlex
from collections.abc import Callable
from typing import Literal, Self

from pydantic import BaseModel, TypeAdapter, model_validator

SESSIONS_ROOT = "/config/workspace/sessions"
SHARED_ROOT = "/config/shared"
DEFAULT_PROFILE = "default"
SETUP_TIMEOUT_SECONDS = 120

NAME = re.compile(r"[A-Za-z0-9._-]+")
REF = re.compile(r"[A-Za-z0-9._/-]*")
DOTS = frozenset({"", ".", ".."})

Kind = Literal["git", "shared"]
Mode = Literal["ro", "rw"]


def _segments_ok(value: str) -> bool:
    """Return True if every segment of the given relative path is a plain name."""
    return all(NAME.fullmatch(part) and part not in DOTS for part in value.split("/"))


class Mount(BaseModel):
    """One thing placed in a session workspace.

    A `git` mount is a shallow clone of `owner/repo` at `ref`. A `shared` mount is the
    directory `source` under the sandbox's shared root: `rw` links the live directory, `ro`
    is a copy made at the session's first command with its write bits removed. Both are
    reached through a link, so `ls -la` shows a symlink.
    """

    kind: Kind
    mode: Mode = "ro"
    path: str
    ref: str = ""
    source: str

    @model_validator(mode="after")
    def check(self) -> Self:
        """Raise ValueError if the path, source or ref could leave the workspace or the repo."""
        if not _segments_ok(self.path):
            raise ValueError(f"mount path {self.path!r} must be a relative path of plain names")
        if self.kind == "git":
            owner_repo = self.source.split("/")
            if len(owner_repo) != 2 or not _segments_ok(self.source):
                raise ValueError(f"git source {self.source!r} must be owner/repo")
            if not REF.fullmatch(self.ref) or self.ref.startswith("-"):
                raise ValueError(f"git ref {self.ref!r} is not a plain ref")
        elif "/" in self.source or not _segments_ok(self.source):
            raise ValueError(f"shared source {self.source!r} must be one plain directory name")
        return self


class Profile(BaseModel):
    """What a kind of session gets: its mounts, and whether commands carry the GitHub token."""

    github: bool = True
    mounts: list[Mount] = []


_PROFILES = TypeAdapter(dict[str, Profile])


def parse_profiles(text: str) -> dict[str, Profile]:
    """Return the profiles written as the given JSON object, or none."""
    return _PROFILES.validate_json(text) if text.strip() else {}


def session_dir(session: str) -> str:
    """Return the workspace directory of the given session."""
    return f"{SESSIONS_ROOT}/{session}"


def _place(target: str, build: Callable[[str], str], *, freeze: bool) -> str:
    """Return the shell that builds a directory beside `target` and links `target` to it.

    Commands of one conversation can run at once. Each builds under its own hidden name and then
    links, which only one can do, since creating a symlink is atomic. A loser deletes its copy.
    """
    name = f".{posixpath.basename(target)}."
    built = f"{shlex.quote(posixpath.dirname(target) + '/' + name)}$$"
    quoted = shlex.quote(target)
    lock = f"chmod -R a-w {built} && " if freeze else ""
    return (
        f"if [ ! -e {quoted} ]; then rm -rf {built}; {build(built)} && {lock}"
        f"{{ ln -sn {shlex.quote(name)}$$ {quoted} 2>/dev/null || "
        f"{{ chmod -R u+w {built}; rm -rf {built}; }}; }}; fi"
    )


def _git_mount(mount: Mount, target: str) -> str:
    """Return the shell that clones the given git mount once."""
    branch = f"--branch {shlex.quote(mount.ref)} " if mount.ref else ""
    url = shlex.quote(f"https://github.com/{mount.source}")
    return _place(
        target,
        lambda tmp: f"git clone --quiet --depth 1 {branch}{url} {tmp}",
        freeze=mount.mode == "ro",
    )


def _shared_mount(mount: Mount, target: str, shared_root: str) -> str:
    """Return the shell that links, or once copies, the given shared mount."""
    source = shlex.quote(f"{shared_root}/{mount.source}")
    if mount.mode == "rw":
        quoted = shlex.quote(target)
        return f"[ -L {quoted} ] || ln -sn {source} {quoted} 2>/dev/null || [ -L {quoted} ]"
    return _place(target, lambda tmp: f"cp -a {source} {tmp}", freeze=True)


def _mount_steps(mount: Mount, root: str, shared_root: str) -> list[str]:
    """Return the shell steps that bring the given mount up to date in the workspace at `root`."""
    target = f"{root}/{mount.path}"
    parent = f"mkdir -p {shlex.quote(posixpath.dirname(target))}"
    if mount.kind == "git":
        return [parent, _git_mount(mount, target)]
    source = f"mkdir -p {shlex.quote(f'{shared_root}/{mount.source}')}"
    return [parent, source, _shared_mount(mount, target, shared_root)]


def setup_script(
    session: str,
    profile: Profile,
    *,
    sessions_root: str = SESSIONS_ROOT,
    shared_root: str = SHARED_ROOT,
) -> str:
    """Return the shell that creates the session's workspace and brings its mounts up to date."""
    root = f"{sessions_root}/{session}"
    steps = [
        f"mkdir -p {shlex.quote(root)}",
        *(step for mount in profile.mounts for step in _mount_steps(mount, root, shared_root)),
    ]
    return "set -e; " + "; ".join(steps)
