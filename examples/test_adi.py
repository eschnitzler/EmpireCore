import logging
import sys

logging.basicConfig(level=logging.WARNING)


def main():
    from empire_core.client.client import EmpireClient
    from empire_core.protocol.models.map import GetTargetInfoRequest, GetTargetInfoResponse, Kingdom

    client = EmpireClient(username="Heimlina", password="abc123")

    try:
        client.login()
        print(f"Logged in: {client.is_logged_in}")
        if not client.is_logged_in:
            print("FAIL: Login failed")
            return 1

        # Get source position from bot's main castle
        castles = list(client.state.castles.values())
        if not castles:
            print("FAIL: No castles found in state")
            return 1

        main_castle = castles[0]
        source_x = main_castle.X
        source_y = main_castle.Y
        print(f"Source (bot castle): ({source_x}, {source_y})")

        # Robber Baron NPC coords from the issue report
        npc_x = 214
        npc_y = 1259
        k_id = Kingdom.GREEN

        print(f"Target (Robber Baron): ({npc_x}, {npc_y})")

        request = GetTargetInfoRequest(SX=source_x, SY=source_y, TX=npc_x, TY=npc_y, KID=k_id)
        response = client.send(request, wait=True, timeout=8.0)

        print(f"Response type: {type(response).__name__}")
        print(f"Response: {response}")

        if isinstance(response, GetTargetInfoResponse):
            print("PASS: Got GetTargetInfoResponse")
            if response.target:
                print(f"  Target type: {response.target.object_type}")
                print(f"  Target pos: ({response.target.x}, {response.target.y})")
            return 0
        else:
            print(f"FAIL: Unexpected response: {response}")
            return 1

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1

    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
