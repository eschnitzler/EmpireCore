"""Storage modules.

EXPERIMENTAL and optional: nothing in the client imports this package. Its
dependencies (``sqlmodel``, ``aiosqlite``) therefore ship as the ``storage``
extra rather than as required dependencies, so a plain install does not pull
in SQLAlchemy and greenlet.

Install with::

    pip install "empire-core[storage]"
"""

from importlib.util import find_spec

_REQUIRED_MODULES = ("sqlmodel", "aiosqlite")


def _missing_modules() -> list[str]:
    missing = []
    for name in _REQUIRED_MODULES:
        try:
            found = find_spec(name) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            missing.append(name)
    return missing


_MISSING = _missing_modules()

if _MISSING:
    raise ImportError(
        "empire_core.storage requires the optional 'storage' extra "
        f"(missing: {', '.join(_MISSING)}).\n"
        'Install it with:  pip install "empire-core[storage]"\n'
        '            or:  uv add "empire-core[storage]"'
    )
