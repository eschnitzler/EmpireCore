"""
Test script for the EmpireClient.

Usage:
    cd ~/EmpireCore
    uv run python examples/test_sync_client.py
"""

import logging
import os
import sys
import time

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Reduce noise from websocket
logging.getLogger("websocket").setLevel(logging.WARNING)


def main():
    from empire_core.client.client import EmpireClient

    # Get credentials from environment
    username = os.getenv("GGE_USERNAME")
    password = os.getenv("GGE_PASSWORD")

    if not username or not password:
        print("Error: GGE_USERNAME and GGE_PASSWORD environment variables required")
        sys.exit(1)

    print(f"Testing client with user: {username}")

    client = EmpireClient(username=username, password=password)

    try:
        # Login
        print("\n=== Logging in ===")
        client.login()
        print(f"Logged in: {client.is_logged_in}")

        if not client.is_logged_in:
            print("Login failed!")
            return 1

        # Get movements
        print("\n=== Getting movements ===")
        movements = client.get_movements()
        print(f"Found {len(movements)} movements")
        for m in movements[:5]:  # Show first 5
            print(f"  - {m}")

        # Test chat subscription
        print("\n=== Setting up chat subscription ===")

        def on_chat(packet):
            print(f"[CHAT] {packet.payload}")

        client.subscribe_alliance_chat(on_chat)
        print("Subscribed to alliance chat")

        # Keep alive for a bit to see if we get any chat
        print("\n=== Waiting 10 seconds for chat messages ===")
        time.sleep(10)

        print("\n=== Success! ===")
        return 0

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    finally:
        print("\n=== Disconnecting ===")
        client.close()


if __name__ == "__main__":
    sys.exit(main())
