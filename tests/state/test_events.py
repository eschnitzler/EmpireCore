"""GameState event tracking: sei and trigger events (tei/tee), their ends, and the replies that carry a sei."""

from typing import Any

import pytest

from empire_core.state import player as player_state

DAY = 86400

# The gbd's tei as seen live
LIVE_TEI: dict[str, Any] = {
    "TE": [
        {"TRID": 610, "GE": [[2, 47884, 10.0]], "SGE": []},
        {"TRID": 612, "GEB": [{"GEID": 2, "BV": 50.0, "C2": 2500}]},
        {"TRID": 601, "KLRT": 42, "KLRD": 1, "RSID": 7, "KLARE": 1, "KLLID": 1},
    ]
}
LIVE_KL_EVENT: dict[str, Any] = {"EID": 103, "RS": 51544, "SP": {"OP": 0, "OR": -1, "LID": 4}, "KL": 1}


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(player_state, "_clock", lambda: now[0])
    return now


class TestTriggerEvents:
    def test_the_login_tei_is_applied_before_its_sei(self, state, clock):
        state.update_from_packet("gbd", {"sei": {"E": [LIVE_KL_EVENT]}, "tei": LIVE_TEI})

        assert state.active_event_ids == [610, 612, 601, 103]
        assert state.get_last_packet_time("tei") is not None

    def test_global_effects_end_with_their_last_effect(self, state, clock):
        tei = {"TE": [{"TRID": 610, "GE": [[2, 100, 10], [3, "300", -1]], "SGE": []}, {"TRID": 612, "GEB": []}]}
        state.update_from_packet("tei", tei)

        assert state.event_end_times[610] == state.event_end_times[612] == 1300.0
        clock[0] = 1299.0
        assert state.active_event_ids == [610, 612]
        clock[0] = 1300.0
        assert state.active_event_ids == []

    def test_a_global_effect_event_without_effects_has_ended(self, state, clock):
        state.update_from_packet("tei", {"TE": [{"TRID": 610, "GE": [], "SGE": []}]})

        assert state.active_event_ids == []

    def test_the_boost_event_keeps_the_end_it_was_given(self, state, clock):
        # GlobalEffectBuffEventVO takes 610's time left as it arrives, 0 without 610
        state.update_from_packet("tei", {"TE": [{"TRID": 612, "GEB": []}, {"TRID": 610, "GE": [[2, 100, 1]]}]})
        assert state.active_event_ids == [610]

        state.update_from_packet("tei", {"TE": [{"TRID": 612, "GEB": []}]})
        state.update_from_packet("tei", {"TE": [{"TRID": 610, "GE": [[2, 500, 1]]}]})

        assert (state.event_end_times[610], state.event_end_times[612]) == (1500.0, 1100.0)

    def test_the_kingdoms_league_runs_while_it_has_days_left(self, state, clock):
        state.update_from_packet("tei", {"TE": [{"TRID": 601, "KLRD": 5}]})

        clock[0] += 30 * DAY

        assert state.active_event_ids == [601]

    def test_on_its_last_day_it_ends_with_the_season_event(self, state, clock):
        state.update_from_packet("gbd", {"sei": {"E": [LIVE_KL_EVENT]}, "tei": LIVE_TEI})
        assert state.event_end_times[601] == 1000.0 + 51544

        clock[0] += 51544

        assert 601 not in state.active_event_ids and 103 not in state.active_event_ids

    def test_on_its_last_day_without_a_season_event_it_keeps_running(self, state, clock):
        state.update_from_packet("tei", {"TE": [{"TRID": 601, "KLRD": 1}]})
        state.update_from_packet("sei", {"E": [{"EID": 103, "RS": 60, "KL": 0}]})

        clock[0] += 30 * DAY

        assert state.active_event_ids == [601]

    def test_with_no_days_left_and_no_season_event_it_has_ended(self, state, clock):
        state.update_from_packet("tei", {"TE": [{"TRID": 601, "KLRT": 42}]})

        assert state.active_event_ids == []

    def test_a_season_event_ending_ends_the_league_on_its_last_day(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 103, "RS": 60, "KL": 1}]})
        state.update_from_packet("tei", {"TE": [{"TRID": 601, "KLRD": 0}]})
        assert state.active_event_ids == [103, 601]

        state.update_from_packet("see", {"EID": 103})

        assert state.active_event_ids == []

    def test_a_tee_ends_its_trigger_event(self, state, clock):
        state.update_from_packet("tei", LIVE_TEI)

        state.update_from_packet("tee", {"TRID": "612"})
        state.update_from_packet("tee", {})
        state.update_from_packet("tee", {"TRID": 0})

        assert state.active_event_ids == [610, 601]
        assert state.get_last_packet_time("tee") is not None

    def test_a_see_ends_a_trigger_event_too(self, state, clock):
        state.update_from_packet("tei", LIVE_TEI)

        state.update_from_packet("see", {"EID": 601})

        assert state.active_event_ids == [610, 612]

    def test_an_empty_tei_changes_nothing(self, state, clock):
        state.update_from_packet("tei", LIVE_TEI)

        state.update_from_packet("tei", {"TE": []})

        assert state.active_event_ids == [610, 612, 601]


class TestEventIds:
    def test_ids_are_read_as_the_client_reads_them(self, state, clock):
        # parse_SEI: int(a.EID); an id of 0 names no event
        state.update_from_packet("sei", {"E": [{"EID": "83", "RS": 60}, {"EID": 60.0, "RS": 60}, {"RS": 60}]})

        assert state.active_event_ids == [83, 60]

    def test_a_see_looks_the_id_up_as_sent(self, state, clock):
        # parse_SEE: _activeEvents.get(e.EID), no int()
        state.update_from_packet("sei", {"E": [{"EID": 83, "RS": 60}]})

        state.update_from_packet("see", {"EID": "83"})
        assert state.active_event_ids == [83]
        state.update_from_packet("see", {"EID": 83.0})
        assert state.active_event_ids == []


class TestRepliesWithEvents:
    def test_a_faction_join_applies_its_sei(self, state, clock):
        state.update_from_packet("fjf", {"FID": 1, "kpi": {}, "sei": {"E": [{"EID": 3, "RS": 60, "LID": 2, "UL": 1}]}})

        assert state.active_event_ids == [3]
        assert (state.get_event_league_id(3), state.is_event_unlocked(3)) == (2, True)
        assert state.get_last_packet_time("sei") is not None

    def test_a_bounty_hunter_skip_applies_its_coins_and_sei(self, state, clock):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}})

        state.update_from_packet("bst", {"gcu": {"C1": 120, "C2": 30}, "sei": {"E": [{"EID": 25, "RS": 600}]}})

        player = state.get_local_player()
        assert (player.coins, player.rubies) == (120, 30)
        assert state.active_event_ids == [25]
        assert state.get_last_packet_time("bst") is not None
