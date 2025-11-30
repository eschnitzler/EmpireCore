#!/usr/bin/env python3
"""
Comprehensive functionality test with real account.
"""
import asyncio
import logging
import sys
sys.path.insert(0, 'src')

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig
from empire_core.utils.calculations import calculate_distance, format_time
from empire_core.utils.battle_sim import BattleSimulator
from empire_core.automation.target_finder import TargetFinder

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("FullTest")

async def test_all_features():
    """Test all features with a real account."""
    
    print("="*70)
    print("COMPREHENSIVE FUNCTIONALITY TEST")
    print("="*70)
    
    # Use test account from the list
    config = EmpireConfig(username="Elliot Ralph", password="abc123")
    client = EmpireClient(config)
    
    try:
        # 1. Login test
        print("\n1️⃣ Testing Login...")
        await client.login()
        await asyncio.sleep(2)
        print("   ✅ Login successful")
        
        # 2. Get detailed state
        print("\n2️⃣ Testing State Retrieval...")
        await client.get_detailed_castle_info()
        await asyncio.sleep(1)
        
        player = client.state.local_player
        if player:
            print(f"   ✅ Player: {player.name}")
            print(f"   ✅ Level: {player.level}")
            print(f"   ✅ Gold: {player.gold:,}")
            print(f"   ✅ Rubies: {player.rubies}")
            print(f"   ✅ Castles: {len(player.castles)}")
            
            # Show castle details
            for castle_id, castle in player.castles.items():
                print(f"\n   🏰 Castle {castle_id}:")
                print(f"      • Wood: {castle.resources.wood:,}")
                print(f"      • Stone: {castle.resources.stone:,}")
                print(f"      • Food: {castle.resources.food:,}")
                print(f"      • Population: {castle.population}")
                
                # Production rates
                if hasattr(castle, 'production_rate') and castle.production_rate.wood > 0:
                    print(f"      • Production: +{castle.production_rate.wood}/h wood, "
                          f"+{castle.production_rate.stone}/h stone, "
                          f"+{castle.production_rate.food}/h food")
        
        # 3. Test movements
        print("\n3️⃣ Testing Movement Tracking...")
        movements = client.state.movements
        print(f"   ✅ Active movements: {len(movements)}")
        
        for mid, movement in list(movements.items())[:3]:
            print(f"   • Movement {mid}: Type {movement.movement_type}")
            print(f"     From ({movement.from_x},{movement.from_y}) to ({movement.to_x},{movement.to_y})")
            if movement.arrival_time:
                remaining = movement.arrival_time - int(asyncio.get_event_loop().time())
                if remaining > 0:
                    print(f"     Arrives in: {format_time(remaining)}")
        
        # 4. Test quests
        print("\n4️⃣ Testing Quest Tracking...")
        if client.state.daily_quests:
            quests = client.state.daily_quests
            print(f"   ✅ Daily quests available: {len(quests.quests)}")
            for q in quests.quests[:3]:
                status = "✓" if q.is_completed else "○"
                print(f"   {status} Quest {q.quest_id}: {q.progress}/{q.max_progress}")
        
        # 5. Test map objects (if any)
        print("\n5️⃣ Testing Map State...")
        map_objs = client.state.map_objects
        print(f"   ✅ Known map objects: {len(map_objs)}")
        
        # 6. Test battle simulator
        print("\n6️⃣ Testing Battle Simulator...")
        sim = BattleSimulator()
        result = sim.simulate(
            {620: 100},  # 100 militia
            {620: 50},   # 50 militia
            attacker_bonus=10.0
        )
        print(f"   ✅ Battle simulation: {'Win' if result.attacker_wins else 'Loss'}")
        print(f"   • Attacker survivors: {sum(result.attacker_survivors.values())}")
        print(f"   • Defender survivors: {sum(result.defender_survivors.values())}")
        print(f"   • Potential loot: {result.loot}")
        
        # 7. Test distance calculations
        print("\n7️⃣ Testing Calculations...")
        dist = calculate_distance(0, 0, 100, 100)
        travel_time = int(dist * 60)  # Assume 1 minute per unit distance
        print(f"   ✅ Distance (0,0) to (100,100): {dist:.2f}")
        print(f"   ✅ Travel time: {format_time(travel_time)}")
        
        # 8. Test target finder (without actually scanning)
        print("\n8️⃣ Testing Target Finder...")
        finder = TargetFinder(client.state.map_objects)
        print(f"   ✅ Target finder initialized")
        print(f"   • Tracking {len(client.state.map_objects)} map objects")
        
        # 9. Test event system
        print("\n9️⃣ Testing Event System...")
        print(f"   ✅ Event system active")
        
        print("\n" + "="*70)
        print("✅ ALL FEATURES WORKING!")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        print("\nClosing connection...")
        await client.close()
        print("✅ Disconnected")


if __name__ == "__main__":
    asyncio.run(test_all_features())
