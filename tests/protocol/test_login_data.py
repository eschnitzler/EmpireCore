"""The login data (gbd) as one typed payload, and the faction join reply (fjf)."""

import logging

import pytest

from empire_core.events.models import BerimondFactionJoinedResponse
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

    def test_a_falsy_section_is_none_quietly_but_counts_as_sent(self, caplog):
        with caplog.at_level(logging.WARNING):
            login = LoginDataResponse.model_validate({"gal": None, "gkl": 0, "tmp": "", "skl": False})

        assert (login.alliance, login.royal_towers, login.treasure_maps, login.skills) == (None, None, None, None)
        assert login.sent_sections == {"gal", "gkl", "tmp", "skl"}
        assert caplog.text == ""

    @pytest.mark.parametrize("value", [5, "x", [1], [[1]], True, -1.5, {"bogus": [1]}, {"A": 5}])
    def test_no_section_value_fails_the_whole_login(self, value):
        sections = {
            field.validation_alias
            for field in LoginDataResponse.model_fields.values()
            if isinstance(field.validation_alias, str)
        } - {"E"}

        login = LoginDataResponse.model_validate(dict.fromkeys(sections, value))

        assert login.sent_sections == sections

    def test_a_falsy_gatp_is_a_training_that_runs_nothing(self):
        # parse_GATP drops the running program before it looks at the block
        login = LoginDataResponse.model_validate({"gatp": None})
        assert login.officer_training is not None and not login.officer_training.is_set
        assert login.sent_sections == {"gatp"}

    def test_the_blocks_the_client_reads_by_a_key_need_it_truthy(self):
        login = LoginDataResponse.model_validate({"bie": {"GE": 0}, "pgl": {"G": None, "RA": 2}, "mcd": {"MTC": ""}})
        assert (login.boosted_global_effects, login.gifts, login.messages_sent_today) == (None, None, None)
        assert login.sent_sections == {"bie", "pgl", "mcd"}

    def test_a_falsy_mcd_gives_way_to_the_login_datas_counts(self):
        login = LoginDataResponse.model_validate({"mcd": 0, "MTC": [[2, 3]]})
        assert login.messages_sent_today is not None and login.messages_sent_today.sent == {2: 3}
        assert LoginDataResponse.model_validate({"mcd": {"X": 1}, "MTC": [[2, 3]]}).messages_sent_today is None

    def test_the_kpis_fki_is_read_but_is_no_section(self):
        login = LoginDataResponse.model_validate({"kpi": {"UL": [], "fki": {"BCR": 1}}})
        assert login.berimond_kingdom_status is not None and login.berimond_kingdom_status.ursidae_capital_reachable
        assert login.sent_sections == {"kpi"}
        assert LoginDataResponse.model_validate({"kpi": {"UL": [], "fki": 0}}).berimond_kingdom_status is None

    def test_the_error_code_is_no_section(self):
        login = LoginDataResponse.model_validate({"E": 0, "gcu": {"C1": 1}})

        assert login.sent_sections == {"gcu"}

    def test_the_live_login_reads_without_a_warning(self, caplog):
        with caplog.at_level(logging.WARNING):
            login = LoginDataResponse.model_validate(LIVE_LOGIN)

        assert login.sent_sections == set(LIVE_LOGIN)
        assert caplog.text == ""

    def test_sections_without_a_model_stay_extras(self):
        login = LoginDataResponse.model_validate({"nsm": 1, "atl": {"X": 1}})
        assert login.model_extra == {"nsm": 1, "atl": {"X": 1}}


class TestFactionJoined:
    def test_the_blocks_and_the_faction(self):
        joined = parse_response(
            "fjf",
            {"kpi": {"UL": []}, "sei": {"E": [{"EID": 83, "RS": 60}]}, "mir": {"gcl": {"PID": 7, "C": []}}, "FID": 2},
        )
        assert isinstance(joined, BerimondFactionJoinedResponse)
        assert joined.kingdoms is not None and joined.kingdoms.kingdoms == ()
        assert joined.events is not None and joined.events.entries[0].event_id == 83
        assert joined.castle_lists is not None and joined.castle_lists.castles is not None
        assert int(joined.faction) == 2

    def test_falsy_blocks_are_none(self):
        joined = BerimondFactionJoinedResponse.model_validate({"kpi": None, "sei": [], "mir": 0})
        assert (joined.kingdoms, joined.events, joined.castle_lists) == (None, None, None)
