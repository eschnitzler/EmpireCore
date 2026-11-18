"""Whether you own the premium flag: gpf, a login section and a push."""

import pytest

from empire_core.player import PremiumFlagResponse
from empire_core.protocol.models import parse_response
from empire_core.state.login_data import LoginDataResponse
from tests.service_helpers import logged_in_state, make_client


# Expected values from the client's `1 == e.PF` (CastleUserData.parse_GPF), run in node
@pytest.mark.parametrize(
    ("value", "owned"),
    [(1, True), ("1", True), (True, True), ([1], True), (0, False), (2, False), ("x", False), (None, False)],
)
def test_the_flag_is_one(value, owned):
    flag = parse_response("gpf", {"PF": value})
    assert isinstance(flag, PremiumFlagResponse)
    assert flag.has_premium_flag is owned


def test_a_missing_flag_is_not_owned():
    assert PremiumFlagResponse.model_validate({}).has_premium_flag is False


def test_the_login_data_types_it():
    login = LoginDataResponse.model_validate({"gpf": {"PF": 1}})
    assert login.premium_flag is not None and login.premium_flag.has_premium_flag


def test_an_unreadable_login_section_is_logged(caplog):
    assert LoginDataResponse.model_validate({"gpf": "bad"}).premium_flag is None
    assert "premium_flag login section" in caplog.text


def owned(state) -> bool | None:
    flag = make_client(state=state).player.premium_flag
    return None if flag is None else flag.has_premium_flag


class TestState:
    def test_none_before_the_login_data_brings_it(self):
        client = make_client(state=logged_in_state())
        assert client.player.premium_flag is None

    def test_the_login_section_is_applied_and_stamped(self):
        client = make_client(state=logged_in_state(gpf={"PF": 1}))
        flag = client.player.premium_flag
        assert flag is not None and flag.has_premium_flag
        assert client.state.get_last_packet_time("gpf") is not None

    def test_an_empty_block_reads_as_not_owned(self):
        state = logged_in_state(gpf={"PF": 1})
        state.update_from_packet("gbd", {"gpi": {"PID": 1001}, "gpf": {}})
        assert owned(state) is False

    @pytest.mark.parametrize("body", [None, 0, "", "bad"])
    def test_a_falsy_or_unreadable_block_keeps_the_flag(self, body):
        state = logged_in_state(gpf={"PF": 1})
        state.update_from_packet("gbd", {"gpi": {"PID": 1001}, "gpf": body})
        assert owned(state) is True

    def test_a_push_replaces_it(self):
        state = logged_in_state(gpf={"PF": 0})
        state.update_from_packet("gpf", {"PF": 1})
        assert owned(state) is True

    def test_a_refused_push_is_not_applied(self):
        state = logged_in_state(gpf={"PF": 0})
        state.update_from_packet("gpf", {"PF": 1}, error_code=1)
        assert owned(state) is False
