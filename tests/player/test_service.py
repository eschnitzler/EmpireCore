"""Tests for the player service."""

from __future__ import annotations

from empire_core.exceptions import CommandError, EmpireTimeoutError
from empire_core.player import service as player_module
from empire_core.player.models.info import GetPlayerInfoRequest
from tests.service_helpers import conn, make_client, xt_packet


def gdi(pid: int):
    return xt_packet("gdi", {"O": {"OID": pid, "N": f"p{pid}"}})


class TestBulkPlayerDetails:
    def test_each_player_lands_in_one_group(self, monkeypatch):
        monkeypatch.setattr(player_module.time, "sleep", lambda _: None)
        script = {"gdi": [gdi(1), xt_packet("gdi", error_code=65), EmpireTimeoutError("slow"), gdi(9), gdi(5)]}
        client = make_client(script)

        result = client.player.get_player_details_bulk([1, 2, 3, 4, 5, 1])

        assert conn(client).request_payloads == [("gdi", {"PID": pid}) for pid in (1, 2, 3, 4, 5)]
        assert sorted(result.found) == [1, 5]
        assert result.found[5].player_name == "p5"
        assert isinstance(result.failed[2], CommandError) and result.failed[2].code == 65
        # A reply about another player is not taken, so player 4's request runs out
        assert 4 not in result.found and 4 not in result.failed
        assert result.timed_out == [3, 4]
        assert result.complete is False

    def test_all_found_is_complete(self):
        client = make_client({"gdi": [gdi(1), gdi(2)]})
        result = client.player.get_player_details_bulk([1, 2], send_delay=0)
        assert result.complete is True and sorted(result.found) == [1, 2]

    def test_nothing_asked_is_nothing_sent(self):
        client = make_client()
        result = client.player.get_player_details_bulk([])
        assert (result.found, result.failed, result.timed_out) == ({}, {}, [])
        assert conn(client).request_payloads == []

    def test_requests_are_paced(self, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr(player_module.time, "sleep", sleeps.append)
        client = make_client({"gdi": [gdi(1), gdi(2), gdi(3)]})

        client.player.get_player_details_bulk([1, 2, 3], send_delay=0.05)

        assert sleeps == [0.05, 0.05]

    def test_no_delay_by_default(self, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr(player_module.time, "sleep", sleeps.append)
        client = make_client({"gdi": [gdi(1), gdi(2)]})

        client.player.get_player_details_bulk([1, 2])

        assert sleeps == []


class TestGdiReplyMatching:
    """gdi replies carry the player they are about (O.OID); nothing else ties them to a request."""

    def test_the_request_accepts_only_a_reply_about_its_player(self):
        request = GetPlayerInfoRequest(PID=42)
        assert request.accepts_reply({"O": {"OID": 42, "N": "p"}})
        assert request.accepts_reply({"O": {"OID": "42"}})
        assert not request.accepts_reply({"O": {"OID": 7}})
        assert not request.accepts_reply({"O": None})
        assert not request.accepts_reply({"raw": ""})
        assert not request.accepts_reply(["O"])

    def test_get_player_info_passes_the_check_to_the_connection(self):
        client = make_client({"gdi": xt_packet("gdi", {"O": {"OID": 42, "N": "p"}})})

        client.player.get_player_info(42)

        accepts = conn(client).accepts[-1]
        assert accepts(xt_packet("gdi", {"O": {"OID": 42}}))
        assert not accepts(xt_packet("gdi", {"O": {"OID": 7}}))

    def test_a_request_without_a_check_passes_none(self):
        client = make_client()

        client.player.search_player_by_name("someone")

        assert conn(client).accepts == [None]

    def test_bulk_lookup_checks_each_reply(self):
        client = make_client({"gdi": [gdi(1), gdi(2)]})

        client.player.get_player_details_bulk([1, 2], send_delay=0.0)

        checks = conn(client).accepts
        assert len(checks) == 2
        assert checks[0](gdi(1)) and not checks[0](gdi(2))
        assert checks[1](gdi(2)) and not checks[1](gdi(1))
