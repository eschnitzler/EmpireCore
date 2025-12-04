#!/usr/bin/env python3
"""
Full integration test - login, get data, send a real attack on barbarians.
This tests the complete action flow.
"""
import asyncio
import sys
import json
sys.path.insert(0, 'src')

from empire_core import EmpireClient, EmpireConfig

async def full_test():
    print("=" * 70)
    print("⚔️  FULL INTEGRATION TEST - Real Attack!")
    print("=" * 70)
    print()
    
    config = EmpireConfig(username="Divine Stella", password="abc123")
    client = EmpireClient(config)
    
    # Log messages
    messages = []
    
    original_send = client.connection.send
    original_process = client.connection._process_message
    
    async def log_send(data):
        messages.append(('SEND', data))
        return await original_send(data)
    
    async def log_recv(msg):
        messages.append(('RECV', msg))
        return await original_process(msg)
    
    client.connection.send = log_send
    client.connection._process_message = log_recv
    
    try:
        # 1. Login
        print("🔐 Step 1: Login")
        await client.login()
        print("✅ Logged in\n")
        await asyncio.sleep(2)
        
        # 2. Get full state
        print("📊 Step 2: Get Full State")
        await client.get_detailed_castle_info()
        await asyncio.sleep(2)
        
        player = client.state.local_player
        if not player or not player.castles:
            print("❌ No player data")
            return
        
        castle = next(iter(player.castles.values()))
        print(f"   Castle: {castle.name} (ID: {castle.id})")
        print(f"   Resources: W:{castle.resources.wood} S:{castle.resources.stone} F:{castle.resources.food}")
        print(f"   Units: {len(castle.units)} types")
        
        # Show available units
        if castle.units:
            print(f"   Available troops:")
            for unit_id, count in list(castle.units.items())[:5]:
                print(f"      Unit {unit_id}: {count}")
        print()
        
        # 3. Get map to find a barbarian camp
        print("🗺️  Step 3: Get Map Data")
        await client.get_map_chunk(0, 50, 50)
        await asyncio.sleep(2)
        
        print(f"   Map objects found: {len(client.state.map_objects)}")
        
        # Find a barbarian camp (type 32)
        barbarian = None
        for obj_id, obj in client.state.map_objects.items():
            if hasattr(obj, 'type_id') and obj.type_id == 32:  # Barbarian camp
                barbarian = obj
                break
        
        if barbarian:
            print(f"   Found barbarian camp: ID={barbarian.id}")
        else:
            print("   No barbarian camps found in this chunk")
            # Use a known barbarian ID or skip
            print("   Will simulate attack command anyway")
        print()
        
        # 4. Prepare attack
        print("⚔️  Step 4: Prepare Attack Command")
        
        # Use militia (620) if available
        attack_units = {}
        if 620 in castle.units and castle.units[620] > 0:
            attack_units[620] = min(10, castle.units[620])  # Send max 10 militia
            print(f"   Will send {attack_units[620]} militia (unit 620)")
        else:
            # Find any available unit
            for unit_id, count in castle.units.items():
                if count > 0:
                    attack_units[unit_id] = min(5, count)
                    print(f"   Will send {attack_units[unit_id]} of unit {unit_id}")
                    break
        
        if not attack_units:
            print("   ❌ No units available to send!")
            print("   Showing what attack command would look like:")
            attack_units = {620: 10}  # Dummy data
        
        target_id = barbarian.id if barbarian else 17599566  # Use found barbarian or dummy ID
        
        attack_payload = {
            "OID": castle.id,
            "TID": target_id,
            "UN": attack_units,
            "TT": 1,  # Type 1 = Attack
            "KID": 0   # Kingdom 0
        }
        
        attack_cmd = f"%xt%EmpireEx_21%att%1%{json.dumps(attack_payload)}%"
        print(f"   Command: {attack_cmd[:100]}...")
        print()
        
        # 5. Send attack (or simulate)
        print("🎯 Step 5: Send Attack")
        
        # Ask for confirmation (in real scenario)
        if attack_units and (620 in attack_units or any(castle.units.get(uid, 0) > 0 for uid in attack_units)):
            print("   ⚠️  SENDING REAL ATTACK!")
            print("   (Barbarian camps don't retaliate, so this is safe)")
            
            # Actually send it
            await client.connection.send(attack_cmd)
            print("   ✅ Attack command sent!")
            
            # Wait for response
            await asyncio.sleep(3)
            print()
            
            # Check for attack confirmation in messages
            print("📥 Looking for attack response...")
            for direction, msg in messages[-20:]:
                if direction == 'RECV' and isinstance(msg, bytes):
                    msg_str = msg.decode('utf-8', errors='ignore')
                    if 'att' in msg_str or 'MID' in msg_str:  # MID = Movement ID
                        print(f"   Response: {msg_str[:150]}")
        else:
            print("   ℹ️  SIMULATION ONLY - No units to send")
        print()
        
        # 6. Summary
        print("=" * 70)
        print("📊 Test Summary")
        print("=" * 70)
        
        # Count message types
        sent_count = sum(1 for d, _ in messages if d == 'SEND')
        recv_count = sum(1 for d, _ in messages if d == 'RECV')
        print(f"Messages sent: {sent_count}")
        print(f"Messages received: {recv_count}")
        print()
        
        # Show recent interesting messages
        print("Recent game responses:")
        for direction, msg in messages[-15:]:
            if direction == 'RECV' and isinstance(msg, bytes):
                msg_str = msg.decode('utf-8', errors='ignore')
                if msg_str.startswith('%xt%'):
                    parts = msg_str.split('%')
                    if len(parts) > 1:
                        cmd = parts[1]
                        # Show attack-related or new commands
                        if cmd in ['att', 'dcl', 'gaa', 'mov', 'atv']:
                            print(f"   {cmd}: {msg_str[:80]}")
        
        print()
        print("=" * 70)
        print("✅ Integration test complete!")
        print("=" * 70)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()
        print("\n🔌 Connection closed")

if __name__ == "__main__":
    print("This test will send a REAL attack on a barbarian camp.")
    print("Barbarian camps are safe targets (they don't attack back).")
    print()
    asyncio.run(full_test())
