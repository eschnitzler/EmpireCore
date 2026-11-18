"""GameState keeps the joined castle's construction slots (scl) from the joins, pushes and replies that carry them."""

from typing import Any

import pytest

from empire_core.castle.models.objects import ConstructionList
from empire_core.castle.models.updates import BuildingChanged
from empire_core.state.manager import GameState
from tests.service_helpers import logged_in_state, make_client
from tests.state.test_castle_pushes import jaa_payload, login

JOINED = {"OIDL": [5, -1], "SSC": 2}
AFTER = {"OIDL": [5, 6, -2], "SSC": 2}
CARRIED = ConstructionList.model_validate(AFTER)

# Each carrier, its payload around the slots AFTER, as AreaDataUpdater reads it
CARRIERS: dict[str, dict[str, Any]] = {
    "ebu": {"NO": [101, 5, 3, 4, 0, 0, 0, 60, 0, 100, 1], "scl": AFTER},
    "eup": {"O": [], "scl": AFTER},
    "edo": {"scl": AFTER},
    "rbu": {"O": [], "scl": AFTER},
    "msb": {"scl": AFTER},
    "ebe": {"gca": {"BD": []}, "scl": AFTER},
    "ego": {"O": [101, 5, 3, 4, 0, 0, 0, 60, 0, 100, 1], "scl": AFTER, "gab": {"B": 5}},
    "scl": AFTER,
    "gca": {"gca": {"BD": [], "scl": AFTER}},
}


def joined(state: GameState) -> None:
    login(state)
    state.update_from_packet("jaa", jaa_payload(gca={"A": [1, 10, 20, 1, 7, 1, 1, 1, 0, 0, "Main"], "scl": JOINED}))


class TestJoin:
    def test_a_jaa_brings_its_gca_blocks_slots(self, state):
        joined(state)

        assert state.get_construction_list() == ConstructionList.model_validate(JOINED)

    def test_a_jaa_without_slots_drops_the_last_castles(self, state):
        joined(state)

        state.update_from_packet("jaa", jaa_payload())

        assert state.get_construction_list() is None

    def test_a_refused_jaa_keeps_them(self, state):
        joined(state)

        state.update_from_packet("jaa", jaa_payload(), error_code=1)

        assert state.get_construction_list() == ConstructionList.model_validate(JOINED)

    def test_nothing_before_a_join(self, state):
        login(state)

        state.update_from_packet("scl", AFTER)

        assert state.get_construction_list() is None


class TestCarriers:
    @pytest.mark.parametrize("command", CARRIERS)
    def test_each_carrier_sets_them(self, state, command):
        joined(state)

        state.update_from_packet(command, CARRIERS[command])

        assert state.get_construction_list() == CARRIED

    @pytest.mark.parametrize("command", CARRIERS)
    def test_a_refused_carrier_does_not(self, state, command):
        joined(state)

        state.update_from_packet(command, CARRIERS[command], error_code=1)

        assert state.get_construction_list() == ConstructionList.model_validate(JOINED)

    @pytest.mark.parametrize("command", [command for command in CARRIERS if command != "scl"])
    def test_a_carrier_without_slots_keeps_them(self, state, command):
        # AreaDataUpdater.parseSCL applies only a truthy scl
        joined(state)

        state.update_from_packet(command, {"gca": {"BD": []}} if command == "gca" else {})

        assert state.get_construction_list() == ConstructionList.model_validate(JOINED)

    def test_an_ebe_keeps_its_own_slots_over_its_gca_blocks(self, state):
        # parseEBE applies gca.scl, then scl
        joined(state)

        state.update_from_packet("ebe", {"gca": {"BD": [], "scl": {"OIDL": [-1], "SSC": 1}}, "scl": AFTER})

        assert state.get_construction_list() == CARRIED

    def test_an_ebe_without_slots_of_its_own_brings_its_gca_blocks(self, state):
        joined(state)

        state.update_from_packet("ebe", {"gca": {"BD": [], "scl": AFTER}})

        assert state.get_construction_list() == CARRIED

    def test_an_unreadable_scl_frame_keeps_them(self, state):
        joined(state)

        state.update_from_packet("scl", {"raw": "%xt%scl%1%0%"})

        assert state.get_construction_list() == ConstructionList.model_validate(JOINED)

    def test_the_reader_hands_out_a_copy(self, state):
        joined(state)

        state.get_construction_list().slot_count = 9  # type: ignore[union-attr]

        assert state.get_construction_list() == ConstructionList.model_validate(JOINED)


class TestReset:
    @pytest.mark.parametrize("command", ["gaa", "gtwara", "rst"])
    def test_leaving_the_castle_drops_them(self, state, command):
        joined(state)

        state.update_from_packet(command, {})

        assert state.get_construction_list() is None

    def test_a_session_reset_drops_them(self, state):
        joined(state)

        state.reset()

        assert state.get_construction_list() is None


def test_the_ego_model_reads_the_building_slots_and_discount():
    pushed = BuildingChanged.model_validate(CARRIERS["ego"])

    assert pushed.building is not None and pushed.building.object_id == 5
    assert pushed.construction_list == CARRIED
    assert pushed.area_booster is not None and pushed.area_booster.builder_discount == 5


def test_client_castle_construction_list_fronts_the_state():
    client = make_client(state=logged_in_state())
    joined(client.state)

    assert client.castle.construction_list == ConstructionList.model_validate(JOINED)
