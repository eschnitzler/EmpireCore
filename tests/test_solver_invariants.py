"""Invariants the wave solver must hold whatever it is handed.

Randomised over fixed seeds: the point is not to reproduce the client's exact
choices but to catch a fill that overfills a flank, oversubscribes a tool's
per-wave budget, or hands out troops nobody owns.
"""

import random

from empire_core.combat import (
    AttackerFlankEffects,
    DefenderFlankEffects,
    Flank,
    Inventory,
    WaveCapacity,
    fill_waves,
)
from empire_core.gamedata import GameData

SEEDS = range(40)
FLANKS = ("L", "M", "R")


def random_game(rng: random.Random) -> tuple[GameData, dict[int, int]]:
    """A small random items payload, and an inventory over the ids in it."""
    units, tools, pool = [], [], {}
    for index in range(rng.randint(1, 6)):
        wod_id = 600 + index
        units.append(
            {
                "wodID": wod_id,
                "name": "Barracks",
                "role": rng.choice(["melee", "ranged"]),
                "meleeAttack": str(rng.randint(0, 400)),
                "rangeAttack": str(rng.randint(0, 400)),
                "fightType": "0",
            }
        )
        pool[wod_id] = rng.randint(0, 5_000)
    for index in range(rng.randint(1, 6)):
        wod_id = 300 + index
        tool = {
            "wodID": wod_id,
            "name": "Workshop",
            # Several tiers share a type string, which shares a per-wave budget.
            "type": rng.choice(["Ram", "Ladder"]),
            "typ": "Attack",
            "slotTypes": rng.choice(["1,2,9", "1,9", "2,9"]),
            "wallBonus": str(rng.randint(0, 60)),
            "gateBonus": str(rng.randint(0, 60)),
            "moatBonus": str(rng.randint(0, 60)),
            "fightType": "1",
        }
        if rng.random() < 0.5:
            tool["amountPerWave"] = str(rng.randint(1, 8))
        tools.append(tool)
        pool[wod_id] = rng.randint(0, 200)
    return GameData.parse("test", {"units": units + tools}), pool


def random_defense(rng: random.Random) -> dict[Flank, DefenderFlankEffects]:
    return {
        flank: DefenderFlankEffects(
            wall_bonus=rng.uniform(0, 2),
            gate_bonus=rng.uniform(0, 2) if flank is Flank.MIDDLE else 0.0,
            moat_bonus=rng.uniform(0, 2),
            melee_bonus=rng.uniform(0, 2),
            range_bonus=rng.uniform(0, 2),
            melee_units_melee_strength=rng.randint(0, 9_000),
            range_units_range_strength=rng.randint(0, 9_000),
        )
        for flank in Flank
    }


class TestSolverInvariants:
    def run(self, seed: int):
        rng = random.Random(seed)
        game, pool = random_game(rng)
        level = rng.randint(1, 70)
        attacker_level = rng.randint(1, 70)
        inventory = Inventory(dict(pool))

        waves = fill_waves(
            inventory,
            game,
            level=level,
            attacker_level=attacker_level,
            attacker=AttackerFlankEffects(melee_bonus=rng.uniform(1, 3), range_bonus=rng.uniform(1, 3)),
            defense=random_defense(rng),
            area_type=rng.choice([None, 1, 2]),
            target_is_player=rng.random() < 0.5,
        )
        return game, pool, inventory, waves, WaveCapacity.for_level(level)

    def test_nothing_is_placed_that_was_not_owned(self):
        for seed in SEEDS:
            game, pool, inventory, waves, _ = self.run(seed)

            placed: dict[int, int] = {}
            for wave in waves:
                payload = wave.model_dump(by_alias=True)
                for flank in FLANKS:
                    for wod_id, count in payload[flank]["U"] + payload[flank]["T"]:
                        placed[wod_id] = placed.get(wod_id, 0) + count
            for wod_id, count in placed.items():
                assert count <= pool[wod_id], f"seed {seed}: {count} of {wod_id}, owned {pool[wod_id]}"
                assert inventory.available(wod_id) == pool[wod_id] - count
            assert all(count >= 0 for count in inventory.counts.values())

    def test_no_flank_is_overfilled(self):
        for seed in SEEDS:
            _, _, _, waves, capacity = self.run(seed)

            for wave in waves:
                payload = wave.model_dump(by_alias=True)
                for name, flank in zip(FLANKS, (Flank.LEFT, Flank.MIDDLE, Flank.RIGHT), strict=True):
                    side = payload[name]
                    assert sum(count for _, count in side["U"]) <= capacity.soldier_capacity(flank)
                    assert sum(count for _, count in side["T"]) <= capacity.tool_capacity(flank)
                    assert len(side["U"]) <= capacity.unit_slots(flank)
                    assert len(side["T"]) <= capacity.tool_slots(flank)

    def test_a_tools_per_wave_budget_holds_across_the_flanks(self):
        # The budget is keyed by type and shared by every tier of it, so the
        # bound is the largest limit among them - but only when they all carry
        # one. A tier with no limit spends against free capacity instead, which
        # is what the client does, so such a type has no bound to check.
        for seed in SEEDS:
            game, _, _, waves, _ = self.run(seed)

            bounded = {}
            for tool in game.tools.values():
                if not tool.is_attack_tool:
                    continue
                limits = bounded.setdefault(tool.tool_type, [])
                limits.append(tool.per_wave_limit)
            bounded = {
                tool_type: max(limits) for tool_type, limits in bounded.items() if all(limit > 0 for limit in limits)
            }

            for index, wave in enumerate(waves):
                payload = wave.model_dump(by_alias=True)
                per_type: dict[str, int] = {}
                for flank in FLANKS:
                    for wod_id, count in payload[flank]["T"]:
                        tool = game.get_tool(wod_id)
                        assert tool is not None
                        per_type[tool.tool_type] = per_type.get(tool.tool_type, 0) + count
                for tool_type, total in per_type.items():
                    if tool_type in bounded:
                        assert total <= bounded[tool_type], f"seed {seed}: wave {index} {tool_type} {total}"

    def test_every_tool_fits_the_slot_it_went_into(self):
        for seed in SEEDS:
            game, _, _, waves, capacity = self.run(seed)

            for wave in waves:
                payload = wave.model_dump(by_alias=True)
                for name, flank in zip(FLANKS, (Flank.LEFT, Flank.MIDDLE, Flank.RIGHT), strict=True):
                    for wod_id, _ in payload[name]["T"]:
                        tool = game.get_tool(wod_id)
                        assert tool is not None
                        assert tool.fits_slot(capacity.tool_slot_type(flank))

    def test_a_flank_with_tools_always_has_units(self):
        for seed in SEEDS:
            _, _, _, waves, _ = self.run(seed)

            for wave in waves:
                payload = wave.model_dump(by_alias=True)
                for flank in FLANKS:
                    if payload[flank]["T"]:
                        assert payload[flank]["U"], f"seed {seed}: tools with no units on {flank}"
