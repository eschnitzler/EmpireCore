"""Combat maths ported from the game client."""

from .bonuses import (
    Bonus,
    CombatEffectType,
    EffectResolver,
    alliance_buff_bonuses,
    commander_bonuses,
    construction_item_bonuses,
    general_skill_bonuses,
    global_effect_bonuses,
    legend_skill_value,
    parse_bonus_entries,
    parse_effect_spec,
    sceat_skill_bonuses,
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
    "alliance_buff_bonuses",
    "commander_bonuses",
    "construction_item_bonuses",
    "defender_flank_effects",
    "general_skill_bonuses",
    "global_effect_bonuses",
    "legend_skill_value",
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
    "parse_effect_spec",
    "sceat_skill_bonuses",
    "pick_soldier_stack",
]
