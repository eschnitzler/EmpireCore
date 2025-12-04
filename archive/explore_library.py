#!/usr/bin/env python3
"""
Use the actual EmpireCore library to connect and explore what data we get.
This helps us see what's working and what needs improvement.
"""
import asyncio
import sys
import json
sys.path.insert(0, 'src')

from empire_core import EmpireClient, EmpireConfig

async def explore():
    print("=" * 70)
    print("🎮 EmpireCore Library Explorer")
    print("=" * 70)
    print()
    
    # Configure client with packet logging
    config = EmpireConfig(
        username="Divine Stella",
        password="abc123"
    )
    
    client = EmpireClient(config)
    
    # Track all packets received
    all_packets = []
    raw_messages = []
    
    # Monkey patch the packet handler to intercept
    original_handler = client._on_packet
    
    async def packet_interceptor(packet):
        all_packets.append(packet)
        print(f"📥 {packet.command_id}: {type(packet.payload).__name__}")
        return await original_handler(packet)
    
    client._on_packet = packet_interceptor
    
    try:
        print("🔐 Logging in...")
        await client.login()
        print("✅ Logged in!")
        print()
        
        # Wait a bit for initial packets
        print("⏳ Waiting for initial packets...")
        await asyncio.sleep(3)
        print()
        
        # Check player state
        player = client.state.local_player
        if player:
            print("👤 Player State:")
            print(f"   Name: {player.name}")
            print(f"   ID: {player.id}")
            print(f"   Level: {player.level}")
            print(f"   Gold: {player.gold}")
            print(f"   Rubies: {player.rubies}")
            print(f"   Castles: {len(player.castles)}")
            print()
        else:
            print("⚠️  No player data yet")
            print()
        
        # Try requesting data
        print("=" * 70)
        print("📡 Requesting Game Data...")
        print("=" * 70)
        print()
        
        # Get detailed castle info
        print("1️⃣  Requesting detailed castle list (dcl)...")
        await client.get_detailed_castle_info()
        await asyncio.sleep(2)
        
        if player and player.castles:
            print(f"   ✅ Got {len(player.castles)} castles")
            for castle_id, castle in list(player.castles.items())[:2]:
                print(f"   🏰 Castle {castle_id}: {castle.name}")
                print(f"      Resources: W:{castle.resources.wood} S:{castle.resources.stone} F:{castle.resources.food}")
                print(f"      Population: {castle.population}")
                print(f"      Buildings: {len(castle.buildings)}")
        print()
        
        # Try getting map data
        if player and player.castles:
            first_castle = next(iter(player.castles.values()))
            if hasattr(first_castle, 'x') and hasattr(first_castle, 'y'):
                print("2️⃣  Requesting map chunk around castle...")
                await client.get_map_chunk(0, first_castle.x, first_castle.y)
                await asyncio.sleep(2)
                print(f"   ✅ Map objects tracked: {len(client.state.map_objects)}")
        print()
        
        # Summary
        print("=" * 70)
        print("📊 Summary")
        print("=" * 70)
        print(f"Total packets received: {len(all_packets)}")
        print()
        
        # Count by command type
        from collections import Counter
        cmd_counts = Counter(p.command_id for p in all_packets if p.command_id)
        print("Packet types:")
        for cmd, count in cmd_counts.most_common(10):
            print(f"   {cmd}: {count}")
        print()
        
        # Show a sample of raw packet data
        print("=" * 70)
        print("🔍 Sample Raw Packet Data")
        print("=" * 70)
        
        for i, packet in enumerate(all_packets[:5]):
            print(f"\n{i+1}. Command: {packet.command_id}")
            if packet.payload:
                if isinstance(packet.payload, dict):
                    print(f"   Keys: {list(packet.payload.keys())}")
                    # Show first few key-value pairs
                    for key in list(packet.payload.keys())[:5]:
                        val = packet.payload[key]
                        if isinstance(val, (dict, list)):
                            print(f"   {key}: {type(val).__name__} with {len(val)} items")
                        else:
                            print(f"   {key}: {val}")
                else:
                    print(f"   Payload: {str(packet.payload)[:200]}")
        
        print("\n" + "=" * 70)
        print("✅ Exploration complete!")
        print("=" * 70)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(explore())
