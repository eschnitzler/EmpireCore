"""List your commanders and send an attack led by one of them.

The script prints the attack it would send and only sends it when you pass
``--send``, so you can inspect the payload before any troops leave.

Pick a real barracks unit for the wave: an inventory also holds tools and
event boosts, and an army built from those is rejected with
MOVEMENT_HAS_NO_UNITS.

Coordinates are absolute map positions, not castle IDs. Unit and tool IDs are
the game's WOD IDs, the same ones ``client.army.get_units()`` returns.

    export GGE_USERNAME=your_user
    export GGE_PASSWORD=your_pass
    python examples/commanders_and_attack.py 700 710 [--send]
"""

import logging
import os
import sys

from empire_core import AttackWave, EmpireClient, EmpireError, WaveFlank

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
        print("Usage: commanders_and_attack.py TARGET_X TARGET_Y [--send]", file=sys.stderr)
        return 2
    target_x, target_y = int(args[0]), int(args[1])
    really_send = "--send" in sys.argv

    client = EmpireClient(username=username, password=password)
    try:
        client.login()

        # Commanders and castellans come back from the same command; the
        # commander is the one that leads an attack.
        commanders = client.commanders.get_commanders()
        print(f"\n{len(commanders)} commander(s):")
        for commander in commanders:
            equipment = commander.equipment()
            print(
                f"  [{commander.commander_id}] {commander.name or '(unnamed)'} "
                f"- {commander.wins}W/{commander.defeats}L, "
                f"spree {commander.win_spree}, {len(equipment)} item(s)"
            )

        castellans = client.commanders.get_castellans()
        print(f"{len(castellans)} castellan(s)")

        # Commander 0 is the free starting one and leads attacks like any other;
        # only a negative id is a sentinel rather than a commander.
        leaders = [c for c in commanders if c.commander_id >= 0]

        castles = client.castle.get_all()
        if not castles or not leaders:
            print("Need at least one castle and one commander.", file=sys.stderr)
            return 1
        source = castles[0]
        leader = leaders[0]

        units = client.army.get_units(castle_id=source.castle_id)
        if not units:
            print(f"No units in {source.castle_name!r}.", file=sys.stderr)
            return 1

        # One wave, everything on the left flank. A real attack spreads units
        # and tools across the left, middle and right flanks of several waves;
        # waves without units are dropped before sending.
        strongest = max(units, key=lambda u: u.count)
        waves = [AttackWave(L=WaveFlank(U=[[strongest.unit_id, min(strongest.count, 10)]]))]

        print(
            f"\nAttack from {source.castle_name!r} ({source.x}, {source.y}) "
            f"to ({target_x}, {target_y}) led by commander {leader.commander_id}:"
        )
        print(f"  {waves[0].model_dump(by_alias=True)}")

        if not really_send:
            print("\nDry run. Re-run with --send to actually send it.")
            return 0

        accepted = client.attack.send_attack(
            source_x=source.x,
            source_y=source.y,
            target_x=target_x,
            target_y=target_y,
            waves=waves,
            kingdom_id=source.kingdom_id,
            commander_id=leader.commander_id,
        )
        # send_attack returns False when the server rejects the attack by rule
        # (no troops, target out of range, commander already in a movement).
        print("Attack sent." if accepted else "Server rejected the attack.")

    except EmpireError as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
