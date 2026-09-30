"""Packaging and import-hygiene tests.

These guard properties of the *distribution* rather than runtime behavior:
the PEP 561 typing marker and the fact that
importing the package has no side effects on the caller's environment.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import empire_core

PACKAGE_DIR = Path(empire_core.__file__).parent
SRC_DIR = PACKAGE_DIR.parent


def test_py_typed_marker_present() -> None:
    """PEP 561: without py.typed, consumers' type checkers ignore our annotations."""
    assert (PACKAGE_DIR / "py.typed").is_file()


def test_import_does_not_read_dotenv_from_cwd(tmp_path: Path) -> None:
    """`import empire_core` must not mutate the caller's os.environ from a nearby .env."""
    (tmp_path / ".env").write_text("EMPIRE_CORE_DOTENV_CANARY=leaked\n")
    env = dict(os.environ, PYTHONPATH=str(SRC_DIR))
    env.pop("EMPIRE_CORE_DOTENV_CANARY", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import empire_core, os; print(os.environ.get('EMPIRE_CORE_DOTENV_CANARY'))",
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert result.stdout.strip() == "None", f"import leaked .env into os.environ: {result.stdout!r}"


REPO_ROOT = SRC_DIR.parent


def _load_toml(path: Path) -> dict:
    tomllib = pytest.importorskip("tomllib", reason="requires Python 3.11+")
    return tomllib.loads(path.read_text())


@pytest.mark.skipif(not (REPO_ROOT / "uv.lock").is_file(), reason="not running from a source checkout")
def test_lockfile_records_the_current_project_version() -> None:
    """uv.lock's entry for this project must match pyproject's version.

    semantic-release bumps only ``pyproject.toml:project.version``, so unless the
    release also refreshes the lock, uv.lock keeps the *previous* version and
    ``uv lock --check`` / ``uv sync --locked`` fail on a fresh clone. Master drifted
    two releases behind this way before it was caught.
    """
    project = _load_toml(REPO_ROOT / "pyproject.toml")["project"]
    lock = _load_toml(REPO_ROOT / "uv.lock")

    locked = [pkg for pkg in lock["package"] if pkg["name"] == project["name"]]
    assert locked, f"{project['name']} has no entry in uv.lock"
    assert locked[0]["version"] == project["version"], (
        f"uv.lock records {project['name']} {locked[0]['version']} but pyproject says "
        f"{project['version']} — run `uv lock`"
    )


@pytest.mark.skipif(not (REPO_ROOT / "pyproject.toml").is_file(), reason="not running from a source checkout")
def test_release_refreshes_and_commits_the_lockfile() -> None:
    """The release must re-lock and carry uv.lock, or the drift above returns.

    build_command runs before semantic-release stages its changes, and only paths
    listed in ``assets`` are added alongside the version bump.
    """
    config = _load_toml(REPO_ROOT / "pyproject.toml")["tool"]["semantic_release"]

    assert "uv lock" in config["build_command"], (
        "build_command must re-lock after the version bump, otherwise uv.lock keeps the previous version"
    )
    assert "uv.lock" in config.get("assets", []), (
        "uv.lock must be in semantic_release assets, otherwise the refreshed lock is never committed with the release"
    )
