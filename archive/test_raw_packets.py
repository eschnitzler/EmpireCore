#!/usr/bin/env python3
"""See RAW packet data."""
import asyncio
import sys
import json
sys.path.insert(0, 'src')

from empire_core.client.client import EmpireClient
from empire_core.config import EmpireConfig

# Monkey patch to see raw data
original_handle_dcl = None

def debug_handle_dcl(self, data):
    print("\n" + "="*70)
    print("RAW DCL PACKET")
    print("="*70)
    print(json.dumps(data, indent=2, default=str)[:2000])
    print("="*70)
    return original_handle_dcl(self, data)

async def main():
    config = EmpireConfig(username="Mr. Aaron", password="abc123")
    client = EmpireClient(config)
    
    # Monkey patch
    global original_handle_dcl
    from empire_core.state.manager import GameState
    original_handle_dcl = GameState._handle_dcl
    GameState._handle_dcl = debug_handle_dcl
    
    try:
        await client.login()
        await asyncio.sleep(1)
        await client.get_detailed_castle_info()
        await asyncio.sleep(2)
    finally:
        await client.close()

asyncio.run(main())
