"""Beyond the Horizon's Jade Desert: entry conditions (bgc), the scoring phase push (abgi), citadels (jci, ujc),
statuette conversion (cjs) and Oasis Settlements (jtci, jtr)."""

import pytest

from empire_core.alliance.models.horizon import (
    HorizonEntryConditionsResponse,
    JadePhase,
    JadePhaseResponse,
    OasisSettlementResponse,
    SendOasisTradeRequest,
    SendOasisTradeResponse,
)
from empire_core.enums import HorizonEntryConditionType, JadeScoringPhase, Kingdom, MovementType
from empire_core.exceptions import CommandError, PremiumCommanderCostError
from empire_core.gamedata import Building, Effect, Horse, OasisSettlementId, OasisTradeId, WodAmount
from empire_core.protocol.base import parse_response
from empire_core.state.manager import GameState
from tests.service_helpers import RUBY_HORSE, conn, make_client, with_horses, xt_packet

CITADEL = {"X": 30, "Y": "40", "CR": 15, "L": 2, "ASJ": "25000", "RSJ": 120, "CD": 3600}
SETTLEMENT = {"X": 50, "Y": 60, "TCI": "101", "L": 2, "TCR": 48000, "CD": 0, "AE": [[1, [10], "x"]]}
TRADE_REPLY = {
    "O": [],
    "A": {"M": {"MID": 7, "T": 35, "TT": 600, "TA": [4, 50, 60, 1]}, "A": [[620, 5]], "TRU": [[620, 2]]},
    "gcu": {"C1": 900, "C2": 4},
}


class TestEntryConditions:
    def test_asked_with_no_payload(self):
        client = make_client({"bgc": xt_packet("bgc", {"ENCO": []})})

        conditions = client.alliance.get_horizon_entry_conditions(timeout=0.2)

        assert conditions.conditions == [] and conditions.missing_buildings == []
        assert conn(client).request_payloads == [("bgc", {})]

    def test_building_conditions_name_their_buildings(self):
        # ABGEntryConditionVO.parseData reads MBW through int(); only BUILDINGS conditions name buildings
        reply = HorizonEntryConditionsResponse.model_validate(
            {"ENCO": [{"ECT": "BUILDINGS", "MBW": ["171", 1]}, {"ECT": "LEVEL", "MBW": [2]}, "bad"]}
        )

        buildings, other = reply.conditions
        assert buildings.condition_type is HorizonEntryConditionType.BUILDINGS
        assert buildings.missing_buildings == [Building.KEEP_L1, Building.HOSPITAL_L1]
        assert other.condition_type == "LEVEL"
        assert reply.missing_buildings == [Building.KEEP_L1, Building.HOSPITAL_L1]

    def test_a_refusal_raises(self):
        client = make_client({"bgc": xt_packet("bgc", error_code=1)})
        with pytest.raises(CommandError):
            client.alliance.get_horizon_entry_conditions(timeout=0.2)


class TestJadePhase:
    def test_absent_and_zero_keys_are_not_sent(self):
        push = JadePhaseResponse.model_validate({"JP": 0, "JPT": "", "JPP": 0})
        assert (push.phase, push.seconds_until_phase_2, push.phase_2_condition_percent) == (None, None, None)

    def test_a_push_keeps_what_it_leaves_out_but_the_condition(self):
        # parseJadePhaseInfo sets JP and JPT only when truthy, and JPP back to -1 when not
        first = JadePhase().updated(JadePhaseResponse.model_validate({"JPT": 600, "JPP": 40}), 1000.0)
        # the phase before any push comes from the event's own data, which is not read
        assert (first.phase, first.phase_2_starts_at, first.phase_2_condition_percent) == (None, 1600.0, 40)
        assert first.current_phase(1000.0) is None

        second = first.updated(JadePhaseResponse.model_validate({"JP": 2}), 1100.0)
        assert (second.phase, second.phase_2_starts_at, second.phase_2_condition_percent) == (
            JadeScoringPhase.PHASE_2,
            1600.0,
            None,
        )

    def test_phase_2_starts_when_its_time_passes(self):
        phase = JadePhase().updated(JadePhaseResponse.model_validate({"JP": 1, "JPT": 600}), 1000.0)
        assert phase.phase_2_timer_running
        assert phase.current_phase(1599.0) is JadeScoringPhase.PHASE_1
        assert phase.seconds_until_phase_2(1599.0) == 1.0
        assert phase.current_phase(1600.0) is JadeScoringPhase.PHASE_2
        assert phase.seconds_until_phase_2(1700.0) == 0.0

    def test_a_push_without_the_time_stops_the_timer(self):
        # parseJadePhaseInfo removes the timer listener on every push and adds it back only for a truthy JPT
        armed = JadePhase().updated(JadePhaseResponse.model_validate({"JP": 1, "JPT": 600}), 1000.0)
        stopped = armed.updated(JadePhaseResponse.model_validate({"JPP": 25}), 1100.0)
        assert not stopped.phase_2_timer_running and stopped.phase_2_starts_at == 1600.0
        assert stopped.current_phase(1700.0) is JadeScoringPhase.PHASE_1

    def test_a_switch_already_made_survives_the_next_push(self):
        armed = JadePhase().updated(JadePhaseResponse.model_validate({"JP": 1, "JPT": 600}), 1000.0)
        later = armed.updated(JadePhaseResponse.model_validate({"JPP": 25}), 1700.0)
        assert later.current_phase(1700.0) is JadeScoringPhase.PHASE_2

    def test_no_timer_once_in_phase_2(self):
        phase = JadePhase().updated(JadePhaseResponse.model_validate({"JP": 2, "JPT": 600}), 1000.0)
        assert not phase.phase_2_timer_running

    def test_the_push_is_kept_on_state_and_read_on_the_alliance(self):
        client = make_client(state=GameState())
        assert client.alliance.jade_phase is None

        client.state.update_from_packet("abgi", {"JP": 1, "JPT": 600})
        client.state.update_from_packet("abgi", {"JPP": 25})

        phase = client.alliance.jade_phase
        assert phase is not None and phase.phase is JadeScoringPhase.PHASE_1
        assert phase.phase_2_starts_at is not None and phase.phase_2_condition_percent == 25

    def test_a_refused_push_is_ignored(self):
        state = GameState()
        state.update_from_packet("abgi", {"JP": 2}, error_code=1)
        assert state.get_jade_phase() is None


class TestCitadels:
    def test_own_and_enemy_citadels(self):
        client = make_client({"jci": xt_packet("jci", {"CI": CITADEL, "ECI": [CITADEL, None, "bad"]})})

        citadels = client.alliance.get_citadels(timeout=0.2)

        assert conn(client).request_payloads == [("jci", {})]
        own = citadels.own
        assert own is not None
        assert (own.x, own.y, own.radius, own.level) == (30, 40, 15, 2)
        assert (own.ancient_jade_statuettes, own.restored_jade_statuettes, own.protection_seconds) == (25000, 120, 3600)
        assert [enemy.x for enemy in citadels.enemies] == [30]

    def test_no_own_citadel(self):
        client = make_client({"jci": xt_packet("jci", {})})
        citadels = client.alliance.get_citadels(timeout=0.2)
        assert citadels.own is None and citadels.enemies == []

    def test_upgrade_sends_nothing_else(self):
        client = make_client({"ujc": xt_packet("ujc", {})})
        client.alliance.upgrade_citadel(timeout=0.2)
        assert conn(client).request_payloads == [("ujc", {})]

    def test_a_refused_upgrade_raises(self):
        client = make_client({"ujc": xt_packet("ujc", error_code=1)})
        with pytest.raises(CommandError):
            client.alliance.upgrade_citadel(timeout=0.2)

    def test_conversion_names_the_restored_statuettes(self):
        client = make_client({"cjs": xt_packet("cjs", {})})
        client.alliance.convert_jade_statuettes(25, timeout=0.2)
        assert conn(client).request_payloads == [("cjs", {"AMT": 25})]

    def test_nothing_to_convert_is_not_sent(self):
        client = make_client()
        with pytest.raises(ValueError):
            client.alliance.convert_jade_statuettes(0)
        assert conn(client).request_payloads == []


class TestOasisSettlements:
    def test_settlement_state(self):
        client = make_client({"jtci": xt_packet("jtci", SETTLEMENT)})

        settlement = client.alliance.get_oasis_settlement(50, 60, timeout=0.2)

        assert conn(client).request_payloads == [("jtci", {"TX": 50, "TY": 60, "KID": 0})]
        assert (settlement.x, settlement.y, settlement.level, settlement.remaining) == (50, 60, 2, 48000)
        assert settlement.settlement_id == OasisSettlementId(101) and settlement.cooldown_seconds == 0
        (effect,) = settlement.area_effects
        assert (effect.effect_id, effect.values, effect.source) == (Effect(1), [10], "x")

    def test_missing_keys_read_as_the_client_reads_them(self):
        settlement = OasisSettlementResponse.model_validate({})
        assert (settlement.settlement_id, settlement.cooldown_seconds, settlement.area_effects) == (0, 0, [])

    def test_trade_request_follows_the_client(self):
        request = SendOasisTradeRequest(
            source_x=1,
            source_y=2,
            target_x=50,
            target_y=60,
            commander_id=5,
            units=WodAmount.slots({620: 10}),
            trades={OasisTradeId(10): 3},
        )
        assert request.to_payload() == {
            "SX": 1,
            "SY": 2,
            "TX": 50,
            "TY": 60,
            "KID": 0,
            "LID": 5,
            "BPC": 0,
            "HBW": -1,
            "PTT": 0,
            "A": [[620, 10]],
            "TR": [[10, 3]],
        }

    def test_send_a_trade(self):
        client = make_client({"jtr": xt_packet("jtr", TRADE_REPLY)})

        reply = client.alliance.send_oasis_trade(
            1, 2, 50, 60, {620: 10}, {OasisTradeId(10): 3, OasisTradeId(11): 0}, 5, kingdom=Kingdom.GREEN, timeout=0.2
        )

        payload = conn(client).request_payloads[0][1]
        assert (payload["LID"], payload["BPC"], payload["TR"]) == (5, 0, [[10, 3]])
        assert reply.movement is not None and reply.movement_id == 7
        assert reply.movement.movement.movement_type == MovementType.HORIZON_OASIS_TRADE
        assert reply.movement.traded_units == {620: 2}

    def test_the_premium_commander_is_sent_as_0_with_the_flag(self):
        client = make_client({"jtr": xt_packet("jtr", TRADE_REPLY)})
        client.alliance.send_oasis_trade(1, 2, 50, 60, {620: 10}, {OasisTradeId(10): 1}, -14, spend_rubies=True)
        payload = conn(client).request_payloads[0][1]
        assert (payload["LID"], payload["BPC"]) == (0, 1)

    def test_the_premium_commander_needs_consent(self):
        client = make_client()
        with pytest.raises(PremiumCommanderCostError):
            client.alliance.send_oasis_trade(1, 2, 50, 60, {620: 10}, {OasisTradeId(10): 1}, -14)
        assert conn(client).request_payloads == []

    def test_feathers_send_no_horse(self):
        client = make_client({"jtr": xt_packet("jtr", TRADE_REPLY)})
        client.alliance.send_oasis_trade(
            1, 2, 50, 60, {620: 1}, {OasisTradeId(10): 1}, 5, horse_booster_id=Horse.COURSER_STABLE1, feathers=True
        )
        payload = conn(client).request_payloads[0][1]
        assert (payload["HBW"], payload["PTT"]) == (-1, 1)

    def test_a_ruby_horse_needs_consent(self):
        # CastlePostTradeHorseDialog.getBoostCostC2: a horse costs rubies unless paid with feathers
        client = with_horses(make_client({"jtr": xt_packet("jtr", TRADE_REPLY)}))
        with pytest.raises(ValueError, match="spend_rubies=True"):
            client.alliance.send_oasis_trade(
                1, 2, 50, 60, {620: 1}, {OasisTradeId(10): 1}, 5, horse_booster_id=RUBY_HORSE
            )
        assert conn(client).request_payloads == []

        client.alliance.send_oasis_trade(
            1, 2, 50, 60, {620: 1}, {OasisTradeId(10): 1}, 5, horse_booster_id=RUBY_HORSE, spend_rubies=True
        )
        payload = conn(client).request_payloads[0][1]
        assert (payload["HBW"], payload["PTT"]) == (int(RUBY_HORSE), 0)

    def test_no_trade_is_not_sent(self):
        client = make_client()
        with pytest.raises(ValueError, match="trade"):
            client.alliance.send_oasis_trade(1, 2, 50, 60, {620: 10}, {OasisTradeId(10): 0}, 5)
        assert conn(client).request_payloads == []

    def test_a_refused_trade_raises(self):
        client = make_client({"jtr": xt_packet("jtr", error_code=1)})
        with pytest.raises(CommandError):
            client.alliance.send_oasis_trade(1, 2, 50, 60, {620: 10}, {OasisTradeId(10): 1}, 5, timeout=0.2)

    def test_the_reply_is_a_sent_movement_kept_on_state(self):
        reply = parse_response("jtr", TRADE_REPLY)
        assert isinstance(reply, SendOasisTradeResponse)
        assert reply.currencies is not None and reply.currencies.coins == 900
        state = GameState()
        state.update_from_packet("jtr", TRADE_REPLY)
        assert state.get_last_packet_time("jtr") is not None
        movement = state.get_movement_by_id(7)
        assert movement is not None and movement.movement_type == MovementType.HORIZON_OASIS_TRADE
