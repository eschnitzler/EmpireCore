import asyncio
import logging
import sys
import json

sys.path.insert(0, 'src')

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.events.base import PacketEvent

logging.basicConfig(level=logging.WARNING)

packets_of_interest = {}

async def main():
    config = EmpireConfig(username="Super Penelope", password="abc123")
    client = EmpireClient(config)
    
    @client.event
    async def on_packet(event: PacketEvent):
        if event.command_id in ["gbd", "gus", "gam"]:
            packets_of_interest[event.command_id] = event.payload
    
    try:
        await client.login()
        await asyncio.sleep(3)
        
        for cmd, data in packets_of_interest.items():
            print(f"\n{'='*60}")
            print(f"=== {cmd} PACKET ===")
            print('='*60)
            if isinstance(data, dict):
                # Print structure without full data
                print(f"Keys: {list(data.keys())}")
                for k, v in data.items():
                    if isinstance(v, list) and len(v) > 0:
                        print(f"\n{k}: [{len(v)} items]")
                        print(f"  First item: {v[0] if len(v) > 0 else 'N/A'}")
                    elif isinstance(v, dict):
                        print(f"\n{k}: {list(v.keys())}")
                    else:
                        print(f"{k}: {v}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()

asyncio.run(main())
