#!/usr/bin/env python3
"""
Test actual game actions: attack, train, build, map requests.
We'll send real commands and see what responses we get.
"""
import asyncio
import sys
import json
sys.path.insert(0, 'src')

from empire_core import EmpireClient, EmpireConfig

async def test_actions():
    print("=" * 70)
    print("🎯 Testing Game Actions")
    print("=" * 70)
    print()
    
    config = EmpireConfig(username="Divine Stella", password="abc123")
    client = EmpireClient(config)
    
    # Track messages
    sent = []
    received = []
    
    original_send = client.connection.send
    original_process = client.connection._process_message
    
    async def log_send(data):
        sent.append(data)
        print(f"📤 {str(data)[:80]}")
        return await original_send(data)
    
    async def log_recv(msg):
        received.append(msg)
        msg_str = msg.decode('utf-8', errors='ignore') if isinstance(msg, bytes) else str(msg)
        if msg_str.startswith('%xt%'):
            parts = msg_str.split('%')
            cmd = parts[1] if len(parts) > 1 else "?"
            print(f"📥 {cmd}: {msg_str[:80]}")
        return await original_process(msg)
    
    client.connection.send = log_send
    client.connection._process_message = log_recv
    
    try:
        print("🔐 Logging in...")
        await client.login()
        print("✅ Logged in!\n")
        await asyncio.sleep(2)
        
        player = client.state.local_player
        if not player or not player.castles:
            print("❌ No player/castle data")
            return
        
        castle = next(iter(player.castles.values()))
        print(f"🏰 Using castle: {castle.name} (ID: {castle.id})")
        print(f"   Resources: W:{castle.resources.wood} S:{castle.resources.stone} F:{castle.resources.food}")
        print(f"   Population: {castle.population}")
        if castle.buildings:
            print(f"   Buildings: {len(castle.buildings)}")
        if castle.units:
            print(f"   Units: {dict(list(castle.units.items())[:3])}")
        print()
        
        # Test 1: Get map data around castle
        print("=" * 70)
        print("1️⃣  TEST: Get Map Chunk (gaa)")
        print("=" * 70)
        
        # Use castle coordinates if available, otherwise use default area
        if hasattr(castle, 'x') and hasattr(castle, 'y'):
            x, y = castle.x, castle.y
            print(f"   Requesting area around castle at ({x}, {y})")
        else:
            x, y = 50, 50  # Default coordinates
            print(f"   Requesting area at ({x}, {y})")
        
        await client.get_map_chunk(0, x, y)  # Kingdom 0 (Green)
        await asyncio.sleep(2)
        print(f"   ✅ Map objects in state: {len(client.state.map_objects)}")
        print()
        
        # Test 2: Try to scout a nearby area (safe, doesn't consume resources)
        print("=" * 70)
        print("2️⃣  TEST: Send Scout (scl) - READ ONLY TEST")
        print("=" * 70)
        print("   Note: NOT sending - showing what command would look like")
        
        # Find a nearby target (just simulate)
        target_area = 16654604  # Adjacent area ID (usually castle_id + 1)
        scout_payload = {
            "OID": castle.id,
            "TID": target_area,
            "UN": {620: 1},  # 1 militia as scout
            "TT": 2  # Type 2 = Scout
        }
        scout_cmd = f"%xt%EmpireEx_21%scl%1%{json.dumps(scout_payload)}%"
        print(f"   Would send: {scout_cmd[:100]}")
        print("   SKIPPING - Don't want to consume units")
        print()
        
        # Test 3: Check building info
        print("=" * 70)
        print("3️⃣  TEST: Get Building Stats (gbs)")
        print("=" * 70)
        
        # Try to get building information
        payload = {"AID": castle.id}
        cmd = f"%xt%EmpireEx_21%gbs%1%{json.dumps(payload)}%"
        print(f"   Sending: gbs for castle {castle.id}")
        await client.connection.send(cmd)
        await asyncio.sleep(2)
        print()
        
        # Test 4: Request quest details
        print("=" * 70)
        print("4️⃣  TEST: Get Quest Details")
        print("=" * 70)
        
        # Try various quest commands
        for quest_cmd in ['gqd', 'gql', 'qli']:
            try:
                cmd = f"%xt%EmpireEx_21%{quest_cmd}%1%{{}}%"
                print(f"   Trying: {quest_cmd}")
                await client.connection.send(cmd)
                await asyncio.sleep(1)
            except:
                pass
        print()
        
        # Test 5: Check what unit training would look like
        print("=" * 70)
        print("5️⃣  TEST: Unit Training (tru) - SIMULATION ONLY")
        print("=" * 70)
        print("   Note: NOT actually training - showing command format")
        
        # Militia (unit 620) is cheapest
        train_payload = {
            "AID": castle.id,
            "UID": 620,  # Militia
            "C": 1  # Count
        }
        train_cmd = f"%xt%EmpireEx_21%tru%1%{json.dumps(train_payload)}%"
        print(f"   Would send: {train_cmd}")
        print(f"   Cost check: Wood=10, Stone=0, Food=10 per militia")
        print(f"   Available: W:{castle.resources.wood}")
        print("   SKIPPING - Don't want to spend resources")
        print()
        
        # Test 6: Try to get alliance info
        print("=" * 70)
        print("6️⃣  TEST: Alliance Data")
        print("=" * 70)
        
        if player.alliance:
            print(f"   Player is in alliance: {player.alliance.name}")
            # Try alliance commands
            for alliance_cmd in ['gam', 'gal', 'gma']:
                try:
                    cmd = f"%xt%EmpireEx_21%{alliance_cmd}%1%{{}}%"
                    print(f"   Trying: {alliance_cmd}")
                    await client.connection.send(cmd)
                    await asyncio.sleep(1)
                except:
                    pass
        else:
            print("   Player not in alliance")
        print()
        
        # Summary
        print("=" * 70)
        print("📊 Test Summary")
        print("=" * 70)
        print(f"Commands sent: {len(sent)}")
        print(f"Responses received: {len(received)}")
        print()
        
        # Analyze responses for new data
        print("🔍 Interesting responses:")
        for msg in received[-20:]:  # Last 20 messages
            if isinstance(msg, bytes):
                msg_str = msg.decode('utf-8', errors='ignore')
                if msg_str.startswith('%xt%'):
                    parts = msg_str.split('%')
                    if len(parts) > 1:
                        cmd = parts[1]
                        # Skip known commands
                        if cmd not in ['gmu', 'ufa', 'ufp', 'tse', 'lfe', 'core_pol', 'core_nfo']:
                            print(f"   {cmd}: {msg_str[:100]}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()
        print("\n🔌 Connection closed")

if __name__ == "__main__":
    asyncio.run(test_actions())
