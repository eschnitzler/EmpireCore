import asyncio
import logging
import sys

sys.path.insert(0, 'src')

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("MovementTest")

async def main():
    config = EmpireConfig(username="zazerzeezba", password="abc123")
    client = EmpireClient(config)
    
    try:
        logger.info("🔐 Logging in...")
        await client.login()
        await asyncio.sleep(2)
        
        logger.info("\n📍 Requesting movements...")
        await client.get_movements()
        await asyncio.sleep(2)
        
        print("\n" + "="*70)
        print("ACTIVE MOVEMENTS")
        print("="*70)
        
        if len(client.state.movements) == 0:
            print("No active movements")
        else:
            for mid, movement in client.state.movements.items():
                print(f"\n🚶 Movement {mid} (Type: {movement.movement_type})")
                print(f"   Progress: {movement.progress_time}/{movement.total_time} ({movement.progress_percent:.1f}%)")
                print(f"   Time Remaining: {movement.time_remaining}s")
                print(f"   Source: ({movement.source_x}, {movement.source_y})")
                print(f"   Target: ({movement.target_x}, {movement.target_y}) -> Area {movement.target_area_id}")
                print(f"   Direction: {'Incoming' if movement.is_incoming else 'Outgoing' if movement.is_outgoing else 'Return'}")
                
        print("\n✅ Movement parsing test complete!")
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()

asyncio.run(main())
