"""The gam reply models, checked against payloads in the shape the server sends."""

from typing import Any

import pytest
from pydantic import ValidationError

from empire_core.protocol.models import GetMovementsResponse, MovementArea
from empire_core.protocol.models.base import Position

# Live capture, names scrubbed
GOOD_MOVEMENT: dict[str, Any] = {
    "M": {
        "MID": 1,
        "PT": 10,
        "TT": 128,
        "D": 0,
        "TID": -202,
        "T": 0,
        "HBW": -1,
        "KID": 0,
        "TA": [2, 3, 4, -1, 0, -1, 0],
        "SID": 17,
        "OID": 17,
        "SA": [1, 1, 2, 555, 17, 2, 2, 2, 1, 0, "Home", 0, 0, -1, -1, -1, 0, 0, [], 0],
    },
    "UM": {"PWD": 0, "TWD": 0, "L": {"ID": 0}},
    "GA": {"L": [[1, 5]], "M": [[2, 10]], "R": [], "RW": [[3, 1]]},
    "ATT": 0,
    "FC": 0,
    "S": 0,
    "AST": [],
}


class TestMalformedMovementBatch:
    """A gam batch is all-or-nothing today; that is worth knowing about."""

    def test_one_entry_missing_a_required_field_discards_the_batch(self):
        broken = {**GOOD_MOVEMENT, "M": {key: value for key, value in GOOD_MOVEMENT["M"].items() if key != "MID"}}
        with pytest.raises(ValidationError) as exc_info:
            GetMovementsResponse.model_validate({"M": [GOOD_MOVEMENT, broken]})
        # The error names the offending index and field, which is what makes a
        # drift diagnosable from a log line.
        assert "MID" in str(exc_info.value)

    def test_non_dict_entry_discards_the_batch(self):
        with pytest.raises(ValidationError):
            GetMovementsResponse.model_validate({"M": [GOOD_MOVEMENT, "junk"]})

    def test_movement_list_of_the_wrong_type_is_a_validation_error(self):
        with pytest.raises(ValidationError):
            GetMovementsResponse.model_validate({"M": "junk"})

    def test_a_clean_batch_still_parses(self):
        response = GetMovementsResponse.model_validate({"M": [GOOD_MOVEMENT], "O": [{"OID": 17, "N": "me"}]})
        wrapper = response.movements[0]
        record = wrapper.movement
        assert record.movement_id == 1 and record.movement_type == 0 and not record.is_returning
        assert record.owner_id == 17 and record.target_id == -202
        assert record.source_area is not None and record.source_area.position == Position(X=1, Y=2)
        assert record.target_area is not None and (record.target_area.area_type, record.target_area.y) == (2, 4)
        assert record.source_area.row[10] == "Home"
        assert wrapper.visible_army is not None and wrapper.visible_army.courtyard == [[3, 1]]
        assert wrapper.unit_info is not None and wrapper.unit_info.wait_total == 0
        assert response.owners[0].name == "me"

    def test_owner_record_as_the_client_reads_it(self):
        # Live capture, name scrubbed
        owner = {
            "OID": 5,
            "N": "someone",
            "E": {"BGT": 0, "BGC1": 3, "BGC2": 0, "SPT": 1, "S1": 2, "SC1": 0, "S2": 0, "SC2": 0, "IS": 1},
            "L": 70,
            "LL": 12,
            "RNP": -1,
            "H": 250,
            "MP": 1267,
            "TOPX": -1,
            "R": 0,
            "AID": 190426,
            "AR": 8,
            "AN": "Clan",
            "SA": 0,
            "RPT": 0,
            "AP": [[0, 16655119, 633, 235, 1]],
            "VP": [],
            "PF": 0,
            "VF": 1,
            "DUM": False,
            "AVP": 0,
            "RRD": 0,
            "FN": {"MC": -1, "FID": 0, "TID": 103, "NS": -1, "PMS": -1, "PMT": 0, "SPC": 0},
            "SUF": -1,
            "PRE": 0,
            "CF": 0,
            "HF": 0,
        }
        record = GetMovementsResponse.model_validate({"M": [], "O": [owner]}).owners[0]
        assert (record.player_id, record.level, record.legend_level, record.honor) == (5, 70, 12, 250)
        assert (record.alliance_id, record.alliance_rank, record.alliance_name) == (190426, 8, "Clan")
        assert record.has_vip and not record.has_premium and not record.is_ruin and not record.is_searching_alliance
        assert record.crest is not None and record.crest.is_set and record.crest.background_color1 == 3
        assert record.castle_positions[0].model_dump() == {
            "kingdom_id": 0,
            "area_id": 16655119,
            "x": 633,
            "y": 235,
            "area_type": 1,
        }
        assert record.faction is not None and record.faction.title_id == 103

    def test_spy_and_market_blocks(self):
        spy = GetMovementsResponse.model_validate(
            {"M": [{**GOOD_MOVEMENT, "S": {"ST": 2, "SA": 40, "SC": 12, "SR": 5}}]}
        ).movements[0]
        assert spy.spy is not None and spy.spy.is_sabotage and spy.spy.accuracy_or_damage == 40
        market = GetMovementsResponse.model_validate(
            {"M": [{**GOOD_MOVEMENT, "S": 0, "MM": {"C": 3, "G": [["W", 100], ["S", 50]]}}]}
        ).movements[0]
        assert market.spy is None
        assert market.market is not None and market.market.carriages == 3
        assert market.market.goods == [("W", 100), ("S", 50)]

    def test_travel_units_and_loot(self):
        travel = {**GOOD_MOVEMENT, "A": [[216, 500]], "G": [["W", 8], ["C1", 28]]}
        wrapper = GetMovementsResponse.model_validate({"M": [travel]}).movements[0]
        assert wrapper.travel_units == [[216, 500]]
        assert wrapper.travel_goods == [("W", 8), ("C1", 28)]

    def test_full_army_wins_over_army(self):
        wrapper = GetMovementsResponse.model_validate({"M": [{**GOOD_MOVEMENT, "FA": {"M": [[9, 1]]}}]}).movements[0]
        assert wrapper.visible_army is not None and wrapper.visible_army.middle == [[9, 1]]

    def test_hidden_army_reports_only_a_size(self):
        hidden = {"M": GOOD_MOVEMENT["M"], "GS": 250}
        wrapper = GetMovementsResponse.model_validate({"M": [hidden]}).movements[0]
        assert wrapper.visible_army is None and wrapper.army_size == 250

    def test_commander_as_the_client_reads_it(self):
        commander = {
            "ID": 3,
            "WID": 2,
            "VIS": 5,
            "N": "",
            "W": 2,
            "D": 1,
            "SPR": 2,
            "EQ": [[6515210043, 6, 2, 10, 0, [[242, [25.0]]], 802, 22, 0, -1, -1, 1]],
            "AE": [[426, [10.0], "GE"]],
        }
        wrapper = GetMovementsResponse.model_validate(
            {"M": [{**GOOD_MOVEMENT, "UM": {"PWD": 0, "TWD": 20, "L": commander}}]}
        ).movements[0]
        assert wrapper.unit_info is not None and wrapper.unit_info.commander is not None
        leader = wrapper.unit_info.commander
        assert (leader.commander_id, leader.wearer_id, leader.picture_id, leader.wins) == (3, 2, 5, 2)
        assert [item.unique_id for item in leader.equipment()] == [802]

    def test_unreadable_commander_keeps_the_wait(self):
        wrapper = GetMovementsResponse.model_validate(
            {"M": [{**GOOD_MOVEMENT, "UM": {"PWD": 4, "TWD": 20, "L": {"N": "no id"}}}]}
        ).movements[0]
        assert wrapper.unit_info is not None
        assert (wrapper.unit_info.commander, wrapper.unit_info.wait_passed) == (None, 4)

    def test_unknown_wrapper_keys_are_kept(self):
        wrapper = GetMovementsResponse.model_validate({"M": [{**GOOD_MOVEMENT, "NEW": 1}]}).movements[0]
        assert wrapper.model_extra == {"NEW": 1}

    def test_numeric_strings_are_coerced_rather_than_rejected(self):
        # GGE has sent numbers as strings before; lax coercion is what keeps a
        # whole batch from vanishing when it happens.
        coerced = {**GOOD_MOVEMENT, "M": {**GOOD_MOVEMENT["M"], "MID": "7"}}
        assert GetMovementsResponse.model_validate({"M": [coerced]}).movements[0].movement.movement_id == 7


class TestMovementAreaLayouts:
    CASTLE = [1, 632, 243, 16654596, 17743260, 2, 2, 2, 1, 0, "Home", 0, 0, -1, -1, -1, 0, 0, [], 0]

    def test_castle_family_reads_id_owner_and_name(self):
        area = MovementArea.model_validate(self.CASTLE)
        assert (area.object_id, area.owner_id, area.name) == (16654596, 17743260, "Home")

    def test_kings_tower_name_is_at_seven(self):
        area = MovementArea.model_validate([23, 10, 20, 55, 7, 1, 30, "Tower"])
        assert (area.object_id, area.owner_id, area.name) == (55, 7, "Tower")

    def test_monument_name_is_at_nine(self):
        area = MovementArea.model_validate([26, 10, 20, 56, 7, 2, 5, 1, 30, "Monument"])
        assert (area.object_id, area.owner_id, area.name) == (56, 7, "Monument")

    def test_village_has_no_name(self):
        area = MovementArea.model_validate([10, 10, 20, 57, 7, 3, 0, 30])
        assert (area.object_id, area.owner_id, area.name) == (57, 7, "")

    def test_faction_targets_keep_the_owner_at_three(self):
        area = MovementArea.model_validate([17, 10, 20, 900, 0, [], 30, 5])
        assert (area.object_id, area.owner_id, area.name) == (None, 900, "")

    def test_npc_camp_reads_nothing_past_the_position(self):
        # Live capture of a robber baron camp
        area = MovementArea.model_validate([2, 630, 243, -1, 0, -1, 0])
        assert (area.x, area.y) == (630, 243)
        assert (area.object_id, area.owner_id, area.name) == (None, None, "")

    def test_relocating_castle_row_reads_nothing(self):
        area = MovementArea.model_validate([1, 10, 20, 17743260])
        assert (area.object_id, area.owner_id, area.name) == (None, None, "")
