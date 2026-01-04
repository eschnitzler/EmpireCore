#!/usr/bin/env python3
"""
Quest automation example for EmpireCore.

This example demonstrates how to automatically collect quest rewards
and monitor daily quest progress.
"""

import asyncio
import logging

from empire_core import accounts

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def quest_monitor_example():
    """Example of quest monitoring and auto-collection."""

    # Create client
    # Create client
    account = accounts.get_default()
    if not account:
        logger.error("No account found in accounts.json")
        return

    client = account.get_client()

    try:
        # Login
        logger.info("Logging in...")
        await client.login()

        # Get initial quest data
        logger.info("Refreshing quest data...")
        await client.quests.refresh_quests()

        # Wait a moment for the response
        await asyncio.sleep(2)

        # Get quest summary
        summary = client.quests.get_daily_quest_summary()
        if summary["available"]:
            logger.info(f"Daily Quest Level: {summary['level']}")
            logger.info(f"Active Quests: {summary['active_count']}")
            logger.info(f"Completed Quests: {summary['completed_count']}")

            if summary["completed_count"] > 0:
                logger.info("Found completed quests! Auto-collecting rewards...")
                collected_count = await client.quests.auto_collect_rewards()
                logger.info(f"Collected rewards for {collected_count} quests!")
            else:
                logger.info("No completed quests to collect yet.")

            # Show active quest details
            active_quests = client.quests.get_active_quests()
            for quest in active_quests[:3]:  # Show first 3
                progress = client.quests.get_quest_progress(quest.quest_id)
                logger.info(f"Quest {quest.quest_id}: Progress {progress}")

        else:
            logger.warning("Daily quest data not available yet")

    except Exception as e:
        logger.error(f"Error in quest monitoring: {e}")

    finally:
        await client.close()


async def continuous_quest_monitor():
    """Example of continuous quest monitoring with periodic checks."""

    # Create client
    account = accounts.get_default()
    if not account:
        logger.error("No account found in accounts.json")
        return

    client = account.get_client()

    try:
        await client.login()
        logger.info("Starting continuous quest monitoring...")

        check_interval = 300  # Check every 5 minutes

        for _i in range(12):  # Run for 1 hour (12 * 5 minutes)
            try:
                # Refresh quest data
                await client.quests.refresh_quests()
                await asyncio.sleep(2)  # Wait for response

                # Auto-collect any completed rewards
                collected = await client.quests.auto_collect_rewards()
                if collected > 0:
                    logger.info(f"✅ Collected {collected} quest rewards!")

                # Log current status
                summary = client.quests.get_daily_quest_summary()
                if summary["available"]:
                    logger.info(
                        f"📊 Quests: {summary['completed_count']}/{summary['active_count'] + summary['completed_count']} completed"
                    )

                # Wait before next check
                logger.info(f"⏰ Next check in {check_interval} seconds...")
                await asyncio.sleep(check_interval)

            except Exception as e:
                logger.error(f"Error during quest check: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying

    except KeyboardInterrupt:
        logger.info("Quest monitoring stopped by user")

    finally:
        await client.close()


if __name__ == "__main__":
    print("EmpireCore Quest Automation Example")
    print("=" * 40)

    # Choose which example to run
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "continuous":
        print("Running continuous quest monitoring...")
        asyncio.run(continuous_quest_monitor())
    else:
        print("Running one-time quest check...")
        asyncio.run(quest_monitor_example())
