"""Buying tools: ibt."""

from __future__ import annotations

import pytest

from empire_core.attack import BuyToolsResponse
from empire_core.enums import Kingdom
from empire_core.exceptions import CommandError, PacketError, UnknownCastleError
from empire_core.gamedata import PackageId, TreasureMapId
from empire_core.protocol.base import parse_response
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

REPLY = {"O": {"W": 614, "A": 20}, "gcu": {"C1": 100, "C2": 40}}


class TestBuyTools:
    def test_sends_the_castle_and_reads_the_tools(self):
        client = make_client({"ibt": xt_packet("ibt", REPLY)}, castles=[(2001, Kingdom.ICE, 512, 256)])

        bought = client.attack.buy_tools(2001, 614, 20, spend_rubies=True)

        assert (bought.tool, bought.amount) == (614, 20)
        assert conn(client).request_payloads == [
            ("ibt", {"W": 614, "A": 20, "CX": 512, "CY": 256, "MID": -1, "KID": 2, "PID": -1})
        ]

    def test_an_event_camp_and_package(self):
        client = make_client({"ibt": xt_packet("ibt", REPLY)}, castles=[(2001, Kingdom.GREEN, 5, 6)])

        client.attack.buy_tools(
            2001, 614, 1, map_id=TreasureMapId.THORNKING_NORMAL, package_id=PackageId(88), spend_rubies=True
        )

        assert conn(client).request_payloads == [
            ("ibt", {"W": 614, "A": 1, "CX": 5, "CY": 6, "MID": 21, "KID": 0, "PID": 88})
        ]

    def test_needs_ruby_consent(self):
        client = make_client(castles=[(2001, Kingdom.GREEN)])
        with pytest.raises(ValueError, match="rubies"):
            client.attack.buy_tools(2001, 614, 1)
        assert conn(client).request_payloads == []

    def test_an_unknown_castle(self):
        client = make_client(castles=[(2001, Kingdom.GREEN)])
        with pytest.raises(UnknownCastleError):
            client.attack.buy_tools(9, 614, 1, spend_rubies=True)

    def test_a_reply_without_tools(self):
        client = make_client({"ibt": xt_packet("ibt", {"gcu": {"C1": 1, "C2": 1}})}, castles=[(2001, Kingdom.GREEN)])
        with pytest.raises(PacketError):
            client.attack.buy_tools(2001, 614, 1, spend_rubies=True)

    def test_a_refusal_raises(self):
        client = make_client({"ibt": xt_packet("ibt", error_code=1)}, castles=[(2001, Kingdom.GREEN)])
        with pytest.raises(CommandError):
            client.attack.buy_tools(2001, 614, 1, spend_rubies=True)

    def test_the_reply_reaches_the_coins_and_rubies(self):
        reply = parse_response("ibt", REPLY)
        assert isinstance(reply, BuyToolsResponse) and reply.currencies is not None
        state = logged_in_state()

        state.update_from_packet("ibt", REPLY)

        assert (state.get_local_player().coins, state.get_local_player().rubies) == (100, 40)
        state.shutdown()
