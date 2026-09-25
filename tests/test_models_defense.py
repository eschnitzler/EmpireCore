"""Castle defense requests and replies, checked against the game client and a live dfc reply."""

from typing import Any

import pytest

from empire_core.protocol.models import (
    ChangeKeepDefenseRequest,
    ChangeMoatDefenseRequest,
    ChangeWallDefenseRequest,
    GetDefenseRequest,
    GetDefenseResponse,
    KeepDefense,
    MoatDefense,
    WallDefense,
    WallSectionSetup,
    parse_response,
)
from empire_core.protocol.models.base import client_int

# Live capture, castle name scrubbed and PR/PM trimmed to three entries
LIVE_DFC: dict[str, Any] = {
    "A": [1, 635, 242, 16655114, 17743796, 1, 1, 1, 0, 0, "Castle", 0, 0, -1, -1, -1, 0, 0, [], 0],
    "PR": [1337, 788, 674],
    "PM": [787, 336, 369],
    "dfw": {
        "L": {"S": [], "UP": 25, "UC": 50},
        "M": {"S": [[-1, 0]], "UP": 50, "UC": 50},
        "R": {"S": [], "UP": 25, "UC": 50},
        "U": 13,
        "US": 20,
        "D": 30.0,
    },
    "dfk": {
        "S": [[-1, 0], [-1, 0], [-1, 0]],
        "STS": [[-1, 0], [-1, 0], [-1, 0]],
        "MAUCT": 0,
        "UC": 50,
        "U": 0,
        "UYL": 110000,
        "AUYL": 100000,
    },
    "dfm": {"LS": [[-1, 0]], "MS": [[-1, 0]], "RS": [[-1, 0]], "D": 0.0},
    "gui": {"I": [[10, 9], [652, 4]], "AI": []},
    "L": {
        "ID": 1,
        "WID": 1,
        "VIS": 0,
        "LICID": 16655114,
        "GID": -1,
        "W": 1,
        "D": 11,
        "SPR": 1,
        "EQ": [],
        "AE": [[702, [10000], "BG"], [706, [100000], "BG"]],
    },
    "GD": 30.0,
    "MDS": 0.0,
    "RDS": 0.0,
    "HDWL": 1,
}


class TestDefenseRequests:
    def test_dfc_addresses_the_castle_by_position_and_area(self):
        request = GetDefenseRequest(CX=635, CY=242, AID=16655114)
        assert list(request.to_payload().items()) == [("CX", 635), ("CY", 242), ("AID", 16655114), ("KID", -1)]

    def test_dfk_keys_and_defaults_follow_the_client(self):
        request = ChangeKeepDefenseRequest(CX=1, CY=2, AID=3, S=[[-1, 0]] * 3)
        assert list(request.to_payload().items()) == [
            ("CX", 1),
            ("CY", 2),
            ("AID", 3),
            ("MAUCT", 0),
            ("UC", 50),
            ("S", [[-1, 0]] * 3),
            ("STS", []),
        ]

    def test_dfw_nests_each_wall_section(self):
        section = WallSectionSetup(S=[[-1, 0]], UP=50, UC=50)
        request = ChangeWallDefenseRequest(CX=1, CY=2, AID=3, L=section, M=section, R=section)
        payload = request.to_payload()
        assert list(payload) == ["CX", "CY", "AID", "L", "M", "R"]
        assert payload["M"] == {"S": [[-1, 0]], "UP": 50, "UC": 50}

    def test_dfw_needs_every_section(self):
        with pytest.raises(ValueError):
            ChangeWallDefenseRequest.model_validate({"CX": 1, "CY": 2, "AID": 3})

    def test_a_wall_section_needs_its_unit_percent_and_composition(self):
        with pytest.raises(ValueError):
            WallSectionSetup.model_validate({"S": [[-1, 0]]})

    def test_dfm_sends_three_slot_lists(self):
        request = ChangeMoatDefenseRequest(CX=1, CY=2, AID=3, LS=[[-1, 0]], MS=[[-1, 0]], RS=[[-1, 0]])
        assert request.to_payload() == {"CX": 1, "CY": 2, "AID": 3, "LS": [[-1, 0]], "MS": [[-1, 0]], "RS": [[-1, 0]]}

    def test_no_request_sends_a_castle_id(self):
        assert "CID" not in GetDefenseRequest(CX=1, CY=2, AID=3).to_payload()


class TestLiveDefenseReply:
    def test_dfc_parses_every_block(self):
        response = parse_response("dfc", LIVE_DFC)
        assert isinstance(response, GetDefenseResponse)
        assert response.area is not None
        assert (response.area.x, response.area.y, response.area.object_id) == (635, 242, 16655114)
        assert response.home_defense_workshop_level == 1
        assert response.gate_defense == 30
        assert response.range_priority == [1337, 788, 674]
        assert response.melee_priority == [787, 336, 369]
        assert response.castellan_id == 1
        assert response.castellan is not None
        assert (response.castellan.wins, response.castellan.defeats, len(response.castellan.area_effects)) == (1, 11, 2)
        assert response.inventory() == {10: 9, 652: 4}
        assert response.unit_inventory.stronghold == {}

    def test_nested_wall_keep_and_moat(self):
        response = GetDefenseResponse.model_validate(LIVE_DFC)
        assert response.wall is not None and response.keep is not None and response.moat is not None
        assert response.wall.middle.slots == [[-1, 0]]
        assert (response.wall.left.unit_percent, response.wall.middle.unit_percent) == (25, 50)
        assert (response.wall.unit_count, response.wall.unit_slot_count, response.wall.defense) == (13, 20, 30)
        assert response.keep.support_tool_slots == [[-1, 0]] * 3
        assert response.keep.unit_composition == 50
        assert response.keep.keep_unit_slot_count == 10000
        assert response.moat.right_slots == [[-1, 0]]
        assert response.moat.defense == 0

    def test_standalone_replies_reuse_the_nested_blocks(self):
        assert isinstance(parse_response("dfw", LIVE_DFC["dfw"]), WallDefense)
        assert isinstance(parse_response("dfk", LIVE_DFC["dfk"]), KeepDefense)
        assert isinstance(parse_response("dfm", LIVE_DFC["dfm"]), MoatDefense)

    def test_error_reply_parses(self):
        response = parse_response("dfc", {"E": 21})
        assert isinstance(response, GetDefenseResponse)
        assert response.wall is None
        assert response.castellan_id == -1
        assert response.inventory() == {}


class TestClientInventoryAndInt:
    def test_inventory_adds_up_like_the_client(self):
        # UnitInventoryDictionary.addUnit clamps at 0 and changeUnitAmount adds
        response = GetDefenseResponse.model_validate({"gui": {"I": [[10, 2], [10, 3], [11, -4], [12, 0]]}})
        assert response.inventory() == {10: 5}

    @pytest.mark.parametrize(
        ("value", "expected"),
        # Outputs of the client's int() run in node
        [(30.0, 30), (30.7, 30), (-2.5, -2), ("12", 12), ("", 0), (None, 0), ("abc", 0), ("#00FF10", 65296), (True, 1)],
    )
    def test_client_int(self, value: Any, expected: int):
        assert client_int(value) == expected
