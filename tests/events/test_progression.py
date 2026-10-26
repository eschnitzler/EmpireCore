"""Event progress: the daimyo (gda, gdc, gdw), alliance invasion camps (aic), part-paid unlocks (ule), season
maps (sje), event difficulties (sede) and the special servers' last runs (gpr)."""

from __future__ import annotations

import pytest

from empire_core.enums import Kingdom
from empire_core.events import (
    AllianceCampInfoResponse,
    DaimyoAreasResponse,
    DaimyoContractsResponse,
    DaimyoWarEffortsResponse,
    NomadInvasionEvent,
    PreviousHorizonRun,
    PreviousOuterRealmsRun,
    PreviousSpecialServerRuns,
    SamuraiInvasionEvent,
    SelectEventDifficultyRequest,
    UnlockEventRequest,
)
from empire_core.exceptions import CommandError, EventNotRunningError
from empire_core.gamedata import EventDifficultyId, PartPayPriceId
from empire_core.gamedata.ids.events import Event
from empire_core.protocol.base import parse_response
from empire_core.state.manager import GameState
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

# Shaped as SamuraiDaimyoAreaVO.parseServerData reads a gda entry
CASTLE_RANK_2 = {"PX": 300, "PY": 400, "R": 2, "L": 3, "SP": 150, "CD": 600, "CDC": 1, "DDCID": 17}
CASTLE_RANK_1 = {"PX": 310, "PY": 410, "R": 1, "L": 5, "SP": 0, "CD": 0, "CDC": 0, "DDCID": -1}
TOWNSHIP = {"PX": 320, "PY": 420, "R": 1, "L": 1, "SP": 20, "CD": 0, "CDC": 0, "DDCID": -1}

NOMAD_ENTRY = {"EID": 72, "RS": 600, "ACE": 1, "AC": {"AR": 5, "PCRP": 1, "PTRP": 2, "ACID": 9}}


def samurai_state() -> GameState:
    state = logged_in_state()
    state.update_from_packet("sei", {"E": [{"EID": 80, "RS": 600}]})
    return state


def samurai_client(script=None):
    client = make_client(script or {}, state=GameState())
    client._on_packet(xt_packet("sei", {"E": [{"EID": 80, "RS": 600}]}))
    return client


class TestDaimyoAreas:
    def test_the_areas_are_read_by_rank(self):
        areas = parse_response("gda", {"DC": [CASTLE_RANK_2, CASTLE_RANK_1], "DT": [TOWNSHIP]})

        assert isinstance(areas, DaimyoAreasResponse)
        assert areas.castles is not None and areas.townships is not None
        assert [area.rank for area in areas.castles] == [1, 2]
        second = areas.castles[1]
        assert (second.x, second.y, second.level, second.shogun_points, second.cooldown_count) == (300, 400, 3, 150, 1)
        assert second.scaling_camp_id == 17
        assert 590 < second.remaining_cooldown_seconds() <= 600

    def test_a_list_not_sent_stays(self):
        state = samurai_state()
        state.update_from_packet("gda", {"DC": [CASTLE_RANK_1], "DT": [TOWNSHIP]})
        state.update_from_packet("gda", {"DC": [CASTLE_RANK_2]})

        event = state.get_event(Event.SAMURAI_INVASION)
        assert isinstance(event, SamuraiInvasionEvent) and event.daimyo_areas is not None
        assert [area.rank for area in event.daimyo_areas.castles or ()] == [2]
        assert [area.x for area in event.daimyo_areas.townships or ()] == [320]
        state.shutdown()

    def test_an_empty_list_clears_it(self):
        # parseGDA: if(e.DC) holds for an empty array
        state = samurai_state()
        state.update_from_packet("gda", {"DC": [CASTLE_RANK_1], "DT": [TOWNSHIP]})
        state.update_from_packet("gda", {"DC": []})

        event = state.get_event(Event.SAMURAI_INVASION)
        assert isinstance(event, SamuraiInvasionEvent) and event.daimyo_areas is not None
        assert event.daimyo_areas.castles == ()
        assert [area.x for area in event.daimyo_areas.townships or ()] == [320]
        state.shutdown()

    def test_get_needs_the_samurai_invasion(self):
        client = make_client(state=GameState())
        with pytest.raises(EventNotRunningError):
            client.events.get_daimyo_areas()
        assert conn(client).request_payloads == []

    def test_get_sends_an_empty_gda(self):
        client = samurai_client({"gda": xt_packet("gda", {"DC": [CASTLE_RANK_1]})})

        areas = client.events.get_daimyo_areas()

        assert conn(client).request_payloads == [("gda", {})]
        assert areas.townships is None

    def test_a_refusal_raises(self):
        client = samurai_client({"gda": xt_packet("gda", None, error_code=1)})
        with pytest.raises(CommandError):
            client.events.get_daimyo_areas()


class TestDaimyoContracts:
    def test_the_contracts_are_read_by_id(self):
        contracts = parse_response("gdc", {"DCC": [[5, 900], [2, 100]], "DTC": [[1, 0]]})

        assert isinstance(contracts, DaimyoContractsResponse)
        assert [(row.contract_id, row.points) for row in contracts.castle_contracts or ()] == [(2, 100), (5, 900)]
        assert [row.contract_id for row in contracts.township_contracts or ()] == [1]

    def test_the_state_keeps_them_on_the_event(self):
        state = samurai_state()
        state.update_from_packet("gdc", {"DCC": [[2, 100]], "DTC": [[1, 0]]})
        state.update_from_packet("gdc", {"DTC": [[3, 40]]})

        event = state.get_event(Event.SAMURAI_INVASION)
        assert isinstance(event, SamuraiInvasionEvent) and event.daimyo_contracts is not None
        assert [row.contract_id for row in event.daimyo_contracts.castle_contracts or ()] == [2]
        assert [row.points for row in event.daimyo_contracts.township_contracts or ()] == [40]
        state.shutdown()

    def test_an_empty_list_clears_it(self):
        # parseGDC: if(e.DCC) holds for an empty array
        state = samurai_state()
        state.update_from_packet("gdc", {"DCC": [[2, 100]], "DTC": [[1, 0]]})
        state.update_from_packet("gdc", {"DCC": []})

        event = state.get_event(Event.SAMURAI_INVASION)
        assert isinstance(event, SamuraiInvasionEvent) and event.daimyo_contracts is not None
        assert event.daimyo_contracts.castle_contracts == ()
        assert [row.contract_id for row in event.daimyo_contracts.township_contracts or ()] == [1]
        state.shutdown()

    def test_get_sends_an_empty_gdc(self):
        client = samurai_client({"gdc": xt_packet("gdc", {"DCC": []})})
        client.events.get_daimyo_contracts()
        assert conn(client).request_payloads == [("gdc", {})]


class TestDaimyoWarEfforts:
    PAYLOAD = {"OR": 4, "TWE": 1200, "CWES": [[1, 300], [2, 700]], "TWES": [[1, 200]]}

    def test_the_efforts_are_read_by_rank(self):
        efforts = parse_response("gdw", self.PAYLOAD)

        assert isinstance(efforts, DaimyoWarEffortsResponse)
        assert (efforts.own_rank, efforts.own_points) == (4, 1200)
        assert efforts.castle_efforts == {1: 300, 2: 700}
        assert efforts.township_efforts == {1: 200}

    def test_the_state_keeps_them_on_the_event(self):
        state = samurai_state()
        state.update_from_packet("gdw", self.PAYLOAD)
        event = state.get_event(Event.SAMURAI_INVASION)
        assert isinstance(event, SamuraiInvasionEvent) and event.daimyo_war_efforts is not None
        assert event.daimyo_war_efforts.own_points == 1200
        state.shutdown()

    def test_kept_across_an_event_update(self):
        state = samurai_state()
        state.update_from_packet("gdw", self.PAYLOAD)
        state.update_from_packet("sei", {"E": [{"EID": 80, "RS": 500}]})
        event = state.get_event(Event.SAMURAI_INVASION)
        assert isinstance(event, SamuraiInvasionEvent) and event.daimyo_war_efforts is not None
        state.shutdown()

    def test_an_error_reply_is_not_kept(self):
        state = samurai_state()
        state.update_from_packet("gdw", self.PAYLOAD, error_code=1)
        event = state.get_event(Event.SAMURAI_INVASION)
        assert isinstance(event, SamuraiInvasionEvent) and event.daimyo_war_efforts is None
        state.shutdown()

    def test_get_sends_an_empty_gdw(self):
        client = samurai_client({"gdw": xt_packet("gdw", self.PAYLOAD)})
        assert client.events.get_daimyo_war_efforts().castle_efforts[2] == 700
        assert conn(client).request_payloads == [("gdw", {})]


class TestAllianceCamp:
    def test_the_push_is_read(self):
        push = parse_response("aic", {"AC": [{"EID": 72, "ACID": 11, "AR": 40}]})
        assert isinstance(push, AllianceCampInfoResponse)
        assert [(camp.event_id, camp.camp_id, camp.alliance_rage) for camp in push.camps] == [(72, 11, 40)]
        assert push.camps[0].event_id is Event.NOMAD_INVASION_72

    def test_updates_the_nomad_invasion(self):
        state = logged_in_state()
        state.update_from_packet("sei", {"E": [NOMAD_ENTRY]})

        state.update_from_packet("aic", {"AC": [{"EID": 72, "ACID": 11, "AR": 40}, {"EID": 72, "ACID": 12, "AR": 1}]})

        event = state.get_event(Event.NOMAD_INVASION_72)
        assert isinstance(event, NomadInvasionEvent)
        assert (event.khan_camp_id, event.alliance_rage, event.player_rage) == (11, 40, 1)
        state.shutdown()

    def test_another_event_or_an_error_is_left_alone(self):
        state = logged_in_state()
        state.update_from_packet("sei", {"E": [NOMAD_ENTRY]})

        state.update_from_packet("aic", {"AC": [{"EID": 71, "ACID": 11, "AR": 40}]})
        state.update_from_packet("aic", {"AC": [{"EID": 72, "ACID": 11, "AR": 40}]}, error_code=1)
        state.update_from_packet("aic", {"AC": []})

        event = state.get_event(Event.NOMAD_INVASION_72)
        assert isinstance(event, NomadInvasionEvent) and (event.khan_camp_id, event.alliance_rage) == (9, 5)
        state.shutdown()


class TestUnlock:
    def test_keys_follow_the_client_order(self):
        request = UnlockEventRequest(part_price_id=PartPayPriceId(31), wood=100)
        assert list(request.to_payload()) == ["SCID", "SKID", "W", "S", "F", "C1", "IID", "SC"]

    def test_goods_from_a_castle(self):
        client = make_client()

        client.events.pay_toward_unlock(PartPayPriceId(31), wood=100, coins=50, castle_id=1234, kingdom=Kingdom.FIRE)

        assert conn(client).request_payloads == [
            ("ule", {"SCID": 1234, "SKID": 3, "W": 100, "S": 0, "F": 0, "C1": 50, "IID": 31, "SC": 0})
        ]

    @pytest.mark.parametrize(("resource", "flags"), [("wood", (1, 0, 0)), ("stone", (0, 1, 0)), ("coins", (0, 0, 1))])
    def test_a_ruby_payment_marks_its_resource(self, resource, flags):
        client = make_client()

        client.events.pay_toward_unlock(PartPayPriceId(31), ruby_payment=resource, spend_rubies=True)

        wood, stone, coins = flags
        assert conn(client).request_payloads == [
            ("ule", {"SCID": -1, "SKID": 0, "W": wood, "S": stone, "F": 0, "C1": coins, "IID": 31, "SC": 1})
        ]

    def test_a_ruby_payment_needs_consent(self):
        client = make_client()
        with pytest.raises(ValueError, match="spend_rubies"):
            client.events.pay_toward_unlock(PartPayPriceId(31), ruby_payment="wood")
        assert conn(client).request_payloads == []

    def test_consent_alone_pays_no_rubies(self):
        client = make_client()
        client.events.pay_toward_unlock(PartPayPriceId(31), stone=10, spend_rubies=True)
        assert conn(client).request_payloads[0][1]["SC"] == 0

    @pytest.mark.parametrize("kwargs", [{}, {"ruby_payment": "wood", "wood": 5, "spend_rubies": True}])
    def test_nothing_or_both_is_refused(self, kwargs):
        client = make_client()
        with pytest.raises(ValueError):
            client.events.pay_toward_unlock(PartPayPriceId(31), **kwargs)
        assert conn(client).request_payloads == []

    def test_a_refusal_raises(self):
        client = make_client({"ule": xt_packet("ule", None, error_code=176)})
        with pytest.raises(CommandError):
            client.events.pay_toward_unlock(PartPayPriceId(31), wood=1)


class TestSeasonMap:
    def test_open_sends_the_running_events_map_without_waiting(self):
        client = make_client(state=GameState())
        client._on_packet(xt_packet("sei", {"E": [{"EID": 2, "RS": 600, "UL": {"MID": 21, "UL": 1}}]}))

        client.events.open_season_map(Event.THORN_KING)

        assert any("%sje%" in frame and '"MID":21' in frame for frame in conn(client).sent)
        assert conn(client).requested == []

    def test_the_event_must_run(self):
        client = make_client(state=GameState())
        with pytest.raises(EventNotRunningError):
            client.events.open_season_map(Event.THORN_KING)


class TestDifficulty:
    def test_keys(self):
        request = SelectEventDifficultyRequest(
            event_id=80, difficulty_id=EventDifficultyId(12), unlock_with_rubies=True
        )
        assert request.to_payload() == {"EID": 80, "EDID": 12, "C2U": 1}
        assert request.event_id is Event.SAMURAI_INVASION

    def test_select(self):
        client = samurai_client()
        client.events.select_difficulty(Event.SAMURAI_INVASION, 12)
        assert conn(client).request_payloads == [("sede", {"EID": 80, "EDID": 12, "C2U": 0})]

    def test_the_ruby_unlock_needs_consent(self):
        client = samurai_client()
        with pytest.raises(ValueError, match="spend_rubies"):
            client.events.select_difficulty(Event.SAMURAI_INVASION, 12, unlock_with_rubies=True)
        assert conn(client).request_payloads == []

        client.events.select_difficulty(Event.SAMURAI_INVASION, 12, unlock_with_rubies=True, spend_rubies=True)
        assert conn(client).request_payloads == [("sede", {"EID": 80, "EDID": 12, "C2U": 1})]

    def test_consent_alone_unlocks_nothing(self):
        client = samurai_client()
        client.events.select_difficulty(Event.SAMURAI_INVASION, 0, spend_rubies=True)
        assert conn(client).request_payloads == [("sede", {"EID": 80, "EDID": 0, "C2U": 0})]

    def test_the_event_must_run(self):
        client = make_client(state=GameState())
        with pytest.raises(EventNotRunningError):
            client.events.select_difficulty(Event.SAMURAI_INVASION, EventDifficultyId(12))

    def test_a_refusal_raises(self):
        client = samurai_client({"sede": xt_packet("sede", None, error_code=1)})
        with pytest.raises(CommandError):
            client.events.select_difficulty(Event.SAMURAI_INVASION, 12)


class TestPreviousRuns:
    def test_both_runs_are_read(self):
        client = make_client({"gpr": xt_packet("gpr", {"TS": {"ET": 3600, "TSID": 4}, "ABG": {"ET": 7200, "TSID": 2}})})

        runs = client.events.get_previous_special_server_runs()

        assert conn(client).request_payloads == [("gpr", {})]
        assert runs.outer_realms is not None and runs.horizon is not None
        assert (runs.outer_realms.setting_id, runs.horizon.setting_id) == (4, 2)
        assert isinstance(runs.outer_realms, PreviousOuterRealmsRun) and isinstance(runs.horizon, PreviousHorizonRun)
        assert 3600 <= runs.outer_realms.ended_seconds_ago() < 3610

    def test_a_run_not_sent_is_none(self):
        runs = parse_response("gpr", {"TS": None})
        assert isinstance(runs, PreviousSpecialServerRuns)
        assert runs.outer_realms is None and runs.horizon is None
