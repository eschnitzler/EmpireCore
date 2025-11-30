#!/usr/bin/env python3
"""Detailed parsing test - see exactly what data we're getting."""
import asyncio
import sys
sys.path.insert(0, 'src')

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig

async def main():
    config = EmpireConfig(username="Super Penelope", password="abc123")
    client = EmpireClient(config)
    
    try:
        print("🔐 Logging in...")
        await client.login()
        await asyncio.sleep(2)
        
        print("📥 Getting detailed castle info...")
        await client.get_detailed_castle_info()
        await asyncio.sleep(2)
        
        player = client.state.local_player
        
        if not player:
            print("❌ No player data!")
            return
        
        print(f"\n{'='*70}")
        print(f"👤 Player: {player.name} (ID: {player.id})")
        print(f"   Level: {player.level}")
        print(f"   XP: {player.XP} (Progress: {player.xp_progress:.1f}%)")
        print(f"   Gold: {player.gold:,}")
        print(f"   Rubies: {player.rubies}")
        print(f"   Castles: {len(player.castles)}")
        print(f"{'='*70}")
        
        for castle_id, castle in player.castles.items():
            print(f"\n🏰 Castle {castle_id}: {castle.name}")
            print(f"   Kingdom: {castle.kingdom_id}")
            print(f"   Population: {castle.population}")
            
            # Resources
            r = castle.resources
            print(f"\n   📦 Resources:")
            print(f"      Wood:  {r.wood:,}/{r.wood_cap:,}  (+{r.wood_rate}/h)")
            print(f"      Stone: {r.stone:,}/{r.stone_cap:,}  (+{r.stone_rate}/h)")
            print(f"      Food:  {r.food:,}/{r.food_cap:,}  (+{r.food_rate}/h)")
            
            if r.iron or r.glass or r.ash:
                print(f"      Iron: {r.iron}, Glass: {r.glass}, Ash: {r.ash}")
            
            # Buildings  
            print(f"\n   🏗️  Buildings ({len(castle.buildings)}):")
            keep = next((b for b in castle.buildings if b.id == 0), None)
            if keep:
                print(f"      [0] Keep: Level {keep.level} ⭐")
            
            # Show first 10 buildings
            for b in sorted(castle.buildings, key=lambda x: x.id)[:10]:
                if b.id == 0:
                    continue
                building_name = {
                    1: "Farm", 2: "Lumbermill", 3: "Quarry", 4: "Barracks",
                    5: "Wall", 6: "Workshop", 7: "Dwelling", 8: "Harbor"
                }.get(b.id, f"Building {b.id}")
                print(f"      [{b.id}] {building_name}: Level {b.level}")
            
            if len(castle.buildings) > 10:
                print(f"      ... and {len(castle.buildings) - 10} more")
            
            # Units
            if castle.units:
                print(f"\n   ⚔️  Units:")
                total_units = sum(castle.units.values())
                print(f"      Total: {total_units:,} units")
                for unit_id, count in sorted(castle.units.items())[:5]:
                    print(f"      Unit {unit_id}: {count:,}")
                if len(castle.units) > 5:
                    print(f"      ... and {len(castle.units) - 5} more types")
        
        # Movements
        print(f"\n{'='*70}")
        print(f"🚶 Active Movements: {len(client.state.movements)}")
        if client.state.movements:
            for mid, movement in list(client.state.movements.items())[:3]:
                print(f"   Movement {mid}: Type {movement.movement_type}")
                print(f"      From ({movement.from_x},{movement.from_y}) → ({movement.to_x},{movement.to_y})")
        
        # Quests
        if client.state.daily_quests and client.state.daily_quests.quests:
            print(f"\n📜 Daily Quests: {len(client.state.daily_quests.quests)}")
            for q in client.state.daily_quests.quests[:3]:
                status = "✓" if q.is_completed else "○"
                print(f"   {status} Quest {q.quest_id}: {q.progress}/{q.max_progress}")
        
        print(f"{'='*70}")
        print("✅ All data retrieved successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await client.close()

asyncio.run(main())
