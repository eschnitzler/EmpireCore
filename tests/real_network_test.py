import asyncio
import logging
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RealNetworkTest")

# Use credentials provided
USERNAME = "Biasthe"
PASSWORD = "abc123"

async def main():
    # Configure via Pydantic Config
    config = EmpireConfig(
        username=USERNAME,
        password=PASSWORD
    )
    
    client = EmpireClient(config)
    
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