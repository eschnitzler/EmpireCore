"""The login data (gbd) as one typed payload, and the faction join reply (fjf)."""

from empire_core.events.models import FactionJoinedResponse
from empire_core.protocol.models import parse_response
from empire_core.state.login_data import LoginDataResponse
from tests.state.test_player import LIVE_LOGIN


class TestLoginData:
    def test_the_live_sections_read_through_their_models(self):
        login = parse_response("gbd", {**LIVE_LOGIN, "gli": {"C": [{"ID": 3, "WID": 2}], "B": []}, "sce": [["PTT", 5]]})
        assert isinstance(login, LoginDataResponse)
        assert login.identity is not None and login.identity.player_id == 7
        assert login.experience is not None and (login.experience.level, login.experience.xp) == (13, 5329)
        assert login.currencies is not None and login.currencies.coins == 155600
        assert login.alliance is not None and login.alliance.name == "Iron Pact"
        assert login.protection is not None and login.second_protection is None
        assert login.commanders is not None and [c.commander_id for c in login.commanders.commanders] == [3]
        assert login.special_currencies is not None and login.special_currencies.amounts == {"PTT": 5}
        assert login.max_spies is None

    def test_an_unreadable_section_costs_only_itself(self, caplog):
        login = LoginDataResponse.model_validate({"gpi": {"PID": 7}, "gli": {"C": "bad"}, "gcu": "bad"})
        assert login.identity is not None and login.currencies is None
        assert "currencies login section" in caplog.text

    def test_sections_without_a_model_stay_extras(self):
        login = LoginDataResponse.model_validate({"nsm": 1, "atl": {"X": 1}})
        assert login.model_extra == {"nsm": 1, "atl": {"X": 1}}


class TestFactionJoined:
    def test_the_blocks_and_the_faction(self):
        joined = parse_response(
            "fjf",
            {"kpi": {"UL": []}, "sei": {"E": [{"EID": 83, "RS": 60}]}, "mir": {"gcl": {"PID": 7, "C": []}}, "FID": 2},
        )
        assert isinstance(joined, FactionJoinedResponse)
        assert joined.kingdoms is not None and joined.kingdoms.kingdoms == ()
        assert joined.events is not None and joined.events.entries[0].event_id == 83
        assert joined.castle_lists is not None and joined.castle_lists.castles is not None
        assert int(joined.faction) == 2

    def test_falsy_blocks_are_none(self):
        joined = FactionJoinedResponse.model_validate({"kpi": None, "sei": [], "mir": 0})
        assert (joined.kingdoms, joined.events, joined.castle_lists) == (None, None, None)
