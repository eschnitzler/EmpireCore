import asyncio
import logging
import sys
import json

sys.path.insert(0, 'src')

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.events.base import PacketEvent

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("MovementTest")

async def main():
    config = EmpireConfig(username="Heimlina", password="abc123")
    client = EmpireClient(config)
    
    gam_data = None
    
    @client.event
    async def on_gam(event: PacketEvent):
        nonlocal gam_data
        gam_data = event.payload
        logger.warning(f"GAM Packet received: {json.dumps(event.payload, indent=2)}")
    
    try:
        await client.login()
        await asyncio.sleep(2)
        
        logger.warning("Requesting movements...")
        await client.get_movements()
        await asyncio.sleep(2)
        
        if gam_data:
            print("\n=== GAM Packet Structure ===")
            print(json.dumps(gam_data, indent=2))
        else:
            print("No GAM data received")
        
        print(f"\nCurrent movements in state: {len(client.state.movements)}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()

asyncio.run(main())
