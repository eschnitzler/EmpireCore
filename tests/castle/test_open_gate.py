"""Open Gate: the price, the quote read from state, and opening and closing a castle's gate (mos)."""

from typing import Any

import pytest

from empire_core.castle import (
    CLOSE_GATE,
    OpenGateDuration,
    OpenGateRefusal,
    OpenGateRequest,
    OpenGateResponse,
    open_gate_rubies,
)
from empire_core.enums import GGEError, Kingdom
from empire_core.exceptions import CommandError, UnknownCastleError
from tests.service_helpers import conn, logged_in_state, make_client, xt_packet

# PlayerConst.getOpenGateCosts run in node for the 1st to 12th opening (6 hours, then 12 hours)
CLIENT_PRICES = {
    OpenGateDuration.HOURS_6: [450, 1110, 2090, 3600, 5910, 9460, 14940, 23390, 36450, 36450, 36450, 36450],
    OpenGateDuration.HOURS_12: [700, 1720, 3260, 5600, 9190, 14720, 23240, 36390, 56700, 56700, 56700, 56700],
}


def gcl(*entries: tuple[int, int, int, dict[str, Any]]) -> dict[str, Any]:
    """A castle list of (castle id, area type, kingdom, entry keys) owned by the logged-in player."""
    blocks: dict[int, list[dict[str, Any]]] = {}
    for castle_id, area_type, kingdom, keys in entries:
        row = [area_type, 10, 20, castle_id, 1001, 1, 1, 1, 0, 0, f"Castle {castle_id}"]
        blocks.setdefault(kingdom, []).append({"AI": row, **keys})
    return {"C": [{"KID": kid, "AI": rows} for kid, rows in blocks.items()]}


def client_with(*entries: tuple[int, int, int, dict[str, Any]], level: int = 20, script: Any = None):
    state = logged_in_state(gcl=gcl(*entries), gxp={"LVL": level}, gcu={"C1": 0, "C2": 4000})
    return make_client(script, state=state)


def challenge(payload: dict[str, Any]):
    return xt_packet("mos", payload, error_code=GGEError.RUBY_CONFIRMATION_REQUIRED)


@pytest.mark.parametrize("duration", list(OpenGateDuration))
def test_the_price_matches_the_client_for_every_opening(duration):
    assert [open_gate_rubies(duration, use) for use in range(1, 13)] == CLIENT_PRICES[duration]


def test_the_durations_are_the_client_list():
    assert [(int(d), d.seconds) for d in OpenGateDuration] == [(0, 21600), (1, 43200)]


def test_the_request_and_reply_keys():
    request = OpenGateRequest(castle_id=5, kingdom=Kingdom.ICE, duration=OpenGateDuration.HOURS_12)
    assert request.to_payload() == {"CID": 5, "KID": 2, "CD": 1}
    reply = OpenGateResponse.model_validate({"CID": "5", "KID": 2, "RPT": 43200, "gcu": {"C1": 1, "C2": 2}})
    assert (reply.castle_id, reply.kingdom, reply.open_seconds) == (5, Kingdom.ICE, 43200)


def test_the_quote_prices_the_next_opening_from_the_castle_list():
    client = client_with((5, 1, 0, {"OGC": 2, "OGT": 600}))
    quote = client.castle.open_gate_quote(5)
    assert (quote.castle_id, quote.kingdom, quote.uses, quote.rubies, quote.refusal) == (5, Kingdom.GREEN, 2, 4000, None)
    assert quote.prices == {OpenGateDuration.HOURS_6: 2090, OpenGateDuration.HOURS_12: 3260}
    assert 590 < quote.open_seconds <= 600
    assert conn(client).request_payloads == []


@pytest.mark.parametrize(
    ("area_type", "level", "refusal"),
    [
        (3, 20, OpenGateRefusal.CAPITAL),
        (22, 20, OpenGateRefusal.TRADING_METROPOLIS),
        (1, 4, OpenGateRefusal.LEVEL),
        (4, 5, None),
    ],
    ids=["capital", "metropolis", "level", "outpost-at-level-5"],
)
def test_the_quote_says_when_the_client_offers_no_open_gate(area_type, level, refusal):
    client = client_with((5, area_type, 0, {}), level=level)
    assert client.castle.open_gate_quote(5).refusal is refusal


def test_opening_needs_consent_and_sends_the_castle_kingdom_and_duration():
    client = client_with((5, 1, 2, {"OGC": 1}), script={"mos": xt_packet("mos", {"CID": 5, "KID": 2, "RPT": 21600})})
    with pytest.raises(ValueError, match="1110 rubies"):
        client.castle.open_gate(5, OpenGateDuration.HOURS_6)
    assert conn(client).request_payloads == []

    reply = client.castle.open_gate(5, OpenGateDuration.HOURS_6, spend_rubies=True)
    assert conn(client).request_payloads == [("mos", {"CID": 5, "KID": 2, "CD": 0})]
    assert reply.open_seconds == 21600


def test_a_castle_the_client_offers_no_open_gate_for_sends_nothing():
    client = client_with((5, 3, 0, {}))
    with pytest.raises(ValueError, match="capital"):
        client.castle.open_gate(5, OpenGateDuration.HOURS_6, spend_rubies=True)
    with pytest.raises(UnknownCastleError):
        client.castle.open_gate(6, OpenGateDuration.HOURS_6, spend_rubies=True)
    assert conn(client).request_payloads == []


def test_an_authorized_opening_confirms_the_ruby_challenge_once():
    payload = {"CID": 5, "KID": 0, "CD": 1}
    script = {"mos": [challenge({**payload, "CC2T": 700}), xt_packet("mos", {"CID": 5, "KID": 0, "RPT": 43200})]}
    client = client_with((5, 1, 0, {}), script=script)
    client.castle.open_gate(5, OpenGateDuration.HOURS_12, spend_rubies=True)
    assert conn(client).request_payloads == [("mos", payload), ("mos", {"cmdID": "mos", **payload, "CC2T": 700})]


def test_a_peace_mode_refusal_raises():
    script = {"mos": xt_packet("mos", error_code=GGEError.INVALID_PARAMETER_VALUE)}
    client = client_with((5, 1, 0, {}), script=script)
    with pytest.raises(CommandError):
        client.castle.open_gate(5, OpenGateDuration.HOURS_6, spend_rubies=True)
    assert len(conn(client).request_payloads) == 1


def test_closing_sends_minus_one_without_rubies():
    client = client_with((5, 1, 0, {}), script={"mos": xt_packet("mos", {"CID": 5, "KID": 0, "RPT": 0})})
    assert client.castle.close_gate(5).open_seconds == 0
    assert conn(client).request_payloads == [("mos", {"CID": 5, "KID": 0, "CD": CLOSE_GATE})]


class TestState:
    def test_an_opening_reply_sets_the_gate_and_counts_once(self):
        client = client_with((5, 1, 0, {"OGC": 1}))
        state = client.state
        castle = state.get_castles()[0]

        state.update_from_packet("mos", {"CID": 5, "KID": 0, "RPT": 21600, "gcu": {"C1": 0, "C2": 2890}})

        assert castle.open_gate_counter == 2
        assert 21590 < castle.open_gate_seconds() <= 21600
        assert state.get_local_player().rubies == 2890

    def test_a_closing_reply_clears_the_gate_without_counting(self):
        client = client_with((5, 1, 0, {"OGC": 1, "OGT": 600}))
        state = client.state
        castle = state.get_castles()[0]

        state.update_from_packet("mos", {"CID": 5, "KID": 0, "RPT": 0})

        assert (castle.open_gate_counter, castle.open_gate_end) == (1, None)

    @pytest.mark.parametrize(
        ("payload", "error_code"),
        [
            ({"CID": 5, "KID": 0, "RPT": 600}, GGEError.INVALID_PARAMETER_VALUE),
            ({"CID": 6, "KID": 0, "RPT": 600}, 0),
            ({"CID": 5, "KID": 2, "RPT": 600}, 0),
            ([1, 2], 0),
        ],
        ids=["refused", "other-castle", "other-kingdom", "unreadable"],
    )
    def test_other_replies_change_nothing(self, payload, error_code):
        client = client_with((5, 1, 0, {"OGC": 1}))
        castle = client.state.get_castles()[0]
        client.state.update_from_packet("mos", payload, error_code)
        assert (castle.open_gate_counter, castle.open_gate_end) == (1, None)

    def test_a_castle_list_without_open_time_closes_the_gate(self):
        client = client_with((5, 1, 0, {"OGT": 600}))
        castle = client.state.get_castles()[0]
        assert castle.open_gate_end is not None
        client.state.update_from_packet("gbd", {"gcl": gcl((5, 1, 0, {}))})
        assert castle.open_gate_end is None
        assert client.state.get_castles()[0] is castle
