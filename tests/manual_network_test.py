import asyncio
import logging
import os
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from empire_core.network.connection import SFSConnection

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("NetworkTest")

HOST = "127.0.0.1"
PORT = 8888


async def mock_server_handler(reader, writer):
    logger.info("Server: Client connected")
    while True:
        try:
            data = await reader.readuntil(b"\x00")
            msg = data.decode().strip("\x00")
            logger.info(f"Server received: {msg}")

            if "LOGIN" in msg:
                # Simulate delayed response
                await asyncio.sleep(0.5)
                response = '%xt%EmpireEx_21%lli%1%{"result":0}%\x00'
                writer.write(response.encode())
                await writer.drain()
                logger.info("Server sent: lli response")

            if "CHAT" in msg:
                # Send 3 chat messages, client might wait for specific one
                await asyncio.sleep(0.1)
                writer.write("%xt%Zone%chat%1%Msg1%\x00".encode())
                await writer.drain()

                await asyncio.sleep(0.1)
                writer.write("%xt%Zone%chat%1%Msg2%\x00".encode())
                await writer.drain()

        except asyncio.IncompleteReadError:
            break
    logger.info("Server: Client disconnected")


async def run_server():
    server = await asyncio.start_server(mock_server_handler, HOST, PORT)
    logger.info(f"Server started on {HOST}:{PORT}")
    async with server:
        await server.serve_forever()


async def run_client():
    # Give server time to start
    await asyncio.sleep(1)

    client = SFSConnection(f"ws://{HOST}:{PORT}")
    await client.connect()

    try:
        # Test 1: Simple wait_for
        logger.info("Client: Sending LOGIN...")
        await client.send("LOGIN")

        logger.info("Client: Waiting for 'lli'...")
        packet = await client.wait_for("lli", timeout=2.0)
        logger.info(f"Client: Received expected packet: {packet.command_id} -> {packet.payload}")
        assert packet.command_id == "lli"

        # Test 2: Wait with predicate (skipping first chat)
        logger.info("Client: Sending CHAT...")
        await client.send("CHAT")

        logger.info("Client: Waiting for 'chat' with payload 'Msg2'...")

        # We want to skip Msg1 and get Msg2
        def is_msg2(p):
            # Packet payload parsing for xt is slightly simplified in our class,
            # check raw_data or payload if it parsed json (chat isn't json usually in simple tests)
            return "Msg2" in p.raw_data

        packet = await client.wait_for("chat", predicate=is_msg2, timeout=2.0)
        logger.info(f"Client: Received specific chat: {packet.raw_data}")
        assert "Msg2" in packet.raw_data

        logger.info("TEST PASSED")

    except Exception as e:
        logger.error(f"TEST FAILED: {e}")
    finally:
        await client.disconnect()


async def main():
    # Start server in background
    server_task = asyncio.create_task(run_server())

    # Run client test
    await run_client()

    # Stop server
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
