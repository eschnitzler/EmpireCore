"""
Lords/Commanders protocol models.

Commands:
- gli: Get Lords Info
"""

from __future__ import annotations

from pydantic import Field

from .base import BasePayload, BaseRequest, BaseResponse


class Equipment(BasePayload):
    """Equipment item on a lord."""

    # Generic equipment structure - fields unknown but likely ID, type, stats
    # Storing as dict/attributes for now
    oid: int = Field(alias="OID", default=0)
    # Add other known fields if found


class Lord(BasePayload):
    """
    Represents a Lord/Commander.

    Fields inferred from typical GGE structures:
    - ID: Lord ID (was LID in some docs, but packet shows ID)
    - N: Name (often empty for non-custom lords)
    - X, Y: Coordinates?
    - EQ: Equipment list
    - G: Gem?
    """

    lord_id: int = Field(alias="ID")
    name: str = Field(alias="N", default="")
    # Add other fields as needed


class GetLordsRequest(BaseRequest):
    """
    Request to get all lords/commanders.

    Command: gli
    Payload: {}
    """

    command = "gli"


class GetLordsResponse(BaseResponse):
    """
    Response containing list of lords.

    Command: gli
    """

    command = "gli"

    lords: list[Lord] = Field(alias="C", default_factory=list)
    error_code: int = Field(alias="E", default=0)
