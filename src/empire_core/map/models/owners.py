"""Owner records and the pieces they share with movements and player profiles.

A player's crest, faction standing, castle positions and alliance crest.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from empire_core.protocol.base import BasePayload, list_or_empty, object_or_none
from empire_core.protocol.js import ClientInt, ParseInt, js_truthy


class OwnerCrest(BasePayload):
    """A player's crest: an owner record's ``E``.

    Client: ``CrestVO.loadFromParamObject`` (bundle line 10587).
    """

    is_set: bool = Field(alias="IS", default=False, description="False means the tutorial crest is shown")

    @field_validator("is_set", mode="before")
    @classmethod
    def _truthy(cls, value: Any) -> bool:
        return js_truthy(value)

    symbol_type: ClientInt = Field(alias="SPT", default=0, description="Symbol layout type")
    symbol1: ClientInt = Field(alias="S1", default=0, description="First symbol id")
    symbol1_color: ClientInt = Field(alias="SC1", default=0, description="First symbol's colour")
    symbol2: ClientInt = Field(alias="S2", default=0, description="Second symbol id")
    symbol2_color: ClientInt = Field(alias="SC2", default=0, description="Second symbol's colour")
    background_type: ClientInt = Field(alias="BGT", default=0, description="Background layout type")
    background_color1: ClientInt = Field(alias="BGC1", default=0, description="First background colour")
    background_color2: ClientInt = Field(alias="BGC2", default=0, description="Second background colour")


class OwnerFaction(BasePayload):
    """Faction event standing: an owner record's ``FN``.

    Client: ``WorldMapOwnerInfoVO.fillFromParamObject`` (bundle line 10794), which reads each key through ``parseInt``.
    """

    faction_id: ParseInt = Field(alias="FID", default=0, description="Faction id")
    protection_status: ParseInt = Field(alias="PMS", default=0, description="Faction protection status")
    protection_end_seconds: ParseInt = Field(
        alias="PMT", default=0, description="Seconds until faction protection ends"
    )
    title_id: ParseInt = Field(alias="TID", default=0, description="Faction title id")


class OwnerCastlePosition(BasePayload):
    """One of an owner's castles or villages: an entry of ``AP`` or ``VP``, ``[kingdom_id, area_id, x, y, area_type]``.

    Client: ``MinWorldMapCastleInfoVO.fillFromParamObject`` (bundle line 18459).
    """

    kingdom_id: ClientInt = Field(description="Kingdom id")
    area_id: ClientInt = Field(description="Area id")
    x: int = Field(description="Map x")
    y: int = Field(description="Map y")
    area_type: int | None = Field(default=None, description="Area type; None when the entry has none")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, list) and len(data) >= 4:
            return dict(zip(("kingdom_id", "area_id", "x", "y", "area_type"), data[:5], strict=False))
        return data


class AllianceCrest(BasePayload):
    """
    An alliance's crest: a layout and its colours.

    Client: ``AllianceCrestVO.fillWithData`` (bundle line 11233); ``fillFromArray``
    (bundle line 11237) reads the same two values from ``[layout_id, color_ids]``.
    """

    layout_id: ClientInt = Field(alias="ACLI", default=0, description="Crest layout id")
    color_ids: list[ClientInt] = Field(
        alias="ACCS", default_factory=list, description="Colour ids, one per layout colour"
    )

    @field_validator("color_ids", mode="before")
    @classmethod
    def _stored_raw(cls, value: Any) -> Any:
        # The client stores ACCS as it arrives, so a missing list is no colours
        return list_or_empty(value)


class AllianceEmblem(BasePayload):
    """
    The alliance crest block of an owner record: its ``aee``.

    Client: ``WorldMapOwnerInfoVO.fillFromParamObject`` (bundle line 10794)
    reads only ``ACCA``, and only for a player in an alliance.
    """

    crest: AllianceCrest | None = Field(alias="ACCA", default=None, description="The alliance's current crest")

    @field_validator("crest", mode="before")
    @classmethod
    def _crest_needs_an_object(cls, value: Any) -> Any:
        return object_or_none(value)


__all__ = [
    "AllianceCrest",
    "AllianceEmblem",
    "OwnerCastlePosition",
    "OwnerCrest",
    "OwnerFaction",
]
