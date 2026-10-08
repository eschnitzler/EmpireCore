"""GameState castle resources from a grc block: the grc reply and every reply that carries one."""

from typing import Any

import pytest

from empire_core.state.manager import GameState
from tests.state.state_helpers import gcl_payload

DCL_ENTRY = {"AID": 1, "W": 100, "S": 200, "F": 300, "HONEY": 9, "gpa": {"MRW": 7000, "DW": 2239, "SAFE_W": 1000.0}}
GRC = {"AID": 1, "KID": 0, "W": 40, "S": 50, "F": 60, "C": 1, "O": 2, "G": 3, "I": 4, "A": 5, "HONEY": 6}


def login(state: GameState, *, with_dcl: bool = True) -> None:
    state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gcl": gcl_payload([(1, "Main")])})
    if with_dcl:
        state.update_from_packet("dcl", {"C": [{"KID": 0, "AI": [DCL_ENTRY]}]})


def stock(state: GameState) -> tuple[int, ...]:
    r = state.get_castles()[0].resources
    return (r.wood, r.stone, r.food, r.coal, r.oil, r.glass, r.iron, r.aquamarine, r.honey, r.mead, r.beef)


class TestCastleResources:
    # AreaDataUpdater.parseGRC -> CastleUserCastleListDetailed.updateDetailVO

    @pytest.mark.parametrize(
        ("command", "payload"),
        [
            ("grc", GRC),
            ("res", {"rei": {"ARID": 1, "ARRT": 60, "BR": []}, "gcu": {}, "grc": GRC}),
            ("ebu", {"NO": [101, 5, 3, 4, 0, 0, 0, 60, 0, 100, 1], "grc": GRC, "scl": {}, "gcu": {}}),
            ("jaa", {"KID": 0, "T": 1, "grc": GRC}),
        ],
    )
    def test_a_grc_sets_the_castles_stock_and_keeps_capacity(self, state, command: str, payload: dict[str, Any]):
        login(state)
        state._castle_details_at.clear()
        state._castle_details_at[next(iter(state.castles))] = 0.0

        state.update_from_packet(command, payload)

        assert stock(state) == (40, 50, 60, 1, 2, 3, 4, 5, 6, 0, 0)
        r = state.get_castles()[0].resources
        assert (r.wood_cap, r.wood_rate, r.wood_safe) == (7000, 223.9, 1000.0)
        # the details time dates the dcl's resources and units together; a grc refreshes only the stock
        assert state.get_castle_last_updated(1) == 0.0
        assert state.get_last_packet_time("grc") is not None

    def test_the_plain_reply_is_stamped(self, state):
        login(state)
        state.update_from_packet("grc", GRC)
        assert state.get_last_packet_time("grc") is not None

    def test_a_resource_the_block_leaves_out_is_zero(self, state):
        # updateDetailVO sets every GROUP_LIST_RESOURCES entry, getAmountOrDefaultByType giving 0
        login(state)
        state.update_from_packet("grc", {"AID": 1, "KID": 0, "W": 40})
        assert stock(state) == (40, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

    def test_a_refused_reply_applies_nothing(self, state):
        login(state)
        state.update_from_packet("res", {"grc": GRC}, error_code=21)
        state.update_from_packet("grc", GRC, error_code=21)
        assert stock(state)[:3] == (100, 200, 300)
        assert state.get_last_packet_time("grc") is None

    @pytest.mark.parametrize("block", [{**GRC, "AID": 2}, {**GRC, "KID": 1}, {**GRC, "KID": 99}])
    def test_a_castle_not_listed_is_left_alone(self, state, block: dict[str, Any]):
        login(state)
        state.update_from_packet("grc", block)
        assert stock(state)[:3] == (100, 200, 300)
        assert state.get_last_packet_time("grc") is None

    def test_a_castle_without_details_is_left_alone(self, state):
        # getVObyCastleID finds only castles with a detailed entry
        login(state, with_dcl=False)
        state.update_from_packet("grc", GRC)
        assert stock(state)[:3] == (0, 0, 0)
        assert state.get_castle_last_updated(1) is None

    def test_a_refused_crm_still_reaches_the_movement_handler(self, state):
        login(state)
        state.update_from_packet("crm", {}, error_code=21)
        assert state.get_last_packet_time("crm") is not None
