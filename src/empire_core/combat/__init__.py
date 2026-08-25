"""Combat maths ported from the game client."""

from .defence import defender_flank_effects, npc_camp_defence
from .effects import AttackerFlankEffects, DefenderFlankEffects, Flank
from .solver import (
    FillOptions,
    Inventory,
    fill_flank_with_soldiers,
    fill_wave,
    pick_soldier_stack,
)

__all__ = [
    "AttackerFlankEffects",
    "DefenderFlankEffects",
    "FillOptions",
    "Flank",
    "Inventory",
    "defender_flank_effects",
    "fill_flank_with_soldiers",
    "fill_wave",
    "npc_camp_defence",
    "pick_soldier_stack",
]
