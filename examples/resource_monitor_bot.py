#!/usr/bin/env python3
"""
Example Bot: Resource Monitor
Demonstrates how to build a simple bot using EmpireCore.
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from empire_core import accounts
from empire_core.client.client import EmpireClient
from empire_core.events.base import PacketEvent

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Bot")

GOLD_ALERT_THRESHOLD = 10000
CHECK_INTERVAL = 60


class ResourceMonitorBot:
    def __init__(self, client: EmpireClient):
        self.client = client
        self.last_gold = 0
        self.running = False
        self.client.event(self.on_gbd)

    async def on_gbd(self, event: PacketEvent):
        if self.client.state.local_player:
            player = self.client.state.local_player
            if self.last_gold > 0 and player.gold != self.last_gold:
                change = player.gold - self.last_gold
                logger.info(f"💰 Gold change: {change:+,}")
            self.last_gold = player.gold
            if player.gold < GOLD_ALERT_THRESHOLD:
                logger.warning(f"⚠️ LOW GOLD: {player.gold:,}")

    def _print_status(self):
        player = self.client.state.local_player
        if not player:
            return

        print("\n" + "=" * 80)
        print(f"📊 {player.name} (Level {player.level}) | Gold: {player.gold:,} | Rubies: {player.rubies:,}")
        print("-" * 80)
        print(f"{'Castle Name':<25} {'Wood':<15} {'Stone':<15} {'Food':<15} {'Pop':<8}")
        print("-" * 80)

        for castle in player.castles.values():
            r = castle.resources
            wood_str = f"{r.wood:,}/{r.wood_cap:,}"
            stone_str = f"{r.stone:,}/{r.stone_cap:,}"
            food_str = f"{r.food:,}/{r.food_cap:,}"
            pop_str = f"{castle.population}/{castle.max_castellans}"

            print(f"{castle.name:<25} {wood_str:<15} {stone_str:<15} {food_str:<15} {pop_str:<8}")
            print(f"{'':<25} (+{r.wood_rate:>5.0f}/h)   (+{r.stone_rate:>5.0f}/h)   ( {r.food_rate:>+5.0f}/h)")

        print("=" * 80 + "\n")

    async def start(self):
        logger.info("Starting bot...")
        await self.client.login()

        # Wait for initial data sync
        await asyncio.sleep(3)
        self.running = True

        while self.running:
            try:
                # Always fetch fresh details before printing
                await self.client.get_detailed_castle_info()
                await asyncio.sleep(1)  # Wait for state to update

                self._print_status()

                await asyncio.sleep(CHECK_INTERVAL)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error in loop: {e}")
                await asyncio.sleep(5)

        await self.client.close()


async def main():
    account = accounts.get_default()
    if not account:
        logger.error("No account found in accounts.json")
        return

    client = account.get_client()
    bot = ResourceMonitorBot(client)
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
