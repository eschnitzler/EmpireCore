"""A castle's abandon timers in state: read from the castle list (gcl), started by mas, cleared by mac."""

import logging
import time
from typing import Any

import pytest

from empire_core.enums import GGEError, MapItemType
from tests.service_helpers import logged_in_state, make_client

MAIN = 4
OUTPOST = 5


def gcl(**outpost_keys: Any) -> dict[str, Any]:
    """A green kingdom castle list of a main castle and an outpost carrying ``outpost_keys``."""

    def row(castle_id: int, area_type: MapItemType) -> list[Any]:
        return [area_type, 10, castle_id, castle_id, 1001, 1, 1, 1, 0, 0, f"Castle {castle_id}"]

    entries = [{"AI": row(MAIN, MapItemType.CASTLE)}, {"AI": row(OUTPOST, MapItemType.OUTPOST), **outpost_keys}]
    return {"C": [{"KID": 0, "AI": entries}]}


def outpost_of(state: Any):
    return next(castle for castle in state.get_castles() if castle.id == OUTPOST)


class TestCastleList:
    def test_running_timers_end_their_seconds_from_now(self):
        before = time.monotonic()
        state = logged_in_state(gcl=gcl(AOT=86000, CAT=10000, TA=3600))
        after = time.monotonic()
        castle = outpost_of(state)

        assert before + 86000 <= castle.abandon_end <= after + 86000
        assert before + 10000 <= castle.cancel_abandon_end <= after + 10000
        assert before + 3600 <= castle.no_abandon_end <= after + 3600
        assert 85990 < castle.abandon_seconds() <= 86000
        assert castle.cancel_abandon_seconds(now=castle.cancel_abandon_end - 60) == 60
        assert castle.no_abandon_seconds(now=castle.no_abandon_end + 1) == 0

    @pytest.mark.parametrize("keys", [{"AOT": -1, "CAT": -1, "TA": -1}, {"AOT": 0, "CAT": 0, "TA": 0}, {}])
    def test_timers_not_above_zero_or_absent_are_not_running(self, keys):
        castle = outpost_of(logged_in_state(gcl=gcl(**keys)))

        assert (castle.abandon_end, castle.cancel_abandon_end, castle.no_abandon_end) == (None, None, None)
        assert (castle.abandon_seconds(), castle.cancel_abandon_seconds(), castle.no_abandon_seconds()) == (0, 0, 0)

    def test_a_list_without_the_timers_clears_them_on_the_same_castle(self):
        state = logged_in_state(gcl=gcl(AOT=86000, CAT=10000, TA=3600))
        castle = outpost_of(state)

        state.update_from_packet("gbd", {"gcl": gcl()})

        assert (castle.abandon_end, castle.cancel_abandon_end, castle.no_abandon_end) == (None, None, None)
        assert outpost_of(state) is castle


class TestReplies:
    def test_an_abandon_reply_starts_both_timers_and_keeps_the_cooldown(self):
        state = logged_in_state(gcl=gcl(TA=3600))
        castle = outpost_of(state)
        cooldown = castle.no_abandon_end

        state.update_from_packet("mas", {"CID": OUTPOST, "KID": 0, "AOT": 86400, "CAT": 10800})

        assert 86390 < castle.abandon_seconds() <= 86400
        assert 10790 < castle.cancel_abandon_seconds() <= 10800
        assert castle.abandon_end - castle.cancel_abandon_end == 86400 - 10800
        assert castle.no_abandon_end == cooldown

    def test_a_cancel_reply_clears_both_timers_and_keeps_the_cooldown(self):
        state = logged_in_state(gcl=gcl(AOT=86000, CAT=10000, TA=3600))
        castle = outpost_of(state)
        cooldown = castle.no_abandon_end

        state.update_from_packet("mac", {"CID": OUTPOST, "KID": 0})

        assert (castle.abandon_end, castle.cancel_abandon_end, castle.no_abandon_end) == (None, None, cooldown)

    @pytest.mark.parametrize(
        ("command", "payload", "error_code"),
        [
            ("mas", {"CID": OUTPOST, "KID": 0, "AOT": 600, "CAT": 600}, GGEError.ALREADY_ABANDONING_OUTPOST),
            ("mac", {"CID": OUTPOST, "KID": 0}, GGEError.INVALID_PARAMETER_VALUE),
            ("mas", {"CID": 6, "KID": 0, "AOT": 600, "CAT": 600}, 0),
            ("mac", {"CID": 6, "KID": 0}, 0),
            ("mas", {"CID": OUTPOST, "KID": 2, "AOT": 600, "CAT": 600}, 0),
            ("mac", {"CID": OUTPOST, "KID": 2}, 0),
        ],
        ids=[
            "refused-mas",
            "refused-mac",
            "other-castle-mas",
            "other-castle-mac",
            "other-kingdom-mas",
            "other-kingdom-mac",
        ],
    )
    def test_other_replies_change_nothing(self, command, payload, error_code):
        state = logged_in_state(gcl=gcl(AOT=86000, CAT=10000))
        castle = outpost_of(state)
        ends = (castle.abandon_end, castle.cancel_abandon_end)

        state.update_from_packet(command, payload, error_code)

        assert (castle.abandon_end, castle.cancel_abandon_end) == ends

    @pytest.mark.parametrize("command", ["mas", "mac"])
    def test_an_unreadable_reply_is_logged_and_changes_nothing(self, command, caplog):
        state = logged_in_state(gcl=gcl(AOT=86000, CAT=10000))
        castle = outpost_of(state)
        ends = (castle.abandon_end, castle.cancel_abandon_end)

        with caplog.at_level(logging.WARNING, logger="empire_core.state.castles"):
            state.update_from_packet(command, {"KID": 0})

        assert (castle.abandon_end, castle.cancel_abandon_end) == ends
        assert f"an {command} reply" in caplog.text


class TestService:
    def test_the_castle_read_shows_the_timers(self):
        client = make_client(state=logged_in_state(gcl=gcl(AOT=86000, CAT=10000, TA=3600)))

        outpost = next(castle for castle in client.castle.castles if castle.id == OUTPOST)

        assert 85990 < outpost.abandon_seconds() <= 86000
        assert 9990 < outpost.cancel_abandon_seconds() <= 10000
        assert 3590 < outpost.no_abandon_seconds() <= 3600
