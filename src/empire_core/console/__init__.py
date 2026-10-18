"""``empire-console``: a Python REPL on a live client beside a view of its socket frames.

Needs the ``console`` extra: ``pip install 'empire-core[console]'``.
"""

import sys


def main(argv: list[str] | None = None) -> int:
    try:
        from empire_core.console.app import run
    except ModuleNotFoundError as e:
        print(f"empire-console needs the console extra (missing {e.name}): pip install 'empire-core[console]'")
        return 2
    return run(sys.argv[1:] if argv is None else argv)
