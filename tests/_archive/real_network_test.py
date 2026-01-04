import asyncio
import logging
import os
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from empire_core import accounts

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("RealNetworkTest")


async def main():
    account = accounts.get_default()
    if not account:
        logger.error("No test account found in accounts.json")
        return

    # Configure via Pydantic Config
    client = account.get_client()

    try:
        await client.login()

        if client.is_logged_in:
            logger.info("TEST SUCCESS: Successfully logged in to Real Server!")

            # Keep connection open for a bit to see any extra traffic
            await asyncio.sleep(5)
        else:
            logger.error("TEST FAILED: Not logged in.")

    except Exception as e:
        logger.error(f"TEST FAILED with Exception: {e}")
        import traceback

        traceback.print_exc()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
