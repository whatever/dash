import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from dash.agent.workspace import (
    DEFAULT_PROFILE,
    Mount,
    Profile,
    parse_profiles,
    session_dir,
    setup_script,
)

SESSION = "0f5c1d3e-6a7b-4c8d-9e0f-123456789abc"


def sh(script: str) -> None:
    """Run the given script in a local shell."""
    subprocess.run(["sh", "-c", script], check=True)  # noqa: S603, S607 — a script the test built


def git(*args: str) -> None:
    """Run git with the given arguments."""
    subprocess.run(["git", *args], check=True)  # noqa: S603, S607 — fixed arguments in a test


def run_setup(tmp_path: Path, profile: Profile, session: str = SESSION) -> Path:
    sessions, shared = tmp_path / "sessions", tmp_path / "shared"
    script = setup_script(session, profile, sessions_root=str(sessions), shared_root=str(shared))
    sh(script)
    return sessions / session


def shared_mount(path: str, mode: str, source: str = "wiki") -> Mount:
    return Mount.model_validate({"kind": "shared", "mode": mode, "path": path, "source": source})


def test_profiles_parse() -> None:
    text = (
        '{"default": {"mounts": [{"kind": "git", "source": "acme/app", "ref": "main",'
        ' "path": "repos/app"}]}, "dream": {"github": false}}'
    )

    profiles = parse_profiles(text)

    assert profiles["default"].mounts[0].mode == "ro"
    assert profiles["default"].github
    assert not profiles["dream"].github
    assert parse_profiles("") == {}
    assert DEFAULT_PROFILE == "default"


@pytest.mark.parametrize(
    "mount",
    [
        {"kind": "shared", "source": "wiki", "path": "../escape"},
        {"kind": "shared", "source": "wiki", "path": "/abs"},
        {"kind": "shared", "source": "wiki", "path": "a//b"},
        {"kind": "shared", "source": "..", "path": "wiki"},
        {"kind": "shared", "source": "a/b", "path": "wiki"},
        {"kind": "shared", "source": "wiki; rm -rf /", "path": "wiki"},
        {"kind": "git", "source": "app", "path": "repos/app"},
        {"kind": "git", "source": "acme/../app", "path": "repos/app"},
        {"kind": "git", "source": "acme/app", "ref": "--upload-pack=x", "path": "repos/app"},
        {"kind": "git", "source": "acme/app", "ref": "a b", "path": "repos/app"},
        {"kind": "other", "source": "wiki", "path": "wiki"},
        {"kind": "shared", "source": "wiki", "path": "wiki", "mode": "rwx"},
    ],
)
def test_a_mount_that_could_escape_is_rejected(mount: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        Mount.model_validate(mount)


def test_the_session_directory_is_under_the_sessions_root() -> None:
    assert session_dir(SESSION) == f"/config/workspace/sessions/{SESSION}"


def test_setup_creates_the_workspace(tmp_path: Path) -> None:
    root = run_setup(tmp_path, Profile())

    assert root.is_dir()


def test_setup_is_repeatable(tmp_path: Path) -> None:
    profile = Profile(mounts=[shared_mount("wiki", "rw")])

    run_setup(tmp_path, profile)
    root = run_setup(tmp_path, profile)

    assert (root / "wiki").is_symlink()


def test_a_rw_shared_mount_writes_through(tmp_path: Path) -> None:
    root = run_setup(tmp_path, Profile(mounts=[shared_mount("notes/wiki", "rw")]))

    (root / "notes/wiki/page.md").write_text("hello")

    assert (tmp_path / "shared/wiki/page.md").read_text() == "hello"


def test_a_ro_shared_mount_is_a_fresh_read_only_copy(tmp_path: Path) -> None:
    profile = Profile(mounts=[shared_mount("wiki", "ro")])
    (tmp_path / "shared/wiki").mkdir(parents=True)
    (tmp_path / "shared/wiki/a.md").write_text("one")
    root = run_setup(tmp_path, profile)

    (tmp_path / "shared/wiki/a.md").write_text("two")
    run_setup(tmp_path, profile)

    page = root / "wiki/a.md"
    assert page.read_text() == "two"
    assert not (page.stat().st_mode & 0o222)
    assert not (root / "wiki").is_symlink()


def test_two_sessions_do_not_share_a_directory(tmp_path: Path) -> None:
    first = run_setup(tmp_path, Profile(), SESSION)
    second = run_setup(tmp_path, Profile(), "11111111-2222-3333-4444-555555555555")

    (first / "scratch.txt").write_text("mine")

    assert not (second / "scratch.txt").exists()


def test_a_missing_shared_directory_is_created(tmp_path: Path) -> None:
    run_setup(tmp_path, Profile(mounts=[shared_mount("wiki", "rw", source="fresh")]))

    assert (tmp_path / "shared/fresh").is_dir()


def test_a_git_mount_clones_once(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    for args in (["init", "-q", "-b", "main"], ["add", "."]):
        (origin / "f.txt").write_text("x")
        git("-C", str(origin), *args)
    git("-C", str(origin), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "m")
    mount = Mount.model_validate(
        {"kind": "git", "source": "acme/app", "ref": "main", "path": "repos/app", "mode": "ro"}
    )
    script = setup_script(SESSION, Profile(mounts=[mount]), sessions_root=str(tmp_path / "s"))

    local = script.replace("https://github.com/acme/app", str(origin))
    assert local != script
    sh(local)
    sh(local)

    clone = tmp_path / "s" / SESSION / "repos/app"
    assert (clone / "f.txt").read_text() == "x"
    assert not ((clone / "f.txt").stat().st_mode & 0o222)
