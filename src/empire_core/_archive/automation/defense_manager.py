"""
Defense management and automation for castles.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient
    from empire_core.state.models import Castle

logger = logging.getLogger(__name__)


@dataclass
class DefensePreset:
    """A predefined defense configuration."""

    name: str
    wall_left_tools: Dict[int, int] = field(default_factory=dict)
    wall_middle_tools: Dict[int, int] = field(default_factory=dict)
    wall_right_tools: Dict[int, int] = field(default_factory=dict)
    wall_left_units_up: int = 0
    wall_left_units_count: int = 0
    wall_middle_units_up: int = 0
    wall_middle_units_count: int = 0
    wall_right_units_up: int = 0
    wall_right_units_count: int = 0
    moat_left_slots: Dict[int, int] = field(default_factory=dict)
    moat_middle_slots: Dict[int, int] = field(default_factory=dict)
    moat_right_slots: Dict[int, int] = field(default_factory=dict)


class DefenseManager:
    """
    Manages defense configurations for castles.

    Features:
    - Apply predefined defense presets to castles.
    - Monitor current defense and apply changes.
    """

    def __init__(self, client: "EmpireClient"):
        self.client = client
        self.presets: Dict[str, DefensePreset] = {}

    def add_preset(self, preset: DefensePreset):
        """Add a defense preset."""
        self.presets[preset.name] = preset
        logger.info(f"Defense preset '{preset.name}' added.")

    def get_preset(self, name: str) -> Optional[DefensePreset]:
        """Get a defense preset by name."""
        return self.presets.get(name)

    async def apply_defense_preset(self, castle_id: int, preset_name: str) -> bool:
        """
        Apply a named defense preset to a specific castle.

        Args:
            castle_id: The ID of the castle to apply the preset to.
            preset_name: The name of the defense preset.

        Returns:
            bool: True if the preset was successfully applied, False otherwise.
        """
        preset = self.get_preset(preset_name)
        if not preset:
            logger.warning(f"Defense preset '{preset_name}' not found.")
            return False

        castle: Optional["Castle"] = (
            self.client.state.local_player.castles.get(castle_id) if self.client.state.local_player else None
        )
        if not castle:
            logger.error(f"Castle {castle_id} not found in state.")
            return False

        logger.info(f"Applying defense preset '{preset_name}' to castle {castle.name}...")

        # Apply wall defense
        wall_success = await self.client.defense.set_wall_defense(
            castle_id=castle.id,
            castle_x=castle.x,
            castle_y=castle.y,
            left_tools=preset.wall_left_tools,
            middle_tools=preset.wall_middle_tools,
            right_tools=preset.wall_right_tools,
            left_units_up=preset.wall_left_units_up,
            left_units_count=preset.wall_left_units_count,
            middle_units_up=preset.wall_middle_units_up,
            middle_units_count=preset.wall_middle_units_count,
            right_units_up=preset.wall_right_units_up,
            right_units_count=preset.wall_right_units_count,
            wait_for_response=True,  # Always wait for critical defense commands
        )
        if not wall_success:
            logger.error(f"Failed to apply wall defense for castle {castle_id}.")
            return False

        await asyncio.sleep(0.5)  # Rate limit

        # Apply moat defense
        moat_success = await self.client.defense.set_moat_defense(
            castle_id=castle.id,
            castle_x=castle.x,
            castle_y=castle.y,
            left_slots=preset.moat_left_slots,
            middle_slots=preset.moat_middle_slots,
            right_slots=preset.moat_right_slots,
            wait_for_response=True,  # Always wait for critical defense commands
        )
        if not moat_success:
            logger.error(f"Failed to apply moat defense for castle {castle_id}.")
            return False

        logger.info(f"Defense preset '{preset_name}' successfully applied to castle {castle.name}.")
        return True

    # TODO: Add methods to read current defense configuration for verification
    # TODO: Add logic for 'auto-defense' based on incoming attacks or threats
    # TODO: Implement dfk (keep defense) if protocol is found
