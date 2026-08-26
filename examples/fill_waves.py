"""Fill an attack the way the game's own "Fill Waves" button does, and send it.

Give it a target on the map. The script scans the tile, works out what the
target is, fills every wave plus the courtyard wave, prints what it would send,
and only sends when you pass ``--send``.

What goes into the sizing: the target owner's level decides how big each flank
is and how many slots it has, your own level decides how many waves you carry,
your commander's bonuses raise the multipliers and cut the target's
fortification, and its general's skills widen the flanks. Tools go in before
units, because a placed tool changes the defence the units are chosen against.

    export GGE_USERNAME=your_user
    export GGE_PASSWORD=your_pass
    python examples/fill_waves.py 700 710 [--send]
"""

import logging
import os
import sys

from empire_core import EmpireClient, EmpireError, Kingdom
from empire_core.protocol.models.map import MapAreaItem, MapItemType

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("websocket").setLevel(logging.WARNING)


def find_target(client: EmpireClient, x: int, y: int, kingdom: Kingdom) -> tuple[MapAreaItem, int] | None:
    """The map row for one tile, plus the owner's level from the same scan."""
    area = client.scan_map_area(x, y, x, y, kingdom=kingdom)
    for row in area.raw_items:
        item = MapAreaItem.from_list(row)
        if (item.x, item.y) != (x, y):
            continue
        # The owner records come back beside the rows and carry the level.
        owner = next((o for o in area.objects if o.owner_id == item.owner_id), None)
        return item, owner.level if owner else 0
    return None


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

        found = find_target(client, target_x, target_y, Kingdom(source.kingdom_id))
        if found is None:
            print(f"Nothing at ({target_x}, {target_y}) in kingdom {source.kingdom_id}.", file=sys.stderr)
            return 1
        target, owner_level = found

        is_camp = target.item_type == MapItemType.DUNGEON
        print(f"\nTarget at ({target_x}, {target_y}): type {target.item_type}")
        if is_camp:
            # A camp needs no espionage: its level, its defenders and its walls
            # all follow from how often it has been beaten.
            print(f"  robber baron camp, {target.victory_count} victories")
            filled = client.attack.fill_attack(
                source.castle_id,
                camp_victories=target.victory_count,
                camp_kingdom_id=target.camp_kingdom_id or 0,
                commander=leader,
            )
        else:
            # A player's castle: pass the row and its walls, gate, moat and area
            # type are read out of it. Without a spy report the defending army
            # is unknown, so only the fortification is modelled.
            if not owner_level:
                print("  no owner level in the scan; cannot size the waves.", file=sys.stderr)
                return 1
            print(f"  player-owned, keep level {target.keep_level}, owner level {owner_level}")
            filled = client.attack.fill_attack(
                source.castle_id,
                target_level=owner_level,
                target_is_player=True,
                target_row=target.raw_data,
                commander=leader,
            )

        print(f"\n{len(filled.waves)} wave(s), {filled.unit_count()} units total:")
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
