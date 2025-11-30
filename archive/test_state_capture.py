import asyncio
import logging
import sys
import os
import json

sys.path.insert(0, 'src')

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.events.base import PacketEvent

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("StateCapture")

# Track interesting packets
captured_packets = {}

async def main():
    config = EmpireConfig(username="Mr. Aaron", password="abc123")
    client = EmpireClient(config)
    
    @client.event
    async def on_packet(event: PacketEvent):
        cmd = event.command_id
        if cmd and cmd not in ["core_pol", "core_gpi", "core_nfo"]:
            if cmd not in captured_packets:
                captured_packets[cmd] = event.payload
                logger.info(f"📦 {cmd}: {json.dumps(event.payload, indent=2) if isinstance(event.payload, dict) else str(event.payload)[:200]}")
    
    try:
        await client.login()
        await asyncio.sleep(3)
        
        # Request more data
        await client.get_detailed_castle_info()
        await asyncio.sleep(1)
        await client.get_movements()
        await asyncio.sleep(1)
        
        logger.info(f"\n✅ Captured {len(captured_packets)} unique packet types")
        logger.info(f"Packet types: {', '.join(sorted(captured_packets.keys()))}")
        
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
