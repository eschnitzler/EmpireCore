"""Drive several accounts through an AccountPool.

The pool hands out one logged-in client per account and refuses to hand the same
account to two callers at once. Prefer the ``leased()`` context manager: it
releases the account (and closes the client) even if your code raises, which the
manual lease/release pair only does if you write the ``try/finally`` yourself.

Accounts come from an AccountRegistry. Either point one at a file explicitly, as
below, or let the pool fall back to the process-wide default registry, which
reads ``accounts.json`` from the working directory plus every
``EMPIRE_ACCOUNT_*`` environment variable. A ``.env`` file is NOT read unless
you opt in with ``registry.load(load_env_file=True)`` — importing empire_core
no longer mutates the process environment as a side effect.

``accounts.json`` holds passwords in plain text: keep it out of version control
and ``chmod 600`` it.

    python examples/account_pool.py [accounts.json]
"""

import logging
import sys

from empire_core import AccountPool, EmpireError, LoginError, PoolExhaustedError
from empire_core.accounts import AccountRegistry

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("websocket").setLevel(logging.WARNING)


def main() -> int:
    accounts_file = sys.argv[1] if len(sys.argv) > 1 else "accounts.json"

    registry = AccountRegistry()
    registry.load(file_path=accounts_file)

    # Injecting the registry keeps this pool independent: a second pool can use a
    # completely different account set in the same process.
    pool = AccountPool(registry=registry)
    print(f"{len(pool)} account(s) configured, {pool.available_count} available")
    if not len(pool):
        print(f"No accounts found in {accounts_file!r} or the environment.", file=sys.stderr)
        return 2

    try:
        # Lease any free account.
        with pool.leased() as client:
            print(f"leased {client.username}: {len(client.castle.get_all())} castle(s)")

        # Or restrict to accounts carrying a tag (matched case-insensitively).
        try:
            with pool.leased(tag="scanner") as client:
                print(f"leased scanner {client.username}")
        except PoolExhaustedError as e:
            # Nothing was tried: no account matched, or all matches were busy or
            # inactive. Distinct from LoginError, which means every candidate was
            # tried and every one failed - back off rather than check credentials.
            print(f"no scanner available: {e}")

    except LoginError as e:
        # Raised once every candidate account has failed. The underlying cause -
        # bad credentials, a login cooldown, a bug - is chained onto it.
        print(f"pool could not log anything in: {e} (cause: {e.__cause__!r})", file=sys.stderr)
        return 1
    except EmpireError as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        # Belt and braces: closes anything still leased.
        pool.release_all()

    return 0


if __name__ == "__main__":
    sys.exit(main())
