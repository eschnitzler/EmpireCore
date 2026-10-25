"""Aqua points (AMACommand, GAPCommand), donation resources (GDRCommand) and the alliance laboratories (SLLCommand)."""

import pytest

from empire_core.alliance.models.aqua import AllianceMemberAquaPointsResponse
from empire_core.enums import AllianceRank, Kingdom
from empire_core.exceptions import CommandError, NotInAllianceError
from empire_core.gamedata import Currency
from empire_core.player.models.aqua import AquaPointsResponse
from tests.alliance.test_auto_join import player_state, wired
from tests.service_helpers import conn, gcl_castles, make_client, xt_packet

CREST = {"IS": 1, "SPT": 2, "S1": 3, "SC1": 4, "S2": 5, "SC2": 6, "BGT": 1, "BGC1": 7, "BGC2": 8}
LABORATORY_ROW = [28, 10, 20, 900, 7, 3, 2, 0, "Lab"]


def test_member_rows_are_read_by_position():
    reply = {"APH": [[8, "Member", "70", 1, "250", 3, CREST], [9, None, 12, 0, 0, 9], "bad"]}
    first, second = AllianceMemberAquaPointsResponse.model_validate(reply).members
    assert (first.player_id, first.name, first.level, first.has_unlocked_storm_islands, first.aqua_points) == (
        8,
        "Member",
        70,
        True,
        250,
    )
    assert first.rank == AllianceRank(3)
    assert first.crest is not None and first.crest.background_color2 == 8
    assert second.name == "" and second.has_unlocked_storm_islands is False and second.crest is None


def test_member_aqua_points_ask_with_your_alliance():
    client = make_client({"ama": xt_packet("ama", {"APH": [[8, "Member", 70, 1, 250, 3]]})}, state=player_state(301))
    (member,) = client.alliance.get_member_aqua_points(timeout=0.2)
    assert member.aqua_points == 250
    assert conn(client).request_payloads == [("ama", {"AID": 301})]


def test_member_aqua_points_outside_an_alliance_are_not_asked():
    client = make_client(state=player_state())
    with pytest.raises(NotInAllianceError):
        client.alliance.get_member_aqua_points()
    assert conn(client).request_payloads == []


def test_aqua_points_reply_keeps_player_and_alliance_points():
    state = player_state(301)
    state.update_from_packet("ain", {"A": {"AID": 301, "N": "Guild", "AP": 5}})
    client = wired({"gap": xt_packet("gap", {"P": 40, "A": 900, "O": 12, "DP": 3})}, state)
    assert client.player.aqua_points is None
    result = client.player.get_aqua_points(timeout=0.2)
    assert (result.player_points, result.alliance_points, result.building_id, result.gained_points) == (40, 900, 12, 3)
    assert conn(client).request_payloads == [("gap", {})]
    assert client.player.aqua_points == 40
    own = client.alliance.own_alliance
    assert own is not None and own.aqua_points == 900


def test_aqua_points_push_without_alliance_points_keeps_them():
    state = player_state(301)
    state.update_from_packet("ain", {"A": {"AID": 301, "AP": 5}})
    state.update_from_packet("gap", {"P": 41})
    state.update_from_packet("gap", {"P": 99, "A": 99}, 1)
    own = state.get_own_alliance()
    assert state.get_aqua_points() == 41 and own is not None and own.aqua_points == 5
    assert AquaPointsResponse.model_validate({}).player_points == 0


def test_donation_resources_ask_for_the_castle_and_apply_the_reply():
    state = player_state(301)
    state.castles = {castle.id: castle for castle in gcl_castles((12345, Kingdom.ICE), owner_id=7)}
    reply = {"grc": {"AID": 12345, "KID": 2, "W": 500, "HONEY": 3}, "sce": [["PTT", "4"], ["NEW_KEY", 2]]}
    client = wired({"gdr": xt_packet("gdr", reply)}, state)
    result = client.alliance.get_donation_resources(12345, timeout=0.2)
    assert (sent := conn(client).request_payloads) == [("gdr", {"AID": 12345, "KID": 2})]
    assert list(sent[0][1]) == ["AID", "KID"]
    assert result.resources.wood == 500 and result.resources.honey == 3
    assert result.currencies == {Currency.FAST_TRAVEL_FEATHERS: 4, "NEW_KEY": 2}
    assert state.get_special_currencies()[Currency.FAST_TRAVEL_FEATHERS] == 4


def test_donation_resources_refusal_raises():
    state = player_state(301)
    state.castles = {castle.id: castle for castle in gcl_castles((12345, Kingdom.GREEN), owner_id=7)}
    client = make_client({"gdr": xt_packet("gdr", {}, error_code=1)}, state=state)
    with pytest.raises(CommandError):
        client.alliance.get_donation_resources(12345, timeout=0.2)


def test_laboratory_push_replaces_the_alliance_laboratories():
    state = player_state(301)
    state.update_from_packet("ain", {"A": {"AID": 301, "N": "Guild", "ALA": [LABORATORY_ROW, LABORATORY_ROW]}})
    state.update_from_packet("sll", {"ALA": [LABORATORY_ROW]})
    own = state.get_own_alliance()
    assert own is not None and [lab.location_id for lab in own.laboratories] == [900]
    state.update_from_packet("sll", {"ALA": []}, 1)
    state.update_from_packet("sll", {})
    own = state.get_own_alliance()
    assert own is not None and own.laboratories == [] and own.name == "Guild"
