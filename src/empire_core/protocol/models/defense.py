"""
Defense protocol models.

Commands:
- dfc: Get defense configuration
- dfk: Change keep defense
- dfw: Change wall defense
- dfm: Change moat defense
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from .base import BaseRequest, BaseResponse, UnitCount

# =============================================================================
# DFC - Get Defense Configuration
# =============================================================================


class GetDefenseRequest(BaseRequest):
    """
    Get defense configuration for a castle.

    Command: dfc
    Payload: {"CID": castle_id}
    """

    command = "dfc"

    castle_id: int = Field(alias="CID")


class DefenseConfiguration(BaseResponse):
    """Defense configuration for a location (keep, wall, moat)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    units: list[UnitCount] = Field(alias="U", default_factory=list)
    tools: list[UnitCount] = Field(alias="T", default_factory=list)


class GetDefenseResponse(BaseResponse):
    """
    Response containing defense configuration.

    Command: dfc
    """

    command = "dfc"

    keep: DefenseConfiguration | None = Field(alias="K", default=None)
    wall: DefenseConfiguration | None = Field(alias="W", default=None)
    moat: DefenseConfiguration | None = Field(alias="M", default=None)
    courtyard: DefenseConfiguration | None = Field(alias="C", default=None)


# =============================================================================
# DFK - Change Keep Defense
# =============================================================================


class ChangeKeepDefenseRequest(BaseRequest):
    """
    Change keep defense configuration.

    Command: dfk
    Payload: {
        "CID": castle_id,
        "U": [{"UID": unit_id, "C": count}, ...],
        "T": [{"TID": tool_id, "C": count}, ...]
    }
    """

    command = "dfk"

    castle_id: int = Field(alias="CID")
    units: list[UnitCount] = Field(alias="U", default_factory=list)
    tools: list[UnitCount] = Field(alias="T", default_factory=list)


class ChangeKeepDefenseResponse(BaseResponse):
    """
    Response to changing keep defense.

    Command: dfk
    """

    command = "dfk"

    success: bool = Field(default=True)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# DFW - Change Wall Defense
# =============================================================================


class ChangeWallDefenseRequest(BaseRequest):
    """
    Change wall defense configuration.

    Command: dfw
    Payload: {
        "CID": castle_id,
        "U": [{"UID": unit_id, "C": count}, ...],
        "T": [{"TID": tool_id, "C": count}, ...]
    }
    """

    command = "dfw"

    castle_id: int = Field(alias="CID")
    units: list[UnitCount] = Field(alias="U", default_factory=list)
    tools: list[UnitCount] = Field(alias="T", default_factory=list)


class ChangeWallDefenseResponse(BaseResponse):
    """
    Response to changing wall defense.

    Command: dfw
    """

    command = "dfw"

    success: bool = Field(default=True)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# DFM - Change Moat Defense
# =============================================================================


class ChangeMoatDefenseRequest(BaseRequest):
    """
    Change moat defense configuration.

    Command: dfm
    Payload: {
        "CID": castle_id,
        "U": [{"UID": unit_id, "C": count}, ...],
        "T": [{"TID": tool_id, "C": count}, ...]
    }
    """

    command = "dfm"

    castle_id: int = Field(alias="CID")
    units: list[UnitCount] = Field(alias="U", default_factory=list)
    tools: list[UnitCount] = Field(alias="T", default_factory=list)


class ChangeMoatDefenseResponse(BaseResponse):
    """
    Response to changing moat defense.

    Command: dfm
    """

    command = "dfm"

    success: bool = Field(default=True)
    error_code: int = Field(alias="E", default=0)


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
    - B: Commander/Lord info
    - gui: Unit inventory
    - gli: Lords info
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

    # Commander/Lord info (optional, not always present)
    commander_info: dict | None = Field(alias="B", default=None)

    # Unit inventory info
    unit_inventory: dict | None = Field(alias="gui", default=None)

    # Lords info
    lords_info: dict | None = Field(alias="gli", default=None)

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
        for position in self.defense_positions:
            if isinstance(position, list):
                for unit_pair in position:
                    if isinstance(unit_pair, list) and len(unit_pair) >= 2:
                        # unit_pair is [unit_id, count]
                        total += unit_pair[1]
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
        for position in self.defense_positions:
            units: dict[int, int] = {}
            if isinstance(position, list):
                for unit_pair in position:
                    if isinstance(unit_pair, list) and len(unit_pair) >= 2:
                        unit_id, count = unit_pair[0], unit_pair[1]
                        units[unit_id] = units.get(unit_id, 0) + count
            result.append(units)
        return result


__all__ = [
    # DFC - Get Defense
    "GetDefenseRequest",
    "GetDefenseResponse",
    "DefenseConfiguration",
    # DFK - Keep Defense
    "ChangeKeepDefenseRequest",
    "ChangeKeepDefenseResponse",
    # DFW - Wall Defense
    "ChangeWallDefenseRequest",
    "ChangeWallDefenseResponse",
    # DFM - Moat Defense
    "ChangeMoatDefenseRequest",
    "ChangeMoatDefenseResponse",
    # SDI - Support Defense Info
    "GetSupportDefenseRequest",
    "GetSupportDefenseResponse",
]
