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
logger = logging.getLogger("HandshakeTest")

HOST = '127.0.0.1'
PORT = 8889

# ... (rest of imports)

async def run_test():
    # Wait for server
    await asyncio.sleep(1)
    
    config = EmpireConfig(game_url=f"ws://{HOST}:{PORT}")
    client = EmpireClient(config)
    try:
        # We use a dummy password "password123"
        await client.login("TestUser", "password123")
        
        if client.is_logged_in:
            logger.info("TEST PASSED: Client successfully logged in.")
        else:
            logger.error("TEST FAILED: Client did not set logged_in flag.")
            
    except Exception as e:
        logger.error(f"TEST FAILED: {e}")
        # raise e # Uncomment to see full traceback if needed
    finally:
        await client.close()

async def main():
    server_task = asyncio.create_task(run_server())
    await run_test()
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass

if __name__ == "__main__":
    asyncio.run(main())
