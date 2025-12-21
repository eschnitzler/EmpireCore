import asyncio
import logging
import os
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from empire_core.automation.multi_account import AccountPool

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(message)s")
logger = logging.getLogger("PoolTest")


async def test_pool():
    # 1. Initialize Pool
    # Ensure we have a valid accounts.json first (from previous steps)
    pool = AccountPool()

    if not pool.all_accounts:
        logger.error("No accounts loaded in pool! Please check accounts.json")
        return

    logger.info(f"Pool initialized with {len(pool.all_accounts)} accounts.")

    # 2. Test Get Available
    available = pool.get_available_accounts()
    logger.info(f"Available accounts: {len(available)}")
    assert len(available) > 0

    # 3. Test Lease
    logger.info("Leasing an account...")
    client = await pool.lease_account()

    if client:
        logger.info(f"Successfully leased: {client.username}")
        assert client.is_logged_in
        assert client.username in pool._busy_accounts

        # 4. Verify availability updates
        remaining = pool.get_available_accounts()
        logger.info(f"Remaining available: {len(remaining)}")
        assert len(remaining) == len(available) - 1

        # 5. Test Release
        logger.info("Releasing account...")
        await pool.release_account(client)

        assert client.username not in pool._busy_accounts
        assert len(pool.get_available_accounts()) == len(available)
        logger.info("Account released and pool restored.")

    else:
        logger.error("Failed to lease account.")


if __name__ == "__main__":
    asyncio.run(test_pool())
