import asyncio
import json
import logging
import os
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("HandshakeTest")

HOST = "127.0.0.1"
PORT = 8889


async def mock_server_handler(reader, writer):
    logger.info("MockServer: Client connected")
    try:
        while True:
            data = await reader.readuntil(b"\x00")
            msg = data.decode().strip("\x00")
            logger.info(f"MockServer received: {msg}")

            if "verChk" in msg:
                response = "<msg t='sys'><body action='apiOK' r='0'></body></msg>\x00"
                writer.write(response.encode())
            elif "action='login'" in msg:
                response = "<msg t='sys'><body action='rlu' r='0'></body></msg>\x00"
                writer.write(response.encode())
            elif "autoJoin" in msg:
                response = "<msg t='sys'><body action='joinOK' r='0'></body></msg>\x00"
                writer.write(response.encode())
            elif "%xt%" in msg and "lli" in msg:
                # Respond to lli (XT JSON)
                response_payload = {"result": 0}
                response = f"%xt%EmpireEx_21%lli%1%{json.dumps(response_payload)}%\x00"
                writer.write(response.encode())

            await writer.drain()
    except asyncio.IncompleteReadError:
        logger.info("MockServer: Client disconnected")
    except Exception as e:
        logger.error(f"MockServer error: {e}")
    finally:
        writer.close()
        await writer.wait_closed()


async def run_server():
    server = await asyncio.start_server(mock_server_handler, HOST, PORT)
    logger.info(f"MockServer started on {HOST}:{PORT}")
    async with server:
        await server.serve_forever()


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
