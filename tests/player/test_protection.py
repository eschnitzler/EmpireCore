"""Your protection: uap, mps and ffp, and the state they update."""

from __future__ import annotations

import pytest

from empire_core.enums import FactionProtectionStatus, Kingdom, PeaceModeDuration, PeaceModeStatus
from empire_core.events.models import BerimondEvent
from empire_core.exceptions import CommandError
from empire_core.gamedata.ids.events import Event
from empire_core.player import ProtectionResponse, StartFactionProtectionResponse
from empire_core.protocol.base import parse_response
from empire_core.state import events as event_state
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

BERIMOND_ENTRY = {"EID": 3, "RS": 600, "LID": 1, "UL": 1, "FN": {"FID": 1, "MC": 9, "PMT": 0, "PMS": -1}}


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(event_state, "_clock", lambda: now[0])
    return now


class TestProtectionModels:
    def test_a_uap_reply_is_the_kingdom_protection(self):
        reply = parse_response("uap", {"KID": 1, "NS": 0, "PMS": 1, "PMT": 3600})

        assert isinstance(reply, ProtectionResponse)
        assert (reply.kingdom_id, reply.peace_mode_status, reply.protection_seconds) == (
            1,
            PeaceModeStatus.PEACETIME,
            3600,
        )
        assert not reply.is_noob_protected

    def test_a_berimond_block_reads_as_faction_protection(self):
        reply = ProtectionResponse.model_validate({"KID": 10, "NS": 0, "PMS": 2, "PMT": 60})
        assert reply.faction_protection_status is FactionProtectionStatus.COOLDOWN

    def test_an_ffp_reply(self):
        reply = parse_response(
            "ffp", {"gcu": {"C1": 10, "C2": 500}, "FN": {"FID": 2, "MC": 7, "PMT": 216000, "PMS": 0, "NS": 0}}
        )

        assert isinstance(reply, StartFactionProtectionResponse)
        assert reply.currencies is not None and reply.currencies.rubies == 500
        assert reply.faction is not None
        assert (reply.faction.faction_id, reply.faction.main_camp_id, reply.faction.protection_seconds) == (
            2,
            7,
            216000,
        )
        assert reply.faction.faction_protection_status is FactionProtectionStatus.PRETIME

    def test_peace_mode_durations_are_the_client_list(self):
        assert [(d.value, d.seconds, d.rubies) for d in PeaceModeDuration] == [
            (0, 604800, 5000),
            (1, 1209600, 7500),
            (2, 1814400, 10000),
            (3, 5184000, 20000),
        ]


class TestGetProtection:
    def test_asks_for_the_kingdom(self):
        client = make_client({"uap": xt_packet("uap", {"KID": 10, "NS": 0, "PMS": 1, "PMT": 50})})

        reply = client.player.get_protection(Kingdom.BERIMOND)

        assert reply.protection_seconds == 50
        assert conn(client).request_payloads == [("uap", {"KID": 10})]

    def test_defaults_to_the_green_kingdom(self):
        client = make_client({"uap": xt_packet("uap", {"KID": 0, "NS": 0, "PMS": -1, "PMT": 0})})
        client.player.get_protection()
        assert conn(client).request_payloads == [("uap", {"KID": 0})]

    def test_a_refusal_raises(self):
        client = make_client({"uap": xt_packet("uap", error_code=1)})
        with pytest.raises(CommandError):
            client.player.get_protection()


class TestPeaceMode:
    def test_sends_the_list_index(self):
        client = make_client()

        client.player.start_peace_mode(PeaceModeDuration.DAYS_21, spend_rubies=True)

        assert conn(client).request_payloads == [("mps", {"CD": 2})]

    def test_needs_ruby_consent(self):
        client = make_client()
        with pytest.raises(ValueError, match="10000 rubies"):
            client.player.start_peace_mode(PeaceModeDuration.DAYS_21)
        assert conn(client).request_payloads == []

    def test_cancel_sends_minus_one(self):
        client = make_client()
        client.player.cancel_peace_mode()
        assert conn(client).request_payloads == [("mps", {"CD": -1})]

    def test_a_refusal_raises(self):
        client = make_client({"mps": xt_packet("mps", error_code=1)})
        with pytest.raises(CommandError):
            client.player.cancel_peace_mode()


class TestFactionProtection:
    def test_sends_the_only_option(self):
        client = make_client({"ffp": xt_packet("ffp", {"gcu": {"C1": 1, "C2": 2}, "FN": {"FID": 1, "PMS": 0}})})

        reply = client.player.start_faction_protection(spend_rubies=True)

        assert reply.faction is not None and reply.faction.faction_id == 1
        assert conn(client).request_payloads == [("ffp", {"ID": 0})]

    def test_needs_ruby_consent(self):
        client = make_client()
        with pytest.raises(ValueError, match="7500 rubies"):
            client.player.start_faction_protection()
        assert conn(client).request_payloads == []

    def test_a_refusal_raises(self):
        client = make_client({"ffp": xt_packet("ffp", error_code=1)})
        with pytest.raises(CommandError):
            client.player.start_faction_protection(spend_rubies=True)


class TestProtectionState:
    def test_login_and_pushes_keep_a_block_per_kingdom(self):
        state = logged_in_state(uap={"KID": 0, "NS": 600, "PMS": -1, "PMT": 0})
        state.update_from_packet("uap", {"KID": 2, "NS": 0, "PMS": 1, "PMT": 3600})

        player = state.get_local_player()
        assert player.beginner_protection == {0: True, 2: False}
        assert player.protection[Kingdom.ICE].peace_mode_status is PeaceModeStatus.PEACETIME
        assert player.protection[Kingdom.GREEN].noob_protection_seconds == 600
        state.shutdown()

    def test_the_service_reads_the_state(self):
        state = logged_in_state(uap={"KID": 0, "NS": 0, "PMS": 0, "PMT": 120})
        client = make_client(state=state)

        protection = client.player.protection()

        assert protection is not None and protection.peace_mode_status is PeaceModeStatus.PRETIME
        assert client.player.protection(Kingdom.FIRE) is None
        state.shutdown()

    def test_a_berimond_block_updates_the_berimond_event(self, clock):
        state = logged_in_state()
        state.update_from_packet("sei", {"E": [BERIMOND_ENTRY]})

        state.update_from_packet("uap", {"KID": 10, "NS": 30, "PMS": 1, "PMT": 200})

        berimond = state.get_event(Event.FACTION)
        assert isinstance(berimond, BerimondEvent)
        assert (berimond.faction_protection_status, berimond.faction_protection_end) == (1, 1200.0)
        assert berimond.beginner_protection_end == 1030.0
        state.shutdown()

    def test_another_kingdom_leaves_the_berimond_event(self, clock):
        state = logged_in_state()
        state.update_from_packet("sei", {"E": [BERIMOND_ENTRY]})

        state.update_from_packet("uap", {"KID": 0, "NS": 30, "PMS": 1, "PMT": 200})

        berimond = state.get_event(Event.FACTION)
        assert isinstance(berimond, BerimondEvent) and berimond.faction_protection_status == -1
        state.shutdown()

    @pytest.mark.parametrize(
        ("command", "payload"),
        [
            ("gaa", {"KID": 2, "AI": [], "OI": [], "uap": {"KID": 2, "NS": 0, "PMS": 1, "PMT": 3600}}),
            ("jaa", {"uap": {"KID": 2, "NS": 0, "PMS": 1, "PMT": 3600}}),
            ("ssi", {"GC": 0, "AS": 1, "gaa": {"AI": [], "OI": [], "uap": {"KID": 2, "NS": 0, "PMS": 1, "PMT": 3600}}}),
        ],
    )
    def test_a_map_read_join_or_spy_screen_applies_its_protection(self, command, payload):
        state = logged_in_state(uap={"KID": 0, "NS": 600, "PMS": -1, "PMT": 0})

        state.update_from_packet(command, payload)

        player = state.get_local_player()
        assert player.protection[Kingdom.ICE].peace_mode_status is PeaceModeStatus.PEACETIME
        assert player.beginner_protection == {0: True, 2: False}
        state.shutdown()

    @pytest.mark.parametrize(
        ("command", "payload"),
        [
            ("gaa", {"uap": {"KID": 2, "NS": 0, "PMS": 1, "PMT": 3600}}),
            ("jaa", {"uap": {"KID": 2, "NS": 0, "PMS": 1, "PMT": 3600}}),
            ("ssi", {"gaa": {"uap": {"KID": 2, "NS": 0, "PMS": 1, "PMT": 3600}}}),
        ],
    )
    def test_a_refused_reply_leaves_the_protection(self, command, payload):
        state = logged_in_state(uap={"KID": 0, "NS": 600, "PMS": -1, "PMT": 0})

        state.update_from_packet(command, payload, error_code=1)

        assert Kingdom.ICE not in state.get_local_player().protection
        state.shutdown()

    def test_a_berimond_map_read_updates_the_berimond_event(self, clock):
        state = logged_in_state()
        state.update_from_packet("sei", {"E": [BERIMOND_ENTRY]})

        state.update_from_packet(
            "gaa", {"KID": 10, "AI": [], "OI": [], "uap": {"KID": 10, "NS": 0, "PMS": 1, "PMT": 200}}
        )

        berimond = state.get_event(Event.FACTION)
        assert isinstance(berimond, BerimondEvent) and berimond.faction_protection_end == 1200.0
        state.shutdown()

    def test_ffp_applies_its_coins_and_faction(self, clock):
        state = logged_in_state()
        state.update_from_packet("sei", {"E": [BERIMOND_ENTRY]})

        state.update_from_packet("ffp", {"gcu": {"C1": 3, "C2": 4}, "FN": {"FID": 2, "MC": 5, "PMT": 90, "PMS": 0}})

        berimond = state.get_event(Event.FACTION)
        assert isinstance(berimond, BerimondEvent)
        assert (berimond.faction_id, berimond.main_camp_id, berimond.faction_protection_end) == (2, 5, 1090.0)
        assert (state.get_local_player().coins, state.get_local_player().rubies) == (3, 4)
        state.shutdown()

    def test_a_refused_ffp_changes_nothing(self, clock):
        state = logged_in_state()
        state.update_from_packet("sei", {"E": [BERIMOND_ENTRY]})

        state.update_from_packet("ffp", {"gcu": {"C1": 3, "C2": 4}, "FN": {"FID": 2}}, error_code=1)

        berimond = state.get_event(Event.FACTION)
        assert isinstance(berimond, BerimondEvent) and berimond.faction_id == 1
        assert state.get_local_player().rubies == 0
        state.shutdown()
