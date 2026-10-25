"""The link to a new world a mail announces: gil, as CastleNewServerAnnounceDialogProperties asks for it."""

import pytest

from empire_core.exceptions import CommandError
from empire_core.messages import GetWorldLinkRequest, WorldLinkResponse
from tests.service_helpers import conn, make_client, xt_packet


def test_keys_follow_the_client_order():
    # C2SGetInstanceLink initialises WID then ZID
    assert list(GetWorldLinkRequest(website_id=4, zone_id=27).to_payload()) == ["WID", "ZID"]


def test_the_link_is_returned():
    client = make_client({"gil": xt_packet("gil", {"L": "https://example.invalid/world"})})

    assert client.messages.get_world_link(27, 4) == "https://example.invalid/world"
    assert conn(client).request_payloads == [("gil", {"WID": 4, "ZID": 27})]
    assert WorldLinkResponse.model_validate({"L": "x"}).url == "x"


def test_a_refusal_raises():
    client = make_client({"gil": xt_packet("gil", error_code=1)})
    with pytest.raises(CommandError):
        client.messages.get_world_link(27, 4)
