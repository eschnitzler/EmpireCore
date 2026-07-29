"""Packaging and import-hygiene tests.

These guard properties of the *distribution* rather than runtime behaviour:
the PEP 561 typing marker, the optional ``storage`` extra, and the fact that
importing the package has no side effects on the caller's environment.
"""

import os
import subprocess
import sys
import textwrap
from importlib.util import find_spec
from pathlib import Path

import pytest

import empire_core

PACKAGE_DIR = Path(empire_core.__file__).parent
SRC_DIR = PACKAGE_DIR.parent

# Installs an import hook that makes the optional storage dependencies look
# uninstalled, so we can exercise a plain `pip install empire-core` environment
# from inside a dev environment that has the extra.
_BLOCK_STORAGE_DEPS = textwrap.dedent(
    """
    import sys

    _BLOCKED = {"sqlmodel", "aiosqlite"}

    class _Blocker:
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in _BLOCKED:
                raise ModuleNotFoundError(f"No module named {fullname!r}", name=fullname)
            return None

    for _name in list(sys.modules):
        if _name.split(".")[0] in _BLOCKED:
            del sys.modules[_name]
    sys.meta_path.insert(0, _Blocker())
    """
)


def _run_without_storage_extra(code: str) -> subprocess.CompletedProcess[str]:
    """Run `code` in a fresh interpreter where sqlmodel/aiosqlite are unimportable."""
    env = dict(os.environ, PYTHONPATH=str(SRC_DIR))
    return subprocess.run(
        [sys.executable, "-c", _BLOCK_STORAGE_DEPS + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        env=env,
    )


def test_py_typed_marker_present() -> None:
    """PEP 561: without py.typed, consumers' type checkers ignore our annotations."""
    assert (PACKAGE_DIR / "py.typed").is_file()


def test_import_works_without_storage_extra() -> None:
    """A plain install must not need sqlmodel/aiosqlite (they are the `storage` extra)."""
    result = _run_without_storage_extra(
        """
        import sys

        import empire_core
        from empire_core import AccountPool, EmpireClient  # noqa: F401

        assert "sqlmodel" not in sys.modules, "sqlmodel imported by empire_core"
        assert "aiosqlite" not in sys.modules, "aiosqlite imported by empire_core"
        print("OK", empire_core.__version__)
        """
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert result.stdout.startswith("OK")


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


def test_storage_import_error_is_actionable_without_extra() -> None:
    """Without the extra, importing the storage package must explain how to get it."""
    result = _run_without_storage_extra(
        """
        try:
            import empire_core.storage  # noqa: F401
        except ImportError as exc:
            print("IMPORTERROR", exc)
        else:
            print("NOERROR")
        """
    )
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert result.stdout.startswith("IMPORTERROR"), result.stdout
    assert "empire-core[storage]" in result.stdout, result.stdout


@pytest.mark.skipif(find_spec("sqlmodel") is None, reason="requires the 'storage' extra")
def test_storage_imports_when_extra_is_present() -> None:
    """The dependency gate must not reject an environment that does have the extra."""
    from empire_core.storage.database import GameDatabase

    assert GameDatabase is not None
