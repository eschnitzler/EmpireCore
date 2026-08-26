"""Fill an attack the way the game's own "Fill Waves" button does, and send it.

Give it a target's coordinates. Everything else is read for you: the target's
area type and structures, the defenders each flank holds, the castellan holding
it, the area effects that widen your flanks, your general's skills and your own.

    export GGE_USERNAME=your_user
    export GGE_PASSWORD=your_pass
    python examples/fill_waves.py 700 710 [--send]

The script prints what it would send and only sends with ``--send``.
"""

import logging
import os
import sys

from empire_core import EmpireClient, EmpireError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("websocket").setLevel(logging.WARNING)


def main() -> int:
    username = os.getenv("GGE_USERNAME")
    password = os.getenv("GGE_PASSWORD")
    if not username or not password:
        print("Set GGE_USERNAME and GGE_PASSWORD first.", file=sys.stderr)
        return 2

    args = [a for a in sys.argv[1:] if a != "--send"]
    if len(args) != 2:
        print("Usage: fill_waves.py TARGET_X TARGET_Y [--send]", file=sys.stderr)
        return 2
    target_x, target_y = int(args[0]), int(args[1])
    really_send = "--send" in sys.argv

    client = EmpireClient(username=username, password=password)
    try:
        client.login()
        # The items payload is a large download, so it is never implicit.
        client.load_game_data()

        castles = client.castle.get_all()
        commanders = [c for c in client.commanders.get_commanders() if c.commander_id >= 0]
        if not castles or not commanders:
            print("Need at least one castle and one commander.", file=sys.stderr)
            return 1
        source, leader = castles[0], commanders[0]

        # Coordinates are enough: the pre-calculation and the map supply the
        # rest. Anything passed here would skip the request that finds it.
        filled = client.attack.fill_attack(
            source.castle_id,
            target_x=target_x,
            target_y=target_y,
            commander=leader,
        )

        print(f"\n{len(filled.waves)} wave(s), {filled.unit_count()} units, led by {leader.commander_id}:")
        for index, wave in enumerate(filled.waves):
            payload = wave.model_dump(by_alias=True)
            for flank in ("L", "M", "R"):
                side = payload[flank]
                if side["U"] or side["T"]:
                    print(f"  wave {index} {flank}: units {side['U']} tools {side['T']}")
        placed = [pair for pair in filled.yard if pair[0] != -1]
        print(f"  courtyard: {placed or 'empty'}")

        if not really_send:
            print("\nDry run. Re-run with --send to actually send it.")
            return 0

        accepted = client.attack.send_attack(
            source_x=source.x,
            source_y=source.y,
            target_x=target_x,
            target_y=target_y,
            waves=filled.waves,
            yard_wave=filled.yard,
            kingdom_id=source.kingdom_id,
            commander_id=leader.commander_id,
        )
        print("Attack sent." if accepted else "Server rejected the attack.")

    except EmpireError as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
