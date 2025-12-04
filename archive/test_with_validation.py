#!/usr/bin/env python3
"""
Test with proper response waiting - use the library's response awaiter system.
"""
import asyncio
import sys
import json
sys.path.insert(0, 'src')

from empire_core import EmpireClient, EmpireConfig

async def test_with_awaiter():
    print("=" * 70)
    print("🧪 Testing Actions with Response Validation")
    print("=" * 70)
    print()
    
    # Use account with resources
    config = EmpireConfig(username="Super Penelope", password="abc123")
    client = EmpireClient(config)
    
    # Enable logging
    import logging
    logging.basicConfig(level=logging.INFO)
    
    try:
        print("🔐 Logging in...")
        await client.login()
        print("✅ Logged in\n")
        
        # Get state
        await client.get_detailed_castle_info()
        await asyncio.sleep(2)
        
        player = client.state.local_player
        castle = next(iter(player.castles.values()))
        
        print(f"🏰 Castle: {castle.name}")
        print(f"   Resources: W:{castle.resources.wood} S:{castle.resources.stone} F:{castle.resources.food}")
        print()
        
        # Test with the library's built-in methods
        print("=" * 70)
        print("TEST 1: Train Unit (using library method)")
        print("=" * 70)
        
        if castle.resources.wood >= 10 and castle.resources.food >= 10:
            print("   Training 1 militia using client.actions.train_units()...")
            
            try:
                # Use the library's train method with response waiting
                result = await client.actions.train_units(
                    castle_id=castle.id,
                    unit_id=620,  # Militia
                    count=1,
                    wait_for_response=True,
                    timeout=5.0
                )
                
                print(f"   ✅ Training result: {result}")
                print()
                
            except Exception as e:
                print(f"   Response: {e}")
                print("   (Command may have succeeded even without response)")
                print()
        
        # Wait and check for state updates
        print("⏳ Waiting 3 seconds for state updates...")
        await asyncio.sleep(3)
        
        # Refresh castle state
        await client.get_detailed_castle_info()
        await asyncio.sleep(1)
        
        castle = next(iter(player.castles.values()))
        print(f"\n📊 Updated resources: W:{castle.resources.wood} S:{castle.resources.stone} F:{castle.resources.food}")
        
        if castle.units and 620 in castle.units:
            print(f"   Militia count: {castle.units[620]}")
        print()
        
        # Test 2: Try to get map
        print("=" * 70)
        print("TEST 2: Map Request")
        print("=" * 70)
        
        print("   Requesting map chunk...")
        await client.get_map_chunk(0, 50, 50)
        await asyncio.sleep(2)
        
        print(f"   ✅ Map objects: {len(client.state.map_objects)}")
        
        # Show some map objects
        for i, (obj_id, obj) in enumerate(list(client.state.map_objects.items())[:5]):
            type_id = getattr(obj, 'type_id', '?')
            name = getattr(obj, 'name', '?')
            print(f"      {i+1}. Type {type_id}: {name} (ID: {obj_id})")
        print()
        
        # Test 3: Check movements (should be empty for new accounts)
        print("=" * 70)
        print("TEST 3: Movements")
        print("=" * 70)
        
        if hasattr(player, 'movements') and player.movements:
            print(f"   Active movements: {len(player.movements)}")
            for mov_id, mov in list(player.movements.items())[:3]:
                print(f"      Movement {mov_id}: Type {mov.movement_type}")
        else:
            print("   No active movements")
        print()
        
        # Test 4: Try building (if there's a building queue slot)
        print("=" * 70)
        print("TEST 4: Building (Format Test)")
        print("=" * 70)
        
        print("   Building command format:")
        print("   {")
        print(f"      'AID': {castle.id},")
        print("      'BID': <building_id>,")
        print("      'L': <target_level>")
        print("   }")
        print("   (Not actually building - just showing format)")
        print()
        
        print("=" * 70)
        print("✅ All Tests Complete")
        print("=" * 70)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()
        print("\n🔌 Connection closed")

if __name__ == "__main__":
    asyncio.run(test_with_awaiter())
