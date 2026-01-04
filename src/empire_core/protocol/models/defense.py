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
]
