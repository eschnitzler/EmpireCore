"""Log in, list your castles, and read live troop movements.

The smallest useful end-to-end script: connect, read state, disconnect.

Run it with credentials in the environment (never inline them in a file that
might get committed)::

    export GGE_USERNAME=your_user
    export GGE_PASSWORD=your_pass
    python examples/login_and_castles.py
"""

import logging
import os
import sys

from empire_core import EmpireClient, EmpireError

# INFO is the right level for an application. DEBUG additionally dumps every
# protocol frame the library sends and receives, which is useful when reverse
# engineering a command but far too noisy otherwise.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("websocket").setLevel(logging.WARNING)


def main() -> int:
    username = os.getenv("GGE_USERNAME")
    password = os.getenv("GGE_PASSWORD")
    if not username or not password:
        print("Set GGE_USERNAME and GGE_PASSWORD first.", file=sys.stderr)
        return 2

    client = EmpireClient(username=username, password=password)
    try:
        # login() opens the connection and raises on failure - LoginError for
        # bad credentials, LoginCooldownError when the server is rate limiting,
        # EmpireTimeoutError when it never answers.
        client.login()

        castles = client.castle.get_all()
        print(f"\n{len(castles)} castle(s):")
        for castle in castles:
            print(f"  [{castle.castle_id}] {castle.castle_name!r} at ({castle.x}, {castle.y}) level {castle.level}")

        if castles:
            resources = client.castle.get_resources(castle_id=castles[0].castle_id)
            if resources is not None:
                print(f"\nResources in {castles[0].castle_name!r}: {resources}")

        movements = client.get_movements()
        print(f"\n{len(movements)} movement(s) in flight:")
        for movement in movements:
            print(f"  {movement}")

    except EmpireError as e:
        # Every failure this library raises derives from EmpireError.
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        # close() stops the receive and keepalive threads. Skipping it leaves
        # the process alive with a connected socket.
        client.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
