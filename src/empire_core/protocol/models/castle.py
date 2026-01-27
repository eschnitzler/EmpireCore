"""
Castle protocol models.

Commands:
- gcl: Get castles list
- dcl: Get detailed castle info
- jca: Jump to / select castle
- arc: Rename castle
- rst: Relocate castle
- grc: Get resources
- gpa: Get production rates
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from .base import BaseRequest, BaseResponse, Position, ResourceAmount

# =============================================================================
# GCL - Get Castles List
# =============================================================================


class GetCastlesRequest(BaseRequest):
    """
    Get list of player's castles.

    Command: gcl
    Payload: {} (empty)
    """

    command = "gcl"


class CastleInfo(BaseResponse):
    """Basic castle information."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    castle_id: int = Field(alias="CID")
    castle_name: str = Field(alias="CN")
    x: int = Field(alias="X")
    y: int = Field(alias="Y")
    kingdom_id: int = Field(alias="KID", default=0)
    castle_type: int = Field(alias="CT", default=0)  # 0=main, 1=outpost, etc.
    level: int = Field(alias="L", default=1)

    @property
    def position(self) -> Position:
        """Get castle position as Position object."""
        return Position(X=self.x, Y=self.y, KID=self.kingdom_id)


class GetCastlesResponse(BaseResponse):
    """
    Response containing list of player's castles.

    Command: gcl
    Payload: {"C": [castle_info, ...]}
    """

    command = "gcl"

    castles: list[CastleInfo] = Field(alias="C", default_factory=list)


# =============================================================================
# DCL - Get Detailed Castle Info
# =============================================================================


class GetDetailedCastleRequest(BaseRequest):
    """
    Get detailed information about a specific castle.

    Command: dcl
    Payload: {"CID": castle_id}
    """

    command = "dcl"

    castle_id: int = Field(alias="CID")


class BuildingInfo(BaseResponse):
    """Building information within a castle."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    building_id: int = Field(alias="BID")
    building_type: int = Field(alias="BT")
    level: int = Field(alias="L")
    x: int = Field(alias="X")
    y: int = Field(alias="Y")
    status: int = Field(alias="S", default=0)  # 0=normal, 1=upgrading, 2=damaged
    health: int = Field(alias="H", default=100)


class DetailedCastleInfo(CastleInfo):
    """Detailed castle information including buildings and resources."""

    buildings: list[BuildingInfo] = Field(alias="B", default_factory=list)
    resources: ResourceAmount | None = Field(alias="R", default=None)
    population: int = Field(alias="P", default=0)
    max_population: int = Field(alias="MP", default=0)
    raw_items: list[list[int]] = Field(alias="AC", default_factory=list)

    @property
    def items(self) -> dict[int, int]:
        """
        Get items/inventory as a dict {item_id: count}.
        Parsed from raw 'AC' list.
        """
        result = {}
        for item in self.raw_items:
            if len(item) >= 2:
                result[item[0]] = item[1]
        return result


class GetDetailedCastleResponse(BaseResponse):
    """
    Response containing detailed castle information.

    Command: dcl
    """

    command = "dcl"

    castle: DetailedCastleInfo | None = Field(alias="C", default=None)


# =============================================================================
# JCA - Jump to Castle / Select Castle
# =============================================================================


class SelectCastleRequest(BaseRequest):
    """
    Select/jump to a castle (makes it the active castle).

    Command: jca
    Payload: {"CID": castle_id, "KID": kingdom_id}
    """

    command = "jca"

    castle_id: int = Field(alias="CID")
    kingdom_id: int = Field(alias="KID", default=0)


class SelectCastleResponse(BaseResponse):
    """
    Response to castle selection.

    Command: jca
    """

    command = "jca"

    success: bool = Field(default=True)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# ARC - Rename Castle
# =============================================================================


class RenameCastleRequest(BaseRequest):
    """
    Rename a castle.

    Command: arc
    Payload: {"CID": castle_id, "CN": "new_name"}
    """

    command = "arc"

    castle_id: int = Field(alias="CID")
    castle_name: str = Field(alias="CN")


class RenameCastleResponse(BaseResponse):
    """
    Response to castle rename.

    Command: arc
    """

    command = "arc"

    success: bool = Field(default=True)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# RST - Relocate Castle
# =============================================================================


class RelocateCastleRequest(BaseRequest):
    """
    Relocate a castle to new coordinates.

    Command: rst
    Payload: {"CID": castle_id, "X": x, "Y": y, "KID": kingdom_id}
    """

    command = "rst"

    castle_id: int = Field(alias="CID")
    x: int = Field(alias="X")
    y: int = Field(alias="Y")
    kingdom_id: int = Field(alias="KID", default=0)


class RelocateCastleResponse(BaseResponse):
    """
    Response to castle relocation.

    Command: rst
    """

    command = "rst"

    success: bool = Field(default=True)
    error_code: int = Field(alias="E", default=0)


# =============================================================================
# GRC - Get Resources
# =============================================================================


class GetResourcesRequest(BaseRequest):
    """
    Get current resources for a castle.

    Command: grc
    Payload: {"CID": castle_id}
    """

    command = "grc"

    castle_id: int = Field(alias="CID")


class GetResourcesResponse(BaseResponse):
    """
    Response containing castle resources.

    Command: grc
    """

    command = "grc"

    resources: ResourceAmount | None = Field(alias="R", default=None)
    storage_capacity: ResourceAmount | None = Field(alias="SC", default=None)


# =============================================================================
# GPA - Get Production
# =============================================================================


class GetProductionRequest(BaseRequest):
    """
    Get production rates for a castle.

    Command: gpa
    Payload: {"CID": castle_id}
    """

    command = "gpa"

    castle_id: int = Field(alias="CID")


class ProductionRates(BaseResponse):
    """Production rates per hour."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    wood: float = Field(alias="W", default=0.0)
    stone: float = Field(alias="S", default=0.0)
    food: float = Field(alias="F", default=0.0)
    coins: float = Field(alias="C", default=0.0)


class GetProductionResponse(BaseResponse):
    """
    Response containing production rates.

    Command: gpa
    """

    command = "gpa"

    production: ProductionRates | None = Field(alias="P", default=None)
    consumption: ProductionRates | None = Field(alias="CO", default=None)


__all__ = [
    # GCL - Get Castles
    "GetCastlesRequest",
    "GetCastlesResponse",
    "CastleInfo",
    # DCL - Detailed Castle
    "GetDetailedCastleRequest",
    "GetDetailedCastleResponse",
    "DetailedCastleInfo",
    "BuildingInfo",
    # JCA - Select Castle
    "SelectCastleRequest",
    "SelectCastleResponse",
    # ARC - Rename Castle
    "RenameCastleRequest",
    "RenameCastleResponse",
    # RST - Relocate Castle
    "RelocateCastleRequest",
    "RelocateCastleResponse",
    # GRC - Get Resources
    "GetResourcesRequest",
    "GetResourcesResponse",
    # GPA - Get Production
    "GetProductionRequest",
    "GetProductionResponse",
    "ProductionRates",
]
