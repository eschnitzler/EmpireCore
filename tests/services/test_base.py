"""Tests for the BaseService contracts and service registration."""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from empire_core.alliance.service import AllianceService
from empire_core.army.service import ArmyService
from empire_core.castle.service import CastleService
from empire_core.commanders.service import CommandersService
from empire_core.config import EmpireConfig
from empire_core.enums import Kingdom
from empire_core.exceptions import CommandError, ConnectionClosedError, EmpireTimeoutError, NetworkError, PacketError
from empire_core.protocol.models import (
    GetAllianceInfoRequest,
    GetAllianceInfoResponse,
    MapItemType,
    SelectCastleRequest,
)
from empire_core.protocol.packet import Packet
from empire_core.ranking.service import RankingService
from empire_core.services import get_registered_services
from empire_core.spy.service import SpyService
from tests.service_helpers import GOLDEN_GCL, conn, make_client, xt_packet

# =============================================================================
# Registration / wiring
# =============================================================================


class TestServiceRegistration:
    def test_every_documented_service_is_registered(self):
        registered = get_registered_services()
        assert set(registered) >= {
            "alliance",
            "castle",
            "army",
            "commanders",
            "spy",
            "ranking",
            "map",
            "movements",
            "defense",
            "player",
            "events",
        }

    def test_services_attach_to_the_client_by_name(self):
        client = make_client()
        assert isinstance(client.alliance, AllianceService)
        assert isinstance(client.castle, CastleService)
        assert isinstance(client.army, ArmyService)
        assert isinstance(client.commanders, CommandersService)
        assert isinstance(client.spy, SpyService)
        assert isinstance(client.ranking, RankingService)

    def test_service_zone_follows_client_config(self):
        client = make_client()
        client.config = EmpireConfig(default_zone="EmpireEx_99")
        assert client.alliance.zone == "EmpireEx_99"
        assert client.castle.zone == "EmpireEx_99"

    def test_requests_are_built_for_the_configured_zone(self):
        client = make_client()
        client.config = EmpireConfig(default_zone="EmpireEx_99")

        client.alliance.send_chat("hi")

        assert conn(client).sent[0].startswith("%xt%EmpireEx_99%acm%")


# =============================================================================
# BaseService contracts (the README's CommandError-vs-bool split)
# =============================================================================


class TestExecuteSemantics:
    """``execute()`` returns False for game-rule rejections and raises for
    transport failures - infrastructure problems must never look like a
    rejected action."""

    def test_accepted_action_returns_true(self):
        client = make_client({"jaa": xt_packet("jaa")})
        assert client.castle.select(12345) is True

    def test_rejected_action_returns_false(self):
        client = make_client({"jaa": xt_packet("jaa", error_code=21)})
        assert client.castle.select(12345) is False

    def test_rejection_is_logged_with_the_command(self, caplog):
        client = make_client({"jaa": xt_packet("jaa", error_code=21)})
        with caplog.at_level(logging.WARNING, logger="empire_core.services.base"):
            client.castle.select(12345)
        assert "jca" in caplog.text

    @pytest.mark.parametrize(
        "failure",
        [
            EmpireTimeoutError("no answer"),
            ConnectionClosedError("socket closed"),
            NetworkError("send failed"),
        ],
    )
    def test_transport_failure_still_raises(self, failure):
        client = make_client({"jaa": failure})
        with pytest.raises(type(failure)):
            client.castle.select(12345)

    def test_malformed_status_is_not_treated_as_acceptance(self):
        # A garbled status field parses to the MALFORMED_STATUS_CODE sentinel,
        # which must read as a rejection rather than a success.
        client = make_client({"jaa": Packet.from_bytes(b"%xt%jaa%1%notanumber%{}%")})
        assert client.castle.select(12345) is False


class TestRequestSemantics:
    def test_server_error_code_raises_command_error(self):
        client = make_client({"ain": xt_packet("ain", error_code=21)})
        with pytest.raises(CommandError) as exc_info:
            client.alliance.get_members(190426)
        assert exc_info.value.command == "ain"
        assert exc_info.value.code == 21

    def test_unparseable_payload_raises_packet_error(self):
        # 'arc' requires the castle id; a drifted reply must surface as a
        # library error, not a raw pydantic ValidationError.
        from empire_core.protocol.models import RenameCastleRequest, RenameCastleResponse

        client = make_client({"arc": xt_packet("arc", {"N": "no id here"})})
        with pytest.raises(PacketError) as exc_info:
            client.request(
                RenameCastleRequest(CID=1, N="x", AT=MapItemType.CASTLE, KID=Kingdom.GREEN, P=1), RenameCastleResponse
            )
        assert "arc" in str(exc_info.value)

    def test_a_gli_entry_without_an_id_is_skipped(self):
        # parse_GLI builds every entry; one the library cannot read costs only itself
        client = make_client({"gli": xt_packet("gli", {"C": [{"N": "no id here"}, {"ID": 2}]})})
        assert [c.commander_id for c in client.commanders.get_commanders()] == [2]

    def test_array_payload_raises_packet_error_not_none(self):
        # A JSON-array payload has no response model, so send() returns None;
        # request() must not hand that back as if it were the typed response.
        client = make_client({"gcl": xt_packet("gcl", [1, 2, 3])})
        with pytest.raises(PacketError, match="GetCastlesResponse"):
            client.castle.get_all()

    def test_timeout_propagates(self):
        client = make_client({"gcl": EmpireTimeoutError("no gcl")})
        with pytest.raises(EmpireTimeoutError):
            client.castle.get_all()


# =============================================================================
# Handler registration via on_response
# =============================================================================


class TestOnResponse:
    def test_registered_handler_receives_parsed_responses(self):
        client = make_client()
        seen: list[object] = []
        client.castle.on_response("gcl", seen.append)

        client._on_packet(xt_packet("gcl", GOLDEN_GCL))

        assert len(seen) == 1
        assert [c.castle_id for c in seen[0].castles] == [2001, 2002]  # type: ignore[attr-defined]

    def test_unparseable_push_does_not_reach_the_handler(self, caplog):
        client = make_client()
        seen: list[object] = []
        client.castle.on_response("arc", seen.append)

        with caplog.at_level(logging.ERROR, logger="empire_core.client.client"):
            client._on_packet(xt_packet("arc", {"N": "no id"}))

        assert seen == []
        assert "arc" in caplog.text

    def test_commands_without_handlers_are_not_parsed(self):
        client = make_client()
        assert "gli" not in client._handlers

        # An unhandled command whose payload no model can parse must not raise
        # on the receive thread: parsing is skipped entirely.
        client._on_packet(xt_packet("gli", {"C": [{"N": "no id"}]}))

        assert client.state.updates == [("gli", {"C": [{"N": "no id"}]})]  # type: ignore[attr-defined]


# =============================================================================
# Request models used by the services
# =============================================================================


class TestRequestBuilding:
    def test_select_castle_request_packet_shape(self):
        packet = SelectCastleRequest(CID=12345, KID=Kingdom.ICE).to_packet(zone="EmpireEx_21")
        assert packet == '%xt%EmpireEx_21%jca%-1%{"CID":12345,"KID":2}%'

    def test_alliance_info_request_requires_an_id(self):
        with pytest.raises(ValidationError):
            GetAllianceInfoRequest()  # type: ignore[call-arg]

    def test_response_members_accessor_tolerates_a_missing_alliance(self):
        response = GetAllianceInfoResponse.model_validate({})
        assert response.members == []
        assert response.online_members == []
