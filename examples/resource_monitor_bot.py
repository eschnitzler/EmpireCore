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
                logger.info(f"Gold change: {change:+,}")
            self.last_gold = player.gold
            if player.gold < GOLD_ALERT_THRESHOLD:
                logger.warning(f"LOW GOLD: {player.gold:,}")

    async def start(self):
        logger.info("Starting bot...")
        await self.client.login()
        await asyncio.sleep(3)
        self.running = True

        while self.running:
            try:
                if self.client.state.local_player:
                    p = self.client.state.local_player
                    logger.info(f"{p.name} | Gold: {p.gold:,} | Castles: {len(p.castles)}")
                await self.client.get_detailed_castle_info()
                await asyncio.sleep(CHECK_INTERVAL)
            except KeyboardInterrupt:
                break

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
