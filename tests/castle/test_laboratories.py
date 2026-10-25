"""Your laboratories and their reset, from GLLCommand, LRRCommand, GBDCommand and CastleUserData.parse_MIR."""

from empire_core.castle.models.landmarks import LaboratoryListResponse, LaboratoryResetResponse
from empire_core.enums import Kingdom
from empire_core.gamedata import Unit
from empire_core.state.manager import GameState
from tests.service_helpers import logged_in_state, make_client

ROW = [28, 10, 20, 900, 7, 3, 2, 0, "Lab"]
GLL = {"AI": [[ROW, [[int(Unit.SWORDMAN), 30], [int(Unit.SWORDMAN), 5]]], [ROW], "bad"]}


def test_laboratory_rows_read_map_row_and_units():
    first, second = LaboratoryListResponse.model_validate(GLL).laboratories
    assert first.location.location_id == 900 and first.location.kingdom == Kingdom.ICE
    assert first.units == {Unit.SWORDMAN: 35}
    assert second.units == {}


def test_login_brings_laboratories_and_reset_read_through_the_castle_service():
    state = logged_in_state(gll=GLL, lrr={"LRS": 3600})
    client = make_client(state=state)
    laboratories = client.castle.laboratories
    assert laboratories is not None and len(laboratories.laboratories) == 2
    reset = client.castle.laboratory_reset
    assert reset is not None and 3590 <= reset.remaining_seconds() <= 3600
    assert state.get_last_packet_time("gll") is not None and state.get_last_packet_time("lrr") is not None


def test_pushes_and_mir_replace_the_laboratories():
    state = GameState()
    state.update_from_packet("gll", GLL)
    state.update_from_packet("mir", {"gll": {"AI": []}})
    assert (labs := state.get_laboratories()) is not None and labs.laboratories == []
    state.update_from_packet("gll", GLL)
    state.update_from_packet("gll", {"AI": []}, 1)
    assert (labs := state.get_laboratories()) is not None and len(labs.laboratories) == 2


def test_reset_keeps_the_countdown_only_when_it_counts_down():
    state = GameState()
    state.update_from_packet("lrr", {"LRS": 0})
    assert state.get_laboratory_reset() is None and state.get_last_packet_time("lrr") is None
    state.update_from_packet("lrr", {"LRS": 60})
    state.update_from_packet("lrr", {"LRS": -1})
    reset = state.get_laboratory_reset()
    assert reset is not None and reset.seconds == 60
    assert LaboratoryResetResponse(seconds=-5).remaining_seconds() == 0
