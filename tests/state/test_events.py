"""GameState event tracking: typed events from sei and tei, their ends, pep scores and the event callbacks."""

import math
import threading
from typing import Any

import pytest
from pydantic import ValidationError

from empire_core.events.models import (
    AlienInvasionEvent,
    BerimondEvent,
    EventPart,
    FactionInvasionEvent,
    GlobalEffectBuffEvent,
    GlobalEffectEvent,
    KingdomsLeagueEvent,
    LongTermPointEvent,
    NomadInvasionEvent,
    PointEvent,
    RaidBossEvent,
    SamuraiInvasionEvent,
    SpecialEvent,
    TempServerEvent,
)
from empire_core.gamedata.ids.events import Event
from empire_core.state import events as event_state

DAY = 86400

# Entries as the login data had them live, ids and names left out
LIVE_TEI: dict[str, Any] = {
    "TE": [
        {"TRID": 610, "GE": [[2, 47884, 10.0]], "SGE": []},
        {"TRID": 612, "GEB": [{"GEID": 2, "BV": 50.0, "C2": 2500}]},
        {"TRID": 601, "KLRT": 42, "KLRD": 1, "RSID": 7, "KLARE": 1, "KLLID": 1},
    ]
}
LIVE_RED_ALIEN: dict[str, Any] = {
    "EID": 103,
    "RS": 51544,
    "SP": {"OP": 0, "OR": -1, "LID": 4, "RSID": 2},
    "A": {"OP": 0, "OR": 0, "LID": 1, "RSID": 2},
    "SZID": 203,
    "TZID": 188,
    "KL": 1,
    "KLCP": 0,
    "KLAP": 190426,
    "CRE": 1,
    "RCKS": ["GTO", "STO", "KM"],
    "EASE": 1,
    "RCSC": 0,
    "RCHC": 0,
    "EDID": -1,
}
LIVE_RAID: dict[str, Any] = {
    "EID": 133,
    "RS": 582484,
    "LRSI": 1,
    "RSID": 5,
    "DRI": 11,
    "SP": {"OP": 0},
    "A": {"OP": 0, "LID": 1, "SDI": 14},
    "BLPP": 0,
    "RBIDS": [1, 2, 3],
    "LID": 1,
}
LIVE_SEI: dict[str, Any] = {
    "E": [
        {"EID": 46, "RS": 2648884},
        LIVE_RAID,
        {
            "EID": 83,
            "RS": 1259344,
            "LRSI": 19,
            "OP": [0],
            "OR": [0],
            "UE": [103, 80, 72],
            "LID": 3,
            "SID": 9,
            "RSID": 74,
        },
        LIVE_RED_ALIEN,
        {"EID": 106, "RS": 278944, "RD": 40743, "TSID": 21, "RSID": 11, "IPS": 0, "ICSE": False},
        {"EID": 60, "RS": 60244, "OP": [0], "OR": [-1], "LID": 7, "PET": 15, "RSID": 9, "SC": 1},
    ]
}


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(event_state, "_clock", lambda: now[0])
    return now


def part(**fields: Any) -> EventPart:
    return EventPart.model_validate(fields)


def settle(state) -> None:
    """Wait until every callback queued so far has run."""
    done = threading.Event()
    state._dispatch_callback(done.set)
    assert done.wait(5)


def ids(state) -> list[int]:
    return list(state.get_events())


class TestTypedEvents:
    def test_the_live_login_gives_each_event_its_model(self, state, clock):
        state.update_from_packet("gbd", {"sei": LIVE_SEI, "tei": LIVE_TEI})

        events = state.get_events()
        assert list(events) == [610, 612, 601, 46, 133, 83, 103, 106, 60]
        kinds = {eid: type(event) for eid, event in events.items()}
        assert kinds == {
            610: GlobalEffectEvent,
            612: GlobalEffectBuffEvent,
            601: KingdomsLeagueEvent,
            46: SpecialEvent,
            133: RaidBossEvent,
            83: LongTermPointEvent,
            103: AlienInvasionEvent,
            106: TempServerEvent,
            60: PointEvent,
        }
        assert events[46].event is Event.EQUIPMENT_ENHANCER and events[46].end_time == 1000 + 2648884
        assert [e for e, event in events.items() if event.is_trigger] == [610, 612, 601]

    def test_a_score_event(self, state, clock):
        state.update_from_packet("sei", LIVE_SEI)

        point = state.get_event(Event.POINT_EVENT)
        assert isinstance(point, PointEvent)
        assert (point.league_id, point.own_rank, point.own_points, point.point_event_type) == (7, -1, 0, 15)
        assert (point.difficulty_id, point.difficulty_scaling, point.point_scale) == (0, False, 1)
        long_term = state.get_event(83)
        assert isinstance(long_term, LongTermPointEvent)
        assert (long_term.league_id, long_term.reward_set_id, long_term.leaderboard_reward_set_id) == (3, 74, 19)
        assert (long_term.own_rank, long_term.upcoming_event_ids) == (0, (103, 80, 72))

    def test_an_invasion(self, state, clock):
        state.update_from_packet("sei", {"E": [LIVE_RED_ALIEN]})

        alien = state.get_event(Event.RED_ALLIANCE_ALIEN_INVASION)
        assert isinstance(alien, AlienInvasionEvent)
        assert alien.parts == {
            "SP": part(league_id=4, own_rank=-1, reward_set_id=2),
            "A": part(league_id=1, own_rank=-1, sub_type=1, reward_set_id=2),
        }
        assert (alien.target_zone_id, alien.source_zone_id, alien.use_reroll) == (188, 203, True)
        assert (alien.reroll_currency_keys, alien.difficulty_id, alien.kingdoms_league_mode) == (
            ("GTO", "STO", "KM"),
            -1,
            True,
        )

    def test_the_raid_boss(self, state, clock):
        state.update_from_packet("sei", {"E": [LIVE_RAID]})

        raid = state.get_event(Event.ALLIANCE_RAIDBOSS_EVENT)
        assert isinstance(raid, RaidBossEvent)
        assert raid.score == part(league_id=1, leaderboard_reward_set_id=1, reward_set_id=5)
        assert (raid.league_id, raid.subdivision_id, raid.division_round_id) == (1, 14, 11)
        assert (raid.raid_boss_ids, raid.boss_level_points, raid.kingdoms_league_mode) == ((1, 2, 3), 0, False)

    def test_the_temporary_server(self, state, clock):
        state.update_from_packet("sei", LIVE_SEI)

        server = state.get_event(Event.TEMP_SERVER)
        assert isinstance(server, TempServerEvent)
        assert (server.daily_reset_time, server.setting_id, server.castle_bought, server.is_cross_play) == (
            1000 + 40743,
            21,
            False,
            False,
        )

    def test_berimond(self, state, clock):
        entry = {"EID": 3, "RS": 600, "LID": 2, "UL": 1, "RSID": 4, "FN": {"FID": 1, "MC": 9, "PMT": 30, "PMS": 2}}
        state.update_from_packet("sei", {"E": [entry]})

        berimond = state.get_event(Event.FACTION)
        assert isinstance(berimond, BerimondEvent)
        assert (berimond.league_id, berimond.unlocked, berimond.reward_set_id) == (2, True, 4)
        assert (berimond.faction_id, berimond.main_camp_id, berimond.faction_protection_status) == (1, 9, 2)
        assert (berimond.faction_protection_end, berimond.own_rank) == (1030.0, -1)

    def test_the_trigger_events(self, state, clock):
        state.update_from_packet("tei", LIVE_TEI)

        effects, boost, league = (state.get_event(e) for e in (610, 612, 601))
        assert isinstance(effects, GlobalEffectEvent) and isinstance(boost, GlobalEffectBuffEvent)
        assert [(e.effect_id, e.end_time, e.strength, e.seen) for e in effects.effects] == [
            (2, 1000 + 47884, 10, False)
        ]
        assert [(b.effect_id, b.boost_value, b.cost) for b in boost.boosts] == [(2, 50.0, 2500)]
        assert isinstance(league, KingdomsLeagueEvent)
        assert (league.remaining_days, league.original_days, league.reward_set_id) == (1, 42, 7)
        assert (league.has_alliance_ranking, league.league_type_id, league.end_time) == (True, 1, math.inf)
        assert league.remaining_seconds(clock[0]) == DAY

    def test_only_events_whose_class_reads_it_take_the_season_mode(self, state, clock):
        # The raid boss, temporary server and donation VOs' parseParamObject skip ASpecialEventVO's
        state.update_from_packet("sei", {"E": [{"EID": eid, "RS": 60, "KL": 1} for eid in (133, 106, 123, 103, 46)]})

        modes = {eid: event.kingdoms_league_mode for eid, event in state.get_events().items()}
        assert modes == {133: False, 106: False, 123: False, 103: True, 46: True}

    def test_the_models_never_change(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 83, "RS": 60, "LID": 3}]})
        before = state.get_events()
        event = before[83]

        state.update_from_packet("sei", {"E": [{"EID": 83, "RS": 60, "LID": 4}, {"EID": 60, "RS": 60}]})

        assert list(before) == [83] and before[83] is event and event.league_id == 3
        with pytest.raises(ValidationError):
            event.league_id = 5  # type: ignore[misc]
        assert state.get_event(83).league_id == 4


class TestReadOnlySnapshots:
    def test_a_snapshot_cannot_be_changed_and_changes_nothing(self, state, clock):
        entry: dict[str, Any] = {"EID": 103, "RS": 60, "SP": {"LID": 4}, "RCKS": ["GTO"]}
        state.update_from_packet("sei", {"E": [entry]})
        event = state.get_event(103)

        entry["SP"]["LID"] = 9
        for change in (
            lambda: event.raw.update(X=1),
            lambda: event.raw["SP"].update(LID=9),
            lambda: event.parts.update(SP=part()),
            lambda: event.parts.pop("SP"),
        ):
            with pytest.raises(TypeError):
                change()
        state.update_from_packet("sei", {"E": [{"EID": 103, "A": {"LID": 2}}]})

        assert event.raw == {"EID": 103, "RS": 60, "SP": {"LID": 4}, "RCKS": ("GTO",)} and list(event.parts) == ["SP"]
        later = state.get_event(103)
        assert (later.raw["SP"], later.parts["SP"].league_id, list(later.parts)) == ({"LID": 4}, 4, ["SP", "A"])

    def test_an_old_snapshot_stays_after_a_pep(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 80, "RS": 60}]})
        before = state.get_event(80)

        state.update_from_packet("pep", {"EID": 80, "OR": [3, 9], "OP": [100, 2000]})

        assert before.parts["SP"].own_points == 0 and state.get_event(80).parts["SP"].own_points == 100


class TestMerging:
    def test_an_entry_is_read_over_the_running_event(self, state, clock):
        # Each field the client reads only when sent keeps its value; unguarded ones are read again
        state.update_from_packet("sei", {"E": [{"EID": 83, "RS": 60, "LID": 3, "OR": [5], "RSID": 74, "X": 1}]})

        state.update_from_packet("sei", {"E": [{"EID": 83, "OP": [40]}]})

        event = state.get_event(83)
        assert (event.league_id, event.own_rank, event.own_points, event.reward_set_id) == (3, 5, 40, 0)
        assert event.end_time == 1060.0
        assert event.raw == {"EID": 83, "RS": 60, "LID": 3, "OR": (5,), "RSID": 74, "X": 1, "OP": (40,)}

    def test_the_difficulty_is_zero_without_scaling(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 103, "RS": 60, "EASE": 1, "EDID": 2}]})
        assert state.get_event(103).difficulty_id == 2

        state.update_from_packet("sei", {"E": [{"EID": 103, "EASE": 1}]})
        assert state.get_event(103).difficulty_id == 2
        state.update_from_packet("sei", {"E": [{"EID": 103}]})
        assert (state.get_event(103).difficulty_id, state.get_event(103).difficulty_scaling) == (0, False)

    def test_samurai_and_berimond_invasion_parts_are_rebuilt_every_time(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 80, "RS": 60, "SP": {"LID": 4}, "A": {"LID": 2}}]})

        state.update_from_packet("sei", {"E": [{"EID": 80, "SP": {"OR": 3}}, {"EID": 85, "RS": 60, "FR": {"LID": 3}}]})

        samurai = state.get_event(80)
        assert isinstance(samurai, SamuraiInvasionEvent)
        assert samurai.parts == {"SP": part(own_rank=3), "A": part(sub_type=1)}
        assert "A" not in samurai.raw
        faction = state.get_event(85)
        assert isinstance(faction, FactionInvasionEvent)
        assert {key: (part.league_id, part.sub_type) for key, part in faction.parts.items()} == {
            "FB": (1, 2),
            "FR": (3, 3),
            "A": (1, 1),
        }

    def test_alien_invasion_parts_are_rebuilt_only_when_sent(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 71, "RS": 60, "SP": {"LID": 4, "OR": 2}}]})

        state.update_from_packet("sei", {"E": [{"EID": 71, "A": {"LID": 2}}]})

        alien = state.get_event(71)
        assert alien.parts == {"SP": part(league_id=4, own_rank=2), "A": part(league_id=2, sub_type=1)}
        assert alien.raw["SP"] == {"LID": 4, "OR": 2}

    def test_the_nomad_invasion_and_its_khan_camp(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 72, "RS": 60, "RSID": 3, "ACE": 1}]})
        nomad = state.get_event(72)
        assert isinstance(nomad, NomadInvasionEvent)
        assert nomad.parts == {"SP": part(), "A": part(), "AC": part(sub_type=16, reward_set_id=3)}

        camp = {"LID": 2, "OP": 7, "AR": 5, "PCRP": 6, "PTRP": 9}
        state.update_from_packet("sei", {"E": [{"EID": 72, "ACE": "1", "AC": camp}]})

        nomad = state.get_event(72)
        assert nomad.parts["AC"] == part(league_id=2, own_points=7, sub_type=16)
        assert (nomad.alliance_rage, nomad.player_rage, nomad.player_total_rage) == (5, 6, 9)

    def test_the_khan_camp_needs_its_flag(self, state, clock):
        # parseData reads AC only under 1==n.ACE
        state.update_from_packet("sei", {"E": [{"EID": 72, "RS": 60, "AC": {"AR": 5, "PCRP": 6, "ACID": 3}}]})

        nomad = state.get_event(72)
        assert (nomad.alliance_rage, nomad.player_rage, nomad.khan_camp_id, list(nomad.parts)) == (
            0,
            0,
            None,
            ["SP", "A"],
        )

    def test_berimond_starts_its_score_over_with_each_entry(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 3, "RS": 60, "LID": 2}]})
        state.update_from_packet("pep", {"EID": 3, "OR": [4], "OP": [900]})
        assert (state.get_event(3).own_rank, state.get_event(3).own_points) == (4, 900)

        state.update_from_packet("sei", {"E": [{"EID": 3}]})

        berimond = state.get_event(3)
        assert (berimond.own_rank, berimond.own_points, berimond.league_id, berimond.unlocked) == (-1, 0, 2, False)

    def test_a_removed_event_added_again_starts_over(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 71, "RS": 60, "LID": 3, "SP": {"LID": 4}}]})
        state.update_from_packet("see", {"EID": 71})

        state.update_from_packet("sei", {"E": [{"EID": 71, "RS": 60}]})

        assert (state.get_event(71).league_id, state.get_event(71).parts) == (1, {})


class TestPoints:
    def test_a_score_event_takes_the_first_of_each(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 60, "RS": 60}]})

        state.update_from_packet("pep", {"EID": 60, "OR": [12, 1], "OP": [3400], "PT": [9000]})

        point = state.get_event(60)
        assert (point.own_rank, point.own_points, point.max_points) == (12, 3400, 9000)
        assert state.get_last_packet_time("pep") is not None

    def test_an_invasion_gives_one_to_each_part(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 80, "RS": 60}, {"EID": 85, "RS": 60}]})

        state.update_from_packet("pep", {"EID": 80, "OR": [3, 9], "OP": [100, 2000], "PT": [1, 2]})
        state.update_from_packet("pep", {"EID": 85, "OR": [1, 2, 3], "OP": [10, 20, 30], "PT": [7, 8, 9]})

        samurai, faction = state.get_event(80), state.get_event(85)
        assert [(p.own_rank, p.own_points, p.max_points) for p in samurai.parts.values()] == [(3, 100, 0), (9, 2000, 0)]
        assert [(p.own_rank, p.own_points, p.max_points) for p in faction.parts.values()] == [
            (1, 10, 7),
            (2, 20, 8),
            (3, 30, 9),
        ]

    def test_the_raid_boss_takes_yours_and_your_alliances(self, state, clock):
        state.update_from_packet("sei", {"E": [LIVE_RAID]})

        state.update_from_packet("pep", {"EID": 133, "OR": [8, 2], "OP": [50, 700], "BLPP": 40})

        raid = state.get_event(133)
        assert (raid.score.own_rank, raid.score.own_points) == (8, 50)
        assert (raid.alliance_rank, raid.alliance_points, raid.boss_level_points) == (2, 700, 40)

    def test_points_for_an_event_not_running_or_without_a_score_change_nothing(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 46, "RS": 60}, {"EID": 60, "RS": 60}]})
        before = state.get_events()

        state.update_from_packet("pep", {"EID": 46, "OR": [1], "OP": [2]})
        state.update_from_packet("pep", {"EID": "60", "OR": [1], "OP": [2]})
        state.update_from_packet("pep", {"EID": 99, "OR": [1], "OP": [2]})

        assert state.get_events() == before


class TestTriggerEvents:
    def test_the_login_tei_is_applied_before_its_sei(self, state, clock):
        state.update_from_packet("gbd", {"sei": {"E": [LIVE_RED_ALIEN]}, "tei": LIVE_TEI})

        assert ids(state) == [610, 612, 601, 103]
        assert state.get_last_packet_time("tei") is not None

    def test_global_effects_end_with_their_last_effect(self, state, clock):
        tei = {"TE": [{"TRID": 610, "GE": [[2, 100, 10], [3, "300", -1], [4, None, 1]], "SGE": [3]}, {"TRID": 612}]}
        state.update_from_packet("tei", tei)

        effects = state.get_event(610)
        assert effects.end_time == state.get_event(612).end_time == 1300.0
        assert [(e.effect_id, e.end_time, e.seen) for e in effects.effects] == [
            (2, 1100.0, False),
            (3, 1300.0, True),
            (4, 1000.0, False),
        ]
        clock[0] = 1299.0
        assert ids(state) == [610, 612]
        clock[0] = 1300.0
        assert ids(state) == []

    def test_effects_without_seen_ones_are_not_read(self, state, clock):
        # GlobalEffectEventVO.parseParamObject calls SGE.indexOf, which throws without an SGE
        state.update_from_packet("tei", {"TE": [{"TRID": 610, "GE": [[2, 100, 1]], "SGE": [2]}]})

        state.update_from_packet("tei", {"TE": [{"TRID": 610, "GE": [[2, 500, 1]]}, {"TRID": 611, "GE": [None]}]})

        assert ids(state) == [610] and state.get_event(610).end_time == 1100.0

    def test_a_global_effect_event_without_effects_has_ended(self, state, clock):
        state.update_from_packet("tei", {"TE": [{"TRID": 610, "GE": [], "SGE": []}]})

        assert ids(state) == []

    def test_the_boost_event_keeps_the_end_it_was_given(self, state, clock):
        # GlobalEffectBuffEventVO takes 610's time left as it arrives, 0 without 610
        state.update_from_packet(
            "tei", {"TE": [{"TRID": 612, "GEB": []}, {"TRID": 610, "GE": [[2, 100, 1]], "SGE": []}]}
        )
        assert ids(state) == [610]

        state.update_from_packet("tei", {"TE": [{"TRID": 612, "GEB": []}]})
        state.update_from_packet("tei", {"TE": [{"TRID": 610, "GE": [[2, 500, 1]], "SGE": []}]})

        assert (state.get_event(610).end_time, state.get_event(612).end_time) == (1500.0, 1100.0)

    def test_the_kingdoms_league_runs_while_it_has_days_left(self, state, clock):
        state.update_from_packet("tei", {"TE": [{"TRID": 601, "KLRD": 5}]})

        clock[0] += 30 * DAY

        assert ids(state) == [601]
        assert state.get_event(601).remaining_seconds(clock[0]) == 5 * DAY

    def test_on_its_last_day_it_ends_with_the_season_event(self, state, clock):
        state.update_from_packet("gbd", {"sei": {"E": [LIVE_RED_ALIEN]}, "tei": LIVE_TEI})
        assert state.get_event(601).end_time == 1000.0 + 51544

        clock[0] += 51544

        assert 601 not in ids(state) and 103 not in ids(state)

    def test_on_its_last_day_without_a_season_event_it_keeps_running(self, state, clock):
        state.update_from_packet("tei", {"TE": [{"TRID": 601, "KLRD": 1}]})
        state.update_from_packet("sei", {"E": [{"EID": 103, "RS": 60, "KL": 0}]})

        clock[0] += 30 * DAY

        assert ids(state) == [601]

    def test_with_no_days_left_and_no_season_event_it_has_ended(self, state, clock):
        state.update_from_packet("tei", {"TE": [{"TRID": 601, "KLRT": 42}]})

        assert ids(state) == []

    def test_a_season_event_ending_ends_the_league_on_its_last_day(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 103, "RS": 60, "KL": 1}]})
        state.update_from_packet("tei", {"TE": [{"TRID": 601, "KLRD": 0}]})
        assert ids(state) == [103, 601]

        state.update_from_packet("see", {"EID": 103})

        assert ids(state) == []

    def test_a_tee_ends_its_trigger_event(self, state, clock):
        state.update_from_packet("tei", LIVE_TEI)

        state.update_from_packet("tee", {"TRID": "612"})
        state.update_from_packet("tee", {})
        state.update_from_packet("tee", {"TRID": 0})

        assert ids(state) == [610, 601]
        assert state.get_last_packet_time("tee") is not None

    def test_a_see_ends_a_trigger_event_too(self, state, clock):
        state.update_from_packet("tei", LIVE_TEI)

        state.update_from_packet("see", {"EID": 601})

        assert ids(state) == [610, 612]

    def test_an_empty_tei_changes_nothing(self, state, clock):
        state.update_from_packet("tei", LIVE_TEI)

        state.update_from_packet("tei", {"TE": []})

        assert ids(state) == [610, 612, 601]


class TestEndsAndIds:
    def test_an_event_ends_when_its_time_runs_out(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 3, "RS": 60}, {"EID": 60, "RS": "600"}]})

        clock[0] += 60

        assert ids(state) == [60]
        assert (state.is_event_active(Event.FACTION), state.is_event_active(60)) == (False, True)
        assert state.get_event(60).remaining_seconds(clock[0]) == 540

    def test_an_event_never_given_an_end_has_ended(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 3}]})

        assert ids(state) == []

    def test_a_later_entry_without_an_end_keeps_it(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 3, "RS": 60}]})

        state.update_from_packet("sei", {"E": [{"EID": 3, "RS": 0}]})

        assert state.get_event(3).end_time == 1060.0

    def test_ids_are_read_as_the_client_reads_them(self, state, clock):
        # parse_SEI: int(a.EID); an id of 0 names no event
        state.update_from_packet("sei", {"E": [{"EID": "83", "RS": 60}, {"EID": 60.0, "RS": 60}, {"RS": 60}, None]})

        assert ids(state) == [83, 60]

    def test_a_see_looks_the_id_up_as_sent(self, state, clock):
        # parse_SEE: _activeEvents.get(e.EID), no int()
        state.update_from_packet("sei", {"E": [{"EID": 83, "RS": 60}]})

        state.update_from_packet("see", {"EID": "83"})
        assert ids(state) == [83]
        state.update_from_packet("see", {"EID": 83.0})
        assert ids(state) == []


class TestRepliesWithEvents:
    def test_a_faction_join_applies_its_sei(self, state, clock):
        state.update_from_packet("fjf", {"FID": 1, "kpi": {}, "sei": {"E": [{"EID": 3, "RS": 60, "LID": 2, "UL": 1}]}})

        berimond = state.get_event(3)
        assert (berimond.league_id, berimond.unlocked) == (2, True)
        assert state.get_last_packet_time("sei") is not None

    def test_a_bounty_hunter_skip_applies_its_coins_and_sei(self, state, clock):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}})

        state.update_from_packet("bst", {"gcu": {"C1": 120, "C2": 30}, "sei": {"E": [{"EID": 25, "RS": 600}]}})

        player = state.get_local_player()
        assert (player.coins, player.rubies) == (120, 30)
        assert ids(state) == [25]
        assert state.get_last_packet_time("bst") is not None


class TestCallbacks:
    def test_added_removed_and_updated(self, state, clock):
        seen: list[tuple[str, Any]] = []
        state.on_event_added(lambda event: seen.append(("added", event.event_id)))
        state.on_event_removed(lambda event: seen.append(("removed", event.event_id)))
        state.on_events_updated(lambda events: seen.append(("updated", list(events))))

        state.update_from_packet("sei", {"E": [{"EID": 3, "RS": 60}, {"EID": 60, "RS": 120}]})
        state.update_from_packet("sei", {"E": [{"EID": 3, "LID": 2}]})
        state.update_from_packet("see", {"EID": 60})
        clock[0] += 60
        state.update_from_packet("gpi", {"PID": 7})
        settle(state)

        assert seen == [
            ("added", 3),
            ("added", 60),
            ("updated", [3, 60]),
            ("updated", [3, 60]),
            ("removed", 60),
            ("removed", 3),
        ]

    def test_a_pep_removes_ended_events_before_it_updates(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 3, "RS": 10}, {"EID": 60, "RS": 60}]})
        seen: list[Any] = []
        state.on_event_removed(lambda event: seen.append(("removed", event.event_id)))
        state.on_events_updated(lambda events: seen.append(("updated", list(events))))
        clock[0] += 10

        state._handle_pep({"EID": 60, "OR": [1], "OP": [5]})
        settle(state)

        assert seen == [("removed", 3), ("updated", [60])]

    def test_an_empty_tei_fires_nothing_and_a_pep_updates(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 60, "RS": 60}]})
        seen: list[Any] = []
        state.on_events_updated(seen.append)

        state.update_from_packet("tei", {"TE": []})
        state.update_from_packet("pep", {"EID": 60, "OR": [1], "OP": [5]})
        settle(state)

        assert [events[60].own_points for events in seen] == [5]

    def test_an_event_added_and_ended_at_once_fires_both(self, state, clock):
        seen: list[str] = []
        state.on_event_added(lambda event: seen.append("added"))
        state.on_event_removed(lambda event: seen.append("removed"))

        state.update_from_packet("tei", {"TE": [{"TRID": 610, "GE": []}]})
        settle(state)

        assert seen == ["added", "removed"]

    def test_a_removed_callback_no_longer_fires(self, state, clock):
        seen: list[Any] = []
        state.on_event_added(seen.append)
        state.on_event_removed(seen.append)
        state.on_events_updated(seen.append)
        state.remove_event_added_callback(seen.append)
        state.remove_event_removed_callback(seen.append)
        state.remove_events_updated_callback(seen.append)

        state.update_from_packet("sei", {"E": [{"EID": 60, "RS": 60}]})
        state.update_from_packet("see", {"EID": 60})
        settle(state)

        assert seen == []


class TestFreshnessAndReset:
    def test_every_event_packet_stamps_the_events(self, state, clock):
        assert state.get_events_last_updated() is None

        packets: list[tuple[str, dict[str, Any]]] = [("sei", {}), ("tei", {}), ("see", {}), ("tee", {}), ("pep", {})]
        for cmd, payload in packets:
            state._events_updated_at = None
            state.update_from_packet(cmd, payload)
            assert state.get_events_last_updated() is not None, cmd

    def test_a_reset_forgets_the_events(self, state, clock):
        state.update_from_packet("sei", {"E": [{"EID": 60, "RS": 60}]})
        removed: list[Any] = []
        state.on_event_removed(removed.append)

        state.reset()
        settle(state)

        assert (state.get_events(), state.get_events_last_updated(), removed) == ({}, None, [])
