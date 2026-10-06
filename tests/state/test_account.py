"""GameState account sections: drt, gai, gatp, bie, pgl, rww and nrf."""

import math
from typing import Any

import pytest
from pydantic import ValidationError

from empire_core.attack import AttackCounterResponse
from empire_core.castle import WishingWellResponse
from empire_core.gamedata import Effect, GlobalEffect
from empire_core.player import OfficerBonus, OfficerTraining

# Shapes as a live login's gbd sends them, values changed
LOGIN: dict[str, Any] = {
    "gpi": {"PID": 7, "PN": "me"},
    "drt": {"STR": 12000},
    "gai": {"AC": 2, "ACTH": 3500, "ACGR": 0.007},
    "gatp": {"S": -1, "E": [], "RS": -1},
    "bie": {"GE": []},
    "pgl": {"RA": 40, "G": []},
    "rww": {"RT": -1, "L": 0},
    "nrf": {"NR": 0},
}
SECTIONS = ("drt", "gai", "gatp", "bie", "pgl", "rww", "nrf")


class TestLoginSections:
    def test_every_section_is_read(self, state):
        state.update_from_packet("gbd", LOGIN)

        reset = state.get_daily_reset()
        assert 11990 < reset.remaining_seconds() <= 12000
        counter = state.get_attack_counter()
        assert (counter.attack_count, counter.attack_count_threshold, counter.growth_rate) == (2, 3500, 0.007)
        assert counter.travel_cost_surcharge == 0
        assert state.get_officer_training() is None
        assert state.get_boosted_global_effects().global_effect_ids == ()
        gifts = state.get_player_gifts()
        assert gifts.gifts == () and gifts.sendable_amount == 40 and gifts.can_send
        well = state.get_wishing_well()
        assert well.level == 0 and well.is_ready_to_start and not well.is_running
        assert state.get_new_relics().has_new_relics is False
        for section in SECTIONS:
            assert state.get_last_packet_time(section) is not None

    def test_reset_forgets_them(self, state):
        state.update_from_packet("gbd", LOGIN)
        state.reset()
        assert state.get_daily_reset() is None and state.get_attack_counter() is None
        assert state.get_wishing_well() is None and state.get_last_packet_time("drt") is None

    @pytest.mark.parametrize(
        ("section", "body"),
        [
            # GBDCommand.exec: n.gai&&...; parse_DRT, parse_RWW: e&&...
            ("gai", None),
            ("drt", None),
            ("rww", None),
            # parse_GIE: e&&e.GE; parse_PGL(n.pgl.G, ...): if(e)
            ("bie", {}),
            ("pgl", {"RA": 40}),
        ],
    )
    def test_a_section_the_client_skips_is_not_applied(self, state, section, body):
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, section: body})
        assert state.get_last_packet_time(section) is None


class TestPushesAndReplies:
    def test_a_gai_push_replaces_the_counter(self, state):
        state.update_from_packet("gbd", LOGIN)
        state.update_from_packet("gai", {"AC": 3600, "ACTH": 3500, "ACGR": 0.007})
        counter = state.get_attack_counter()
        assert counter.attack_count == 3600
        assert counter.travel_cost_surcharge == pytest.approx(math.exp(0.7) - 1)

    def test_a_bie_push_lists_the_boosted_effects(self, state):
        state.update_from_packet("bie", {"GE": [2, 11, 999]})
        effects = state.get_boosted_global_effects().global_effect_ids
        assert effects == (GlobalEffect.SPEED_BOOST_2, GlobalEffect.SPEED_BOOST_11, 999)
        assert effects[0] is GlobalEffect.SPEED_BOOST_2

    def test_a_pgl_reply_lists_the_gifts(self, state):
        state.update_from_packet("pgl", {"G": [[301, 2], ["302", 1]], "RA": 0})
        gifts = state.get_player_gifts()
        assert [(gift.package_id, gift.amount) for gift in gifts.gifts] == [(301, 2), (302, 1)]
        assert not gifts.can_send

    def test_an_rww_reply_starts_the_wishing_well(self, state):
        state.update_from_packet("gbd", LOGIN)
        state.update_from_packet("rww", {"RT": 3600, "L": 1})
        well = state.get_wishing_well()
        assert well.is_running and 3590 < well.remaining_seconds() <= 3600

    def test_a_refused_rww_is_not_applied(self, state):
        # RWWCommand parses only an ALL_OK reply
        state.update_from_packet("gbd", LOGIN)
        state.update_from_packet("rww", {"W": 1, "S": 2}, error_code=6)
        assert state.get_wishing_well().is_ready_to_start

    def test_an_nrf_push_flags_new_relics(self, state):
        state.update_from_packet("nrf", {"NR": 1})
        assert state.get_new_relics().has_new_relics


class TestOfficerTraining:
    def test_a_running_program_is_kept(self, state):
        state.update_from_packet("gbd", {**LOGIN, "gatp": {"S": 2, "E": [810, [5]], "RS": 7200}})
        training = state.get_officer_training()
        assert training.slot_id == 2 and training.bonus == OfficerBonus(effect=810, values=(5,))
        assert 7190 < training.remaining_seconds() <= 7200

    def test_a_gatp_without_a_program_drops_it(self, state):
        # parse_GATP sets _activeEffectVO=null before reading the block
        state.update_from_packet("gatp", {"S": 2, "E": [810, [5]], "RS": 7200})
        state.update_from_packet("gatp", {"S": -1, "E": [], "RS": -1})
        assert state.get_officer_training() is None
        assert state.get_last_packet_time("gatp") is not None

    def test_a_null_gatp_drops_it(self, state):
        state.update_from_packet("gatp", {"S": 2, "E": [810, [5]], "RS": 7200})
        state.update_from_packet("gbd", {"gpi": {"PID": 7}, "gatp": None})
        assert state.get_officer_training() is None

    def test_a_number_in_e_is_no_error_code(self, state):
        state.update_from_packet("gatp", {"S": 1, "E": 5, "RS": 100})
        training = state.get_officer_training()
        assert (training.slot_id, training.bonus) == (1, None)
        assert not hasattr(training, "error_code")

    def test_the_bonus_is_its_effect_and_values(self, state):
        state.update_from_packet("gatp", {"S": 2, "E": [276, [3, 4.5]], "RS": 7200})
        bonus = state.get_officer_training().bonus
        assert bonus is not None and bonus.effect is Effect(276) and bonus.values == (3, 4.5)
        with pytest.raises(ValidationError):
            bonus.values = ()  # type: ignore[misc]

    def test_a_gtp_swaps_in_its_running_program_with_the_time_left(self, state):
        # parse_GTP: setActiveTime(this._activeEffectVO.remainingTimeInSeconds) on the program from AT
        state.update_from_packet("gatp", {"S": 2, "E": [810, [5]], "RS": 7200})
        state.update_from_packet("gtp", {"AT": {"TE": 3, "S": 4, "E": [811, [7]], "D": 9000}, "TP": []})
        training = state.get_officer_training()
        assert (training.slot_id, training.bonus) == (4, OfficerBonus(effect=811, values=(7,)))
        assert 7190 < training.remaining_seconds() <= 7200
        assert state.get_last_packet_time("gtp") is not None

    def test_a_gtp_without_a_running_program_drops_it(self, state):
        state.update_from_packet("gatp", {"S": 2, "E": [810, [5]], "RS": 7200})
        state.update_from_packet("gtp", {"TP": [], "PC": 0})
        assert state.get_officer_training() is None

    def test_a_gtp_sets_no_program_when_none_is_known(self, state):
        state.update_from_packet("gtp", {"AT": {"TE": 3, "S": 4, "E": [811, [7]], "D": 9000}})
        assert state.get_officer_training() is None

    def test_an_error_gtp_changes_nothing(self, state):
        state.update_from_packet("gatp", {"S": 2, "E": [810, [5]], "RS": 7200})
        state.update_from_packet("gtp", {}, error_code=1)
        assert state.get_officer_training().slot_id == 2
        assert state.get_last_packet_time("gtp") is None


class TestModels:
    def test_the_surcharge_starts_past_the_threshold(self):
        # TravelConst.getAttackTravelCostC1: s<=a returns the plain cost
        at = AttackCounterResponse.model_validate({"AC": 10, "ACTH": 10, "ACGR": 0.5})
        past = AttackCounterResponse.model_validate({"AC": 12, "ACTH": 10, "ACGR": 0.5})
        assert at.travel_cost_surcharge == 0
        assert past.travel_cost_surcharge == pytest.approx(math.e - 1)

    def test_the_wishing_well_waits_to_be_collected_at_0(self):
        well = WishingWellResponse.model_validate({"RT": 0, "L": 3})
        assert well.is_ready_to_collect and not well.is_running and well.remaining_seconds() == 0

    def test_a_program_with_a_bonus_counts_as_set_without_time(self):
        # parse_GATP: (t>-1&&n>0||i.length>0)
        training = OfficerTraining.model_validate({"S": -1, "E": [810, [5]], "RS": 0})
        assert training.is_set and training.remaining_seconds() == 0
