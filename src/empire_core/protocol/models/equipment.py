"""
Equipment inventory protocol models.

Commands:
- gei: Get Equipment Inventory - the items no commander or castellan wears
- eeq: Equip Equipment - put an item on a commander or castellan, or take it off
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, ValidationError, field_validator

from .base import BaseRequest, BaseResponse
from .commanders import Equipment

logger = logging.getLogger(__name__)


class GetEquipmentInventoryRequest(BaseRequest):
    """
    Request the player's equipment inventory.

    Command: gei
    Payload: {}
    Client: ``C2SGetEquipmentInventory`` (bundle line 19854)
    """

    command = "gei"


class GetEquipmentInventoryResponse(BaseResponse):
    """
    The player's equipment inventory.

    Command: gei
    Payload: {"I": [EQ entry, ...]}, each entry laid out as a ``gli`` ``EQ`` entry.

    Client: ``CastleEquipmentData.parse_GEI`` (bundle line 143731), which builds every
    entry with ``CastleEquipmentFactory.createEquipmentVO`` (bundle line 18134).
    """

    command = "gei"

    items: list[Equipment] = Field(
        alias="I",
        default_factory=list,
        description="Inventory items; entries that do not parse are skipped, and a missing I reads as empty",
    )

    @field_validator("items", mode="before")
    @classmethod
    def _readable_items(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return []
        items: list[Equipment] = []
        for entry in value:
            if isinstance(entry, Equipment):
                items.append(entry)
                continue
            if not isinstance(entry, (list, tuple)):
                continue
            try:
                items.append(Equipment.from_list(list(entry)))
            except ValidationError:
                continue
        if skipped := len(value) - len(items):
            logger.warning(f"Skipped {skipped}/{len(value)} unparseable gei entries")
        return items


class EquipEquipmentRequest(BaseRequest):
    """
    Put an item on a commander or castellan (``equip=1``), or take it off (``equip=0``).

    Moving an item between two leaders takes two requests: the client takes it
    off the first, then puts it on the second. The reply has no body.

    Command: eeq
    Payload: {"EID": equipment_id, "LID": commander_id, "E": 0 or 1}
    Client: ``C2SEquipEquipmentVO`` (bundle line 143914) sends ``E`` as ``int(n?1:0)``;
    ``CastleEquipmentData.startDrag`` (bundle line 143801) sends 0 when an item is
    lifted off a leader's slot, ``stopDrag`` (bundle line 143807) sends 1 when it is
    dropped on one, and ``EquipmentEquipmentClickHandler.init`` (bundle line 65626)
    handles the 0 reply as an unequip.
    """

    command = "eeq"

    equipment_id: int = Field(alias="EID", description="The item's id, EQ index 0")
    commander_id: int = Field(alias="LID", description="The commander's or castellan's gli ID")
    equip: int = Field(alias="E", description="1 puts the item on the leader, 0 takes it off")

    @field_validator("equip", mode="before")
    @classmethod
    def _as_flag(cls, value: Any) -> int:
        return 1 if value else 0
