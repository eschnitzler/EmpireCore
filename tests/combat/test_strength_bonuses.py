"""Strength bonuses that the game's auto-fill helper omits."""

import pytest

from empire_core.combat import Bonus, EffectResolver, attacker_flank_effects
from empire_core.enums import CombatEffectType, Flank
from empire_core.gamedata import GameData


@pytest.fixture
def game():
    return GameData.parse(
        "test",
        {
            "legendskills": [
                {"skillID": "1", "effectType": "attackBonus", "totalEffectValue": "12"},
                {"skillID": "2", "effectType": "attackYardBonus", "totalEffectValue": "10"},
            ],
            "effects": [
                {"effectID": str(int(kind)), "effectTypeID": str(int(kind))}
                for kind in (
                    CombatEffectType.ATTACK_BOOST_YARD,
                    CombatEffectType.ATTACK_BOOST_FRONT,
                    CombatEffectType.ATTACK_BOOST_FLANK,
                )
            ],
        },
    )


@pytest.mark.parametrize("flank", list(Flank))
@pytest.mark.parametrize("legendary", [False, True])
def test_general_and_yard_legend_skills(game, flank, legendary):
    effects = attacker_flank_effects(
        EffectResolver(game), [], flank=flank, legendary_skill_ids=[1, 2], legendary=legendary
    )
    expected = 1 + (0.12 + (0.10 if flank is Flank.YARD else 0)) * legendary
    assert effects.melee_bonus == pytest.approx(expected)
    assert effects.range_bonus == pytest.approx(expected)


@pytest.mark.parametrize(
    "kind,flanks",
    [
        (CombatEffectType.ATTACK_BOOST_YARD, {Flank.YARD}),
        (CombatEffectType.ATTACK_BOOST_FRONT, {Flank.MIDDLE}),
        (CombatEffectType.ATTACK_BOOST_FLANK, {Flank.LEFT, Flank.RIGHT}),
    ],
)
def test_commander_boost_is_scoped_to_its_flanks(game, kind, flanks):
    for flank in Flank:
        effects = attacker_flank_effects(EffectResolver(game), [Bonus(effect_id=int(kind), value=25)], flank=flank)
        assert effects.melee_bonus == (1.25 if flank in flanks else 1)
        assert effects.range_bonus == (1.25 if flank in flanks else 1)


def test_courtyard_multiplier_changes_the_selected_troops():
    from empire_core.combat import AttackerFlankEffects, Inventory, fill_yard_wave
    from tests.combat.combat_helpers import solver_data

    def fill(attacker=None):
        return fill_yard_wave(Inventory({601: 100, 211: 100}), 10, attacker=attacker, game_data=solver_data())

    assert fill()[0].item == 211
    assert fill(AttackerFlankEffects(melee_bonus=4))[0].item == 601


def test_each_wave_flank_uses_its_own_multiplier():
    from empire_core.combat import AttackerFlankEffects, Inventory, fill_wave
    from tests.combat.combat_helpers import solver_data
    from tests.combat.test_solver import _capacity

    wave = fill_wave(
        Inventory({601: 100, 211: 100}),
        _capacity(10, 1),
        attacker={Flank.LEFT: AttackerFlankEffects(melee_bonus=4)},
        game_data=solver_data(),
    )
    assert wave.left.units[0].item == 601
    assert wave.middle.units[0].item == 211
    assert wave.right.units[0].item == 211


@pytest.mark.parametrize("legendary", [False, True])
def test_fill_attack_passes_distinct_strength_to_waves_and_courtyard(game, legendary):
    from unittest.mock import patch

    from empire_core.attack.service import filling, waves
    from tests.attack.fill_helpers import FillClient

    client = FillClient().build([[601, 100000]])
    assert client.state.local_player is not None
    client.state.local_player.legendary_level = int(legendary)
    client.game_data = GameData.parse(
        "test",
        {
            **FillClient.UNITS,
            "legendskills": [row.model_dump(by_alias=True) for row in game.legendary_skills.values()],
            "effects": [{"effectID": "33", "effectTypeID": "33"}],
        },
    )
    with (
        patch.object(filling, "fill_yard_wave", wraps=filling.fill_yard_wave) as yard,
        patch.object(waves, "solve_waves", wraps=waves.solve_waves) as front,
    ):
        client.attack.fill_attack(
            12345,
            target_level=70,
            area_type=21,
            target_owner_id=-1000,
            legendary_skill_ids=[1, 2],
            general_skill_ids=[],
            area_bonuses=[Bonus(effect_id=33, value=25)],
        )
    assert yard.call_args.kwargs["attacker"].melee_bonus == pytest.approx(1.25 + 0.22 * legendary)
    for effect in front.call_args.kwargs["attacker"].values():
        assert effect.melee_bonus == pytest.approx(1 + 0.12 * legendary)
