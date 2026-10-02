"""GameState progress sections: rei, boi, gmu, ufa, ufp, uar, vli, gri and cpi."""

import math
from typing import Any

import pytest

from empire_core.enums import TitleSystem
from empire_core.player import PERMANENT_BOOSTER_DURATION, BoosterInfoResponse

# Shapes as a live login's gbd sends them, values changed
LOGIN: dict[str, Any] = {
    "gpi": {"PID": 7, "PN": "me"},
    "rei": {"ARID": -1, "ARRT": 0, "BR": [256, 1, 2, 171]},
    "boi": {
        "BO": [{"L": 4, "ID": 19, "RT": 3600}, {"L": 2, "ID": 11, "RT": PERMANENT_BOOSTER_DURATION}],
        "PA": 0,
        "PT": -1,
        "SU": [-1, -1, 0, 0, 0],
        "ST": [-1, 5, 0, 0, 0],
        "bfs": {"T": -1, "RT": 0},
    },
    "gmu": {"MP": 1000, "TSBM": 200, "HMP": 5000},
    "ufa": {"CF": 7000, "HF": 9000, "NHT": -1},
    "ufp": {"CFP": 400, "HFP": 800, "NHT": -1},
    "uar": {
        "FTM": {"RS": 600, "TOID": 11, "CTXT": -1, "NTFP": [900, 800, 700, 600]},
        "BTM": {"RS": 600, "TOID": 12, "CTXT": -1, "NTFP": [90, 80, 70, 60]},
        "ITM": {"TID": -1},
        "PFX": "FACTION",
        "SFX": "FACTION",
    },
    "vli": {"AVP": 300, "RA": [{"AID": 44, "P": [12]}, {"AID": 51, "P": [0]}], "FA": [112, 1]},
    "gri": {"RLC": 3, "RMC": 0, "RD": -1, "JM": "0"},
    "cpi": {"APM": 1, "TPM": 2},
}


class TestLoginSections:
    def test_every_section_is_read(self, state):
        state.update_from_packet("gbd", LOGIN)

        research = state.get_research()
        assert research.bought_research_ids == (256, 1, 2, 171)
        assert not research.is_research_active()

        boosts = state.get_boosts()
        assert [b.booster_id for b in boosts.boosters] == [19, 11]
        assert (boosts.bought_tool_slots, boosts.permanent_tool_slots, boosts.permanent_unit_slots) == (1, 1, 2)
        assert not boosts.is_premium_active() and boosts.premium_account_type() == -1
        assert boosts.festival is not None and not boosts.festival.is_active()

        assert state.get_might().might_points == 1000
        assert state.get_glory_points().glory_points == 7000
        assert state.get_title_ranks().prefix_title_system is TitleSystem.FACTION
        assert state.get_title_ranks().island_title.held_title_id == -1
        assert state.get_achievements().achievement_points == 300
        assert state.get_relocation().relocation_count == 3
        assert state.get_plague_monks().total_plague_monks == 2
        for section in ("rei", "boi", "gmu", "ufa", "uar", "vli", "gri", "cpi"):
            assert state.get_last_packet_time(section) is not None

    def test_the_login_ufp_is_ignored_and_the_push_read(self, state):
        # GBDCommand.exec never reads n.ufp; UFPCommand does
        state.update_from_packet("gbd", LOGIN)
        assert state.get_faction_points() is None
        state.update_from_packet("ufp", {"CFP": "450", "HFP": 800})
        assert state.get_faction_points().faction_points == 450

    def test_reset_forgets_them(self, state):
        state.update_from_packet("gbd", LOGIN)
        state.reset()
        assert state.get_research() is None and state.get_boosts() is None and state.get_achievements() is None


class TestPushesAndReplies:
    def test_pushes_replace_the_section(self, state):
        state.update_from_packet("gbd", LOGIN)
        state.update_from_packet("gmu", {"MP": 1100, "TSBM": 210, "HMP": 5000})
        state.update_from_packet("cpi", {"APM": 0, "TPM": 2})
        state.update_from_packet("gri", {"RLC": 4, "RMC": 3600, "RD": 600, "JM": 0})
        assert state.get_might().might_points == 1100
        assert state.get_plague_monks().available_plague_monks == 0
        relocation = state.get_relocation()
        assert relocation.relocation_count == 4
        assert 0 < relocation.remaining_relocation_seconds() <= 600

    def test_a_gmu_without_mp_and_hmp_is_not_read(self, state):
        # MightData.parse_GMU: e.hasOwnProperty("MP")&&e.hasOwnProperty("HMP")
        state.update_from_packet("gbd", LOGIN)
        state.update_from_packet("gmu", {"MP": 1})
        assert state.get_might().might_points == 1000

    def test_replies_carrying_a_section(self, state):
        state.update_from_packet("gbd", LOGIN)
        state.update_from_packet("res", {"rei": {"ARID": 172, "ARRT": 300, "BR": [256, 1, 2, 171]}, "gcu": {}})
        assert state.get_research().is_research_active()
        state.update_from_packet("cpm", {"cpi": {"APM": 0, "TPM": 2}})
        assert state.get_plague_monks().available_plague_monks == 0
        state.update_from_packet("ovs", {"boi": {"BO": [{"L": 5, "ID": 19, "RT": 7200}], "PA": 0, "PT": -1}})
        assert state.get_boosts().booster(19).level == 5

    def test_an_error_reply_is_not_applied(self, state):
        state.update_from_packet("gbd", LOGIN)
        state.update_from_packet("cpm", {"cpi": {"APM": 9, "TPM": 9}}, error_code=3)
        state.update_from_packet("rei", {"ARID": 5, "ARRT": 60, "BR": []}, error_code=3)
        assert state.get_plague_monks().available_plague_monks == 1
        assert state.get_research().bought_research_ids == (256, 1, 2, 171)


class TestReplyCurrencies:
    # RESCommand, BCSCommand and the other booster replies, UPSCommand, BTXCommand, SEQCommand,
    # ADOCommand and SBPCommand parse the reply's gcu next to the section
    @pytest.mark.parametrize(
        ("command", "section"),
        [
            ("res", {"rei": {"ARID": -1, "ARRT": 0, "BR": []}}),
            ("bcs", {"boi": {"BO": [], "PA": 0, "PT": -1}}),
            ("ups", {"boi": {"BO": [], "PA": 0, "PT": -1}}),
            ("btx", {"boi": {"BO": [], "PA": 0, "PT": -1}}),
            ("seq", {"gli": {"C": [], "B": []}}),
            ("ado", {}),
            ("sbp", {"cpi": {"APM": 1, "TPM": 2}}),
        ],
    )
    def test_the_reply_coins_and_rubies_are_applied(self, state, command, section):
        state.update_from_packet("gbd", {**LOGIN, "gcu": {"C1": 100, "C2": 5}})
        state.update_from_packet(command, {**section, "gcu": {"C1": 40, "C2": 2}})
        player = state.get_local_player()
        assert (player.coins, player.rubies) == (40, 2)

    def test_an_sbp_reply_applies_its_vip(self, state):
        state.update_from_packet("gbd", {**LOGIN, "vip": {"VP": 10, "VRL": 2, "VRS": 0}})
        state.update_from_packet("sbp", {"gcu": {"C1": 1}, "vip": {"VP": 50}})
        assert state.get_local_player().vip_points == 50

    def test_an_error_reply_keeps_the_coins(self, state):
        state.update_from_packet("gbd", {**LOGIN, "gcu": {"C1": 100, "C2": 5}})
        state.update_from_packet("bcs", {"gcu": {"C1": 1, "C2": 1}}, error_code=3)
        assert state.get_local_player().coins == 100


class TestStamps:
    def test_an_unreadable_section_is_not_applied_or_stamped(self, state):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}})
        state.update_from_packet("rei", {"raw": "unreadable"})
        state.update_from_packet("boi", {"raw": "unreadable"})
        assert state.get_research() is None and state.get_last_packet_time("rei") is None
        assert state.get_boosts() is None and state.get_last_packet_time("boi") is None


class TestMerges:
    def test_a_boi_keeps_the_boosters_it_does_not_list(self, state):
        # CastlePremiumBoostData.parse_BOI updates only the boosters in BO
        state.update_from_packet("gbd", LOGIN)
        state.update_from_packet("boi", {"BO": [{"L": 6, "ID": 19, "RT": 60}, {"L": 1, "ID": 30, "RT": 60}], "PA": 0})
        boosts = state.get_boosts()
        assert [(b.booster_id, b.level) for b in boosts.boosters] == [(19, 6), (11, 2), (30, 1)]
        assert boosts.festival is not None, "a boi without bfs keeps the festival"

    def test_a_bfs_reply_sets_the_festival(self, state):
        state.update_from_packet("bfs", {"T": 2, "RT": 3600})
        festival = state.get_boosts().festival
        assert festival.festival_type == 2 and festival.is_active()

    def test_a_vli_adds_to_what_is_known(self, state):
        state.update_from_packet("gbd", LOGIN)
        state.update_from_packet("vli", {"AVP": 310, "RA": [{"AID": 44, "P": [-1]}], "FA": [44]})
        achievements = state.get_achievements()
        assert achievements.achievement_points == 310
        assert achievements.finished_achievement_ids == (112, 1, 44)
        assert {p.achievement_id: p.progress for p in achievements.progress} == {44: (-1,), 51: (0,)}

    def test_a_uar_without_atm_keeps_the_alliance_city_title(self, state):
        state.update_from_packet("uar", {**LOGIN["uar"], "ATM": {"TID": 400, "PID": 7}})
        state.update_from_packet("uar", LOGIN["uar"])
        assert state.get_title_ranks().alliance_city_title.title_id == 400


class TestModels:
    def test_boosters_run_out_as_the_client_counts(self):
        boosts = BoosterInfoResponse.model_validate(LOGIN["boi"])
        timed, permanent = boosts.boosters
        start = timed.received_at
        assert timed.is_active(start + 3600) and not timed.is_active(start + 3601)
        assert permanent.is_permanent and permanent.is_active(start + 10**9)
        assert permanent.remaining_seconds() == math.inf

    def test_premium_account(self):
        boosts = BoosterInfoResponse.model_validate({"BO": [], "PA": 60, "PT": 2})
        assert boosts.is_premium_active() and boosts.premium_account_type() == 2
        assert boosts.premium_account_type(boosts.received_at + 61) == -1

    def test_relocation_time_counts_only_in_mode_0(self, state):
        state.update_from_packet("gri", {"RLC": 1, "RMC": 0, "RD": 600, "JM": 1})
        assert state.get_relocation().remaining_relocation_seconds() == 0

    @pytest.mark.parametrize("value", ["123abc", 123])
    def test_glory_points_read_like_parse_ufa(self, value):
        from empire_core.player import GloryPointsResponse

        assert GloryPointsResponse.model_validate({"CF": value}).glory_points == 123

    def test_models_are_frozen(self, state):
        state.update_from_packet("gbd", LOGIN)
        with pytest.raises(ValueError):
            state.get_research().current_research_id = 3  # type: ignore[misc]
