"""The ignore list: ili and ipl, as CastleMessageData reads them."""

import pytest

from empire_core.exceptions import CommandError
from empire_core.messages import (
    GetIgnoredPlayersRequest,
    IgnoredPlayer,
    IgnoredPlayersResponse,
    IgnorePlayerRequest,
    IgnorePlayerResponse,
)
from tests.service_helpers import conn, make_client, xt_packet

LISTED = {"IPS": [{"PID": 11, "N": "first"}, {"PID": "12", "N": "second"}]}


class TestWireShapes:
    def test_the_requests(self):
        assert GetIgnoredPlayersRequest().to_payload() == {}
        # C2SIgnorePlayerVO (bundle line 60860): IGN is 1 or 0
        assert IgnorePlayerRequest(player_id=11, ignore=True).to_payload() == {"IPID": 11, "IGN": 1}
        assert IgnorePlayerRequest(player_id=11, ignore=False).to_payload() == {"IPID": 11, "IGN": 0}

    def test_the_replies(self):
        listed = IgnoredPlayersResponse.model_validate(LISTED)
        assert listed.players == [IgnoredPlayer(player_id=11, name="first"), IgnoredPlayer(player_id=12, name="second")]
        # IPLCommand reads the list nested under ili
        assert IgnorePlayerResponse.model_validate({"ili": LISTED}).ignore_list.players == listed.players
        assert IgnorePlayerResponse.model_validate({}).ignore_list.players == []


class TestService:
    def test_get_ignored_players(self):
        client = make_client({"ili": xt_packet("ili", LISTED)})

        players = client.messages.get_ignored_players()

        assert conn(client).request_payloads == [("ili", {})]
        assert [p.player_id for p in players] == [11, 12]

    def test_ignore_and_unignore_return_the_new_list(self):
        client = make_client({"ipl": [xt_packet("ipl", {"ili": LISTED}), xt_packet("ipl", {"ili": {"IPS": []}})]})

        assert [p.name for p in client.messages.ignore(11)] == ["first", "second"]
        assert client.messages.unignore(11) == []

        assert conn(client).request_payloads == [("ipl", {"IPID": 11, "IGN": 1}), ("ipl", {"IPID": 11, "IGN": 0})]

    def test_a_refusal_raises(self):
        client = make_client({"ipl": xt_packet("ipl", {}, error_code=1)})

        with pytest.raises(CommandError):
            client.messages.ignore(11)
