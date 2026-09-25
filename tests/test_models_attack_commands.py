"""Attack-side request and reply models, checked against the payloads the game client builds."""

import json

from empire_core.protocol.models import (
    MinuteSkipDungeonRequest,
    MinuteSkipDungeonResponse,
    SkipDungeonCooldownRequest,
    SkipDungeonCooldownResponse,
    parse_response,
)


class TestDungeonCooldownSkips:
    def test_minute_skip_sends_the_client_keys_with_kingdom_as_string(self):
        request = MinuteSkipDungeonRequest(MST="MS2", KID=2, X=100, Y=200)
        payload = request.to_payload()
        assert list(payload.items()) == [("X", 100), ("Y", 200), ("MID", -1), ("NID", -1), ("MST", "MS2"), ("KID", "2")]

    def test_minute_skip_on_a_treasure_map_node(self):
        request = MinuteSkipDungeonRequest(MST="MS1", KID=0, X=5, Y=6, MID=3, NID=12)
        assert request.to_payload()["MID"] == 3
        assert request.to_payload()["NID"] == 12
        assert json.loads(request.to_packet().split("%")[5])["KID"] == "0"

    def test_full_skip_sends_the_client_keys_with_kingdom_as_number(self):
        request = SkipDungeonCooldownRequest(X=100, Y=200, KID=2)
        assert list(request.to_payload().items()) == [("X", 100), ("Y", 200), ("KID", 2), ("MID", -1), ("NID", -1)]

    def test_full_skip_on_a_treasure_map_node(self):
        payload = SkipDungeonCooldownRequest(X=1, Y=2, KID=0, MID=7, NID=4).to_payload()
        assert (payload["MID"], payload["NID"]) == (7, 4)

    def test_replies_carry_the_dungeon_row(self):
        row = [2, 100, 200, -1, 0, 0, 0]
        assert isinstance(parse_response("msd", {"AI": row}), MinuteSkipDungeonResponse)
        assert isinstance(parse_response("sdc", {"AI": row}), SkipDungeonCooldownResponse)
        assert SkipDungeonCooldownResponse.model_validate({"AI": row}).area_row == row
        assert not hasattr(SkipDungeonCooldownResponse.model_validate({"AI": row}), "rubies_spent")
