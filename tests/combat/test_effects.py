"""Tests for attacker and defender effects and camp defences."""

import pytest

from empire_core.combat import (
    AttackerFlankEffects,
    DefenderFlankEffects,
    Flank,
    defender_flank_effects,
    event_camp_defense,
    robber_baron_camp_defense,
)
from empire_core.enums import Kingdom
from empire_core.gamedata import GameData, UnitStats
from tests.combat.combat_helpers import PAYLOAD, data, unit_of


def flanks_of(effects: dict[Flank, DefenderFlankEffects] | None) -> dict[Flank, DefenderFlankEffects]:
    """The per-flank effects, insisting the camp was found."""
    assert effects is not None, "no camp matched"
    return effects


class TestAttackerEffects:
    def test_stack_value_scales_with_capacity(self):
        effects = AttackerFlankEffects()
        unit = unit_of(data(), 211)

        # Capacity binds: 10 of a 270-attack unit.
        assert effects.soldier_stack_attack_value(unit, free_items=10, available=500) == 2700
        # Stock binds instead.
        assert effects.soldier_stack_attack_value(unit, free_items=500, available=3) == 810

    def test_bonus_is_applied_per_unit_and_truncated(self):
        # int() per unit, as the client does, not on the stack total.
        effects = AttackerFlankEffects(range_bonus=1.005)
        unit = unit_of(data(), 211)

        assert effects.soldier_stack_attack_value(unit, 10, 10) == 2710

    def test_role_selects_the_matching_bonus(self):
        effects = AttackerFlankEffects(melee_bonus=2.0, range_bonus=1.0)
        game = data()

        assert effects.soldier_stack_attack_value(unit_of(game, 601), 1, 1) == 200
        assert effects.soldier_stack_attack_value(unit_of(game, 211), 1, 1) == 270

    def test_a_roleless_unit_has_no_stack_value(self):
        # Tools are not units at all, and a unit with no role matches neither
        # bonus, so it can never be picked as a stack.
        assert data().get_unit(646) is None

        roleless = UnitStats.model_validate({"wodID": 1, "meleeAttack": "500"})
        assert AttackerFlankEffects().soldier_stack_attack_value(roleless, 10, 10) == 0

    def test_no_capacity_means_no_value(self):
        effects = AttackerFlankEffects()
        assert effects.soldier_stack_attack_value(unit_of(data(), 211), 0, 100) == 0


class TestDefenderAggregation:
    def test_defenders_credit_both_defenses_to_their_own_role(self):
        effects = defender_flank_effects([(601, 10), (211, 5)], game_data=data())

        # 601 is melee: 60 melee / 20 range defense, ten of them.
        assert effects.melee_units_melee_strength == 600
        assert effects.melee_units_range_strength == 200
        # 211 is ranged: 25 melee / 42 range defense, five of them.
        assert effects.range_units_melee_strength == 125
        assert effects.range_units_range_strength == 210

    def test_defense_values_combine_both_groups(self):
        effects = defender_flank_effects([(601, 10), (211, 5)], game_data=data())

        assert effects.melee_defense_value() == 600 + 125
        assert effects.range_defense_value() == 210 + 200

    def test_reductions_are_subtracted_from_the_matching_bonus(self):
        effects = defender_flank_effects([(601, 10)], game_data=data())

        # melee_units_melee_strength * (1.0 - 0.25)
        assert effects.melee_defense_value(melee_reduction=0.25) == 450

    def test_bonuses_multiply(self):
        effects = defender_flank_effects([(601, 10)], melee_bonus=1.5, game_data=data())
        assert effects.melee_defense_value() == 900

    def test_tools_among_the_stacks_are_not_counted_as_units(self):
        effects = defender_flank_effects([(646, 2)], game_data=data())
        assert effects.is_empty()

    def test_a_defending_tool_raises_the_fortification(self):
        # 646 is a moat tool worth 80%. The client adds a defending tool's
        # bonus once per stack, whatever the stack holds, so two of them are
        # still one 80%.
        effects = defender_flank_effects([(646, 2)], moat_bonus=0.5, game_data=data())

        assert effects.moat_bonus == pytest.approx(1.3)

    def test_only_the_middle_meets_the_gate(self):
        stacks = [(601, 10)]
        kwargs = {"wall_bonus": 0.3, "gate_bonus": 0.3, "moat_bonus": 0.3}

        middle = defender_flank_effects(stacks, flank=Flank.MIDDLE, **kwargs, game_data=data())
        left = defender_flank_effects(stacks, flank=Flank.LEFT, **kwargs, game_data=data())

        assert middle.gate_bonus == 0.3
        assert left.gate_bonus == 0.0
        # Only the gate is flank-specific.
        assert left.wall_bonus == 0.3
        assert left.moat_bonus == 0.3

    def test_unknown_ids_are_reported_not_guessed(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="empire_core.combat.defense"):
            effects = defender_flank_effects([(999999, 5)], game_data=data())

        assert effects.is_empty()
        assert "matched no known unit or tool" in caplog.text

    def test_zero_and_negative_counts_are_ignored(self):
        assert defender_flank_effects([(601, 0), (211, -3)], game_data=data()).is_empty()


class TestEventCampDefence:
    PAYLOAD = dict(
        PAYLOAD,
        nomadCamps=[
            {
                "countVictory": "48",
                "defStrength": "8800",
                "defenceUnits": "601,211",
                "defenceTools": "646",
                "wallBonus": "30",
                "gateBonus": "30",
                "lordID": "-21",
            }
        ],
    )

    def data(self):
        return GameData.parse("test", self.PAYLOAD)

    def test_wall_and_gate_are_read_as_fractions(self):
        effects = event_camp_defense("nomadCamps", 48, game_data=self.data())

        assert effects is not None
        middle = effects[Flank.MIDDLE]
        assert (middle.wall_bonus, middle.gate_bonus) == (0.3, 0.3)

    def test_only_the_middle_keeps_the_gate(self):
        # Same rule as every other per-flank builder: getDefenceBonuses zeroes
        # the gate everywhere but the middle.
        effects = event_camp_defense("nomadCamps", 48, game_data=self.data())

        assert effects is not None
        assert effects[Flank.MIDDLE].gate_bonus == 0.3
        for flank in (Flank.LEFT, Flank.RIGHT, Flank.YARD):
            assert effects[flank].gate_bonus == 0.0
            # Only the gate is flank-specific.
            assert effects[flank].wall_bonus == 0.3

    def test_every_flank_is_defended(self):
        effects = event_camp_defense("nomadCamps", 48, game_data=self.data())

        # These tables list one defending force rather than a per-flank split.
        assert all(not e.is_empty() for e in flanks_of(effects).values())

    def test_unknown_camp_or_table(self):
        assert event_camp_defense("nomadCamps", 999, game_data=self.data()) is None
        assert event_camp_defense("notATable", 48, game_data=self.data()) is None

    def test_a_berimond_camp_takes_its_factions_row(self):
        # CastleFactionInvasionCampData keeps a blue and a red map keyed by countVictory, the camp's level
        data = GameData.parse(
            "test",
            dict(
                PAYLOAD,
                factioninvasioncamps=[
                    {
                        "countVictory": "5",
                        "factionID": "0",
                        "defenceUnits": "601",
                        "wallBonus": "10",
                        "gateBonus": "20",
                    },
                    {
                        "countVictory": "5",
                        "factionID": "1",
                        "defenceUnits": "601",
                        "wallBonus": "40",
                        "gateBonus": "50",
                    },
                ],
            ),
        )

        blue = event_camp_defense("factioninvasioncamps", 5, faction_id=0, game_data=data)
        red = event_camp_defense("factioninvasioncamps", 5, faction_id=1, game_data=data)

        assert blue is not None and red is not None
        assert (blue[Flank.MIDDLE].wall_bonus, blue[Flank.MIDDLE].gate_bonus) == (0.1, 0.2)
        assert (red[Flank.MIDDLE].wall_bonus, red[Flank.MIDDLE].gate_bonus) == (0.4, 0.5)
        assert event_camp_defense("factioninvasioncamps", 6, faction_id=0, game_data=data) is None
        with pytest.raises(ValueError, match="faction_id"):
            event_camp_defense("factioninvasioncamps", 5, game_data=data)


class TestNpcCampDefence:
    def test_camp_defense_is_read_per_flank(self):
        effects = robber_baron_camp_defense(victories=-6, kingdom_id=Kingdom.GREEN, game_data=data())

        assert effects is not None
        middle = effects[Flank.MIDDLE]
        assert middle.melee_units_melee_strength == 600
        assert middle.range_units_range_strength == 210
        # Left flank holds two melee units, the right and keep nothing.
        assert effects[Flank.LEFT].melee_units_melee_strength == 120
        assert effects[Flank.RIGHT].is_empty()
        assert effects[Flank.YARD].is_empty()

    def test_unknown_camp_returns_none(self):
        assert robber_baron_camp_defense(victories=-6, kingdom_id=Kingdom.ICE, game_data=data()) is None
        assert robber_baron_camp_defense(victories=-7, game_data=data()) is None
        # Past the highest row, the client reads the highest
        assert robber_baron_camp_defense(victories=99, game_data=data()) is not None

    def test_defending_tools_raise_the_flank_they_stand_on(self):
        # toolM is "646+2", a moat tool
        game = data()
        stakes = game.get_tool(646)
        assert stakes is not None and stakes.moat_bonus > 0

        effects = flanks_of(robber_baron_camp_defense(victories=-6, game_data=game))

        assert effects[Flank.MIDDLE].moat_bonus == pytest.approx(stakes.moat_bonus)
        assert effects[Flank.LEFT].moat_bonus == 0.0

    def test_the_camps_commander_is_not_applied(self):
        # Live rows: lord -21 holds the camp with effects 10 and 11, melee and ranged bonus
        payload = dict(
            PAYLOAD,
            lords=[{"lordID": "-21", "type": "Dungeonbaron", "wearerID": "1", "effects": "10&15,11&15"}],
            equipment_effects=[
                {"equipmentEffectID": "10", "wearerID": "1", "effectID": "10"},
                {"equipmentEffectID": "11", "wearerID": "1", "effectID": "11"},
            ],
            effects=[
                {"effectID": "10", "name": "meleeBonus", "effectTypeID": "9", "capID": "9"},
                {"effectID": "11", "name": "rangeBonus", "effectTypeID": "10", "capID": "10"},
            ],
        )

        effects = flanks_of(robber_baron_camp_defense(victories=-6, game_data=GameData.parse("test", payload)))

        # Nothing shows the server defends the camp with the row's commander
        assert (effects[Flank.LEFT].melee_bonus, effects[Flank.LEFT].range_bonus) == (1.0, 1.0)


class TestValueObjects:
    def test_an_empty_defense_has_no_value(self):
        effects = DefenderFlankEffects()
        assert effects.melee_defense_value() == 0
        assert effects.range_defense_value() == 0
        assert effects.is_empty()

    def test_flank_constants_match_the_client(self):
        assert (Flank.LEFT, Flank.MIDDLE, Flank.RIGHT, Flank.YARD) == (0, 1, 2, 3)
        assert (Flank.REINFORCEMENT, Flank.REINFORCEMENT_SUMMARY) == (4, 5)
