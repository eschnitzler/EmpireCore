"""The Outer Realms and Beyond the Horizon: castle pick (tsc), server kind (tse), castles (tcc),
collector points (tpc) and the charge camp effects (gce, ccr, ace)."""

from __future__ import annotations

import pytest

from empire_core.enums import ServerType
from empire_core.events import (
    ChargeCampEffects,
    CurrentServer,
    OuterRealmsEvent,
    SelectSpecialServerCastleRequest,
    SpecialServerCastles,
)
from empire_core.exceptions import CommandError, EventNotRunningError
from empire_core.gamedata import Effect, Event, PrebuiltCastle
from empire_core.protocol.base import parse_response
from empire_core.state.manager import GameState
from tests.service_helpers import conn, make_client, with_prebuilt_castles, xt_packet


def _running(client, *event_ids: int) -> None:
    client.state = GameState()
    client._on_packet(xt_packet("sei", {"E": [{"EID": eid, "RS": 60} for eid in event_ids]}))


class TestSelectCastle:
    def test_keys_follow_the_client_order(self):
        request = SelectSpecialServerCastleRequest(
            castle_id=PrebuiltCastle.HORIZON_PIONEERS_OUTPOST, server_type=ServerType.HORIZON
        )
        assert request.to_payload() == {"ID": 34, "OC2": 0, "PWR": 0, "GST": 3}
        assert list(request.to_payload()) == ["ID", "OC2", "PWR", "GST"]

    def test_a_free_castle_goes_as_bought_with_0_rubies_as_the_client_sends_it(self):
        client = with_prebuilt_castles(make_client())
        _running(client, 106)

        client.events.select_special_server_castle(
            PrebuiltCastle.OUTER_REALMS_PIONEERS_OUTPOST, ServerType.OUTER_REALMS
        )

        assert conn(client).request_payloads == [("tsc", {"ID": 31, "OC2": 1, "PWR": 0, "GST": 2})]

    def test_a_ruby_castle_with_consent_sends_oc2(self):
        client = with_prebuilt_castles(make_client())
        _running(client, 113)

        client.events.select_special_server_castle(
            PrebuiltCastle.HORIZON_BATTALIONS_KEEP, ServerType.HORIZON, spend_rubies=True
        )

        assert conn(client).request_payloads == [("tsc", {"ID": 35, "OC2": 1, "PWR": 0, "GST": 3})]

    def test_a_ruby_castle_without_consent_raises(self):
        client = with_prebuilt_castles(make_client())
        _running(client, 113)

        with pytest.raises(ValueError, match="19999 rubies"):
            client.events.select_special_server_castle(PrebuiltCastle.HORIZON_BATTALIONS_KEEP, ServerType.HORIZON)
        assert conn(client).request_payloads == []

    def test_a_castle_priced_in_passage_tokens_sends_no_ruby_flag(self):
        client = with_prebuilt_castles(make_client())
        _running(client, 106)

        client.events.select_special_server_castle(
            PrebuiltCastle.OUTER_REALMS_CASTLE_TRANSPORTATION, ServerType.OUTER_REALMS
        )

        assert conn(client).request_payloads == [("tsc", {"ID": 40, "OC2": 0, "PWR": 0, "GST": 2})]

    def test_ruby_price_on_a_castle_without_one_is_refused(self):
        client = with_prebuilt_castles(make_client())
        _running(client, 106)

        with pytest.raises(ValueError, match="no ruby price"):
            client.events.select_special_server_castle(
                PrebuiltCastle.OUTER_REALMS_PIONEERS_OUTPOST, ServerType.OUTER_REALMS, ruby_price=True
            )
        assert conn(client).request_payloads == []

    def test_ruby_price_on_a_ruby_castle_still_needs_consent(self):
        client = with_prebuilt_castles(make_client())
        _running(client, 113)

        with pytest.raises(ValueError, match="19999 rubies"):
            client.events.select_special_server_castle(
                PrebuiltCastle.HORIZON_BATTALIONS_KEEP, ServerType.HORIZON, ruby_price=True
            )
        assert conn(client).request_payloads == []

    def test_a_castle_the_server_does_not_offer_is_refused(self):
        client = with_prebuilt_castles(make_client())
        _running(client, 113)

        with pytest.raises(ValueError, match="castle selection"):
            client.events.select_special_server_castle(PrebuiltCastle.OUTER_REALMS_ROYAL_KEEP_32, ServerType.HORIZON)
        assert conn(client).request_payloads == []

    @pytest.mark.parametrize(
        "castle,server_type,event_id",
        [
            (PrebuiltCastle.OUTER_REALMS_PIONEERS_OUTPOST, ServerType.OUTER_REALMS, 113),
            (PrebuiltCastle.HORIZON_BATTALIONS_KEEP, ServerType.HORIZON, 106),
        ],
    )
    def test_the_servers_event_must_run(self, castle, server_type, event_id):
        client = with_prebuilt_castles(make_client())
        _running(client, event_id)

        with pytest.raises(EventNotRunningError):
            client.events.select_special_server_castle(castle, server_type, spend_rubies=True)
        assert conn(client).request_payloads == []

    def test_the_normal_server_has_no_castle_pick(self):
        client = make_client()
        with pytest.raises(ValueError):
            client.events.select_special_server_castle(PrebuiltCastle.OUTER_REALMS_PIONEERS_OUTPOST, ServerType.NORMAL)

    def test_a_refusal_raises(self):
        client = with_prebuilt_castles(make_client({"tsc": xt_packet("tsc", error_code=145)}))
        _running(client, 106)
        with pytest.raises(CommandError):
            client.events.select_special_server_castle(
                PrebuiltCastle.OUTER_REALMS_PIONEERS_OUTPOST, ServerType.OUTER_REALMS
            )


class TestServerKind:
    @pytest.mark.parametrize(
        "payload,kind,temporary,horizon,cross_play",
        [
            ({"GST": 1, "ICS": 0}, ServerType.NORMAL, False, False, False),
            ({"GST": 2, "ICS": 1}, ServerType.OUTER_REALMS, True, False, True),
            ({"GST": 3}, ServerType.HORIZON, False, True, False),
        ],
    )
    def test_the_push_is_read(self, payload, kind, temporary, horizon, cross_play):
        server = parse_response("tse", payload)
        assert isinstance(server, CurrentServer)
        assert server.server_type is kind
        assert (server.is_outer_realms, server.is_horizon, server.is_cross_play) == (
            temporary,
            horizon,
            cross_play,
        )

    def test_the_push_is_kept_for_the_session(self):
        client = make_client()
        client.state = GameState()
        assert client.events.current_server is None

        client._on_packet(xt_packet("tse", {"GST": 2, "ICS": 0}))

        assert client.events.current_server is not None
        assert client.events.current_server.server_type is ServerType.OUTER_REALMS
        client.state.reset()
        assert client.events.current_server is None

    def test_a_refused_push_is_not_applied(self):
        client = make_client()
        client.state = GameState()
        client._on_packet(xt_packet("tse", {"GST": 2}, error_code=1))
        assert client.events.current_server is None


class TestSpecialServerCastles:
    def test_ids_above_zero_are_bought(self):
        castles = parse_response("tcc", {"TSCI": 7, "BGCI": 0})
        assert isinstance(castles, SpecialServerCastles)
        assert (castles.outer_realms_castle_bought, castles.horizon_castle_bought) == (True, False)

    @pytest.mark.parametrize("castle_id,bought", [(7, True), (0, False), (-1, False)])
    def test_the_push_marks_the_outer_realms_event(self, castle_id, bought):
        client = make_client()
        client.state = GameState()
        client._on_packet(xt_packet("sei", {"E": [{"EID": 106, "RS": 60, "IPS": 0 if bought else 1}]}))

        client._on_packet(xt_packet("tcc", {"TSCI": castle_id, "BGCI": 0}))

        event = client.state.get_event(Event.OUTER_REALMS)
        assert isinstance(event, OuterRealmsEvent)
        assert event.castle_bought is bought
        assert client.events.special_server_castles is not None
        assert client.events.special_server_castles.outer_realms_castle_id == castle_id

    def test_the_push_without_the_event_is_kept(self):
        client = make_client()
        client.state = GameState()
        client._on_packet(xt_packet("tcc", {"TSCI": 0, "BGCI": 9}))
        assert client.events.special_server_castles == SpecialServerCastles(
            outer_realms_castle_id=0, horizon_castle_id=9
        )


class TestCollectorPoints:
    def test_the_amount_is_returned(self):
        client = make_client({"tpc": xt_packet("tpc", {"PID": 78, "CCA": 1200})})

        assert client.events.get_outer_realms_collector_points(78) == 1200
        assert conn(client).request_payloads == [("tpc", {"PID": 78})]


class TestChargeCampEffects:
    def test_both_effects_are_read(self):
        client = make_client({"gce": xt_packet("gce", {"CCOE": [[1, [10]]], "CCNE": [[2, [15, 3]]]})})

        effects = client.events.get_charge_camp_effects(300, 400)

        assert conn(client).request_payloads == [("gce", {"XPOS": 300, "YPOS": 400})]
        assert (effects.current.effect, effects.current.values) == (Effect(1), (10,))
        assert effects.rerolled is not None
        assert (effects.rerolled.effect, effects.rerolled.values) == (Effect(2), (15, 3))

    @pytest.mark.parametrize("rolled", [None, [], [[-1, [0]]], [[0, [0]]]])
    def test_no_reroll_yet_is_none(self, rolled):
        payload = {"CCOE": [[1, [10]]]} | ({} if rolled is None else {"CCNE": rolled})
        effects = parse_response("gce", payload)
        assert isinstance(effects, ChargeCampEffects)
        assert effects.rerolled is None

    def test_an_unknown_effect_id_stays_an_int(self):
        effects = ChargeCampEffects.model_validate({"CCOE": [[987654, [1]]]})
        assert effects.current.effect == 987654

    def test_a_reroll_needs_consent(self):
        client = make_client()
        with pytest.raises(ValueError, match="spend_rubies"):
            client.events.reroll_charge_camp_effect(300, 400)
        assert conn(client).request_payloads == []

    def test_a_reroll_with_consent(self):
        client = make_client()
        client.events.reroll_charge_camp_effect(300, 400, spend_rubies=True)
        assert conn(client).request_payloads == [("ccr", {"XPOS": 300, "YPOS": 400})]

    def test_apply(self):
        client = make_client()
        client.events.apply_charge_camp_effect(300, 400)
        assert conn(client).request_payloads == [("ace", {"XPOS": 300, "YPOS": 400})]

    @pytest.mark.parametrize("command", ["ccr", "ace"])
    def test_a_refusal_raises(self, command):
        client = make_client({command: xt_packet(command, error_code=1)})
        with pytest.raises(CommandError):
            if command == "ccr":
                client.events.reroll_charge_camp_effect(1, 2, spend_rubies=True)
            else:
                client.events.apply_charge_camp_effect(1, 2)
