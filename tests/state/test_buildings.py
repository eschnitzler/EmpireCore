"""GameState keeps the joined castle's placed objects, as the client's IsoUpdaterData does: whole from jaa, gca
and ebe, row by row from the pushes and replies that carry one, and removed by sob, sbd and etc."""

from typing import Any

import pytest

from empire_core.enums import GGEError
from empire_core.state.manager import GameState
from tests.service_helpers import logged_in_state, make_client
from tests.state.state_helpers import later

AREA_ROW = [1, 10, 20, 1, 7, 1, 1, 1, 0, 0, "Main"]
# Rows as AIsoObjectVO and ABasicBuildingVO read them: wod id, object id, x, y, rotation, then the building fields
WOODCUTTER = [101, 5, 3, 4, 0, 0, 0, 100, 0, 100, 0]
WALL = [1600, 20, 0, 0, 0, 0, 0, 100, 0, 100, 0]
GATE = [1700, 21, 0, 0, 0, 0, 0, 100, 0, 100, 0]
TOWER = [1800, 22, 0, 0, 0, 0, 0, 100, 0, 100, 0]
GROUND = [2, 30, 0, 0, 0]
MOVED = [102, 5, 6, 7, 0]


def castle(**groups: list[list[Any]]) -> dict[str, Any]:
    return {"A": AREA_ROW, "BD": [WOODCUTTER], "D": [WALL], "G": [GATE], "T": [TOWER], "BG": [GROUND], **groups}


def joined(**groups: list[list[Any]]) -> GameState:
    state = GameState()
    state.update_from_packet("jaa", {"KID": 0, "T": 1, "gca": castle(**groups)})
    return state


def ids(state: GameState) -> set[int]:
    buildings = state.get_buildings()
    assert buildings is not None
    return set(buildings)


def row_of(state: GameState, object_id: int) -> list[Any]:
    buildings = state.get_buildings()
    assert buildings is not None
    row = buildings[object_id].row
    return [row.wod_id, row.object_id, row.x, row.y]


class TestWholeCastle:
    def test_jaa_keeps_every_group_by_object_id(self):
        state = joined(FP=[[900, 40, 1, 1, 0]])

        assert ids(state) == {5, 20, 21, 22, 30, 40}
        assert row_of(state, 5) == [101, 5, 3, 4]

    def test_a_jaa_without_buildings_has_none(self):
        state = joined()
        state.update_from_packet("jaa", {"KID": 0, "T": 1})

        assert state.get_buildings() is None

    def test_a_refused_jaa_keeps_them(self):
        state = joined()
        state.update_from_packet(
            "jaa", {"KID": 0, "T": 1, "gca": castle(BD=[[102, 6, 1, 1, 0]])}, GGEError.GENERAL_ERROR
        )

        assert ids(state) == {5, 20, 21, 22, 30}

    def test_gca_replaces_them_whole(self):
        state = joined()
        state.update_from_packet("gca", {"gca": {"BD": [[102, 6, 1, 1, 0]]}})

        assert ids(state) == {6}

    def test_gca_before_any_join_or_without_its_block_changes_nothing(self):
        state = GameState()
        state.update_from_packet("gca", {"gca": castle()})
        assert state.get_buildings() is None

        state = joined()
        state.update_from_packet("gca", {"O": {}})
        assert ids(state) == {5, 20, 21, 22, 30}

    def test_ebe_replaces_them_whole(self):
        # AreaDataUpdater.parseEBE hands its gca to parseGCA
        state = joined()
        state.update_from_packet("ebe", {"gca": castle(BG=[GROUND, [2, 31, 9, 9, 0]])})

        assert 31 in ids(state)

    def test_an_ebe_without_gca_keeps_them(self):
        state = joined()
        state.update_from_packet("ebe", {"grc": {}})

        assert ids(state) == {5, 20, 21, 22, 30}


class TestRows:
    @pytest.mark.parametrize("command", ["gcb", "gdb", "ira"])
    def test_b_rows_replace_or_add_their_objects(self, command):
        state = joined()
        state.update_from_packet(command, {"B": [[102, 5, 3, 4, 0], [103, 7, 8, 8, 0]]})

        assert row_of(state, 5) == [102, 5, 3, 4]
        assert row_of(state, 7) == [103, 7, 8, 8]

    def test_eup_reads_its_o_list(self):
        state = joined()
        state.update_from_packet("eup", {"O": [[102, 5, 3, 4, 0]], "grc": {}, "scl": {}})

        assert row_of(state, 5) == [102, 5, 3, 4]

    @pytest.mark.parametrize(
        ("command", "key"),
        [("ebu", "NO"), ("pio", "NO"), ("emo", "MO"), ("mde", "MO"), ("rde", "MO")]
        + [("edo", "O"), ("fco", "O"), ("rbu", "O"), ("ego", "O"), ("eud", "N")],
    )
    def test_a_reply_with_one_row_replaces_its_object(self, command, key):
        state = joined()
        state.update_from_packet(command, {key: [102, 5, 6, 7, 0]})

        assert row_of(state, 5) == [102, 5, 6, 7]

    def test_a_row_wrapped_in_o_is_read(self):
        state = joined()
        state.update_from_packet("ebu", {"NO": {"O": [104, 8, 1, 2, 0]}})

        assert row_of(state, 8) == [104, 8, 1, 2]

    def test_eud_keeps_the_rest_of_the_defence(self):
        # parseEUD re-inits the DEFENCE group first, which re-lays positions and keeps its objects
        state = joined()
        state.update_from_packet("eud", {"N": [1701, 21, 0, 0, 0], "grc": {}})

        assert row_of(state, 21) == [1701, 21, 0, 0]
        assert {20, 22} <= ids(state)

    def test_ego_sets_the_builder_discount(self):
        state = joined()
        state.update_from_packet("ego", {"O": [102, 5, 3, 4, 0], "gab": {"B": 15}})

        assert row_of(state, 5) == [102, 5, 3, 4]
        assert state.joined_area is not None and state.joined_area.builder_discount == 15
        assert state.get_last_packet_time("gab") is not None

    def test_ego_without_an_object_changes_no_row(self):
        # getRealServerObject falls back to the payload, which is no row
        state = joined()
        before = state.get_buildings()
        state.update_from_packet("ego", {"skl": {"SID": []}})

        assert state.get_buildings() == before

    def test_a_negative_object_id_is_skipped(self):
        state = joined()
        state.update_from_packet("gcb", {"B": [[102, -1, 3, 4, 0]]})

        assert -1 not in ids(state)

    def test_rows_before_any_join_are_dropped(self):
        state = GameState()
        state.update_from_packet("gcb", {"B": [WOODCUTTER]})

        assert state.get_buildings() is None

    def test_each_row_keeps_when_it_arrived(self):
        state = joined()
        buildings = state.get_buildings()
        assert buildings is not None
        with later(60):
            state.update_from_packet("gdb", {"B": [[101, 5, 3, 4, 0, 30, 0, 50, 0, 100, 1]]})
        updated = state.get_buildings()
        assert updated is not None

        assert updated[5].received_at - buildings[5].received_at == pytest.approx(60, abs=1)
        assert updated[20].received_at == buildings[20].received_at

    @pytest.mark.parametrize("command", ["cbx", "fbe"])
    def test_building_xp_changes_no_row(self, command):
        state = joined()
        before = state.get_buildings()
        state.update_from_packet(command, {"OID": 5, "XP": 10})

        assert state.get_buildings() == before


class TestRemovals:
    @pytest.mark.parametrize("command", ["sob", "sbd", "etc"])
    def test_the_named_object_is_removed(self, command):
        state = joined()
        state.update_from_packet(command, {"OID": 5})

        assert 5 not in ids(state)
        assert {20, 21, 22, 30} <= ids(state)

    def test_an_unknown_object_id_removes_nothing(self):
        state = joined()
        state.update_from_packet("sob", {"OID": 99})

        assert ids(state) == {5, 20, 21, 22, 30}


class TestRefusedReplies:
    @pytest.mark.parametrize(
        ("command", "payload"),
        [("ebu", {"NO": MOVED}), ("eup", {"O": [MOVED]}), ("gcb", {"B": [MOVED]}), ("ego", {"O": MOVED})],
    )
    def test_a_refused_reply_changes_nothing(self, command, payload):
        state = joined()
        state.update_from_packet(command, payload, GGEError.NO_FREE_CONSTRUCTION_SLOT)

        assert row_of(state, 5) == [101, 5, 3, 4]

    def test_a_refused_removal_changes_nothing(self):
        state = joined()
        state.update_from_packet("sbd", {"OID": 5}, GGEError.GENERAL_ERROR)

        assert 5 in ids(state)

    @pytest.mark.parametrize("command", ["emo", "mde", "rde"])
    def test_a_failed_move_still_places_the_building(self, command):
        # EMOCommand, MDECommand and RDECommand read MO on MOVE_FAILED too
        state = joined()
        state.update_from_packet(command, {"MO": [101, 5, 3, 4, 0]}, GGEError.MOVE_FAILED)
        state.update_from_packet(command, {"MO": [101, 5, 9, 9, 0]}, GGEError.GENERAL_ERROR)

        assert row_of(state, 5) == [101, 5, 3, 4]


class TestResets:
    @pytest.mark.parametrize("command", ["gaa", "gtwara", "rst"])
    def test_a_map_read_forgets_them(self, command):
        state = joined()
        state.update_from_packet(command, {})

        assert state.get_buildings() is None

    def test_rows_after_a_map_read_are_dropped_until_a_join(self):
        state = joined()
        state.update_from_packet("gaa", {})
        state.update_from_packet("gcb", {"B": [WOODCUTTER]})
        assert state.get_buildings() is None

        state.update_from_packet("jaa", {"KID": 0, "T": 1, "gca": castle()})
        assert ids(state) == {5, 20, 21, 22, 30}

    def test_a_new_join_replaces_the_old_castle(self):
        state = joined()
        state.update_from_packet("jaa", {"KID": 0, "T": 1, "gca": {"A": AREA_ROW, "BD": [[102, 6, 1, 1, 0]]}})

        assert ids(state) == {6}

    def test_reset_forgets_them(self):
        state = joined()
        state.reset()

        assert state.get_buildings() is None

    def test_the_read_is_a_copy(self):
        state = joined()
        buildings = state.get_buildings()
        assert buildings is not None
        buildings.clear()

        assert ids(state) == {5, 20, 21, 22, 30}


def test_client_castle_buildings_fronts_the_state():
    client = make_client(state=logged_in_state())
    assert client.castle.buildings is None

    client.state.update_from_packet("jaa", {"KID": 0, "T": 1, "gca": castle()})

    buildings = client.castle.buildings
    assert buildings is not None and set(buildings) == {5, 20, 21, 22, 30}
