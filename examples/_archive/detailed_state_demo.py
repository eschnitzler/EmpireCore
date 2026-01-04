#!/usr/bin/env python3
"""
Detailed State Demo - Shows all parsed game state information
"""

import asyncio
import logging
import sys

sys.path.insert(0, "src")

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("DetailedDemo")


async def main():
    username = "zazerzeezba"
    password = "abc123"

    config = EmpireConfig(username=username, password=password)
    client = EmpireClient(config)

    try:
        logger.info("🔐 Logging in...")
        await client.login()
        await asyncio.sleep(2)

        player = client.state.local_player
        if not player:
            logger.error("No player data")
            return

        logger.info("\n" + "=" * 70)
        logger.info("PLAYER INFORMATION")
        logger.info("=" * 70)
        logger.info(f"Name: {player.name}")
        logger.info(f"ID: {player.id}")
        logger.info(f"Level: {player.level} (LL: {player.legendary_level})")
        logger.info(f"XP: {player.XP:,} / {player.XPTNL:,} ({player.xp_progress:.1f}%)")
        logger.info(f"Gold: {player.gold:,}")
        logger.info(f"Rubies: {player.rubies}")

        if player.alliance:
            logger.info(f"\n🏰 Alliance: {player.alliance.name} [{player.alliance.abbreviation}]")
            logger.info(f"   Rank: {player.alliance.rank}")

        # Request detailed castle info
        logger.info("\n📍 Loading castle details...")
        await client.get_detailed_castle_info()
        await asyncio.sleep(2)

        # Request movements
        logger.info("📍 Loading army movements...")
        await client.get_movements()
        await asyncio.sleep(1)

        logger.info("\n" + "=" * 70)
        logger.info(f"CASTLES ({len(player.castles)})")
        logger.info("=" * 70)

        for _castle_id, castle in player.castles.items():
            logger.info(f"\n🏰 {castle.name} (ID: {castle.id}, K{castle.kingdom_id})")
            logger.info(f"   Population: {castle.population}/{castle.max_castellans}")

            res = castle.resources
            logger.info("\n   📦 Resources:")
            logger.info(f"      Wood:  {res.wood:,}/{res.wood_cap:,} (+{res.wood_rate:.1f}/h)")
            logger.info(f"      Stone: {res.stone:,}/{res.stone_cap:,} (+{res.stone_rate:.1f}/h)")
            logger.info(f"      Food:  {res.food:,}/{res.food_cap:,} (+{res.food_rate:.1f}/h)")

            if res.iron > 0 or res.glass > 0 or res.ash > 0:
                logger.info("\n   ⚙️  Special Resources:")
                if res.iron > 0:
                    logger.info(f"      Iron: {res.iron:,}")
                if res.glass > 0:
                    logger.info(f"      Glass: {res.glass:,}")
                if res.ash > 0:
                    logger.info(f"      Ash: {res.ash:,}")

            logger.info(f"\n   🏗️  Buildings: {len(castle.buildings)}")
            if castle.buildings:
                for building in castle.buildings[:10]:  # Show first 10
                    logger.info(f"      • Building ID {building.id} - Level {building.level}")
                if len(castle.buildings) > 10:
                    logger.info(f"      ... and {len(castle.buildings) - 10} more")

            logger.info("\n   🏛️  Facilities:")
            logger.info(f"      Barracks: {'✓' if castle.B else '✗'}")
            logger.info(f"      Workshop: {'✓' if castle.WS else '✗'}")
            logger.info(f"      Dwelling: {'✓' if castle.DW else '✗'}")
            logger.info(f"      Harbour:  {'✓' if castle.H else '✗'}")

        # Show movements
        logger.info("\n" + "=" * 70)
        logger.info(f"ARMY MOVEMENTS ({len(client.state.movements)})")
        logger.info("=" * 70)

        if len(client.state.movements) == 0:
            logger.info("No active movements")
        else:
            for mid, movement in client.state.movements.items():
                logger.info(f"\n🚶 Movement #{mid}")
                logger.info(f"   Type: {movement.movement_type_name}")
                logger.info(
                    f"   Progress: {movement.progress_time}/{movement.total_time}s ({movement.progress_percent:.1f}%)"
                )
                logger.info(f"   Time Remaining: {movement.time_remaining}s")
                logger.info(f"   From: ({movement.source_x}, {movement.source_y})")
                logger.info(f"   To: ({movement.target_x}, {movement.target_y}) [Area {movement.target_area_id}]")

                if movement.is_incoming:
                    logger.info("   ⚠️  INCOMING to your area!")
                elif movement.is_outgoing:
                    logger.info("   ⏩ OUTGOING from your area")
                else:
                    logger.info("   ↩️  RETURNING to your area")

        logger.info("\n" + "=" * 70)
        logger.info("✅ Complete state information displayed!")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
