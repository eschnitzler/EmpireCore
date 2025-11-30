#!/usr/bin/env python3
"""
Deep dive into what packets we're sending and receiving.
Log everything at the network layer.
"""
import asyncio
import sys
import json
sys.path.insert(0, 'src')

from empire_core import EmpireClient, EmpireConfig

async def deep_explore():
    print("=" * 70)
    print("🔍 Deep Packet Analysis")
    print("=" * 70)
    print()
    
    config = EmpireConfig(username="Divine Stella", password="abc123")
    client = EmpireClient(config)
    
    # Store all raw messages
    sent_messages = []
    received_messages = []
    
    # Monkey patch connection to log everything
    original_send = client.connection.send
    original_process = client.connection._process_message
    
    async def logged_send(data):
        sent_messages.append(data)
        print(f"📤 SEND: {str(data)[:80]}")
        return await original_send(data)
    
    async def logged_process(message):
        received_messages.append(message)
        msg_str = message.decode('utf-8', errors='ignore') if isinstance(message, bytes) else str(message)
        print(f"📥 RECV: {msg_str[:80]}")
        return await original_process(message)
    
    client.connection.send = logged_send
    client.connection._process_message = logged_process
    
    try:
        print("🔐 Logging in...")
        await client.login()
        print("\n✅ Logged in!")
        print()
        
        await asyncio.sleep(2)
        
        player = client.state.local_player
        if player:
            print(f"👤 Player: {player.name} (Level {player.level})")
            print(f"   Gold: {player.gold}, Rubies: {player.rubies}")
            print()
        
        print("=" * 70)
        print("📡 Requesting detailed castle info...")
        print("=" * 70)
        await client.get_detailed_castle_info()
        await asyncio.sleep(2)
        print()
        
        if player and player.castles:
            castle = next(iter(player.castles.values()))
            print(f"🏰 Castle: {castle.name}")
            print(f"   Resources: W:{castle.resources.wood}/{castle.resources.wood_cap}")
            print(f"   Production: {castle.resources.wood_rate}/h")
            print(f"   Population: {castle.population}")
            print()
        
        print("=" * 70)
        print("📊 Message Summary")
        print("=" * 70)
        print(f"Messages sent: {len(sent_messages)}")
        print(f"Messages received: {len(received_messages)}")
        print()
        
        # Show sent messages
        print("📤 SENT MESSAGES:")
        for i, msg in enumerate(sent_messages[:10], 1):
            print(f"{i}. {msg[:80]}")
        print()
        
        # Show received messages
        print("📥 RECEIVED MESSAGES:")
        for i, msg in enumerate(received_messages[:15], 1):
            if isinstance(msg, str):
                # Parse XT format
                if msg.startswith('%xt%'):
                    parts = msg.split('%')
                    cmd = parts[1] if len(parts) > 1 else "?"
                    print(f"{i}. CMD:{cmd} - {msg[:70]}")
                else:
                    print(f"{i}. {msg[:70]}")
            else:
                print(f"{i}. {type(msg).__name__}: {str(msg)[:70]}")
        print()
        
        # Try to identify what command gives us what data
        print("=" * 70)
        print("🔬 Analyzing Command Responses...")
        print("=" * 70)
        
        # Look for key data in responses
        for msg in received_messages:
            if isinstance(msg, str):
                if '"AID"' in msg and '"W"' in msg:  # Likely castle data
                    print(f"🏰 Castle data found: {msg[:100]}...")
                if '"gbd"' in msg or 'gbd' in msg:
                    print(f"📊 GBD response: {msg[:100]}...")
                if '"dcl"' in msg or 'dcl' in msg:
                    print(f"🏰 DCL response: {msg[:100]}...")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()
        print("\n🔌 Connection closed")

if __name__ == "__main__":
    asyncio.run(deep_explore())
