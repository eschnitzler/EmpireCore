"""Owner records shared by map objects, movements and player profiles.

A player's crest, faction standing and castle positions.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from empire_core.protocol.base import BasePayload
from empire_core.protocol.js import ClientInt, js_truthy


class OwnerCrest(BasePayload):
    """A player's crest: an owner record's ``E``.

    Client: ``CrestVO.loadFromParamObject``.
    """

    is_set: bool = Field(alias="IS", default=False, description="False means the tutorial crest is shown")

    @field_validator("is_set", mode="before")
    @classmethod
    def _truthy(cls, value: Any) -> bool:
        return js_truthy(value)

    symbol_type: ClientInt = Field(alias="SPT", default=0)
    symbol1: ClientInt = Field(alias="S1", default=0)
    symbol1_color: ClientInt = Field(alias="SC1", default=0)
    symbol2: ClientInt = Field(alias="S2", default=0)
    symbol2_color: ClientInt = Field(alias="SC2", default=0)
    background_type: ClientInt = Field(alias="BGT", default=0)
    background_color1: ClientInt = Field(alias="BGC1", default=0)
    background_color2: ClientInt = Field(alias="BGC2", default=0)


class OwnerFaction(BasePayload):
    """Faction event standing: an owner record's ``FN``."""

    faction_id: ClientInt = Field(alias="FID", default=0)
    protection_status: ClientInt = Field(alias="PMS", default=-1)
    protection_end_seconds: ClientInt = Field(
        alias="PMT", default=0, description="Seconds until faction protection ends"
    )
    title_id: ClientInt = Field(alias="TID", default=0)


class OwnerCastlePosition(BasePayload):
    """One of an owner's castles or villages: an entry of ``AP`` or ``VP``.

    Client: ``MinWorldMapCastleInfoVO.fillFromParamObject``.
    """

    kingdom_id: int = Field(description="Kingdom id")
    area_id: int = Field(description="Area id")
    x: int = Field(description="Map x")
    y: int = Field(description="Map y")
    area_type: int = Field(default=0, description="Area type; 0 when the row has none")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, list) and len(data) >= 4:
            return dict(zip(("kingdom_id", "area_id", "x", "y", "area_type"), data[:5], strict=False))
        return data


__all__ = [
    "OwnerCastlePosition",
    "OwnerCrest",
    "OwnerFaction",
]
