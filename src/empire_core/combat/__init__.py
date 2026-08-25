"""Combat maths ported from the game client."""

from .bonuses import (
    Bonus,
    CombatEffectType,
    EffectResolver,
    commander_bonuses,
    parse_bonus_entries,
)
from .capacity import (
    WaveCapacity,
    flank_soldier_capacity,
    flank_tool_capacity,
    max_attackers,
    max_wave_count,
    middle_soldier_capacity,
    middle_tool_capacity,
)
from .defence import defender_flank_effects, npc_camp_defence
from .effects import AttackerFlankEffects, DefenderFlankEffects, Flank
from .solver import (
    FillOptions,
    Inventory,
    fill_flank_with_soldiers,
    fill_wave,
    fill_waves,
    pick_soldier_stack,
)

__all__ = [
    "AttackerFlankEffects",
    "Bonus",
    "CombatEffectType",
    "EffectResolver",
    "DefenderFlankEffects",
    "FillOptions",
    "Flank",
    "Inventory",
    "WaveCapacity",
    "commander_bonuses",
    "defender_flank_effects",
    "fill_flank_with_soldiers",
    "fill_wave",
    "fill_waves",
    "flank_soldier_capacity",
    "flank_tool_capacity",
    "max_attackers",
    "max_wave_count",
    "middle_soldier_capacity",
    "middle_tool_capacity",
    "npc_camp_defence",
    "parse_bonus_entries",
    "pick_soldier_stack",
]
