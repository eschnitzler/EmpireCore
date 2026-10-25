"""The Storm Islands: the standing (sii, SIICommand), the reset push (ikr, IKRCommand) and the rca push."""

import pytest

from empire_core.alliance import RoyalCapitalAllianceResponse
from empire_core.enums import Kingdom
from empire_core.exceptions import CommandError
from empire_core.player import StormIslandsInfo, StormIslandsReset
from empire_core.protocol.models import parse_response
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, xt_packet
from tests.state.state_helpers import gam_payload, login, wait_for

SII = {"IR": 3, "AP": 1200, "AR": 1, "KA": 1, "AE": "1"}


def test_the_standing_reads_ranks_points_and_flags():
    info = StormIslandsInfo.model_validate(SII)
    assert (info.rank, info.aqua_points, info.alliance_rank) == (3, 1200, 1)
    assert info.alliance_is_island_king and info.alliance_entered_islands
    assert not StormIslandsInfo.model_validate({"KA": 0, "AE": 2}).alliance_is_island_king


def test_get_storm_islands_info_sends_sii_and_keeps_the_standing_and_aqua_points():
    client = make_client({"sii": xt_packet("sii", SII)}, state=GameState())
    conn(client).on_packet = client._on_packet
    info = client.player.get_storm_islands_info()
    assert conn(client).request_payloads == [("sii", {})]
    assert client.player.storm_islands == info
    assert client.player.aqua_points == 1200


def test_a_refused_standing_raises_and_keeps_nothing():
    client = make_client({"sii": xt_packet("sii", error_code=1)}, state=GameState())
    conn(client).on_packet = client._on_packet
    with pytest.raises(CommandError):
        client.player.get_storm_islands_info()
    assert client.player.storm_islands is None


def test_the_reset_locks_the_islands_zeroes_aqua_points_and_drops_movements_there():
    state = GameState()
    login(state, alliance_id=5)
    state.update_from_packet("ain", {"A": {"AID": 5, "N": "Clan", "AP": 900}})
    state.update_from_packet("kpi", {"UL": [{"KID": 4, "U": 1}, {"KID": 2, "U": 1}]})
    state.update_from_packet("gap", {"P": 50, "A": 900})
    state.update_from_packet("gam", gam_payload(1, extra={"KID": 4}))
    state.update_from_packet("gam", gam_payload(2))
    assert sorted(m.movement_id for m in state.get_all_movements()) == [1, 2]
    removed: list[int] = []
    state.on_movement_removed(removed.append)

    state.update_from_packet("ikr", {})

    kingdoms = state.get_kingdoms()
    assert kingdoms is not None
    assert {k.kingdom_id: k.is_unlocked for k in kingdoms.kingdoms} == {Kingdom.STORM: False, Kingdom.ICE: True}
    assert state.get_aqua_points() == 0
    alliance = state.get_own_alliance()
    assert alliance is not None and alliance.aqua_points == 0
    assert [m.movement_id for m in state.get_all_movements()] == [2]
    assert wait_for(lambda: removed == [1])
    assert StormIslandsReset.model_validate({}).command == "ikr"


def test_the_royal_capital_push_is_read_and_kept_nowhere():
    assert isinstance(parse_response("rca", {"X": 1}), RoyalCapitalAllianceResponse)
    state = GameState()
    state.update_from_packet("rca", {"X": 1})
    assert state.get_last_packet_time("rca") is None
