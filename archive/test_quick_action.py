#!/usr/bin/env python3
import asyncio
import sys
sys.path.insert(0, 'src')
from empire_core import EmpireClient, EmpireConfig

async def quick_test():
    # Try a different account  
    config = EmpireConfig(username="zazerzeezba", password="abc123")
    client = EmpireClient(config)
    
    try:
        print("🔐 Logging in...")
        await client.login()
        
        await client.get_detailed_castle_info()
        await asyncio.sleep(1)
        
        player = client.state.local_player
        castle = next(iter(player.castles.values()))
        
        print(f"🏰 {castle.name}")
        print(f"   Resources: W:{castle.resources.wood} F:{castle.resources.food}")
        
        if castle.resources.wood >= 10 and castle.resources.food >= 10:
            print("\n⚔️  Training 1 militia...")
            await client.actions.recruit_units(castle.id, 620, 1)
            print("✅ Command sent!")
            
            await asyncio.sleep(3)
            
            # Check for response
            await client.get_detailed_castle_info()
            await asyncio.sleep(1)
            
            castle = next(iter(player.castles.values()))
            print(f"\n📊 After training:")
            print(f"   Resources: W:{castle.resources.wood} F:{castle.resources.food}")
        else:
            print("❌ Not enough resources")
            
    except Exception as e:
        print(f"❌ {e}")
    finally:
        await client.close()

asyncio.run(quick_test())
