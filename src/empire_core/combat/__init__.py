"""Combat maths ported from the game client."""

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
    "DefenderFlankEffects",
    "FillOptions",
    "Flank",
    "Inventory",
    "WaveCapacity",
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
    "pick_soldier_stack",
]
