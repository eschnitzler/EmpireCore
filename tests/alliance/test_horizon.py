"""Beyond the Horizon: entry (ajp), performance (gae), influence (gabgap, gabgpp), centers of power (cpe, cpd)
and alliance towers (tie, tpi, tbi, aatb, iatb)."""

import pytest

from empire_core.alliance.models.horizon import (
    AllianceTowerBuffIncrease,
    CentersOfPowerDetailResponse,
    GetHorizonPerformanceRequest,
    HorizonPerformanceResponse,
    IncreaseAllianceTowerBuffsRequest,
)
from empire_core.enums import AllianceRank, MapItemType, PerformanceStatistic
from empire_core.exceptions import CommandError, NotInAllianceError
from empire_core.gamedata import AllianceTowerEffect
from empire_core.gamedata.ids.effects import Effect
from empire_core.gamedata.ids.events import Event
from tests.alliance.test_auto_join import player_state, wired
from tests.service_helpers import conn, make_client, xt_packet

CREST = {"IS": 1, "SPT": 2, "S1": 3, "SC1": 4, "S2": 5, "SC2": 6, "BGT": 1, "BGC1": 7, "BGC2": 8}
TOWER_ROW = [41, 10, 20, 7, "Tower", 1, 3, 301, "Guild", None, [[11, 21, "Member", 1]]]
CASTLE_ROW = [1, 11, 21, 8]
BUFFS = {"TE": [{"TEID": 4, "L": "2"}, {"TEID": 5, "L": 0}, "bad"], "TEA": 1}
PERFORMANCE = {
    "AME": [
        {
            "PID": 8,
            "NOM": "Member",
            "L": "70",
            "AMT": 1200,
            "PST": [{"PSI": 1, "AMT": "300"}, {"PSI": 13, "AMT": 4}, {"PSI": 999, "AMT": 1}],
            "E": CREST,
        }
    ]
}


def test_entry_is_asked_with_no_payload_and_read():
    client = make_client({"ajp": xt_packet("ajp", {"N": "Guild", "M": "12", "R": 3})})
    entry = client.alliance.get_horizon_entry(timeout=0.2)
    assert (entry.alliance_name, entry.member_count, entry.rank) == ("Guild", 12, AllianceRank(3))
    assert conn(client).request_payloads == [("ajp", {})]


def test_refused_entry_raises():
    client = make_client({"ajp": xt_packet("ajp", {}, error_code=1)})
    with pytest.raises(CommandError):
        client.alliance.get_horizon_entry(timeout=0.2)


def test_performance_request_names_the_horizon_event():
    assert GetHorizonPerformanceRequest(alliance_id=301).to_payload() == {"AID": 301, "EID": 113}
    assert GetHorizonPerformanceRequest(alliance_id=301).event_id is Event.BEYOND_THE_HORIZON


def test_performance_rows_are_read_with_their_statistics():
    (member,) = HorizonPerformanceResponse.model_validate(PERFORMANCE).members
    assert (member.player_id, member.player_name, member.level, member.influence) == (8, "Member", 70, 1200)
    assert member.statistics == {
        PerformanceStatistic.CONTRIBUTION_TO_ALLIANCE_INFLUENCE: 300,
        PerformanceStatistic.SUPPORT_TROOPS_SENT_TO_ALLIANCE_TOWERS: 4,
        999: 1,
    }
    assert member.crest is not None and member.crest.background_color2 == 8


def test_performance_is_asked_for_your_alliance_and_kept():
    client = wired({"gae": xt_packet("gae", PERFORMANCE)}, player_state(301))
    assert client.alliance.horizon_performance is None
    (member,) = client.alliance.get_horizon_performance(timeout=0.2)
    assert member.influence == 1200
    assert conn(client).request_payloads == [("gae", {"AID": 301, "EID": 113})]
    kept = client.alliance.horizon_performance
    assert kept is not None and [m.player_id for m in kept] == [8]


def test_refused_performance_keeps_the_last():
    state = player_state(301)
    state.update_from_packet("gae", PERFORMANCE)
    state.update_from_packet("gae", {"AME": []}, 1)
    kept = state.get_horizon_performance()
    assert kept is not None and len(kept) == 1


def test_performance_outside_an_alliance_is_not_asked():
    client = make_client(state=player_state())
    with pytest.raises(NotInAllianceError):
        client.alliance.get_horizon_performance()
    assert conn(client).request_payloads == []


def test_influence_of_an_alliance_and_a_player():
    client = make_client(
        {
            "gabgap": xt_packet("gabgap", {"AID": 301, "AMT": "5000"}),
            "gabgpp": xt_packet("gabgpp", {"PID": 8, "AMT": 70}),
        }
    )
    assert client.alliance.get_horizon_alliance_influence(301, timeout=0.2) == 5000
    assert client.alliance.get_horizon_player_influence(8, timeout=0.2) == 70
    assert conn(client).request_payloads == [("gabgap", {"AID": 301}), ("gabgpp", {"PID": 8})]


def test_centers_of_power_counts():
    reply = {"CPA": 1, "CPL": 1, "CSA": 2, "CSPL": 1, "CSAL": 5, "TWM": 0, "TPL": 1, "TAL": 3}
    client = make_client({"cpe": xt_packet("cpe", reply)}, state=player_state(301))
    centers = client.alliance.get_centers_of_power(timeout=0.2)
    assert (centers.capitals, centers.metropolises, centers.metropolis_alliance_limit) == (1, 2, 5)
    assert (centers.tower_player_limit, centers.tower_alliance_limit) == (1, 3)
    assert conn(client).request_payloads == [("cpe", {"AID": 301})]


def test_centers_of_power_detail_rows():
    reply = {
        "AAI": [
            {"AI": CASTLE_ROW, "PN": "Member", "AMT": "40", "AOT": 0, "PB": 0},
            {"AI": "bad", "PN": "Other", "AOT": 3600},
        ]
    }
    first, second = CentersOfPowerDetailResponse.model_validate(reply).centers
    assert first.area is not None and (first.area.x, first.area.y) == (11, 21)
    assert (first.player_name, first.amount) == ("Member", 40)
    assert second.area is None and second.seconds_left == 3600 and second.percent_boost == 0


def test_centers_of_power_detail_asks_for_your_alliance():
    client = make_client({"cpd": xt_packet("cpd", {"AAI": []})}, state=player_state(301))
    assert client.alliance.get_centers_of_power_detail(timeout=0.2) == []
    assert conn(client).request_payloads == [("cpd", {"AID": 301})]


def test_towers_are_map_rows():
    client = make_client({"tie": xt_packet("tie", {"T": [TOWER_ROW, []]})})
    (tower,) = client.alliance.get_towers(301, timeout=0.2)
    assert tower.item_type == MapItemType.HORIZON_TOWER
    assert (tower.x, tower.y, tower.alliance_id) == (10, 20, 301)
    assert conn(client).request_payloads == [("tie", {"AID": 301})]


def test_tower_castles_with_their_owners():
    reply = {"O": [{"OID": 8, "N": "Member"}, "bad"], "C": [CASTLE_ROW]}
    client = make_client({"tpi": xt_packet("tpi", reply)})
    result = client.alliance.get_tower_castles(10, 20, timeout=0.2)
    assert [owner.owner_id for owner in result.owners] == [8]
    assert [(castle.x, castle.y) for castle in result.castles] == [(11, 21)]
    assert conn(client).request_payloads == [("tpi", {"XPOS": 10, "YPOS": 20})]


def test_tower_buffs_are_read():
    client = make_client({"tbi": xt_packet("tbi", BUFFS)})
    buffs = client.alliance.get_tower_buffs(10, 20, 301, timeout=0.2)
    assert [(buff.tower_effect_id, buff.level) for buff in buffs.buffs] == [
        (AllianceTowerEffect.MELEE_BONUS_TOWER, 2),
        (AllianceTowerEffect.RANGE_BONUS_TOWER, 0),
    ]
    assert buffs.is_active is True
    assert conn(client).request_payloads == [("tbi", {"XPOS": 10, "YPOS": 20, "AID": 301})]


def test_activating_tower_buffs_needs_consent():
    client = make_client({"aatb": xt_packet("aatb", {"tbi": BUFFS})})
    with pytest.raises(ValueError, match="spend_rubies"):
        client.alliance.activate_tower_buffs(10, 20)
    assert conn(client).request_payloads == []
    buffs = client.alliance.activate_tower_buffs(10, 20, spend_rubies=True, timeout=0.2)
    assert buffs.is_active is True and len(buffs.buffs) == 2
    assert conn(client).request_payloads == [("aatb", {"XPOS": 10, "YPOS": 20})]


def test_increase_request_rows():
    increase = AllianceTowerBuffIncrease(effect_id=Effect(1), level_before=0, level_after=2)
    assert IncreaseAllianceTowerBuffsRequest(x=10, y=20, increases=[increase]).to_payload() == {
        "XPOS": 10,
        "YPOS": 20,
        "TE": [{"E": 1, "ELBI": 0, "ELAI": 2}],
    }


def test_increasing_tower_buffs():
    client = make_client({"iatb": xt_packet("iatb", {"tbi": {"TE": [{"TEID": 4, "L": 2}], "TEA": 0}})})
    increase = AllianceTowerBuffIncrease(effect_id=1, level_before=0, level_after=2)
    with pytest.raises(ValueError, match="spend_rubies"):
        client.alliance.increase_tower_buffs(10, 20, [increase])
    with pytest.raises(ValueError):
        client.alliance.increase_tower_buffs(10, 20, [], spend_rubies=True)
    unraised = AllianceTowerBuffIncrease(effect_id=1, level_before=2, level_after=2)
    with pytest.raises(ValueError):
        client.alliance.increase_tower_buffs(10, 20, [unraised], spend_rubies=True)
    assert conn(client).request_payloads == []
    buffs = client.alliance.increase_tower_buffs(10, 20, [increase], spend_rubies=True, timeout=0.2)
    assert buffs.is_active is False and buffs.buffs[0].level == 2
    assert conn(client).request_payloads == [("iatb", {"XPOS": 10, "YPOS": 20, "TE": [{"E": 1, "ELBI": 0, "ELAI": 2}]})]


def test_refused_tower_buff_increase_raises():
    client = make_client({"iatb": xt_packet("iatb", {}, error_code=1)})
    increase = AllianceTowerBuffIncrease(effect_id=1, level_before=0, level_after=1)
    with pytest.raises(CommandError):
        client.alliance.increase_tower_buffs(10, 20, [increase], spend_rubies=True, timeout=0.2)
