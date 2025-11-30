#!/usr/bin/env python3
"""
Real action test - actually send actions and document responses.
We'll be careful and only do safe operations (train 1 unit, attack 1 barbarian).
"""
import asyncio
import sys
import json
from datetime import datetime
sys.path.insert(0, 'src')

from empire_core import EmpireClient, EmpireConfig

# Test with an account that hasn't hit cooldown
ACCOUNTS = [
    "Super Penelope",
    "zazerzeezba", 
    "Heimlina",
    "Mr. Aaron"
]

async def test_real_actions():
    print("=" * 70)
    print("⚔️  REAL ACTION TESTING")
    print("=" * 70)
    print(f"Time: {datetime.now().strftime('%H:%M:%S')}")
    print()
    
    # Try accounts until one works
    client = None
    for account in ACCOUNTS:
        config = EmpireConfig(username=account, password="abc123")
        temp_client = EmpireClient(config)
        
        try:
            print(f"🔐 Trying account: {account}...")
            await temp_client.login()
            client = temp_client
            print(f"✅ Logged in as {account}!\n")
            break
        except Exception as e:
            await temp_client.close()
            if "cooldown" in str(e).lower():
                print(f"   ⏱️  Cooldown - trying next account\n")
                continue
            else:
                print(f"   ❌ Error: {e}\n")
                continue
    
    if not client:
        print("❌ All accounts on cooldown or errored!")
        return
    
    # Log all traffic
    all_messages = []
    
    original_send = client.connection.send
    original_process = client.connection._process_message
    
    async def log_send(data):
        all_messages.append(('SEND', datetime.now(), data))
        return await original_send(data)
    
    async def log_recv(msg):
        all_messages.append(('RECV', datetime.now(), msg))
        return await original_process(msg)
    
    client.connection.send = log_send
    client.connection._process_message = log_recv
    
    try:
        # Get full state
        print("📊 Getting game state...")
        await client.get_detailed_castle_info()
        await asyncio.sleep(2)
        
        player = client.state.local_player
        if not player or not player.castles:
            print("❌ No player data")
            return
        
        castle = next(iter(player.castles.values()))
        print(f"🏰 Castle: {castle.name}")
        print(f"   ID: {castle.id}")
        print(f"   Resources: W:{castle.resources.wood} S:{castle.resources.stone} F:{castle.resources.food}")
        print(f"   Units available:")
        
        has_units = False
        for unit_id, count in sorted(castle.units.items())[:10]:
            if count > 0:
                print(f"      Unit {unit_id}: {count}")
                has_units = True
        
        if not has_units:
            print("      (No units yet)")
        print()
        
        # TEST 1: Train a single militia (cheapest unit)
        print("=" * 70)
        print("TEST 1: Train Units")
        print("=" * 70)
        
        can_train = castle.resources.wood >= 10 and castle.resources.food >= 10
        
        if can_train:
            print("   💰 Resources sufficient for 1 militia (W:10, F:10)")
            print("   🎯 Training 1 militia...")
            
            train_payload = {
                "AID": castle.id,
                "UID": 620,  # Militia
                "C": 1
            }
            
            train_cmd = f"%xt%EmpireEx_21%tru%1%{json.dumps(train_payload)}%"
            await client.connection.send(train_cmd)
            
            # Wait for response
            await asyncio.sleep(2)
            
            # Check for training response
            print("   📥 Looking for training response...")
            for direction, timestamp, msg in all_messages[-10:]:
                if direction == 'RECV' and isinstance(msg, bytes):
                    msg_str = msg.decode('utf-8', errors='ignore')
                    if 'tru' in msg_str or 'error' in msg_str.lower():
                        print(f"      {msg_str[:120]}")
            print()
        else:
            print(f"   ❌ Not enough resources (need W:10, F:10)")
            print(f"      Have: W:{castle.resources.wood}, F:{castle.resources.food}")
            print("   SKIPPING training test")
            print()
        
        # TEST 2: Get map and find a target
        print("=" * 70)
        print("TEST 2: Map & Target Finding")
        print("=" * 70)
        
        print("   🗺️  Getting map chunk...")
        await client.get_map_chunk(0, 50, 50)
        await asyncio.sleep(2)
        
        print(f"   ✅ Found {len(client.state.map_objects)} map objects")
        
        # Look for barbarians
        barbarians = []
        for obj_id, obj in client.state.map_objects.items():
            if hasattr(obj, 'type_id') and obj.type_id == 32:
                barbarians.append(obj)
                print(f"      Barbarian camp: ID={obj.id}, Level={getattr(obj, 'level', '?')}")
        
        if not barbarians:
            print("      (No barbarians in this chunk)")
        print()
        
        # TEST 3: Send attack (if we have units and found target)
        print("=" * 70)
        print("TEST 3: Send Attack")
        print("=" * 70)
        
        if has_units and barbarians:
            target = barbarians[0]
            
            # Find smallest unit count to send
            attack_units = {}
            for unit_id, count in castle.units.items():
                if count > 0:
                    attack_units[unit_id] = min(5, count)
                    print(f"   Sending {attack_units[unit_id]}x unit {unit_id}")
                    break
            
            if attack_units:
                print(f"   🎯 Target: Barbarian camp {target.id}")
                print(f"   ⚔️  Launching attack...")
                
                attack_payload = {
                    "OID": castle.id,
                    "TID": target.id,
                    "UN": attack_units,
                    "TT": 1,
                    "KID": 0
                }
                
                attack_cmd = f"%xt%EmpireEx_21%att%1%{json.dumps(attack_payload)}%"
                await client.connection.send(attack_cmd)
                
                # Wait for response
                await asyncio.sleep(3)
                
                # Check for attack response
                print("   📥 Attack response:")
                found_response = False
                for direction, timestamp, msg in all_messages[-15:]:
                    if direction == 'RECV' and isinstance(msg, bytes):
                        msg_str = msg.decode('utf-8', errors='ignore')
                        if 'att' in msg_str or 'mov' in msg_str or 'MID' in msg_str:
                            print(f"      {msg_str[:150]}")
                            found_response = True
                
                if not found_response:
                    print("      (No attack response captured yet)")
                print()
        else:
            if not has_units:
                print("   ℹ️  No units available - SKIPPING")
            if not barbarians:
                print("   ℹ️  No barbarians found - SKIPPING")
            print()
        
        # TEST 4: Check for any movement updates
        print("=" * 70)
        print("TEST 4: Movement Tracking")
        print("=" * 70)
        
        print("   Looking for movement packets...")
        movements_found = False
        for direction, timestamp, msg in all_messages[-30:]:
            if direction == 'RECV' and isinstance(msg, bytes):
                msg_str = msg.decode('utf-8', errors='ignore')
                if msg_str.startswith('%xt%'):
                    parts = msg_str.split('%')
                    if len(parts) > 1:
                        cmd = parts[1]
                        if cmd in ['mov', 'atv', 'gml', 'uml']:
                            print(f"      {cmd}: {msg_str[:100]}")
                            movements_found = True
        
        if not movements_found:
            print("      (No movement packets received)")
        print()
        
        # Summary
        print("=" * 70)
        print("📊 TEST SUMMARY")
        print("=" * 70)
        
        sent_count = sum(1 for d, t, m in all_messages if d == 'SEND')
        recv_count = sum(1 for d, t, m in all_messages if d == 'RECV')
        
        print(f"Total messages: {sent_count} sent, {recv_count} received")
        print()
        
        # Show all unique response types
        response_types = set()
        for direction, timestamp, msg in all_messages:
            if direction == 'RECV' and isinstance(msg, bytes):
                msg_str = msg.decode('utf-8', errors='ignore')
                if msg_str.startswith('%xt%'):
                    parts = msg_str.split('%')
                    if len(parts) > 1:
                        response_types.add(parts[1])
        
        print(f"Response types seen: {sorted(response_types)[:20]}")
        print()
        
        # Save detailed log
        print("💾 Saving detailed message log...")
        with open('action_test_log.txt', 'w') as f:
            f.write(f"Action Test Log - {datetime.now()}\n")
            f.write(f"Account: {player.name}\n")
            f.write("=" * 70 + "\n\n")
            
            for direction, timestamp, msg in all_messages:
                time_str = timestamp.strftime('%H:%M:%S.%f')[:-3]
                if isinstance(msg, bytes):
                    msg_str = msg.decode('utf-8', errors='ignore')
                else:
                    msg_str = str(msg)
                
                f.write(f"[{time_str}] {direction}: {msg_str[:200]}\n")
        
        print("   ✅ Saved to action_test_log.txt")
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()
        print("\n🔌 Connection closed")
        print("\n✅ Test complete!")

if __name__ == "__main__":
    asyncio.run(test_real_actions())
