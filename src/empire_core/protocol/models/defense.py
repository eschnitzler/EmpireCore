"""
Defense protocol models.

Commands:
- dfc: Read a castle's keep, wall and moat setup
- dfk: Set the keep's tools and unit settings
- dfw: Set the wall's tools and unit split
- dfm: Set the moat's tools
- sdi: Defense info for an alliance member's castle
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field

from .army import UnitInventory
from .base import BasePayload, BaseRequest, BaseResponse, ClientInt
from .commanders import Castellan
from .movement import MovementArea

logger = logging.getLogger(__name__)


def _as_int(value: Any) -> int | None:
    """Coerce a wire value to int, or None when it is not numeric.

    The server sometimes sends counts as strings, and these accessors are the
    documented way to read a castle's defense, so a drifted type must not raise.
    """
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


Slot = list[int]
"""One container slot: ``[wod_id, amount]``, ``[-1, 0]`` when empty."""


# =============================================================================
# DFC - Read a castle's defense setup
# =============================================================================


class GetDefenseRequest(BaseRequest):
    """
    Read the defense setup of one of your castles.

    Command: dfc
    Client: ``C2SDefenceCompleteVO`` (bundle line 32769); every call site
    passes the castle's ``absAreaPos`` and ``objectId``, with ``KID`` -1 or
    omitted (``CastleDefenceDialog.updateDefenceData``, bundle line 15978)
    """

    command = "dfc"

    castle_x: int = Field(alias="CX", description="Castle map x")
    castle_y: int = Field(alias="CY", description="Castle map y")
    area_id: int = Field(alias="AID", description="The castle's area id")
    kingdom_id: int = Field(alias="KID", default=-1, description="Kingdom id; the client sends -1")


class WallSection(BasePayload):
    """
    One wall section's setup as the ``dfw`` reply carries it; a missing
    number reads as 0, as the client's ``int()`` gives.

    Client: ``CastleDefenceData.parse_DFW`` (bundle line 134250)
    """

    slots: list[Slot] = Field(alias="S", default_factory=list, description="Wall tool slots")
    unit_percent: ClientInt = Field(alias="UP", default=0, description="Share of the wall's units on this section")
    unit_composition: ClientInt = Field(alias="UC", default=0, description="Unit composition of this section")


class WallDefense(BaseResponse):
    """
    The wall setup: the ``dfw`` reply, also nested in ``dfc``.

    Command: dfw
    Client: ``DFWCommand.executeCommand`` (bundle line 123525),
    ``CastleDefenceData.parse_DFW`` (bundle line 134250)
    """

    command = "dfw"

    left: WallSection = Field(alias="L", default_factory=WallSection, description="Left wall section")
    middle: WallSection = Field(alias="M", default_factory=WallSection, description="Middle wall section")
    right: WallSection = Field(alias="R", default_factory=WallSection, description="Right wall section")
    unit_count: ClientInt = Field(alias="U", default=0, description="Units on the wall")
    unit_slot_count: ClientInt = Field(alias="US", default=0, description="Units the wall can hold")
    defense: ClientInt = Field(alias="D", default=0, description="Wall defence, truncated as the client does")


class KeepDefense(BaseResponse):
    """
    The keep setup: the ``dfk`` reply, also nested in ``dfc``.

    Command: dfk
    Client: ``DFKCommand.executeCommand`` (bundle line 123495),
    ``CastleDefenceData.parse_DFK`` (bundle line 134251)
    """

    command = "dfk"

    slots: list[Slot] = Field(alias="S", default_factory=list, description="Keep tool slots")
    support_tool_slots: list[Slot] = Field(alias="STS", default_factory=list, description="Keep support-tool slots")
    alliance_unit_yard_limit: ClientInt = Field(alias="AUYL", default=0, description="Alliance unit yard limit")
    unit_yard_limit: ClientInt = Field(alias="UYL", default=0, description="Unit yard limit")
    unit_count: ClientInt = Field(alias="U", default=0, description="Units in the keep")
    unit_composition: ClientInt = Field(alias="UC", default=0, description="Keep unit composition")
    min_attacking_units_for_tools: ClientInt = Field(
        alias="MAUCT",
        default=0,
        description="Minimum attacking units before the keep's tools are used",
    )

    @property
    def keep_unit_slot_count(self) -> int:
        """
        Units the keep can hold: ``UYL - AUYL``.

        The client makes it unlimited on special servers and in daimyo
        townships, which this reply cannot tell.
        """
        return self.unit_yard_limit - self.alliance_unit_yard_limit


class MoatDefense(BaseResponse):
    """
    The moat setup: the ``dfm`` reply, also nested in ``dfc``.

    Command: dfm
    Client: ``DFMCommand.executeCommand`` (bundle line 123510),
    ``CastleDefenceData.parse_DFM`` (bundle line 134252)
    """

    command = "dfm"

    left_slots: list[Slot] = Field(alias="LS", default_factory=list, description="Left moat slots")
    middle_slots: list[Slot] = Field(alias="MS", default_factory=list, description="Middle moat slots")
    right_slots: list[Slot] = Field(alias="RS", default_factory=list, description="Right moat slots")
    defense: ClientInt = Field(alias="D", default=0, description="Moat defence, truncated as the client does")


class GetDefenseResponse(BaseResponse):
    """
    A castle's whole defense setup.

    Command: dfc
    Client: ``DFCCommand.executeCommand`` (bundle line 123480),
    ``CastleDefenceData.parse_DFC`` (bundle line 134243). The server also
    sends ``MDS`` and ``RDS``, which the client does not read.
    """

    command = "dfc"

    unit_inventory: UnitInventory = Field(
        alias="gui",
        default_factory=UnitInventory,
        description="The castle's unit inventory; the client reads only gui.I",
    )
    area: MovementArea | None = Field(alias="A", default=None, description="The castle's map row")
    home_defense_workshop_level: int | None = Field(
        alias="HDWL",
        default=None,
        description="Defense workshop level, which unlocks the keep's support-tool slots",
    )
    wall: WallDefense | None = Field(alias="dfw", default=None, description="Wall setup")
    keep: KeepDefense | None = Field(alias="dfk", default=None, description="Keep setup")
    moat: MoatDefense | None = Field(alias="dfm", default=None, description="Moat setup")
    range_priority: list[int] = Field(alias="PR", default_factory=list, description="Ranged unit priority")
    melee_priority: list[int] = Field(alias="PM", default_factory=list, description="Melee unit priority")
    gate_defense: ClientInt = Field(alias="GD", default=0, description="Gate defence, truncated as the client does")
    castellan: Castellan | None = Field(
        alias="L",
        default=None,
        description="The castle's castellan; the client reads L.ID and parses the rest with BaronVO.parseLord",
    )

    @property
    def castellan_id(self) -> int:
        """The castellan's id, ``L.ID``; -1 when none is set, as the client starts from."""
        return self.castellan.commander_id if self.castellan else -1

    def inventory(self) -> dict[int, int]:
        """The castle's units as ``{wod_id: amount}``, the only inventory ``parse_DFC`` reads."""
        return dict(self.unit_inventory.units)


# =============================================================================
# DFK / DFW / DFM - Change the keep, wall and moat setup
# =============================================================================


class ChangeKeepDefenseRequest(BaseRequest):
    """
    Set the keep's tools, support tools and unit settings.

    The client builds the slot lists from its keep containers, one pair per
    slot; start from the ``dfc`` reply's ``dfk`` lists. Fields follow the
    client's key order.

    Command: dfk
    Client: ``C2SDefenceKeepVO`` (bundle line 66597), built by
    ``CastleDefenceDialog.sendKeepData`` (bundle line 16041), which sends an
    empty ``STS`` when there is no support-tool container
    """

    command = "dfk"

    castle_x: int = Field(alias="CX", description="Castle map x")
    castle_y: int = Field(alias="CY", description="Castle map y")
    area_id: int = Field(alias="AID", description="The castle's area id")
    min_attacking_units_for_tools: int = Field(
        alias="MAUCT",
        default=0,
        description="Minimum attacking units before the keep's tools are used",
    )
    unit_composition: int = Field(alias="UC", default=50, description="Keep unit composition")
    slots: list[Slot] = Field(alias="S", description="Keep tool slots")
    support_tool_slots: list[Slot] = Field(alias="STS", default_factory=list, description="Keep support-tool slots")


class WallSectionSetup(BasePayload):
    """
    One wall section in a ``dfw`` request; the client has no defaults.

    Client: ``C2SDefenceWallVO`` (bundle line 66616)
    """

    slots: list[Slot] = Field(alias="S", description="Wall tool slots")
    unit_percent: int = Field(alias="UP", description="Share of the wall's units on this section")
    unit_composition: int = Field(alias="UC", description="Unit composition of this section")


class ChangeWallDefenseRequest(BaseRequest):
    """
    Set the wall's tools and unit split per section.

    Every section needs its slots, unit percent and unit composition; the
    client has no defaults for them. Start from the ``dfc`` reply's ``dfw``.

    Command: dfw
    Client: ``C2SDefenceWallVO`` (bundle line 66616), built by
    ``CastleDefenceDialog.sendWallData`` (bundle line 16045)
    """

    command = "dfw"

    castle_x: int = Field(alias="CX", description="Castle map x")
    castle_y: int = Field(alias="CY", description="Castle map y")
    area_id: int = Field(alias="AID", description="The castle's area id")
    left: WallSectionSetup = Field(alias="L", description="Left wall section")
    middle: WallSectionSetup = Field(alias="M", description="Middle wall section")
    right: WallSectionSetup = Field(alias="R", description="Right wall section")


class ChangeMoatDefenseRequest(BaseRequest):
    """
    Set the moat's tools.

    Start from the ``dfc`` reply's ``dfm`` lists.

    Command: dfm
    Client: ``C2SDefenceMoatVO`` (bundle line 66607), built by
    ``CastleDefenceDialog.sendMoatData`` (bundle line 16049)
    """

    command = "dfm"

    castle_x: int = Field(alias="CX", description="Castle map x")
    castle_y: int = Field(alias="CY", description="Castle map y")
    area_id: int = Field(alias="AID", description="The castle's area id")
    left_slots: list[Slot] = Field(alias="LS", description="Left moat slots")
    middle_slots: list[Slot] = Field(alias="MS", description="Middle moat slots")
    right_slots: list[Slot] = Field(alias="RS", description="Right moat slots")


# =============================================================================
# SDI - Support Defense Info (Alliance Member Castle Defense)
# =============================================================================


class GetSupportDefenseRequest(BaseRequest):
    """
    Get defense info for an alliance member's castle.

    Command: sdi
    Payload: {"TX": target_x, "TY": target_y, "SX": source_x, "SY": source_y}

    Note: Can only query castles of players in the same alliance.
    TX/TY = Target castle coordinates (the one being attacked)
    SX/SY = Source castle coordinates (your castle sending support)
    """

    command = "sdi"

    target_x: int = Field(alias="TX")
    target_y: int = Field(alias="TY")
    source_x: int = Field(alias="SX")
    source_y: int = Field(alias="SY")


class GetSupportDefenseResponse(BaseResponse):
    """
    Response containing defense information for an alliance member's castle.

    Command: sdi

    The response contains:
    - SCID: Castle ID queried
    - S: List of 6 defense positions, each containing [[unit_id, count], ...] pairs
    - B: Castellan info
    - gui: Unit inventory
    - gli: Commander info
    - UYL: Total yard limit (max troops in courtyard)
    - AUYL: Available yard limit
    - UWL: Wall limit

    To get total defenders, sum all unit counts across all positions in S.
    """

    command = "sdi"

    castle_id: int = Field(alias="SCID", default=0)

    # S contains 6 arrays (defense positions), each with [unit_id, count] pairs
    # e.g. [[[487, 5174], [488, 20]], [[487, 347]], ...]
    defense_positions: list = Field(alias="S", default_factory=list)

    # Castellan info (optional, not always present)
    castellan_info: dict | None = Field(alias="B", default=None)

    # Unit inventory info
    unit_inventory: dict | None = Field(alias="gui", default=None)

    # Commander info
    commanders_info: dict | None = Field(alias="gli", default=None)

    # Capacity limits
    yard_limit: int = Field(alias="UYL", default=0)  # Total yard/courtyard limit
    available_yard_limit: int = Field(alias="AUYL", default=0)  # Available yard space
    wall_limit: int = Field(alias="UWL", default=0)  # Wall limit

    def get_total_defenders(self) -> int:
        """
        Calculate total number of defending troops.

        Returns:
            Total count of all units across all defense positions.
        """
        total = 0
        skipped = 0
        for position in self.defense_positions:
            if not isinstance(position, list):
                skipped += 1
                continue
            for unit_pair in position:
                if not (isinstance(unit_pair, list) and len(unit_pair) >= 2):
                    skipped += 1
                    continue
                # unit_pair is [unit_id, count]
                count = _as_int(unit_pair[1])
                if count is None:
                    skipped += 1
                    continue
                total += count
        if skipped:
            # One line per response, not per entry, so a fully drifted S
            # array can't flood the log.
            logger.warning(
                f"Skipped {skipped} malformed defense entries for castle {self.castle_id}; "
                "the defender total may be incomplete"
            )
        return total

    def get_max_defense(self) -> int:
        """
        Get the maximum defense capacity for this castle.

        UYL (yard_limit) represents the total capacity including
        courtyard limit plus room for alliance support.

        Returns:
            Maximum number of troops that can defend this castle.
        """
        return self.yard_limit

    def get_units_by_position(self) -> list[dict[int, int]]:
        """
        Get unit counts grouped by defense position.

        Returns:
            List of 6 dicts, each mapping unit_id -> count for that position.
        """
        result = []
        skipped = 0
        for position in self.defense_positions:
            units: dict[int, int] = {}
            if isinstance(position, list):
                for unit_pair in position:
                    if not (isinstance(unit_pair, list) and len(unit_pair) >= 2):
                        skipped += 1
                        continue
                    unit_id, count = _as_int(unit_pair[0]), _as_int(unit_pair[1])
                    if unit_id is None or count is None:
                        skipped += 1
                        continue
                    units[unit_id] = units.get(unit_id, 0) + count
            else:
                skipped += 1
            result.append(units)
        if skipped:
            logger.warning(
                f"Skipped {skipped} malformed defense entries for castle {self.castle_id}; "
                "the per-position unit counts may be incomplete"
            )
        return result


__all__ = [
    # DFC - Get Defense
    "GetDefenseRequest",
    "GetDefenseResponse",
    "WallSection",
    "WallSectionSetup",
    "WallDefense",
    "KeepDefense",
    "MoatDefense",
    # DFK - Keep Defense
    "ChangeKeepDefenseRequest",
    # DFW - Wall Defense
    "ChangeWallDefenseRequest",
    # DFM - Moat Defense
    "ChangeMoatDefenseRequest",
    # SDI - Support Defense Info
    "GetSupportDefenseRequest",
    "GetSupportDefenseResponse",
]
