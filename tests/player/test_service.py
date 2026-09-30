"""Tests for the player service."""

from __future__ import annotations

from empire_core.player import service as player_module
from empire_core.player.models.info import GetPlayerInfoRequest, GetPlayerInfoResponse
from tests.service_helpers import conn, make_client, xt_packet


class TestBulkPlayerDetailsPacing:
    """The server drops connections that sustain high request rates."""

    def test_sends_are_paced(self, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr(player_module.time, "sleep", sleeps.append)
        client = make_client()

        client.player.get_player_details_bulk([1, 2, 3], timeout=0.0, send_delay=0.05)

        assert len(conn(client).sent) == 3
        # Paced between sends only - no leading or trailing sleep.
        assert sleeps == [0.05, 0.05]

    def test_zero_delay_keeps_the_old_burst_behavior(self, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr(player_module.time, "sleep", sleeps.append)
        client = make_client()

        client.player.get_player_details_bulk([1, 2, 3], timeout=0.0, send_delay=0.0)

        assert sleeps == []

    def test_single_id_is_not_delayed(self, monkeypatch):
        sleeps: list[float] = []
        monkeypatch.setattr(player_module.time, "sleep", sleeps.append)
        client = make_client()

        client.player.get_player_details_bulk([7], timeout=0.0)

        assert sleeps == []

    def test_handler_is_removed_afterwards(self):
        client = make_client()

        client.player.get_player_details_bulk([1, 2], timeout=0.0, send_delay=0.0)

        assert client._handlers.get("gdi", []) == []

    def test_pacing_does_not_break_response_collection(self):
        client = make_client()
        original_send = client.send

        def send_and_answer(request, wait=False, timeout=5.0):
            result = original_send(request, wait=wait, timeout=timeout)
            # Simulate the server answering immediately on the recv thread.
            client._on_packet(xt_packet("gdi", {"O": {"OID": request.player_id, "N": "p"}}))
            return result

        client.send = send_and_answer  # type: ignore[method-assign]
        collected: dict[int, GetPlayerInfoResponse] = client.player.get_player_details_bulk(
            [1, 2], timeout=1.0, send_delay=0.01
        )

        assert sorted(collected) == [1, 2]
        assert all(isinstance(r, GetPlayerInfoResponse) for r in collected.values())


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

    def test_bulk_lookup_holds_gdi_for_its_whole_run(self):
        client = make_client()

        client.player.get_player_details_bulk([1, 2], timeout=0.0, send_delay=0.0)

        assert conn(client).events[0] == "lock:gdi"
        assert conn(client).events[-1] == "unlock:gdi"
        assert len(conn(client).sent) == 2
