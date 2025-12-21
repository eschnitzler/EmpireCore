#!/usr/bin/env python3
"""
Battle report analysis example for EmpireCore.

This example demonstrates how to fetch and analyze battle reports
to understand farming efficiency and combat outcomes.
"""

import asyncio
import logging

from empire_core import accounts

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def battle_report_example():
    """Example of fetching and analyzing battle reports."""

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

        # Fetch recent battle reports
        logger.info("Fetching battle reports...")
        await client.reports.fetch_recent_reports(20)
        await asyncio.sleep(2)  # Wait for response

        # Get recent reports
        reports = client.reports.get_recent_reports(10)
        logger.info(f"Retrieved {len(reports)} battle reports")

        if not reports:
            logger.info("No battle reports found. Try attacking some barbarian camps first!")
            return

        # Analyze each report
        for i, report in enumerate(reports[:5]):  # Show first 5
            logger.info(f"\n--- Battle Report {i + 1} ---")
            summary = client.reports.get_report_summary(report)
            logger.info(f"ID: {summary['report_id']}")
            logger.info(f"Time: {summary['datetime']}")
            logger.info(f"Target: {summary['target']['name']} ({summary['target']['x']}, {summary['target']['y']})")
            logger.info(f"Winner: {summary['winner']}")
            logger.info(f"Loot: {summary['loot']}")

            # Analyze efficiency
            analysis = client.reports.analyze_battle_efficiency(report)
            logger.info(f"Victory: {analysis['victory']}")
            logger.info(f"Total Loot: {analysis['loot_total']}")
            if "efficiency" in analysis:
                logger.info(f"Efficiency: {analysis['efficiency']}")
            if "loot_per_attacker_loss" in analysis:
                logger.info(f"Loot per loss: {analysis['loot_per_attacker_loss']:.1f}")

        # Get aggregate statistics
        logger.info("\n--- Aggregate Statistics ---")
        stats = client.reports.get_battle_stats(reports)
        logger.info(f"Total Battles: {stats['total_battles']}")
        logger.info(f"Win Rate: {stats['win_rate']:.1%}")
        logger.info(f"Victories: {stats['victories']}")
        logger.info(f"Defeats: {stats['defeats']}")
        logger.info(f"Total Loot: {stats['total_loot']}")
        logger.info(f"Total Losses: {stats['total_losses']}")

    except Exception as e:
        logger.error(f"Error in battle report analysis: {e}")

    finally:
        await client.close()


async def farming_efficiency_monitor():
    """Example of monitoring farming efficiency over time."""

    # Create client
    account = accounts.get_default()
    if not account:
        logger.error("No account found in accounts.json")
        return

    client = account.get_client()

    try:
        await client.login()
        logger.info("Starting farming efficiency monitor...")

        check_interval = 600  # Check every 10 minutes

        while True:
            try:
                # Fetch latest reports
                await client.reports.fetch_recent_reports(50)
                await asyncio.sleep(2)

                # Analyze recent farming efficiency
                client.reports.get_recent_reports(20)  # Last 20 battles
                analysis = await client.reports.auto_fetch_and_analyze(20)

                stats = analysis["stats"]
                logger.info("\n📊 Farming Efficiency Report")
                logger.info(f"Recent Battles: {stats['total_battles']}")
                logger.info(f"Win Rate: {stats['win_rate']:.1%}")
                logger.info(f"Total Loot: {stats['total_loot']}")
                logger.info(f"Total Losses: {stats['total_losses']}")

                if stats["total_losses"] > 0:
                    avg_loot_per_loss = sum(stats["total_loot"].values()) / stats["total_losses"]
                    logger.info(f"Avg Loot per Loss: {avg_loot_per_loss:.1f}")

                    if avg_loot_per_loss > 100:
                        logger.info("🎯 Excellent farming efficiency!")
                    elif avg_loot_per_loss > 50:
                        logger.info("👍 Good farming efficiency")
                    elif avg_loot_per_loss > 20:
                        logger.info("🤔 Fair farming efficiency")
                    else:
                        logger.info("⚠️ Poor farming efficiency - consider different targets")

                # Wait before next check
                logger.info(f"⏰ Next check in {check_interval // 60} minutes...")
                await asyncio.sleep(check_interval)

            except KeyboardInterrupt:
                logger.info("Farming monitor stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in farming monitor: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying

    except Exception as e:
        logger.error(f"Error starting farming monitor: {e}")

    finally:
        await client.close()


if __name__ == "__main__":
    print("EmpireCore Battle Report Analysis Example")
    print("=" * 50)

    # Choose which example to run
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "monitor":
        print("Running continuous farming efficiency monitor...")
        asyncio.run(farming_efficiency_monitor())
    else:
        print("Running one-time battle report analysis...")
        asyncio.run(battle_report_example())
