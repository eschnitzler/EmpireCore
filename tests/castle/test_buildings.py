"""Buildings, the construction list, the gca block, jaa and the building commands."""

from __future__ import annotations

from typing import Any

import pytest

from empire_core.castle.models.actions import JoinAreaRequest, SelectCastleResponse
from empire_core.castle.models.buildings import (
    BuildRequest,
    BuildResponse,
    BuyExtensionRequest,
    BuyExtensionResponse,
    CollectExtensionGiftRequest,
    CollectExtensionGiftResponse,
    DestroyBuildingRequest,
    DestroyBuildingResponse,
    FastCompleteRequest,
    FastCompleteResponse,
    MoveBuildingRequest,
    MoveBuildingResponse,
    RepairAllRequest,
    RepairAllResponse,
    RepairBuildingRequest,
    RepairBuildingResponse,
    SellBuildingRequest,
    SellBuildingResponse,
    TimeSkipBuildingRequest,
    TimeSkipBuildingResponse,
    UpgradeBuildingRequest,
    UpgradeBuildingResponse,
    UpgradeWallRequest,
    UpgradeWallResponse,
)
from empire_core.castle.models.objects import (
    BuildingRow,
    CastleBuildings,
    ConstructionList,
    ShowConstructionListRequest,
)
from empire_core.enums import BuildingState, ExpansionType, Kingdom, MapItemType
from empire_core.exceptions import CommandError, GameDataNotLoadedError, UnknownCastleError
from empire_core.gamedata import ConstructionItem, Currency, GameData
from empire_core.protocol.models import parse_response
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, stub_player, xt_packet

# wod 101, object 5 at (10, 12), rotation 0, 30 s done, building (2), 100 hp,
# boost 150, efficiency 100, damage 0, production speed 55, district 0 slot 0, upgrading to 102
FULL_ROW = [101, 5, 10, 12, 0, 30, 2, 100, 150, 100, 0, 55, 0, 0, 0, 0, 102]


# =============================================================================
# BuildingRow
# =============================================================================


class TestBuildingRow:
    def test_a_full_row(self):
        row = BuildingRow.from_list(FULL_ROW)
        assert (row.wod_id, row.object_id, row.x, row.y, row.rotation) == (101, 5, 10, 12, 0)
        assert (row.construction_completed_seconds, row.state, row.hit_points) == (
            30,
            BuildingState.BUILD_IN_PROGRESS,
            100,
        )
        assert (row.construction_boost_at_start, row.efficiency, row.damage_type) == (1.5, 100, 0)
        assert (row.district_id, row.district_slot_id, row.upgrade_target_wod_id) == (0, 0, 102)

    def test_a_wrapped_row(self):
        # IsoHelperData.createIsoObjectVOByServer reads e.O when there is one
        assert BuildingRow.from_list({"O": FULL_ROW}).object_id == 5

    def test_a_row_without_upgrade_target_or_damage_type(self):
        row = BuildingRow.from_list(FULL_ROW[:10])
        # ABasicBuildingVO: damage type 0 when absent, upgrade target -1 when absent
        assert (row.damage_type, row.upgrade_target_wod_id, row.efficiency) == (0, -1, 100)

    def test_a_row_that_ends_before_the_building_fields(self):
        row = BuildingRow.from_list([7, 3, 1, 2, 1])
        assert (row.wod_id, row.object_id, row.x, row.y, row.rotation) == (7, 3, 1, 2, 1)
        assert (row.state, row.hit_points, row.construction_completed_seconds) == (None, None, None)

    def test_a_building_in_a_district_reads_rotation_1(self):
        # AIsoObjectVO.parseServerObject: rotation is 1 inside a district
        row = FULL_ROW[:14] + [900, 3, 102]
        parsed = BuildingRow.from_list(row)
        assert (parsed.district_id, parsed.district_slot_id, parsed.rotation, parsed.is_in_district) == (
            900,
            3,
            1,
            True,
        )

    def test_an_unknown_state_reads_as_initial(self):
        # IsoBuildingStateEnum.getTypeById falls back to INITIAL
        row = list(FULL_ROW)
        row[6] = 3
        assert BuildingRow.from_list(row).state is BuildingState.INITIAL

    @pytest.mark.parametrize("bad", [None, [], {}, {"O": None}, "row"])
    def test_not_a_row(self, bad: Any):
        with pytest.raises(ValueError):
            BuildingRow.from_list(bad)


# =============================================================================
# scl / gca
# =============================================================================


class TestConstructionList:
    def test_slots(self):
        slots = ConstructionList.model_validate({"OIDL": [5, -1, -2, "9"], "SSC": 2})
        assert ([slot.object_id for slot in slots.slots], slots.slot_count) == ([5, -1, -2, 9], 2)
        assert (slots.free_slots, slots.building_object_ids) == (1, [5, 9])
        # ConstructionSlotVO: free at -1, locked at -2, waiting from the slot count on
        assert [(slot.is_free, slot.is_locked, slot.is_waiting) for slot in slots.slots] == [
            (False, False, False),
            (True, False, False),
            (False, True, True),
            (False, False, True),
        ]
        assert [slot.position for slot in slots.slots] == [0, 1, 2, 3]

    def test_the_slot_count_defaults_to_1(self):
        # AreaDataConstructionList.parseSCL: e.SSC ? e.SSC : 1
        assert ConstructionList.model_validate({"OIDL": [-1]}).slot_count == 1
        assert ConstructionList.model_validate({"OIDL": [], "SSC": 0}).slot_count == 1

    def test_the_request_sends_nothing(self):
        assert ShowConstructionListRequest().to_payload() == {}

    def test_get_build_queue(self):
        client = make_client({"scl": xt_packet("scl", {"OIDL": [5, -1], "SSC": 2})})
        queue = client.castle.get_build_queue()
        assert conn(client).request_payloads == [("scl", {})]
        assert (queue.building_object_ids, queue.slot_count) == ([5], 2)


GCA = {
    "BD": [FULL_ROW, [202, 6, 1, 1, 0, 0, 4, 100, 0, 100], None, "junk"],
    "D": [[301, 7, 0, 0, 0, 0, 4, 100, 0, 100]],
    "G": [[302, 8, 0, 0, 0, 0, 4, 100, 0, 100]],
    "T": [[303, 9, 0, 0, 0, 0, 4, 100, 0, 100], [303, 10, 0, 0, 0, 0, 4, 100, 0, 100]],
    "BG": [[1, 11, 0, 0, 0]],
    "FP": [],
    "scl": {"OIDL": [5, -1]},
    "CI": [],
    "RAW": 120,
    "RAF": "80",
    "A": [1, 10, 20, 555],
    "O": {"OID": 42},
}


class TestCastleBuildings:
    def test_every_group(self):
        castle = CastleBuildings.model_validate(GCA)
        # The null and the non-row entry cost only themselves
        assert [b.object_id for b in castle.buildings] == [5, 6]
        assert ([w.wod_id for w in castle.walls], [g.wod_id for g in castle.gates]) == ([301], [302])
        assert [t.object_id for t in castle.towers] == [9, 10]
        assert [g.object_id for g in castle.grounds] == [11]
        assert castle.fixed_positions == []
        assert castle.construction_list is not None and castle.construction_list.building_object_ids == [5]
        # AreaDataStorageItem.parseGCA: RA<key> through int()
        assert (castle.field_efficiency.wood, castle.field_efficiency.food, castle.field_efficiency.stone) == (
            120,
            80,
            0,
        )
        assert castle.find(9) is not None and castle.find(99) is None
        assert len(castle.all_objects()) == 7
        assert castle.construction_items == ()

    def test_construction_items_by_building(self):
        # ABasicBuildingVO.parseConstructionItems (bundle lines 18000-18010): OID, then CIL entries of CID, S and RS
        castle = CastleBuildings.model_validate(
            {"CI": [{"OID": 5, "CIL": [{"CID": 1, "S": 0}, {"CID": 9999999, "S": "2", "RS": 3600}, "junk"]}, None]}
        )
        (building,) = castle.construction_items
        assert building.object_id == 5
        assert [(item.construction_item_id, item.slot, item.remaining_seconds) for item in building.items] == [
            (ConstructionItem(1), 0, 0),
            (9999999, 2, 3600),
        ]
        assert isinstance(building.items[0].construction_item_id, ConstructionItem)


# =============================================================================
# jaa
# =============================================================================


JAA = {
    "KID": 2,
    "T": 1,
    "gca": GCA,
    "grc": {"AID": 555, "KID": 2, "W": 100.5, "S": 50},
    "gpa": {"P": 80, "DW": 100, "RFPPA": 0.4},
    "gui": {"I": []},
    "spl0": {},
}


class TestJoinCastle:
    def test_jaa_carries_buildings_resources_and_production(self):
        joined = parse_response("jaa", JAA)
        assert isinstance(joined, SelectCastleResponse)
        assert (joined.kingdom_id, joined.area_type) == (2, MapItemType.CASTLE)
        assert joined.buildings is not None and [b.object_id for b in joined.buildings.buildings] == [5, 6]
        assert joined.resources is not None and (joined.resources.castle_id, joined.resources.wood) == (555, 100)
        assert joined.production_area is not None and joined.production_area.faction_buff == 0.4

    def test_a_jaa_without_blocks(self):
        joined = SelectCastleResponse.model_validate({"KID": 0, "T": 999, "gca": "x"})
        assert (joined.area_type, joined.buildings, joined.resources, joined.production_area) == (
            None,
            None,
            None,
            None,
        )

    def test_join_returns_the_castle_state(self):
        client = make_client({"jaa": xt_packet("jaa", JAA)}, castles=[(555, Kingdom.ICE)])
        joined = client.castle.join(555)
        assert conn(client).request_payloads == [("jaa", {"CID": 555, "KID": 2})]
        assert joined.buildings is not None


# The blocks a live server answered an own outpost's jaa by position with, values made up.
OUTPOST_JAA: dict[str, Any] = {
    "KID": 0,
    "T": 4,
    "gca": {**GCA, "O": {"OID": 1001}, "A": [4, 512, 256, 2002]},
    "grc": {"AID": 2002, "W": 800.0, "S": 800.0, "F": 1500.0, "C": 0.0, "KID": 0},
    "gpa": {"P": 40, "DW": 900, "WM": 20.0, "RFPPA": 0.0},
    "gui": {"I": [[277, 2]], "SHI": [], "HI": [], "TU": []},
    "uap": {"KID": 0, "NS": -1, "PMS": -1, "PMT": 0},
    "csl": {"SL": -1},
    "gab": {"B": 0.0},
    "hin": {"FB": 25, "WSR": -75},
    "sin": [],
    "abpi": [],
    "crai": {"CAI": {"CBI": [], "CE": []}},
    **{f"spl{i}": {"PS": {}, "QS": [], "RM": 0, "TCT": 0, "LID": i} for i in range(4)},
}


class TestJoinArea:
    def test_request_keys_follow_the_client(self):
        # C2SJoinAreaVO sets PX, PY, KID
        request = JoinAreaRequest(x=5, y=6, kingdom_id=Kingdom.ICE)
        assert (request.get_command(), request.get_response_command()) == ("jaa", "jaa")
        assert list(request.to_payload().items()) == [("PX", 5), ("PY", 6), ("KID", 2)]

    def test_join_area_returns_the_outposts_state(self):
        client = make_client({"jaa": xt_packet("jaa", OUTPOST_JAA)})

        joined = client.castle.join_area(512, 256)

        assert conn(client).request_payloads == [("jaa", {"PX": 512, "PY": 256, "KID": 0})]
        assert (joined.kingdom_id, joined.area_type) == (0, MapItemType.OUTPOST)
        assert joined.buildings is not None and [b.object_id for b in joined.buildings.buildings] == [5, 6]
        assert joined.resources is not None and (joined.resources.castle_id, joined.resources.food) == (2002, 1500)
        assert joined.production_area is not None and joined.production_area.population == 40

    def test_a_kingdom_castle_by_position(self):
        client = make_client(
            {"jaa": xt_packet("jaa", {**OUTPOST_JAA, "KID": 1, "T": 12, "gca": {**GCA, "A": [12, 510, 257, 2003]}})}
        )

        joined = client.castle.join_area(510, 257, Kingdom.SANDS)

        assert conn(client).request_payloads == [("jaa", {"PX": 510, "PY": 257, "KID": 1})]
        assert (joined.kingdom_id, joined.area_type) == (1, MapItemType.KINGDOM_CASTLE)

    def test_an_object_the_client_never_joins_raises(self):
        client = make_client({"jaa": xt_packet("jaa", error_code=6)})
        with pytest.raises(CommandError) as raised:
            client.castle.join_area(509, 255)
        assert raised.value.code == 6


# =============================================================================
# Building requests, keys and order as the client's VOs build them
# =============================================================================


@pytest.mark.parametrize(
    ("request_model", "expected"),
    [
        # C2SIsoBuyObjectVO: PWR is initialised before PO
        (
            BuildRequest(wod_id=101, x=5, y=6, rotation=1),
            {"WID": 101, "X": 5, "Y": 6, "R": 1, "PWR": 0, "PO": -1, "DOID": -1},
        ),
        (
            BuildRequest(wod_id=101, x=-1, y=-1, pay_with_rubies=True, private_offer_id=7, district_object_id=99),
            {"WID": 101, "X": -1, "Y": -1, "R": 0, "PWR": 1, "PO": 7, "DOID": 99},
        ),
        (UpgradeBuildingRequest(object_id=42), {"OID": 42, "PWR": 0, "PO": -1}),
        (
            UpgradeBuildingRequest(object_id=42, pay_with_rubies=True, private_offer_id=7),
            {"OID": 42, "PWR": 1, "PO": 7},
        ),
        (MoveBuildingRequest(object_id=42, x=3, y=4, rotation=1), {"OID": 42, "X": 3, "Y": 4, "R": 1}),
        (SellBuildingRequest(object_id=42), {"OID": 42}),
        (DestroyBuildingRequest(object_id=42), {"OID": 42}),
        (FastCompleteRequest(object_id=42), {"OID": 42, "FS": 0}),
        # C2SMinuteSkipBuildingVO: OID is initialised, MST set after it
        (TimeSkipBuildingRequest(object_id=42, minute_skip=Currency.SKIP_5_MINUTES), {"OID": 42, "MST": "MS2"}),
        (UpgradeWallRequest(object_id=42), {"OID": 42, "PO": -1, "PWR": 0}),
        (RepairBuildingRequest(object_id=42), {"OID": 42, "PO": -1, "PWR": 0}),
        (RepairAllRequest(), {}),
        (BuyExtensionRequest(x=3, y=4), {"X": 3, "Y": 4, "R": 0, "CT": 1}),
        (CollectExtensionGiftRequest(object_id=42), {"OID": 42}),
    ],
)
def test_building_requests_match_the_client(request_model: Any, expected: dict[str, Any]):
    payload = request_model.to_payload()
    assert payload == expected
    assert list(payload) == list(expected)


# =============================================================================
# Building replies
# =============================================================================


ROW = [202, 6, 1, 1, 0, 60, 13, 100, 0, 100]


class TestBuildingReplies:
    def test_ebu(self):
        reply = parse_response(
            "ebu", {"NO": ROW, "grc": {"AID": 555, "W": 5}, "scl": {"OIDL": [6]}, "gcu": {"C1": 10, "C2": 3}, "sin": {}}
        )
        assert isinstance(reply, BuildResponse)
        assert reply.building is not None and reply.building.object_id == 6
        assert reply.resources is not None and reply.resources.wood == 5
        assert reply.construction_list is not None and [slot.object_id for slot in reply.construction_list.slots] == [6]
        assert reply.currencies is not None and (reply.currencies.coins, reply.currencies.rubies) == (10, 3)

    def test_eup(self):
        reply = parse_response("eup", {"O": [ROW, None], "gcu": {"C1": 1}})
        assert isinstance(reply, UpgradeBuildingResponse)
        assert [b.state for b in reply.buildings] == [BuildingState.UPGRADE_IN_PROGRESS]
        assert reply.resources is None and reply.construction_list is None

    def test_emo(self):
        reply = parse_response("emo", {"MO": ROW})
        assert isinstance(reply, MoveBuildingResponse) and reply.building is not None

    def test_sbd(self):
        reply = parse_response("sbd", {"OID": 6, "gcu": {"C1": 100}})
        assert isinstance(reply, SellBuildingResponse)
        assert reply.object_id == 6 and reply.currencies is not None and reply.currencies.coins == 100

    def test_edo(self):
        reply = parse_response("edo", {"O": ROW, "scl": {"OIDL": [6]}})
        assert isinstance(reply, DestroyBuildingResponse) and reply.building is not None

    def test_fco(self):
        reply = parse_response("fco", {"O": ROW, "gcu": {"C2": 5}})
        assert isinstance(reply, FastCompleteResponse) and reply.building is not None

    def test_msb(self):
        reply = parse_response("msb", {"scl": {"OIDL": [-1], "SSC": 1}})
        assert isinstance(reply, TimeSkipBuildingResponse) and reply.construction_list is not None

    def test_eud(self):
        reply = parse_response("eud", {"N": ROW, "grc": {"AID": 1}})
        assert isinstance(reply, UpgradeWallResponse) and reply.building is not None and reply.resources is not None

    def test_rbu(self):
        reply = parse_response("rbu", {"O": ROW, "scl": {"OIDL": []}, "grc": {}, "gcu": {}})
        assert isinstance(reply, RepairBuildingResponse) and reply.building is not None

    def test_ira(self):
        reply = parse_response("ira", {"gpa": {"P": 5}, "B": [ROW, ROW], "gcu": {"C2": 1}})
        assert isinstance(reply, RepairAllResponse)
        assert reply.production_area is not None and reply.production_area.population == 5
        assert len(reply.buildings) == 2

    def test_ebe(self):
        reply = parse_response("ebe", {"gca": GCA, "grc": {"AID": 1}, "scl": {"OIDL": []}, "gcu": {}})
        assert isinstance(reply, BuyExtensionResponse)
        assert reply.castle_buildings is not None and len(reply.castle_buildings.towers) == 2

    def test_etc(self):
        reply = parse_response("etc", {"RID": "77", "OID": 12})
        assert isinstance(reply, CollectExtensionGiftResponse) and (reply.reward_id, reply.object_id) == (77, 12)

    def test_an_unreadable_row_is_none(self):
        assert BuildResponse.model_validate({"NO": "junk", "grc": 5}).building is None


# =============================================================================
# Service
# =============================================================================


# 101 builds in 600 s and upgrades for free to 102 (1000 s); 103 upgrades to 104 for rubies;
# 105 costs rubies to build; 106 costs rubies only at player level 2 (its low level costs are
# 0, 20, -1); 107 upgrades to 108, which costs 30 rubies at player level 2 only; 109 upgrades to 110
BUILDING_ITEMS = {
    "buildings": [
        {"wodID": "101", "name": "Dwelling", "upgradeWodID": "102", "buildDuration": "600"},
        {"wodID": "102", "name": "Dwelling", "buildDuration": "1000"},
        {"wodID": "103", "name": "Tower", "upgradeWodID": "104"},
        {"wodID": "104", "name": "Tower", "costC2": "500"},
        {"wodID": "105", "name": "Decoration", "costC2": "900"},
        {"wodID": "106", "name": "Dwelling", "lowLevelMainCastleCostC2": "0,20,-1"},
        {"wodID": "107", "name": "Dwelling", "upgradeWodID": "108"},
        {"wodID": "108", "name": "Dwelling", "lowLevelMainCastleCostC2": "0,30"},
        {"wodID": "109", "name": "Tower", "upgradeWodID": "110"},
        {"wodID": "110", "name": "Tower"},
    ]
}


def row(wod_id: int, object_id: int, done: int = 0, state: int = 4, boost: int = 100, target: int = -1) -> list:
    """A gca building row: index 5 the seconds done, 6 the state, 8 the boost times 100, 16 the upgrade target."""
    return [wod_id, object_id, 1, 1, 0, done, state, 100, boost, 100, 0, 0, 0, 0, 0, 0, target]


JOINED_CASTLE = {
    "KID": 0,
    "gca": {
        "BD": [
            row(101, 42),
            row(103, 43),
            row(101, 44, done=360, state=2),  # 600 - 360 = 240 s left
            row(101, 45, done=0, state=2),  # just started, 600 s left
            row(101, 47, done=300, state=13, boost=200, target=102),  # 1000 / 2 - 300 = 200 s left
            row(107, 48),
            row(109, 49, state=13, target=104),  # upgrading to 104, not to its upgradeWodID
            row(101, 50, done=10, state=10),  # repairing: the time left is not worked out
            row(110, 51),  # the last level
        ]
    },
}
JOIN = ("jaa", {"CID": 12345, "KID": 0})


def building_client(script: dict[str, Any] | None = None, level: int = 5) -> Any:
    client = make_client({"jaa": xt_packet("jaa", JOINED_CASTLE), **(script or {})}, castles=[(12345, Kingdom.GREEN)])
    client.state.local_player = stub_player(level=level)
    client.game_data = GameData.parse("test", BUILDING_ITEMS)
    return client


class TestBuildingService:
    @pytest.mark.parametrize(
        ("call", "sent"),
        [
            (
                lambda c: c.castle.build(101, 5, 6),
                [("ebu", {"WID": 101, "X": 5, "Y": 6, "R": 0, "PWR": 0, "PO": -1, "DOID": -1})],
            ),
            (
                lambda c: c.castle.build(105, 5, 6, spend_rubies=True),
                [("ebu", {"WID": 105, "X": 5, "Y": 6, "R": 0, "PWR": 1, "PO": -1, "DOID": -1})],
            ),
            (lambda c: c.castle.upgrade_building(12345, 42), [JOIN, ("eup", {"OID": 42, "PWR": 0, "PO": -1})]),
            (lambda c: c.castle.upgrade_building(12345, 48), [JOIN, ("eup", {"OID": 48, "PWR": 0, "PO": -1})]),
            (
                lambda c: c.castle.upgrade_building(12345, 43, spend_rubies=True),
                [JOIN, ("eup", {"OID": 43, "PWR": 1, "PO": -1})],
            ),
            (lambda c: c.castle.move_building(42, 3, 4, 1), [("emo", {"OID": 42, "X": 3, "Y": 4, "R": 1})]),
            (lambda c: c.castle.sell_decoration(42), [("sbd", {"OID": 42})]),
            (lambda c: c.castle.destroy_building(42), [("edo", {"OID": 42})]),
            (lambda c: c.castle.finish_construction(12345, 44), [JOIN, ("fco", {"OID": 44, "FS": 1})]),
            (lambda c: c.castle.finish_construction(12345, 47), [JOIN, ("fco", {"OID": 47, "FS": 1})]),
            (
                lambda c: c.castle.finish_construction(12345, 45, spend_rubies=True),
                [JOIN, ("fco", {"OID": 45, "FS": 0})],
            ),
            (
                lambda c: c.castle.skip_construction_time(42, Currency.SKIP_10_MINUTES),
                [("msb", {"OID": 42, "MST": "MS3"})],
            ),
            (lambda c: c.castle.upgrade_defense(12345, 42), [JOIN, ("eud", {"OID": 42, "PO": -1, "PWR": 0})]),
            (lambda c: c.castle.repair_building(42), [("rbu", {"OID": 42, "PO": -1, "PWR": 0})]),
            (lambda c: c.castle.repair_building(42, spend_rubies=True), [("rbu", {"OID": 42, "PO": -1, "PWR": 1})]),
            (lambda c: c.castle.repair_all(spend_rubies=True), [("ira", {})]),
            (lambda c: c.castle.buy_expansion(3, 4), [("ebe", {"X": 3, "Y": 4, "R": 0, "CT": 1})]),
            (
                lambda c: c.castle.buy_expansion(3, 4, expansion_type=ExpansionType.PREMIUM, spend_rubies=True),
                [("ebe", {"X": 3, "Y": 4, "R": 0, "CT": 0})],
            ),
            (lambda c: c.castle.open_treasure_chest(42), [("etc", {"OID": 42})]),
        ],
    )
    def test_actions_send_the_client_payload(self, call: Any, sent: list[tuple[str, dict[str, Any]]]):
        client = building_client()
        assert call(client) is True
        assert conn(client).request_payloads == sent

    @pytest.mark.parametrize(
        ("call", "reason"),
        [
            (lambda c: c.castle.build(105, 5, 6), "900 rubies"),
            (lambda c: c.castle.build(999, 5, 6), "not in the game data"),
            (lambda c: c.castle.upgrade_building(12345, 43), "500 rubies"),
            (lambda c: c.castle.upgrade_defense(12345, 43), "500 rubies"),
            (lambda c: c.castle.upgrade_building(12345, 49), "500 rubies"),
            (lambda c: c.castle.upgrade_building(12345, 46), "not in the castle"),
            (lambda c: c.castle.upgrade_building(12345, 51), "no next level"),
            (lambda c: c.castle.finish_construction(12345, 45), "seconds left"),
            (lambda c: c.castle.finish_construction(12345, 46), "seconds left"),
            (lambda c: c.castle.finish_construction(12345, 50), "seconds left"),
            (lambda c: c.castle.repair_all(), "rubies"),
            (lambda c: c.castle.buy_expansion(3, 4, expansion_type=ExpansionType.PREMIUM), "premium"),
        ],
    )
    def test_a_call_that_spends_rubies_is_refused_before_the_action(self, call: Any, reason: str):
        client = building_client()
        with pytest.raises(ValueError, match=reason):
            call(client)
        assert {command for command, _ in conn(client).request_payloads} <= {"jaa"}

    def test_a_just_started_build_needs_spend_rubies_and_a_nearly_done_one_is_free(self):
        # ABasicBuildingVO.getTimeLeftForBuilding: getBuildDuration() less the seconds done (row index 5)
        client = building_client()
        with pytest.raises(ValueError, match="spend_rubies=True"):
            client.castle.finish_construction(12345, 45)
        assert client.castle.finish_construction(12345, 44) is True
        assert conn(client).request_payloads[-1] == ("fco", {"OID": 44, "FS": 1})

    def test_the_time_left_needs_the_player_level(self):
        # basicBuildDuration reads lowLevelBuildDuration by the player's level
        client = building_client(level=0)
        with pytest.raises(ValueError, match="spend_rubies=True"):
            client.castle.finish_construction(12345, 44)

    def test_the_upgrade_price_follows_the_player_level(self):
        # getUpgradeCostList prices C2 with the next level's costC2, low level branch included
        client = building_client(level=2)
        with pytest.raises(ValueError, match="30 rubies"):
            client.castle.upgrade_building(12345, 48)

    def test_the_build_price_follows_the_player_level(self):
        # ABasicBuildingVO.costC2: the low level cost at the player's level, unless it is -1
        client = building_client()
        client.state.local_player = stub_player(level=1)
        assert client.castle.build(106, 5, 6) is True
        client.state.local_player = stub_player(level=2)
        with pytest.raises(ValueError, match="20 rubies"):
            client.castle.build(106, 5, 6)
        client.state.local_player = stub_player(level=3)
        assert client.castle.build(106, 5, 6) is True

    def test_a_castle_not_yours_raises_before_joining(self):
        client = building_client()
        with pytest.raises(UnknownCastleError):
            client.castle.upgrade_building(777, 42)
        with pytest.raises(UnknownCastleError):
            client.castle.finish_construction(777, 44)
        assert conn(client).request_payloads == []

    def test_pricing_a_building_needs_the_game_data(self):
        client = building_client()
        client.game_data = None
        with pytest.raises(GameDataNotLoadedError):
            client.castle.build(101, 5, 6)
        with pytest.raises(GameDataNotLoadedError):
            client.castle.upgrade_building(12345, 42)
        with pytest.raises(GameDataNotLoadedError):
            client.castle.finish_construction(12345, 44)
        assert conn(client).request_payloads == []

    def test_skip_construction_time_refuses_a_currency_that_is_no_minute_skip(self):
        client = make_client()
        with pytest.raises(ValueError, match="no minute skip"):
            client.castle.skip_construction_time(42, Currency.CONSTRUCTION_TOKEN)
        assert conn(client).request_payloads == []

    def test_skip_construction_time_refuses_a_minute_skip_you_hold_none_of(self):
        # CastleMinuteSkipDialog.showLoaded lists only the skips with an amount above 0
        state = GameState()
        state.update_from_packet("gbd", {"gpi": {"PID": 1, "PN": "me"}})
        state.update_from_packet("sce", [["MS3", 0]])  # type: ignore[arg-type]
        client = make_client(state=state)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="SKIP_10_MINUTES"):
            client.castle.skip_construction_time(42, Currency.SKIP_10_MINUTES)
        assert conn(client).request_payloads == []

    def test_a_rejected_build_is_false(self):
        client = building_client({"ebu": xt_packet("ebu", error_code=21)})
        assert client.castle.build(101, 5, 6) is False
