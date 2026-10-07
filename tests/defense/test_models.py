"""Castle defense requests and replies, checked against the game client and a live dfc reply."""

import json
from typing import Any

import pytest

from empire_core.enums import Kingdom
from empire_core.gamedata import EMPTY_SLOT, Unit, WodAmount
from empire_core.protocol.js import js_int
from empire_core.protocol.models import (
    ChangeKeepDefenseRequest,
    ChangeMoatDefenseRequest,
    ChangeWallDefenseRequest,
    GetDefenseRequest,
    GetDefenseResponse,
    GetSupportDefenseResponse,
    KeepDefense,
    MoatDefense,
    WallDefense,
    WallSectionSetup,
    parse_response,
)

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
        request = GetDefenseRequest(castle_x=635, castle_y=242, area_id=16655114)
        assert list(request.to_payload().items()) == [("CX", 635), ("CY", 242), ("AID", 16655114), ("KID", -1)]

    def test_dfc_sends_a_given_kingdom_in_place_of_the_client_default(self):
        # C2SDefenceCompleteVO defaults KID to -1; a kingdom takes the same place
        request = GetDefenseRequest(castle_x=635, castle_y=242, area_id=16655114, kingdom_id=Kingdom.ICE)
        assert list(request.to_payload().items()) == [("CX", 635), ("CY", 242), ("AID", 16655114), ("KID", 2)]
        assert json.loads(request.to_packet().split("%")[5])["KID"] == 2

    def test_dfc_reads_the_client_default_as_no_kingdom(self):
        request = GetDefenseRequest.model_validate({"CX": 1, "CY": 2, "AID": 3, "KID": -1})
        assert request.kingdom_id is None
        assert request.to_payload()["KID"] == -1
        with pytest.raises(ValueError):
            GetDefenseRequest.model_validate({"CX": 1, "CY": 2, "AID": 3, "KID": 11})

    def test_dfk_keys_and_defaults_follow_the_client(self):
        request = ChangeKeepDefenseRequest(castle_x=1, castle_y=2, area_id=3, slots=(EMPTY_SLOT,) * 3)
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
        section = WallSectionSetup(slots=(EMPTY_SLOT,), unit_percent=50, unit_composition=50)
        request = ChangeWallDefenseRequest(
            castle_x=1, castle_y=2, area_id=3, left=section, middle=section, right=section
        )
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
        request = ChangeMoatDefenseRequest(
            castle_x=1, castle_y=2, area_id=3, left_slots=(EMPTY_SLOT,), middle_slots=(EMPTY_SLOT,), right_slots=()
        )
        assert request.to_payload() == {"CX": 1, "CY": 2, "AID": 3, "LS": [[-1, 0]], "MS": [[-1, 0]], "RS": []}

    def test_slots_go_out_as_built_duplicates_and_empty_slots_kept(self):
        # getSlotList writes one [wodId, amount] per slot, -1 and 0 for an empty one
        slots = (WodAmount(651, 20), EMPTY_SLOT, WodAmount(651, 5))
        request = ChangeKeepDefenseRequest(castle_x=1, castle_y=2, area_id=3, slots=slots, support_tool_slots=slots)
        assert (
            request.to_packet().split("%")[5].endswith('"S":[[651,20],[-1,0],[651,5]],"STS":[[651,20],[-1,0],[651,5]]}')
        )

    def test_a_read_setup_goes_back_byte_for_byte(self):
        keep = KeepDefense.model_validate({"S": [[651, 20], [-1, 0], [651, 5]], "STS": [[-1, 0]]})
        assert keep.slots == ((651, 20), (None, 0), (651, 5))
        request = ChangeKeepDefenseRequest(
            castle_x=1, castle_y=2, area_id=3, slots=keep.slots, support_tool_slots=keep.support_tool_slots
        )
        assert json.loads(request.to_packet().split("%")[5])["S"] == [[651, 20], [-1, 0], [651, 5]]

    def test_no_request_sends_a_castle_id(self):
        assert "CID" not in GetDefenseRequest(castle_x=1, castle_y=2, area_id=3).to_payload()


class TestLiveDefenseReply:
    def test_dfc_parses_every_block(self):
        response = parse_response("dfc", LIVE_DFC)
        assert isinstance(response, GetDefenseResponse)
        assert response.area is not None
        assert (response.area.x, response.area.y, response.area.object_id) == (635, 242, 16655114)
        assert response.home_defense_workshop_level == 1
        assert response.gate_defense == 30
        # parse_DFC keeps PR and PM; the allocator places each through int() as a unit (bundle lines 70838-70852)
        assert response.range_priority == (1337, 788, 674)
        assert response.melee_priority == (787, 336, 369)
        assert all(isinstance(unit, Unit) for unit in response.range_priority + response.melee_priority)
        assert response.castellan_id == 1
        assert response.castellan is not None
        assert (response.castellan.wins, response.castellan.defeats, len(response.castellan.area_effects)) == (1, 11, 2)
        assert response.inventory() == {10: 9, 652: 4}
        assert response.unit_inventory.stronghold == {}

    def test_nested_wall_keep_and_moat(self):
        response = GetDefenseResponse.model_validate(LIVE_DFC)
        assert response.wall is not None and response.keep is not None and response.moat is not None
        assert response.wall.middle.slots == (EMPTY_SLOT,)
        assert (response.wall.left.unit_percent, response.wall.middle.unit_percent) == (25, 50)
        assert (response.wall.unit_count, response.wall.unit_slot_count, response.wall.defense) == (13, 20, 30)
        assert response.keep.support_tool_slots == (EMPTY_SLOT,) * 3
        assert response.keep.unit_composition == 50
        assert response.keep.keep_unit_slot_count == 10000
        assert response.moat.right_slots == (EMPTY_SLOT,)
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
        assert js_int(value) == expected


class TestDefenseCastellanLeniency:
    def test_an_unreadable_castellan_keeps_the_reply(self):
        # parse_DFC: e.L && (this._lordID = int(e.L.ID)); {} is truthy, so the id reads as 0
        assert GetDefenseResponse.model_validate({"L": {}}).castellan is None
        assert GetDefenseResponse.model_validate({"L": {}}).castellan_id == 0
        assert GetDefenseResponse.model_validate({"L": {"ID": None}}).castellan_id == 0
        assert GetDefenseResponse.model_validate({"L": None}).castellan_id == -1
        assert GetDefenseResponse.model_validate({"L": {"ID": "4"}}).castellan_id == 4


class TestSupportDefenseReply:
    # sdi, shaped as CastleSupportDefenceVO.fillFromParamObject reads it
    PAYLOAD = {
        "SCID": 12345,
        "S": [[[487, 50], [488, "3"]], [], [[487, 10]], [[601, 7]], [], []],
        "AS": 0,
        "B": {"ID": 1003, "WID": 1, "N": "", "W": 2, "D": 0, "AE": [[426, [10.0], "GE"]]},
        "LS": [],
        "gui": {"I": [[487, 400], [620, 0]], "SHI": [[620, 5]]},
        "gli": {"C": [{"ID": 3, "WID": 2}], "B": [{"ID": 1003, "WID": 1}]},
        "UYL": 12000,
        "AUYL": 3000,
        "UWL": 5000,
    }

    def test_every_block_is_typed(self):
        response = GetSupportDefenseResponse.model_validate(self.PAYLOAD)

        army = response.defense_positions
        assert army is not None
        assert army.left == ((487, 50), (488, 3))
        assert army.keep == ((601, 7),)
        assert army.total() == 70
        assert response.castellan is not None
        assert (response.castellan.commander_id, [e.effect_id for e in response.castellan.area_effects]) == (
            1003,
            [426],
        )
        assert response.tower_castellan is None
        assert response.unit_inventory.units == {487: 400}
        assert response.unit_inventory.stronghold == {620: 5}
        assert [c.commander_id for c in response.commander_roster.commanders] == [3]
        assert [c.commander_id for c in response.commander_roster.castellans] == [1003]

    def test_an_unreadable_castellan_is_none(self):
        assert GetSupportDefenseResponse.model_validate({"B": {"N": "no id"}}).castellan is None
        assert GetSupportDefenseResponse.model_validate({"B": {}}).castellan is None

    def test_the_tower_castellan_comes_from_abe(self):
        response = GetSupportDefenseResponse.model_validate({"abe": {"ID": 7, "WID": 1}})

        assert response.tower_castellan is not None and response.tower_castellan.commander_id == 7
        assert response.castellan is None


GOLDEN_SDI = {
    "SCID": 12345,
    # Six defense positions, each a list of [unit_id, count] pairs.
    "S": [[[487, 5174], [488, 20]], [[487, 347]], [], [[301, 10]], [], []],
    "B": {"LID": -14},
    "gui": {"U": []},
    "gli": {"C": []},
    "UYL": 12000,
    "AUYL": 3000,
    "UWL": 5000,
}


class TestGoldenSupportDefense:
    def test_registry_parses_sdi(self):
        assert isinstance(parse_response("sdi", GOLDEN_SDI), GetSupportDefenseResponse)

    def test_total_defenders_sums_every_position(self):
        response = GetSupportDefenseResponse.model_validate(GOLDEN_SDI)
        assert response.defense_positions is not None
        assert response.defense_positions.total() == 5174 + 20 + 347 + 10

    def test_units_are_read_per_position(self):
        response = GetSupportDefenseResponse.model_validate(GOLDEN_SDI)
        assert response.defense_positions is not None
        assert [stacks for _section, stacks in response.defense_positions.sections()] == [
            ((487, 5174), (488, 20)),
            ((487, 347),),
            (),
            ((301, 10),),
            (),
            (),
            (),
        ]

    def test_capacity_fields(self):
        response = GetSupportDefenseResponse.model_validate(GOLDEN_SDI)
        assert (response.yard_limit, response.available_yard_limit, response.wall_limit) == (12000, 3000, 5000)
        assert response.get_max_defense() == 12000

    def test_no_defense_block_is_none(self):
        # parseArmyInfo reads the positions only for a non-empty S
        assert GetSupportDefenseResponse.model_validate({"SCID": 1}).defense_positions is None
        assert GetSupportDefenseResponse.model_validate({"S": []}).defense_positions is None
