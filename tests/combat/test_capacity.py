"""Tests for wave capacity, wave filling and castle defence."""

from typing import ClassVar

import pytest

from empire_core.army.spy_army import SpyArmy
from empire_core.combat import (
    DefenderFlankEffects,
    Flank,
    Inventory,
    LegendaryFight,
    WaveCapacity,
    boost_to_modifier,
    fill_wave,
    fill_waves,
    fill_yard_wave,
    invasion_camp_level,
    max_attackers,
    max_wave_count,
    minimum_owner_level,
    owner_id_from_row,
    spied_castle_defense,
    wave_level,
    wave_limit_violations,
    yard_capacity,
)
from empire_core.combat.capacity import OTHER_PLAYER_INFO_AREA_TYPES
from empire_core.enums import MapItemType
from empire_core.gamedata import GameData
from empire_core.map.models.items import MapAreaItem
from empire_core.protocol.models import AttackWave, Commander, WaveFlank
from tests.combat.combat_helpers import SOLVER_PAYLOAD, placed, solver_data

# =============================================================================
# Wave capacity
# =============================================================================


class TestWaveCapacity:
    def test_capacity_follows_the_target_not_the_attacker(self):
        # Live samples, all made by the same level 70 attacker: a wave against
        # a level 13 castle holds far less than one against a level 70 castle.
        assert WaveCapacity.for_level(13).flank_soldiers == 15
        assert WaveCapacity.for_level(28).flank_soldiers == 30
        assert WaveCapacity.for_level(70).flank_soldiers == 64
        assert WaveCapacity.for_level(1).flank_soldiers == 3

    def test_flanks_and_middle_add_up_to_the_wave_total(self):
        # The middle takes what the two flanks leave, so the three must sum to
        # getMaxAttackers exactly at every level.
        for level in (1, 5, 12, 13, 26, 36, 50, 68, 69, 70, 100):
            capacity = WaveCapacity.for_level(level)
            assert capacity.total_soldiers() == max_attackers(level), f"level {level}"

    def test_attacker_count_caps_at_level_69(self):
        assert max_attackers(69) == 260
        assert max_attackers(70) == 320
        assert max_attackers(200) == 320

    def test_low_level_capacity_follows_the_linear_rule(self):
        # 5*level + 8, capped at 260.
        assert max_attackers(5) == 33
        assert max_attackers(12) == 68

    def test_level_70_matches_the_client(self):
        capacity = WaveCapacity.for_level(70)

        assert (capacity.flank_soldiers, capacity.middle_soldiers) == (64, 192)
        assert (capacity.flank_tools, capacity.middle_tools) == (40, 50)
        assert (capacity.flank_unit_slots, capacity.middle_unit_slots) == (2, 6)
        assert (capacity.flank_tool_slots, capacity.middle_tool_slots) == (2, 3)

    def test_slots_unlock_with_level(self):
        # Unit slots: flank [0, 13], middle [0, 0, 13, 13, 26, 26].
        assert WaveCapacity.for_level(12).flank_unit_slots == 1
        assert WaveCapacity.for_level(13).flank_unit_slots == 2
        assert WaveCapacity.for_level(12).middle_unit_slots == 2
        assert WaveCapacity.for_level(26).middle_unit_slots == 6
        # Tool slots: flank [0, 37], middle [0, 11, 37].
        assert WaveCapacity.for_level(36).flank_tool_slots == 1
        assert WaveCapacity.for_level(37).flank_tool_slots == 2
        assert WaveCapacity.for_level(10).middle_tool_slots == 1

    def test_flank_and_front_bonuses_are_independent(self):
        # The client resizes the sides and the middle from two different
        # effects, so one must not move the other.
        flank_only = WaveCapacity.for_level(70, flank_bonus_percent=50)
        front_only = WaveCapacity.for_level(70, front_bonus_percent=50)

        assert (flank_only.flank_soldiers, flank_only.middle_soldiers) == (96, 192)
        assert (front_only.flank_soldiers, front_only.middle_soldiers) == (64, 288)

    def test_matches_the_attack_dialog_across_targets(self):
        """Five targets captured from one level 70 attacker.

        Flank capacity matches exactly. The middle is within one unit on three
        of them because the game's effects panel rounds its percentages to one
        decimal, and the bonuses here are read off that panel.
        """
        castle = (57.8 + 60, 67.4 + 6.5)  # equipment + general
        camp = (46 + 60, 41 + 6.5)  # fewer effects apply to a camp
        legend = (30, 25)  # only in a legendary fight

        samples = [
            # target level, bonuses, legendary, expected flank, expected middle
            (13, castle, False, 32, 75),
            (28, castle, False, 65, 154),
            (70, castle, True, 159, 382),
            (1, camp, False, 6, 11),
            (45, camp, False, 96, 206),
        ]
        for level, (flank_bonus, front_bonus), legendary, want_flank, want_middle in samples:
            capacity = WaveCapacity.for_level(
                level,
                flank_bonus_percent=flank_bonus + (legend[0] if legendary else 0),
                front_bonus_percent=front_bonus + (legend[1] if legendary else 0),
            )
            assert capacity.flank_soldiers == want_flank, f"flank at level {level}"
            assert capacity.middle_soldiers == want_middle, f"middle at level {level}"

    # Expected flags from AttackDialogHelper.isLegendaryFight, CastleAttackArmyVO.init
    # and the CastleAttackWaveVO constructor, run in node against these inputs:
    # (attacker level, attacker legend level, target owner level, wave level,
    # owner id, owner legend level, area type) -> (unit amount, extra wave, flank tools).
    LEGENDARY_CASES: ClassVar[list] = [
        pytest.param((70, 1, 70, 70, 4242, 1, 1), (True, True, True), id="legend player"),
        pytest.param((70, 1, 70, 70, 4242, 0, 1), (False, True, True), id="level 70 player, no legend level"),
        pytest.param((70, 0, 70, 70, 4242, 3, 1), (False, False, True), id="attacker without legend level"),
        pytest.param((50, 0, 70, 70, 4242, 0, 26), (True, False, False), id="low player's monument"),
        pytest.param((70, 1, 75, 75, -1000, 0, 21), (True, True, True), id="alien camp at 75"),
        pytest.param((70, 1, 60, 60, -1002, 0, 34), (False, False, False), id="red alien camp at 60"),
        pytest.param((70, 1, 70, 70, -202, 0, 2), (False, False, False), id="robber baron camp"),
        pytest.param((70, 1, 70, 70, -1103, 0, 1), (False, False, True), id="listed collector"),
        pytest.param((70, 1, 70, 70, -1108, 0, 1), (False, False, False), id="collector isCollectorPlayer skips"),
        pytest.param((70, 1, 70, 70, 4242, 1, 17), (True, True, False), id="faction tower"),
    ]

    @pytest.mark.parametrize(("case", "flags"), LEGENDARY_CASES)
    def test_the_three_legendary_rules_match_the_client(self, case, flags):
        attacker_level, attacker_legend, owner_level, level, owner_id, owner_legend, area_type = case

        fight = LegendaryFight.evaluate(
            attacker_level=attacker_level,
            attacker_legend_level=attacker_legend,
            target_owner_level=owner_level,
            wave_level=level,
            owner_id=owner_id,
            owner_legend_level=owner_legend,
            area_type=area_type,
            has_other_player_info=area_type in OTHER_PLAYER_INFO_AREA_TYPES,
        )

        assert (fight.unit_amount, fight.extra_wave, fight.flank_tools) == flags

    def test_a_target_without_owner_info_gets_no_legend_skills(self):
        fight = LegendaryFight.evaluate(
            attacker_level=70,
            attacker_legend_level=5,
            target_owner_level=70,
            wave_level=70,
            owner_id=None,
            owner_legend_level=5,
            area_type=1,
            has_other_player_info=True,
        )

        assert not (fight.unit_amount or fight.extra_wave or fight.flank_tools)

    def test_the_owner_id_comes_from_the_row_or_the_alien_class(self):
        assert owner_id_from_row([1, 5, 6, 900, 4242, 1, 1, 1, 0, 0, "castle"]) == 4242
        assert owner_id_from_row([1, 5, 6, 900]) is None
        assert owner_id_from_row([21, 5, 6, 75, 0, 0, 30, 30, 0]) == -1000
        assert owner_id_from_row([34, 5, 6, 75]) == -1002
        # FactionCampMapobjectVO reads the row through InteractiveMapobjectVO, owner at 4
        assert owner_id_from_row([15, 5, 6, 900, 4242, 1, 1, 1, 0, 0, "camp", 0]) == 4242
        assert owner_id_from_row([2, 5, 6, 0, 12, 0]) is None
        assert owner_id_from_row(None) is None

    def test_bonuses_are_not_clamped(self):
        # An earlier version clamped these at 50%, which reproduced one target
        # and broke every other. Nothing in the tables caps them.
        assert WaveCapacity.for_level(70, flank_bonus_percent=60).flank_soldiers == 103
        assert WaveCapacity.for_level(70, flank_bonus_percent=117.8).flank_soldiers == 140

    def test_wave_count_unlocks_and_conquest_adds_two(self):
        assert max_wave_count(12) == 1
        assert max_wave_count(13) == 2
        assert max_wave_count(26) == 3
        assert max_wave_count(51) == 4
        assert max_wave_count(70, conquer=True) == 6
        assert max_wave_count(70, bonus=1) == 5

    def test_per_flank_lookups(self):
        capacity = WaveCapacity.for_level(70)

        assert capacity.soldier_capacity(Flank.MIDDLE) == 192
        assert capacity.soldier_capacity(Flank.LEFT) == 64
        assert capacity.soldier_capacity(Flank.RIGHT) == 64
        assert capacity.tool_slot_type(Flank.MIDDLE) == 1
        assert capacity.tool_slot_type(Flank.LEFT) == 2


class TestFillWaves:
    def test_waves_are_sized_and_counted_from_the_level(self):
        game = solver_data()
        # Level 13: 73 attackers, so 15 per flank and 43 in the middle.
        inventory = Inventory({601: 10_000})

        waves = fill_waves(inventory, game, level=13)

        assert len(waves) == 2
        first = waves[0].model_dump(by_alias=True)
        assert placed(first["L"]["U"]) == [[601, 15]]
        assert placed(first["M"]["U"]) == [[601, 43]]
        assert waves[0].unit_count() == max_attackers(13)

    def test_filling_stops_when_the_pool_runs_dry(self):
        game = solver_data()
        # Enough for the first wave and a little of the second.
        waves = fill_waves(Inventory({601: 80}), game, level=13)

        assert len(waves) == 2
        assert waves[0].unit_count() == 73
        assert waves[1].unit_count() == 7

    def test_no_units_means_no_waves(self):
        assert fill_waves(Inventory({}), solver_data(), level=70) == []

    def test_conquest_attacks_get_more_waves(self):
        game = solver_data()
        pool = {601: 10_000}

        normal = fill_waves(Inventory(pool), game, level=70)
        conquest = fill_waves(Inventory(pool), game, level=70, conquer=True)

        assert len(normal) == 4
        assert len(conquest) == 6

    def test_a_level_70_wave_maxes_out(self):
        waves = fill_waves(Inventory({601: 10_000}), solver_data(), level=70)

        assert waves[0].unit_count() == 320


class TestYardCapacity:
    """The courtyard / final-assault wave."""

    def test_matches_four_captured_dialogs(self):
        # One account, attacker level 70, four targets. The implied bonus is
        # identical across all four, which is what confirms the formula.
        for target_level, expected in ((1, 3109), (13, 3349), (45, 3989), (70, 4489)):
            assert yard_capacity(70, target_level, bonus=2872) == expected

    def test_it_grows_with_both_levels(self):
        # Unlike a flank, the attacker's own level counts here too.
        assert yard_capacity(70, 10) > yard_capacity(10, 10)
        assert yard_capacity(70, 70) > yard_capacity(70, 10)

    def test_the_bonus_is_absolute_not_a_percentage(self):
        plain = yard_capacity(70, 13)
        assert yard_capacity(70, 13, bonus=100) == plain + 100

    def test_the_boost_is_a_multiplier_applied_last(self):
        import math

        plain = yard_capacity(70, 13, bonus=2872)
        # The client rounds once, at the end, so doubling the *rounded* result
        # is not the same answer: 3349.33 x 2 rounds to 6699, not 6698.
        unrounded = 20 * math.sqrt(70) + 50 + 20 * 13 + 2872

        assert boost_to_modifier(0) == 1.0
        assert yard_capacity(70, 13, bonus=2872, boost=0) == plain
        assert yard_capacity(70, 13, bonus=2872, boost=100) == round(unrounded * 2.0)

    def test_a_negative_boost_cannot_go_below_zero(self):
        assert boost_to_modifier(-500) == 0.0
        assert yard_capacity(70, 13, bonus=2872, boost=-500) == 0


class TestWaveWithTools:
    """A wave now carries tools, and the client's ordering is observable."""

    PAYLOAD = dict(
        SOLVER_PAYLOAD,
        units=[
            *SOLVER_PAYLOAD["units"],
            {
                "wodID": 611,
                "name": "Workshop",
                "type": "Ram",
                "typ": "Attack",
                "slotTypes": "1,2,9",
                "gateBonus": "10",
                "fightType": "1",
            },
        ],
    )

    def data(self):
        return GameData.parse("test", self.PAYLOAD)

    def capacity(self):
        return WaveCapacity(
            level=70,
            flank_soldiers=10,
            middle_soldiers=10,
            flank_tools=5,
            middle_tools=5,
            flank_unit_slots=1,
            middle_unit_slots=1,
            flank_tool_slots=1,
            middle_tool_slots=1,
        )

    def test_tools_are_placed_alongside_units(self):
        game = self.data()
        inv = Inventory({601: 100, 611: 100})
        defense = {
            f: DefenderFlankEffects(gate_bonus=0.30, melee_units_melee_strength=50)
            for f in (Flank.LEFT, Flank.MIDDLE, Flank.RIGHT)
        }

        wave = fill_wave(inv, game, self.capacity(), defense=defense)

        payload = wave.model_dump(by_alias=True)
        assert placed(payload["L"]["T"]) == [[611, 3]]  # 30 gate / 10 per ram
        assert placed(payload["L"]["U"]) == [[601, 10]]

    def test_tools_are_returned_when_a_flank_gets_no_units(self):
        game = self.data()
        # Rams but no soldiers: the tools must come back rather than be sent.
        inv = Inventory({611: 100})
        defense = {Flank.LEFT: DefenderFlankEffects(gate_bonus=0.30)}

        wave = fill_wave(inv, game, self.capacity(), defense=defense)

        payload = wave.model_dump(by_alias=True)
        assert placed(payload["L"]["T"]) == []
        assert inv.available(611) == 100

    def test_a_unit_only_wave_is_still_available(self):
        game = self.data()
        inv = Inventory({601: 100, 611: 100})
        defense = {Flank.LEFT: DefenderFlankEffects(gate_bonus=0.30)}

        wave = fill_wave(inv, game, self.capacity(), defense=defense, strategies=[])

        assert placed(wave.model_dump(by_alias=True)["L"]["T"]) == []
        assert inv.available(611) == 100


class TestYardWave:
    def test_units_only_and_capped_by_capacity(self):
        game = GameData.parse("test", SOLVER_PAYLOAD)
        inv = Inventory({601: 10_000})

        yard = fill_yard_wave(inv, game, 3349)

        assert yard == [[601, 3349]] + [[-1, 0]] * 7
        assert inv.available(601) == 10_000 - 3349

    def test_every_slot_goes_out_even_when_empty(self):
        game = GameData.parse("test", SOLVER_PAYLOAD)
        assert fill_yard_wave(Inventory({}), game, 3349) == [[-1, 0]] * 8


class TestYardRounding:
    def test_a_half_unit_rounds_up_not_to_even(self):
        # base 50, boost 1 -> 50.5. JS Math.round gives 51; Python's round gives 50.
        assert yard_capacity(0, 0, boost=1) == 51


class TestWhichLevelDrivesWhat:
    """Two different levels, and mixing them up changes every number."""

    def test_flanks_tools_and_slots_follow_the_target(self):
        small = WaveCapacity.for_level(13)
        large = WaveCapacity.for_level(70)

        assert small.flank_soldiers < large.flank_soldiers
        assert small.flank_tools < large.flank_tools
        assert small.middle_unit_slots < large.middle_unit_slots

    def test_wave_count_follows_the_attacker(self):
        # A level 70 attacker gets four waves whether the target is level 1 or
        # level 70; the target only decides how big each one is.
        assert max_wave_count(70) == 4
        assert max_wave_count(13) == 2

    def test_the_courtyard_grows_with_both(self):
        assert yard_capacity(70, 13) != yard_capacity(13, 70)


class TestAreaTypeLevelFloor:
    """``CastleAttackWaveVO`` opens with ``e = int(max(e, t))``."""

    def test_a_landmark_defends_at_its_own_level(self):
        # A level 12 owner's monument is still built for level 70.
        assert wave_level(12, MapItemType.MONUMENT) == 70
        assert wave_level(12, MapItemType.KINGS_TOWER) == 70
        assert wave_level(12, MapItemType.LABORATORY) == 70

    def test_an_ordinary_target_keeps_its_owners_level(self):
        for area_type in (MapItemType.CASTLE, MapItemType.OUTPOST, MapItemType.DUNGEON):
            assert wave_level(12, area_type) == 12
        assert wave_level(12, None) == 12

    def test_the_floor_never_lowers_the_level(self):
        assert wave_level(70, MapItemType.MONUMENT) == 70
        assert wave_level(80, MapItemType.MONUMENT) == 80

    def test_a_capital_reads_its_landmark(self):
        # The client takes this from the landmark at runtime, so it is supplied.
        assert wave_level(12, MapItemType.CAPITAL, landmark_min_level=55) == 55
        assert minimum_owner_level(12, MapItemType.CAPITAL, landmark_min_level=55) == 55
        # Without it there is no floor to apply.
        assert wave_level(12, MapItemType.CAPITAL) == 12

    def test_the_floor_changes_what_a_flank_holds(self):
        assert WaveCapacity.for_level(wave_level(12, MapItemType.MONUMENT)).flank_soldiers > (
            WaveCapacity.for_level(12).flank_soldiers
        )


class TestWaveLimitViolations:
    def test_a_legal_attack_reports_nothing(self):
        capacity = WaveCapacity.for_level(70)
        wave = AttackWave(L=WaveFlank(U=[[601, capacity.flank_soldiers]]))

        assert wave_limit_violations([wave], capacity) == []

    def test_an_overfull_flank_is_named(self):
        capacity = WaveCapacity.for_level(70)
        wave = AttackWave(L=WaveFlank(U=[[601, capacity.flank_soldiers + 1]]))

        problems = wave_limit_violations([wave], capacity)

        assert len(problems) == 1
        assert "wave 0 L" in problems[0]

    def test_an_overfull_courtyard_is_named(self):
        capacity = WaveCapacity.for_level(70)
        yard = [[601, 5000]] + [[-1, 0]] * 7

        problems = wave_limit_violations([], capacity, yard=yard, yard_capacity=4489)

        assert problems == ["courtyard: 5000 units, limit 4489"]

    def test_empty_courtyard_slots_do_not_count(self):
        capacity = WaveCapacity.for_level(70)

        assert wave_limit_violations([], capacity, yard=[[-1, 0]] * 8, yard_capacity=0) == []


class TestCastellanDefence:
    """The defending castellan, from a live aci capture and its effects panel."""

    PAYLOAD = {
        "effecttypes": [
            {"effectTypeID": "6", "name": "wallBonus"},
            {"effectTypeID": "7", "name": "gateBonus"},
            {"effectTypeID": "8", "name": "moatBonus"},
            {"effectTypeID": "9", "name": "meleeBonus"},
            {"effectTypeID": "10", "name": "rangeBonus"},
            {"effectTypeID": "31", "name": "defenseBonus"},
            {"effectTypeID": "32", "name": "defenseBoostYard"},
        ],
        "effects": [
            {"effectID": "515", "name": "newDefenseWallBonusPVP", "effectTypeID": "6", "capID": "2100"},
            {"effectID": "524", "name": "newDefenseGateBonusPVP", "effectTypeID": "7", "capID": "2105"},
            {"effectID": "529", "name": "newDefenseMoatBonusPVP", "effectTypeID": "8", "capID": "2110"},
            {"effectID": "518", "name": "newDefenseMeleeBonusPVP", "effectTypeID": "9", "capID": "2103"},
            {"effectID": "527", "name": "newDefenseRangeBonusPVP", "effectTypeID": "10", "capID": "2108"},
            {"effectID": "533", "name": "newDefenseBonusPVP", "effectTypeID": "31", "capID": "2113"},
            {"effectID": "532", "name": "newDefenseBoostYardPVP", "effectTypeID": "32", "capID": "2112"},
        ],
        "effectCaps": [
            {"capID": "2100", "maxTotalBonus": "420"},
            {"capID": "2103", "maxTotalBonus": "324"},
            {"capID": "2105", "maxTotalBonus": "420"},
            {"capID": "2108", "maxTotalBonus": "324"},
            {"capID": "2110", "maxTotalBonus": "270"},
            {"capID": "2112", "maxTotalBonus": "298"},
            {"capID": "2113", "maxTotalBonus": "38"},
        ],
    }

    # Three items each granting wall/gate/moat, and three each granting
    # melee/range/courtyard. Verbatim from the capture's B block.
    CASTELLAN = {
        "ID": 1,
        "WID": 1,
        "EQ": [],
        "AE": [],
        "E": [
            [515, [140.0], "EQ"],
            [524, [140.0], "EQ"],
            [529, [90.0], "EQ"],
            [515, [140.0], "EQ"],
            [524, [140.0], "EQ"],
            [529, [90.0], "EQ"],
            [533, [5.0], "EQ"],
            [518, [120.0], "EQ"],
            [527, [120.0], "EQ"],
            [532, [110.0], "EQ"],
            [518, [120.0], "EQ"],
            [527, [120.0], "EQ"],
            [532, [110.0], "EQ"],
            [518, [120.0], "EQ"],
            [527, [120.0], "EQ"],
            [532, [110.0], "EQ"],
        ],
    }

    def parts(self):
        from empire_core.combat import EffectResolver, commander_bonuses
        from empire_core.protocol.models import Commander

        game = GameData.parse("test", self.PAYLOAD)
        return EffectResolver(game), commander_bonuses(game, Commander.model_validate(self.CASTELLAN))

    def test_the_fortification_matches_the_effects_panel(self):
        from empire_core.combat import castellan_fortification

        resolver, bonuses = self.parts()

        # The panel reads +280% wall, +280% gate, +180% moat.
        assert castellan_fortification(resolver, bonuses, area_type=1) == pytest.approx((2.8, 2.8, 1.8))

    def test_a_flank_multiplier_is_capped(self):
        from empire_core.combat import castellan_defense_multiplier

        resolver, bonuses = self.parts()

        # 3 x 120% of melee unit strength is capped at 324%, plus the 5%
        # all-flank defense bonus. The panel reads "+360% (max: 324%)".
        assert castellan_defense_multiplier(
            resolver, bonuses, flank=Flank.LEFT, melee=True, area_type=1
        ) == pytest.approx(3.29)

    def test_the_middle_also_takes_the_courtyard_boost(self):
        from empire_core.combat import castellan_defense_multiplier

        resolver, bonuses = self.parts()

        # 3 x 110% capped at 298%, added on the middle flank - which is where
        # the client adds it, not on the courtyard.
        assert castellan_defense_multiplier(
            resolver, bonuses, flank=Flank.MIDDLE, melee=True, area_type=1
        ) == pytest.approx(6.27)

    def test_the_courtyard_does_not_take_its_own_boost(self):
        from empire_core.combat import castellan_defense_multiplier

        resolver, bonuses = self.parts()

        assert castellan_defense_multiplier(
            resolver, bonuses, flank=Flank.YARD, melee=True, area_type=1
        ) == pytest.approx(3.29)


class TestInvasionCampLevel:
    """
    An invasion event camp's level, which its map row does not carry.

    The rows are live captures; the tables are trimmed to the ranks they name.
    """

    PAYLOAD = {
        "daimyoCastles": [
            {"id": "1", "rank": "1", "level": "81", "wallBonus": "110", "gateBonus": "110"},
            {"id": "3", "rank": "1", "level": "83", "wallBonus": "110", "gateBonus": "110"},
        ],
        "daimyoTownships": [
            {"id": "25", "rank": "3", "level": "110"},
            {"id": "26", "rank": "4", "level": "116"},
        ],
        "leaguetypes": [
            {"leaguetypeID": "1", "eventID": "80", "minLevel": 10, "maxLevel": "69", "countVictoryMin": "16"},
            {"leaguetypeID": "2", "eventID": "80", "minLevel": 70, "maxLevel": "369", "countVictoryMin": "81"},
            {"leaguetypeID": "1", "eventID": "72", "minLevel": 10, "maxLevel": "69", "countVictoryMin": "61"},
        ],
        "eventAutoScalingCamps": [{"eventAutoScalingCampID": "3", "camplevel": "70"}],
    }

    @pytest.fixture
    def data(self) -> GameData:
        return GameData.parse("test", self.PAYLOAD)

    def level(self, data: GameData, row: list, player_level: int) -> int | None:
        return invasion_camp_level(data, MapAreaItem.from_list(row), player_level)

    def test_a_samurai_camp_starts_where_the_players_league_starts(self, data):
        row = [29, 624, 240, -1, 0, -1787922790, 0, -651, -1, 110, 110, 0]

        assert self.level(data, row, 70) == 81
        assert self.level(data, row, 45) == 16

    def test_every_defeat_raises_a_samurai_camp(self, data):
        row = [29, 624, 240, -1, 4, 0, 0, 0, -1, 110, 110, 0]

        assert self.level(data, row, 70) == 85

    def test_a_nomad_camp_climbs_from_the_nomad_invasions_league(self, data):
        # NomadCampMapObjectVO.dungeonLevel: the nomad invasion's (event 72) base camp level plus the victories
        row = [27, 624, 240, -1, 4, 0, 0, 0, -1, 110, 110, 0]

        assert self.level(data, row, 45) == 65
        assert self.level(data, row, 70) is None
        assert self.level(data, [27, 624, 240, -1, 4, 0, 0, 0, 3, 110, 110, 0], 45) == 70

    def test_a_daimyo_castle_rank_is_looked_up_not_counted_off(self, data):
        # Rank 3 is level 83, not two levels past rank 1 by arithmetic: the
        # level jumps at a rank boundary.
        assert self.level(data, [37, 624, 242, -1, 1, 0, 0, 15, -1, 110, 110, 0], 70) == 81
        assert self.level(data, [37, 624, 242, -1, 3, 0, 0, 15, -1, 110, 110, 0], 70) == 83

    def test_a_township_is_fought_at_the_attackers_own_level(self, data):
        # The game counts whoever attacks a township as its owner, so its rank
        # says nothing about the level it is fought at.
        row = [38, 619, 250, -1, 26, 0, 0, 0, -1, 100, 100, 0]

        assert self.level(data, row, 70) == 70
        assert self.level(data, row, 45) == 45
        # Not rank 26's own level, which the table does carry.
        assert data.get_event_camp("daimyoTownships", 26) is not None

    def test_a_chosen_difficulty_overrides_the_rank(self, data):
        assert self.level(data, [37, 624, 242, -1, 1, 0, 0, 15, 3, 110, 110, 0], 70) == 70

    def test_a_rank_the_tables_do_not_describe_has_no_level(self, data):
        assert self.level(data, [37, 624, 242, -1, 99, 0, 0, 0, -1, 110, 110, 0], 70) is None
        # A player too low for any samurai band gets no level either.
        assert self.level(data, [29, 624, 240, -1, 0, 0, 0, 0, -1, 110, 110, 0], 5) is None

    def test_a_row_too_short_to_name_its_camp_has_no_level(self, data):
        # The game reads a row this short as not on the map at all. Taking the
        # missing field as a zero would report the band's base as a real level.
        assert self.level(data, [29, 624, 240], 70) is None
        assert self.level(data, [38, 619, 250], 70) is None
        # A camp that really is at zero defeats still has a level.
        assert self.level(data, [29, 624, 240, -1, 0, 0, 0, 0, -1, 110, 110, 0], 70) == 81

    def test_other_area_types_are_not_invasion_camps(self, data):
        assert self.level(data, [1, 700, 710, 900, 4242, 1, 1, 1, 0, 0, "castle"], 70) is None
        assert self.level(data, [2, 625, 244, -1, 0, -1, 0], 70) is None


class TestSpiedCastleDefence:
    """
    A spied castle's defenders, tools, castellan and legend skills per flank.

    Expected values from running the client's own
    ``FightScreenHelper.getDefendingUnitStrength`` and ``getDefenceBonuses``,
    with its ``ToolUnitVO.getBonusByEffect`` and ``EffectValueSimple``, in node
    on these rows. Tool and skill rows are from items payload v786.03; 990 is a
    made-up unit with no role. The client's castellan helpers were stubbed with the values the
    library's castellan helpers give for :class:`TestCastellanDefence`'s
    castellan.
    """

    PAYLOAD = {
        "units": [
            {"wodID": "601", "name": "Barracks", "role": "melee", "meleeDefence": "5", "rangeDefence": "3"},
            {"wodID": "211", "name": "Barracks", "role": "ranged", "meleeDefence": "25", "rangeDefence": "42"},
            {"wodID": "990", "name": "Barracks", "meleeDefence": "10", "rangeDefence": "7"},
            {"wodID": "645", "name": "Dworkshop", "typ": "Defence", "slotTypes": "1,9", "defRangeBonus": "50"},
            {"wodID": "730", "name": "Elitetool", "typ": "Defence", "slotTypes": "1,9", "defMeleeBonus": "33"},
            {"wodID": "441", "name": "Dworkshop", "typ": "Defence", "slotTypes": "6,9", "effects": "618&20,619&1"},
            {"wodID": "450", "name": "Dworkshop", "typ": "Defence", "slotTypes": "6,9", "effects": "618&40,619&10"},
            {
                "wodID": "326",
                "name": "Dworkshop",
                "typ": "Defence",
                "slotTypes": "1,9",
                "wallBonus": "50",
                "defRangeBonus": "30",
            },
            {"wodID": "646", "name": "Dworkshop", "typ": "Defence", "slotTypes": "4,9", "moatBonus": "80"},
        ],
        "effects": [
            *TestCastellanDefence.PAYLOAD["effects"],
            {"effectID": "618", "name": "bonusWallCapacity", "effectTypeID": "12", "capID": "99"},
            {"effectID": "619", "name": "bonusDefencePower", "effectTypeID": "31", "capID": "99"},
        ],
        "effecttypes": TestCastellanDefence.PAYLOAD["effecttypes"],
        "effectCaps": TestCastellanDefence.PAYLOAD["effectCaps"],
        "legendskills": [
            {"skillID": "331", "effectType": "defenseMeleeBonus", "totalEffectValue": "0.5"},
            {"skillID": "371", "effectType": "defenseRangeBonus", "totalEffectValue": "0.5"},
            {"skillID": "430", "effectType": "wallBonus", "totalEffectValue": "6"},
            {"skillID": "301", "effectType": "gateBonus", "totalEffectValue": "3"},
            {"skillID": "512", "effectType": "moatBonus", "totalEffectValue": "5"},
            {"skillID": "551", "effectType": "defenseBonus", "totalEffectValue": "12"},
        ],
    }

    # Left, middle, right, keep, stronghold, support.
    ARMY = [
        [[601, 100], [645, 3], [441, 2], [450, 1]],
        [[211, 50], [730, 1], [326, 1]],
        [[990, 20], [601, 0]],
        [[601, 10]],
        [],
        [[211, 5], [646, 1]],
    ]

    # Per flank: the client's [meleeMelee, meleeRange, meleeMult, rangeMelee,
    # rangeRange, rangeMult] and [wall, gate, moat].
    ITEMS_ONLY = {
        Flank.LEFT: ([500, 300, 1.11, 125, 210, 1.61], [0.5, 0, 1.1]),
        Flank.MIDDLE: ([0, 0, 1.33, 1375, 2310, 1.3], [1, 0.4, 1.1]),
        Flank.RIGHT: ([0, 0, 1, 325, 350, 1], [0.5, 0, 1.1]),
        Flank.YARD: ([50, 30, 1, 125, 210, 1], [0.5, 0, 1.1]),
    }
    WITH_SKILLS = {
        Flank.LEFT: ([500, 300, 1.1199999999999999, 125, 210, 1.615], [0.56, 0, 1.1500000000000001]),
        Flank.MIDDLE: (
            [0, 0, 1.3399999999999999, 1375, 2310, 1.305],
            [1.06, 0.43000000000000005, 1.1500000000000001],
        ),
        Flank.RIGHT: ([0, 0, 1.0099999999999998, 325, 350, 1.005], [0.56, 0, 1.1500000000000001]),
        Flank.YARD: ([50, 30, 1.0099999999999998, 125, 210, 1.005], [0.56, 0, 1.1500000000000001]),
    }
    WITH_CASTELLAN_AND_SKILLS = {
        Flank.LEFT: ([500, 300, 4.405, 125, 210, 4.905], [3.36, 0, 2.95]),
        Flank.MIDDLE: (
            [0, 0, 7.6049999999999995, 1375, 2310, 7.574999999999999],
            [3.86, 3.2299999999999995, 2.95],
        ),
        Flank.RIGHT: ([0, 0, 4.295, 325, 350, 4.295], [3.36, 0, 2.95]),
        Flank.YARD: ([50, 30, 4.295, 125, 210, 4.295], [3.36, 0, 2.95]),
    }

    def defense(self, **kwargs) -> dict[Flank, DefenderFlankEffects]:
        army = SpyArmy.from_spy_data(self.ARMY)
        assert army is not None
        game = GameData.parse("test", self.PAYLOAD)
        return spied_castle_defense(game, army, wall_bonus=0.5, gate_bonus=0.4, moat_bonus=0.3, area_type=1, **kwargs)

    def assert_matches(self, defense: dict[Flank, DefenderFlankEffects], expected) -> None:
        for flank, (strength, fortification) in expected.items():
            effects = defense[flank]
            assert [
                effects.melee_units_melee_strength,
                effects.melee_units_range_strength,
                effects.melee_bonus,
                effects.range_units_melee_strength,
                effects.range_units_range_strength,
                effects.range_bonus,
            ] == strength, flank
            assert [effects.wall_bonus, effects.gate_bonus, effects.moat_bonus] == fortification, flank

    def test_tools_raise_the_multipliers_and_roleless_units_defend_as_ranged(self):
        self.assert_matches(self.defense(), self.ITEMS_ONLY)

    def test_defender_legend_skills_raise_the_defenders_and_the_fortification(self):
        self.assert_matches(
            self.defense(defender_legend_skill_ids=[331, 371, 430, 301, 512, 551, 331]),
            self.WITH_SKILLS,
        )

    def test_the_castellan_is_added_after_the_items_and_before_the_skills(self):
        self.assert_matches(
            self.defense(
                castellan=Commander.model_validate(TestCastellanDefence.CASTELLAN),
                defender_legend_skill_ids=[331, 371, 430, 301, 512, 551],
            ),
            self.WITH_CASTELLAN_AND_SKILLS,
        )

    def test_an_unknown_legend_skill_is_an_error(self):
        with pytest.raises(ValueError, match="Defender legend skill 9999"):
            self.defense(defender_legend_skill_ids=[9999])
