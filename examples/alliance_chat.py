"""Read alliance chat history and follow new messages as they arrive.

Demonstrates the two halves of the chat API: a request/response history fetch,
and a callback subscription served by the library's background receive thread.

    export GGE_USERNAME=your_user
    export GGE_PASSWORD=your_pass
    python examples/alliance_chat.py [seconds_to_listen]
"""

import logging
import os
import sys
import time

from empire_core import EmpireClient, EmpireError
from empire_core.protocol.models.chat import AllianceChatMessageResponse

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("websocket").setLevel(logging.WARNING)

LISTEN_SECONDS = 60.0


def main() -> int:
    username = os.getenv("GGE_USERNAME")
    password = os.getenv("GGE_PASSWORD")
    if not username or not password:
        print("Set GGE_USERNAME and GGE_PASSWORD first.", file=sys.stderr)
        return 2

    listen_for = float(sys.argv[1]) if len(sys.argv) > 1 else LISTEN_SECONDS

    client = EmpireClient(username=username, password=password)
    try:
        client.login()

        print("\n--- recent history ---")
        for entry in client.alliance.get_chat_log():
            print(f"  {entry.player_name}: {entry.decoded_text}")

        def on_message(message: AllianceChatMessageResponse) -> None:
            # Called on the receive thread: keep it quick and do not block.
            print(f"  [live] {message.player_name}: {message.decoded_text}")

        client.alliance.on_chat_message(on_message)

        print(f"\n--- listening for {listen_for:.0f}s (Ctrl+C to stop) ---")
        deadline = time.monotonic() + listen_for
        while time.monotonic() < deadline:
            time.sleep(0.5)

        # To send a message:
        # client.alliance.send_chat("Hello from EmpireCore")

    except KeyboardInterrupt:
        print("\nStopped.")
    except EmpireError as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
