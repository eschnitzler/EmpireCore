"""
Debug script to capture all incoming packets and identify chat command IDs.

Usage:
    cd ~/EmpireCore
    uv run python examples/debug_packets.py
"""

import logging
import os
import sys
import time

# Setup verbose logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Reduce noise from websocket
logging.getLogger("websocket").setLevel(logging.WARNING)

logger = logging.getLogger("debug_packets")


def main():
    from empire_core.client.client import EmpireClient
    from empire_core.protocol.packet import Packet

    # Get credentials from environment
    username = os.getenv("GGE_USERNAME")
    password = os.getenv("GGE_PASSWORD")

    if not username or not password:
        print("Error: GGE_USERNAME and GGE_PASSWORD environment variables required")
        sys.exit(1)

    print(f"Debugging packets for user: {username}")

    client = EmpireClient(username=username, password=password)

    # Track all unique command IDs we see
    seen_commands = set()

    def log_all_packets(packet: Packet) -> None:
        """Log all incoming packets."""
        cmd = packet.command_id or "UNKNOWN"

        if cmd not in seen_commands:
            seen_commands.add(cmd)
            logger.info(f"NEW COMMAND: {cmd}")

        # Log packet details
        if packet.payload:
            payload_str = str(packet.payload)
            if len(payload_str) > 200:
                payload_str = payload_str[:200] + "..."
            logger.debug(f"[{cmd}] payload={payload_str}")

        # Specifically look for chat-related packets
        if "chat" in cmd.lower() or cmd in ("sam", "ram", "acm", "aci", "rcm", "sct", "rct"):
            logger.warning(f"CHAT PACKET FOUND: {cmd}")
            logger.warning(f"  Payload: {packet.payload}")

    # Override the packet handler to log everything
    original_handler = client._on_packet

    def debug_handler(packet: Packet) -> None:
        log_all_packets(packet)
        original_handler(packet)

    client.connection.on_packet = debug_handler

    try:
        # Login
        print("\n=== Logging in ===")
        client.login()
        print(f"Logged in: {client.is_logged_in}")

        if not client.is_logged_in:
            print("Login failed!")
            return 1

        print("\n=== Monitoring packets for 60 seconds ===")
        print("Try sending a message in alliance chat to capture the command ID")
        print("Press Ctrl+C to stop early\n")

        start = time.time()
        while time.time() - start < 60:
            time.sleep(1)
            # Print heartbeat every 10 seconds
            elapsed = int(time.time() - start)
            if elapsed % 10 == 0:
                print(f"  ... {elapsed}s elapsed, seen {len(seen_commands)} unique commands")

        print("\n=== Summary ===")
        print(f"Unique commands seen: {sorted(seen_commands)}")
        return 0

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        print(f"Unique commands seen: {sorted(seen_commands)}")
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
