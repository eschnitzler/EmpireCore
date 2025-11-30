import asyncio
import logging
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from empire_core.client.client import EmpireClient

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("HandshakeTest")

HOST = '127.0.0.1'
PORT = 8889

async def mock_sfs_handshake(reader, writer):
    logger.info("Server: Connected")
    
    try:
        # 1. Policy
        data = await reader.readuntil(b'\x00')
        msg = data.decode().strip('\x00')
        logger.info(f"Server received: {msg}")
        if "policy-file-request" in msg:
            writer.write(b"<cross-domain-policy><allow-access-from domain='*' to-ports='*' /></cross-domain-policy>\x00")
            await writer.drain()
        
        # 2. VerChk
        data = await reader.readuntil(b'\x00')
        msg = data.decode().strip('\x00')
        logger.info(f"Server received: {msg}")
        if "verChk" in msg:
            writer.write(b"<msg t='sys'><body action='apiOK' r='0'></body></msg>\x00")
            await writer.drain()

        # 3. Login
        data = await reader.readuntil(b'\x00')
        msg = data.decode().strip('\x00')
        logger.info(f"Server received: {msg}")
        if "login" in msg:
            # Verify password format if needed, but for now just accept
            writer.write(b"<msg t='sys'><body action='logOK' r='0'><loginName>User</loginName></body></msg>\x00")
            await writer.drain()

        # 4. AutoJoin
        data = await reader.readuntil(b'\x00')
        msg = data.decode().strip('\x00')
        logger.info(f"Server received: {msg}")
        if "autoJoin" in msg:
            # Reply with an XT packet to simulate entering the extension
            writer.write(b"%xt%EmpireEx_21%lli%1%{\"result\":0}%\x00")
            await writer.drain()
            # Keep connection open for a bit so client receives it
            await asyncio.sleep(1.0)

    except asyncio.IncompleteReadError:
        pass
    except Exception as e:
        logger.error(f"Server Error: {e}")
    finally:
        logger.info("Server: Closing connection")
        writer.close()
        await writer.wait_closed()

async def run_server():
    server = await asyncio.start_server(mock_sfs_handshake, HOST, PORT)
    logger.info(f"Mock SFS Server running on {HOST}:{PORT}")
    async with server:
        await server.serve_forever()

async def run_test():
    # Wait for server
    await asyncio.sleep(1)
    
    client = EmpireClient(HOST, PORT)
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
