"""GameState castle pushes: units received (rue), the open-gate reset (kik), the joined area (jaa),
its mines (gsm, cmr), resource carts (rci, rcc), slum level (csl), builder discount (gab), and
the building callbacks (fbe, cbx, gdb, gcb)."""

import threading
from typing import Any

import pytest
from pydantic import ValidationError

from empire_core.castle.models.updates import BuildingEfficiencyChanged, BuildingFinished, BuildingXP, DamagedBuildings
from empire_core.enums import Kingdom, ResourceCartType
from empire_core.state.manager import GameState
from empire_core.state.models import JoinedArea
from tests.service_helpers import make_client, xt_packet
from tests.state.state_helpers import gcl_payload


def settle(state: GameState) -> None:
    """Wait until every callback queued so far has run."""
    done = threading.Event()
    state._dispatch_callback(done.set)
    assert done.wait(5)


def login(state: GameState, *, kingdom: int = 0, entry: dict[str, Any] | None = None) -> None:
    section = gcl_payload([(1, "Main")], kingdom=kingdom)
    if entry:
        section["C"][0]["AI"][0].update(entry)
    state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": section})


def jaa_payload(**blocks: Any) -> dict[str, Any]:
    """A jaa reply for castle 1 at (10, 20), as JAACommand reads it."""
    return {"KID": 0, "T": 1, "gca": {"A": [1, 10, 20, 1, 7, 1, 1, 1, 0, 0, "Main"], "BD": []}, **blocks}


MINES = {"M": [{"OID": 42, "RC": 3, "NC": 600}, {"OID": 43, "RC": 0, "NC": -1}]}
CARTS = {"RC": [{"RT": 0, "A": 10, "RS": 3600}, {"RT": 1, "A": 20, "RS": 0}, {"RT": 2, "A": 0, "RS": 90}]}
ROW = [101, 5, 3, 4, 0, 0, 0, 60, 0, 100, 1]


class TestUnitsReceived:
    # CastleUserCastleListDetailed.parse_rue: getVObyCastleID(AID, SID), then setUnit(WID, NUA)

    def test_rue_sets_the_castles_count_of_the_unit(self, state):
        login(state)
        state.update_from_packet("dcl", {"C": [{"KID": 0, "AI": [{"AID": 1, "AC": [[620, 5], [621, 3]]}]}]})

        state.update_from_packet("rue", {"AID": 1, "SID": 0, "WID": 620, "NUA": 12})
        state.update_from_packet("rue", {"AID": "1", "SID": "0", "WID": "622", "NUA": "4"})

        assert state.get_castles()[0].units == {620: 12, 621: 3, 622: 4}
        assert state.get_last_packet_time("rue") is not None

    def test_a_count_of_zero_or_below_drops_the_unit(self, state):
        # UnitInventoryDictionary.setUnit: t<=0 deletes the entry
        login(state)
        state.update_from_packet("dcl", {"C": [{"KID": 0, "AI": [{"AID": 1, "AC": [[620, 5], [621, 3]]}]}]})

        state.update_from_packet("rue", {"AID": 1, "SID": 0, "WID": 620, "NUA": 0})

        assert state.get_castles()[0].units == {621: 3}

    def test_sid_is_the_castles_kingdom(self, state):
        login(state, kingdom=2)

        state.update_from_packet("rue", {"AID": 1, "SID": 0, "WID": 620, "NUA": 5})
        assert state.get_castles()[0].units == {}

        state.update_from_packet("rue", {"AID": 1, "SID": 2, "WID": 620, "NUA": 5})
        assert state.get_castles()[0].units == {620: 5}

    def test_the_units_are_swapped_not_edited(self, state):
        login(state)
        state.update_from_packet("rue", {"AID": 1, "SID": 0, "WID": 620, "NUA": 5})
        reader_view = state.get_castles()[0].units

        state.update_from_packet("rue", {"AID": 1, "SID": 0, "WID": 620, "NUA": 9})

        assert reader_view == {620: 5}
        assert state.get_castles()[0].units == {620: 9}

    def test_unknown_castles_and_unreadable_pushes_are_ignored(self, state):
        login(state)

        state.update_from_packet("rue", {"AID": 99, "SID": 0, "WID": 620, "NUA": 5})
        state.update_from_packet("rue", [1, 2])  # type: ignore[arg-type]

        assert state.get_castles()[0].units == {}


class TestOpenGateCounter:
    def test_the_counter_comes_from_the_castle_list_entry(self, state):
        # CastleListVO.parseCastleList: u.OGC&&(d.openGateCounter=int(u.OGC))
        login(state, entry={"OGC": "3"})
        assert state.get_castles()[0].open_gate_counter == 3

        login(state, entry={"OGC": 0})
        assert state.get_castles()[0].open_gate_counter == 0

    def test_a_monday_kik_resets_every_counter(self, state):
        # KIKCommand: i.DOW==TimeConst.MONDAY (2) resets the counters
        login(state, entry={"OGC": 2})
        castle = state.get_castles()[0]

        state.update_from_packet("kik", {"DOW": 3})
        assert castle.open_gate_counter == 2

        state.update_from_packet("kik", {"DOW": "2"})
        assert castle.open_gate_counter == 0
        assert state.get_castles()[0] is castle


class TestJoinedArea:
    def test_jaa_records_the_joined_area(self, state):
        assert state.get_joined_area() is None

        state.update_from_packet("jaa", jaa_payload(csl={"SL": 2}, gab={"B": 5}))

        assert state.get_joined_area() == JoinedArea(
            kingdom_id=Kingdom.GREEN, castle_id=1, slum_level=2, builder_discount=5
        )
        assert state.get_last_packet_time("csl") is not None
        assert state.get_last_packet_time("gab") is not None

    def test_a_jaa_without_csl_or_gab_has_the_defaults(self, state):
        # AreaDataSlum starts at -1, AreaDataCommonInfo's builder discount at 0
        state.update_from_packet("jaa", jaa_payload())

        area = state.get_joined_area()
        assert (area.slum_level, area.builder_discount) == (-1, 0)
        assert state.get_last_packet_time("csl") is None

    def test_csl_and_gab_update_the_joined_area(self, state):
        state.update_from_packet("jaa", jaa_payload())
        before = state.get_joined_area()

        state.update_from_packet("csl", {"SL": 3})
        state.update_from_packet("gab", {"B": 10})

        assert (before.slum_level, before.builder_discount) == (-1, 0)
        area = state.get_joined_area()
        assert (area.castle_id, area.slum_level, area.builder_discount) == (1, 3, 10)

    def test_csl_and_gab_before_any_join_are_dropped(self, state):
        state.update_from_packet("csl", {"SL": 3})
        state.update_from_packet("gab", {"B": 10})

        assert state.get_joined_area() is None

    def test_a_map_read_drops_only_the_mines(self, state):
        # SwitchToWorldmapCommand destroys mineData; the active area and the carts stay, a refused gaa too
        state.update_from_packet("jaa", jaa_payload(gsm=MINES, rci=CARTS))
        carts = state.get_resource_carts()

        state.update_from_packet("gaa", {"KID": 0, "AI": [], "OI": []}, 1)
        state.update_from_packet("csl", {"SL": 3})

        assert state.get_mines() == {}
        area = state.get_joined_area()
        assert (area.castle_id, area.slum_level) == (1, 3)
        assert state.get_resource_carts() == carts
        assert state.get_last_packet_time("gaa") is not None

    def test_a_join_after_a_map_read_fills_the_mines_again(self, state):
        state.update_from_packet("jaa", jaa_payload(gsm=MINES))
        state.update_from_packet("gaa", {"KID": 0, "AI": [], "OI": []})

        state.update_from_packet("jaa", jaa_payload(gsm=MINES))

        assert sorted(state.get_mines()) == [42, 43]

    def test_mines_and_carts_are_read_only(self, state):
        state.update_from_packet("jaa", jaa_payload(gsm=MINES, rci=CARTS))
        with pytest.raises(ValidationError):
            state.get_mines()[42].next_collect_seconds = 0
        with pytest.raises(ValidationError):
            state.get_resource_carts()[0].amount = 0

    def test_reset_forgets_the_joined_area_mines_and_carts(self, state):
        state.update_from_packet("jaa", jaa_payload(gsm=MINES, rci=CARTS))

        state.reset()

        assert (state.get_joined_area(), state.get_mines(), state.get_resource_carts()) == (None, {}, [])
        assert state.get_last_packet_time("gsm") is None


class TestMines:
    def test_a_gsm_push_replaces_every_mine(self, state):
        # CastleMineData.parse_GSM: existingMines=new Map, keyed by OID
        state.update_from_packet("gsm", MINES)
        state.update_from_packet("gsm", {"M": [{"OID": 43, "RC": 5, "NC": 30}]})

        mines = state.get_mines()
        assert list(mines) == [43]
        assert (mines[43].remaining_collection_amount, mines[43].next_collect_seconds) == (5, 30)
        assert state.get_last_packet_time("gsm") is not None

    def test_the_jaa_and_cmr_replies_carry_them(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcu": {"C1": 100, "C2": 5}})
        state.update_from_packet("jaa", jaa_payload(gsm=MINES))
        assert sorted(state.get_mines()) == [42, 43]

        collected = {"M": [{"OID": 42, "RC": 2, "NC": 3600, "C1": 250}]}
        state.update_from_packet("cmr", {"gsm": collected, "gcu": {"C1": 350}})

        assert state.get_mines()[42].coins == 250
        assert state.get_local_player().coins == 350

    def test_a_jaa_without_gsm_keeps_the_mines(self, state):
        # JAACommand: i.gsm&&parse_GSM(i.gsm)
        state.update_from_packet("gsm", MINES)

        state.update_from_packet("jaa", jaa_payload())

        assert sorted(state.get_mines()) == [42, 43]

    def test_a_cmr_without_gsm_applies_nothing(self, state):
        # CMRCommand calls parse_GSM(i.gsm), which throws on undefined before parseGCU
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcu": {"C1": 100}})

        state.update_from_packet("cmr", {"gcu": {"C1": 350}})

        assert state.get_local_player().coins == 100
        assert state.get_mines() == {}

    def test_the_mines_are_a_copy(self, state):
        state.update_from_packet("gsm", MINES)
        held = state.get_mines()

        state.update_from_packet("gsm", {"M": []})

        assert sorted(held) == [42, 43]
        assert state.get_mines() == {}


class TestResourceCarts:
    def test_an_rci_push_replaces_the_carts(self, state):
        state.update_from_packet("rci", CARTS)

        carts = state.get_resource_carts()
        assert [(cart.cart_type, cart.amount, cart.remaining_seconds) for cart in carts] == [
            (ResourceCartType.WOOD, 10, 3600),
            (ResourceCartType.STONE, 20, 0),
            (ResourceCartType.FOOD, 0, 90),
        ]
        assert state.get_resource_cart(ResourceCartType.STONE).amount == 20
        assert state.get_last_packet_time("rci") is not None

    def test_the_jaa_and_rcc_replies_carry_them(self, state):
        state.update_from_packet("jaa", jaa_payload(rci=CARTS))
        assert len(state.get_resource_carts()) == 3

        collected = {"RC": [{"RT": 0, "A": 0, "RS": 7200}, *CARTS["RC"][1:]]}
        state.update_from_packet("rcc", {"RT": 0, "A": 10, "rci": collected})

        assert state.get_resource_cart(ResourceCartType.WOOD).remaining_seconds == 7200

    def test_only_the_first_three_are_read(self, state):
        # CastleResourceCartsData.parse_RCI reads RC[0] to RC[2]
        state.update_from_packet("rci", {"RC": [*CARTS["RC"], {"RT": 0, "A": 99, "RS": 0}]})

        assert [cart.amount for cart in state.get_resource_carts()] == [10, 20, 0]

    def test_an_unreadable_cart_moves_no_other(self, state):
        state.update_from_packet("rci", {"RC": [CARTS["RC"][0], None, CARTS["RC"][2]]})

        assert state.get_resource_cart(ResourceCartType.STONE) is None
        assert state.get_resource_cart(ResourceCartType.FOOD).remaining_seconds == 90

    def test_no_cart_before_any_rci(self, state):
        assert state.get_resource_carts() == []
        assert state.get_resource_cart(ResourceCartType.FOOD) is None


class TestBuildingCallbacks:
    def test_fbe_and_cbx_report_the_building_and_its_xp(self, state):
        # FBECommand and CBXCommand: parseCBX(OID, XP) -> onGainedBuildingPoints
        finished: list[BuildingFinished] = []
        gained: list[BuildingXP] = []
        state.on_building_finished(finished.append)
        state.on_building_xp(gained.append)

        state.update_from_packet("fbe", {"OID": 5, "XP": 120})
        state.update_from_packet("cbx", {"OID": 6, "XP": 40})
        settle(state)

        assert [(event.object_id, event.xp) for event in finished] == [(5, 120)]
        assert [(event.object_id, event.xp) for event in gained] == [(6, 40)]
        assert type(gained[0]) is BuildingXP

    def test_gdb_and_gcb_report_the_changed_rows(self, state):
        # GDBCommand and GCBCommand: updateMultipleObjectInfos(e.B); a row may be wrapped as {"O": row}
        changed: list[DamagedBuildings] = []
        state.on_buildings_changed(changed.append)

        state.update_from_packet("gdb", {"B": [ROW]})
        state.update_from_packet("gcb", {"B": [{"O": [*ROW[:9], 50, 0]}]})
        settle(state)

        assert [type(event) for event in changed] == [DamagedBuildings, BuildingEfficiencyChanged]
        assert changed[0].buildings[0].hit_points == 60
        assert changed[1].buildings[0].efficiency == 50

    def test_a_removed_callback_no_longer_fires(self, state):
        seen: list[object] = []
        state.on_building_finished(seen.append)
        state.on_building_xp(seen.append)
        state.on_buildings_changed(seen.append)
        state.on_building_finished.remove(seen.append)
        state.on_building_xp.remove(seen.append)
        state.on_buildings_changed.remove(seen.append)

        state.update_from_packet("fbe", {"OID": 5, "XP": 1})
        state.update_from_packet("cbx", {"OID": 5, "XP": 1})
        state.update_from_packet("gdb", {"B": [ROW]})
        settle(state)

        assert seen == []


class TestRefusedReplies:
    def test_a_refused_castle_push_or_reply_is_not_applied(self):
        # Each of these commands parses only on ALL_OK
        client = make_client(state=GameState())  # type: ignore[arg-type]
        state = client.state
        login(state)
        seen: list[object] = []
        state.on_building_finished(seen.append)

        client._on_packet(xt_packet("rue", {"AID": 1, "SID": 0, "WID": 620, "NUA": 5}, error_code=1))
        client._on_packet(xt_packet("gsm", MINES, error_code=1))
        client._on_packet(xt_packet("rci", CARTS, error_code=1))
        client._on_packet(xt_packet("jaa", jaa_payload(), error_code=1))
        client._on_packet(xt_packet("fbe", {"OID": 5, "XP": 1}, error_code=1))
        settle(state)

        assert state.get_castles()[0].units == {}
        assert (state.get_mines(), state.get_resource_carts(), state.get_joined_area(), seen) == ({}, [], None, [])
        assert state.get_last_packet_time("jaa") is None
