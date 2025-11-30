import asyncio
import logging
import sys
import os
import json

sys.path.insert(0, 'src')

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.events.base import PacketEvent

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("Analyzer")

async def main():
    config = EmpireConfig(username="Divine Stella", password="abc123")
    client = EmpireClient(config)
    
    dcl_data = None
    
    @client.event
    async def on_dcl(event: PacketEvent):
        nonlocal dcl_data
        dcl_data = event.payload
    
    try:
        await client.login()
        await asyncio.sleep(2)
        await client.get_detailed_castle_info()
        await asyncio.sleep(2)
        
        if dcl_data:
            print("=== DCL Packet Structure ===")
            print(json.dumps(dcl_data, indent=2))
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.close()

asyncio.run(main())
