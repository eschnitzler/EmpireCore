"""Your kings towers, monuments, villages and the monument reset, from GKLCommand, GMLCommand, KGVCommand,
MRECommand, GBDCommand and CastleUserData.parse_MIR, and the kgv and kpi requests."""

import pytest

from empire_core.castle import (
    KingdomInfoResponse,
    KingsTowerListResponse,
    MonumentListResponse,
    MonumentResetResponse,
    VillageListResponse,
)
from empire_core.enums import Kingdom, MapItemType
from empire_core.exceptions import CommandError
from empire_core.gamedata import PrivateVillageType, Unit
from empire_core.state.manager import GameState
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

# KingstowerMapobjectVO, MonumentMapobjectVO, VillageMapobjectVO and ResourceIsleMapobjectVO.parseAreaInfo
TOWER_ROW = [23, 100, 200, 501, 7, 0, -1, "Tower"]
MONUMENT_ROW = [26, 110, 210, 601, 7, 1, 2, 0, -1, "Monument"]
VILLAGE_ROW = [10, 120, 220, 701, 7, 1, 2, -1, "Village"]
ISLE_ROW = [24, 130, 230, 801, 7, 4, "Isle", -1, 3, 0]
UNITS = [[int(Unit.SWORDMAN), 30]]
GKL = {"AI": [[TOWER_ROW, UNITS], "bad"]}
GML = {"AI": [[MONUMENT_ROW]]}
KGV = {"VI": [[VILLAGE_ROW, UNITS], [ISLE_ROW, []]], "PV": [{"VID": 9, "XID": "41"}, {"VID": 10, "XID": 999}]}


def test_kings_tower_and_monument_rows_read_map_row_and_units():
    (tower,) = KingsTowerListResponse.model_validate(GKL).kings_towers
    assert tower.location.location_id == 501 and tower.location.item_type == MapItemType.KINGS_TOWER
    assert tower.units == {Unit.SWORDMAN: 30}
    (monument,) = MonumentListResponse.model_validate(GML).monuments
    assert monument.location.location_id == 601 and monument.units == {}


def test_villages_read_both_lists_and_keep_unknown_private_village_types():
    villages = VillageListResponse.model_validate(KGV)
    assert [v.location.item_type for v in villages.villages] == [MapItemType.VILLAGE, MapItemType.ISLE_RESOURCE]
    assert villages.villages[0].units == {Unit.SWORDMAN: 30}
    assert [(p.village_id, p.village_type_id) for p in villages.private_villages] == [(9, 41), (10, 999)]
    assert villages.private_villages[0].village_type_id is PrivateVillageType.ICE_PRIVATE_WOOD_VILLAGE_L1
    assert VillageListResponse.model_validate({"VI": []}).private_villages == []


def test_login_brings_the_lists_and_the_monument_reset_read_through_the_castle_service():
    state = logged_in_state(gkl=GKL, gml=GML, kgv=KGV, mre={"MRS": 3600})
    client = make_client(state=state)
    assert (towers := client.castle.kings_towers) is not None and len(towers.kings_towers) == 1
    assert (monuments := client.castle.monuments) is not None and len(monuments.monuments) == 1
    assert (villages := client.castle.villages) is not None and len(villages.villages) == 2
    assert (reset := client.castle.monument_reset) is not None and 3590 <= reset.remaining_seconds() <= 3600
    for section in ("gkl", "gml", "kgv", "mre"):
        assert state.get_last_packet_time(section) is not None


def test_pushes_and_mir_replace_the_kings_towers_and_monuments():
    state = GameState()
    state.update_from_packet("gkl", GKL)
    state.update_from_packet("gml", GML)
    state.update_from_packet("mir", {"gkl": {"AI": []}, "gml": {"AI": []}})
    assert (towers := state.get_kings_towers()) is not None and towers.kings_towers == []
    assert (monuments := state.get_monuments()) is not None and monuments.monuments == []
    state.update_from_packet("gkl", GKL)
    state.update_from_packet("gkl", {"AI": []}, 1)
    assert (towers := state.get_kings_towers()) is not None and len(towers.kings_towers) == 1


def test_monument_reset_keeps_the_countdown_only_when_it_counts_down():
    state = GameState()
    state.update_from_packet("mre", {"MRS": 0})
    assert state.get_monument_reset() is None and state.get_last_packet_time("mre") is None
    state.update_from_packet("mre", {"MRS": 60})
    state.update_from_packet("mre", {"MRS": -1})
    reset = state.get_monument_reset()
    assert reset is not None and reset.seconds == 60
    assert MonumentResetResponse(seconds=-5).remaining_seconds() == 0


def test_get_villages_sends_kgv_and_its_reply_updates_state():
    client = make_client({"kgv": xt_packet("kgv", KGV)}, state=GameState())
    conn(client).on_packet = client._on_packet
    villages = client.castle.get_villages()
    assert conn(client).request_payloads == [("kgv", {})]
    assert len(villages.villages) == 2
    assert client.castle.villages == villages


def test_get_kingdoms_sends_kpi_and_merges_its_reply():
    state = logged_in_state(kpi={"UL": [{"KID": 2, "U": 1, "C": 1}, {"KID": 4, "U": 0}]})
    client = make_client({"kpi": xt_packet("kpi", {"UL": [{"KID": 4, "U": 1}]})}, state=state)
    conn(client).on_packet = client._on_packet
    reply = client.castle.get_kingdoms()
    assert conn(client).request_payloads == [("kpi", {})]
    assert isinstance(reply, KingdomInfoResponse)
    kingdoms = client.castle.kingdoms
    assert kingdoms is not None
    assert {k.kingdom_id: k.is_unlocked for k in kingdoms.kingdoms} == {Kingdom.ICE: True, Kingdom.STORM: True}


@pytest.mark.parametrize("call", ["get_villages", "get_kingdoms"])
def test_a_refused_read_raises(call):
    command = {"get_villages": "kgv", "get_kingdoms": "kpi"}[call]
    client = make_client({command: xt_packet(command, error_code=1)})
    with pytest.raises(CommandError):
        getattr(client.castle, call)()
