"""The player sections of the login data, each also a push: gpi, gxp, gcu, vip, gho, gal, sce and glu."""

import pytest

from empire_core.gamedata import Currency
from empire_core.player.models.login import (
    Alliance,
    CurrencyResponse,
    ExperienceResponse,
    HonorResponse,
    LevelUpResponse,
    PlayerIdentityResponse,
    SpecialCurrenciesResponse,
    VipStatusResponse,
)
from empire_core.protocol.models import parse_response


class TestPlayerIdentity:
    def test_a_live_gpi(self):
        identity = PlayerIdentityResponse.model_validate(
            {"UID": 230862, "PID": 7, "PN": "me", "E": "-1", "V": 0, "CTAC": 1, "CL": 0, "RD": 1762208793}
        )
        assert (identity.user_id, identity.player_id, identity.name) == (230862, 7, "me")
        assert (identity.email, identity.email_confirmed, identity.is_cheater, identity.accepted_terms) == (
            "",
            False,
            False,
            True,
        )
        assert identity.success and identity.error_code == 0

    def test_the_email_is_not_an_error_code(self):
        identity = PlayerIdentityResponse.model_validate({"PID": 7, "E": "me@example.com", "V": "1"})
        assert (identity.email, identity.email_confirmed, identity.error_code) == ("me@example.com", True, 0)
        assert "error_code" not in identity.model_dump()

    @pytest.mark.parametrize(("value", "expected"), [("-1", ""), (-1, ""), (None, ""), ("x@y", "x@y")])
    def test_minus_one_is_no_email(self, value, expected):
        # parse_GPI: "-1" != e.E ? e.E : ""
        assert PlayerIdentityResponse.model_validate({"E": value}).email == expected

    def test_the_registry_knows_it(self):
        assert isinstance(parse_response("gpi", {"PID": 7}), PlayerIdentityResponse)


class TestExperience:
    def test_level_and_xp(self):
        experience = ExperienceResponse.model_validate({"XP": "5329", "LVL": 13, "LL": 0, "XPFCL": 1, "XPTNL": 2})
        assert (experience.xp, experience.level) == (5329, 13)

    @pytest.mark.parametrize("bad", [None, "", "x"])
    def test_a_level_that_is_no_number_is_none(self, bad):
        assert ExperienceResponse.model_validate({"XP": 1, "LVL": bad}).level is None


class TestCurrencyAndVip:
    def test_gcu_is_the_currency_totals(self):
        currencies = parse_response("gcu", {"C1": 155600, "C2": 3098})
        assert isinstance(currencies, CurrencyResponse) and (currencies.coins, currencies.rubies) == (155600, 3098)

    def test_vip_reads_each_key_through_int_and_keeps_no_negative_time(self):
        vip = VipStatusResponse.model_validate({"VP": "2", "VRL": 3, "VRS": -5, "UPG": 1.9})
        assert (vip.vip_points, vip.vip_level, vip.vip_seconds_left, vip.used_premium_commanders) == (2, 3, 0, 1)
        assert VipStatusResponse.model_validate({}).vip_points == 0

    def test_honor(self):
        honor = HonorResponse.model_validate({"H": "120", "RP": 95})
        assert (honor.honor, honor.ranking_points) == (120, 95)


class TestAlliance:
    def test_a_live_gal(self):
        alliance = Alliance.model_validate({"AID": 301, "R": 1, "N": "Iron Pact", "ACF": 22, "SA": 0})
        assert (alliance.alliance_id, alliance.rank, alliance.name, alliance.current_fame) == (301, 1, "Iron Pact", 22)
        assert alliance.is_member and not alliance.is_searching

    def test_the_client_reads_an(self):
        alliance = Alliance.model_validate({"AID": 5, "AN": "Clan", "SA": "1"})
        assert (alliance.name, alliance.is_searching) == ("Clan", True)

    @pytest.mark.parametrize("body", [{}, {"AID": 0}, {"AID": -1}, {"AID": "x"}])
    def test_no_alliance(self, body):
        assert not Alliance.model_validate(body).is_member


class TestSpecialCurrencies:
    def test_pairs_are_read_as_the_client_reads_them(self):
        # parseSCE: int(amount); a key the enum lacks stays a str
        currencies = parse_response("sce", [["PTT", 5], ["BAD", "not-a-number"], ["TEXT", "12.7"], ["NONE"], "x"])
        assert isinstance(currencies, SpecialCurrenciesResponse)
        assert currencies.amounts == {Currency.FAST_TRAVEL_FEATHERS: 5, "BAD": 0, "TEXT": 12, "NONE": 0}

    def test_a_dict_body_is_read_by_name(self):
        assert SpecialCurrenciesResponse.model_validate({"amounts": {"PTT": 1}}).amounts == {"PTT": 1}


class TestLevelUp:
    def test_a_level_up(self):
        level_up = LevelUpResponse.model_validate(
            {"gcu": {"C1": 160000, "C2": 3098}, "gxp": {"LVL": 14, "XP": 5880}, "L": 14, "LL": 0}
        )
        assert level_up.currencies is not None and level_up.currencies.coins == 160000
        assert level_up.experience is not None and (level_up.experience.level, level_up.experience.xp) == (14, 5880)
        assert (level_up.level, level_up.is_legend_level_up) == (14, False)

    def test_sections_that_are_no_objects_are_none(self):
        level_up = LevelUpResponse.model_validate({"gcu": None, "gxp": [], "L": "71", "LL": 1})
        assert (level_up.currencies, level_up.experience) == (None, None)
        assert (level_up.level, level_up.is_legend_level_up) == (71, True)
