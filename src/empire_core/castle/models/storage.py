"""
The decoration storage: decorations taken out of your castles, waiting to be placed again or sold.

Commands:
- sin: the storages, read whole, and inside the ebu, ebe, pio, sob, sds, sbp and jaa replies
- mbs: mark a storage's new decorations as seen
- sob: put a placed decoration into the storage
- sds: sell decorations from the storage
- pio: place a custom or unique decoration from the storage
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BeforeValidator, Field, field_validator, model_validator

from empire_core.enums import DecorationStorageId, Kingdom
from empire_core.gamedata import EnumOrInt
from empire_core.gamedata.ids.treasure_maps import TreasureMapId
from empire_core.gamedata.lenient import known
from empire_core.protocol.base import (
    DEFAULT_ZONE,
    NO_ROOM,
    BasePayload,
    BaseRequest,
    BaseResponse,
    CurrencyBlock,
    build_command,
    readable_list,
)
from empire_core.protocol.js import ClientInt, js_int

from .objects import BuildingRow, building_or_none

if TYPE_CHECKING:
    from empire_core.gamedata import Building

logger = logging.getLogger(__name__)

DecorationStorageKey = DecorationStorageId | Kingdom | TreasureMapId | int
"""
A decoration storage: the main one or a castle's area inventory, else the event kingdom whose own it is,
Berimond's or a season event's map.

Client: ``DecorationConst.getStorageID`` (dll line 19001) names a season map's storage by its map id and
Berimond's by its kingdom id
"""

_STORAGE_ENUMS = (DecorationStorageId, Kingdom, TreasureMapId)


def _row(*names: str) -> Any:
    def read(data: Any) -> Any:
        if not isinstance(data, list):
            return data
        return dict(zip(names, data, strict=False))

    return read


class StoredDecoration(BasePayload):
    """
    A regular decoration in storage, counted by type; sent as ``[wod_id, amount, new_amount]``.

    Client: ``DecoStorageRegularDecoVO.parseData`` (bundle line 141718)
    """

    wod_id: Annotated[EnumOrInt["Building"], BeforeValidator(js_int)] = Field(description="The decoration's type")
    amount: ClientInt = Field(default=0, description="How many are stored")
    new_amount: ClientInt = Field(default=0, description="How many of them are new, not yet seen")

    _from_list = model_validator(mode="before")(_row("wod_id", "amount", "new_amount"))


class StoredCustomDecoration(BasePayload):
    """
    A custom decoration in storage, one per entry; sent as ``[wod_id, custom_id, value, is_new]``.

    Client: ``DecoStorageCustomDecoVO.parseData`` (bundle line 141695)
    """

    wod_id: Annotated[EnumOrInt["Building"], BeforeValidator(js_int)] = Field(description="The decoration's type")
    custom_id: ClientInt = Field(description="The decoration's own id, to place it with pio")
    value: ClientInt = Field(default=0, description="Its decoration (public order) value")
    is_new: bool = Field(default=False, description="Whether it is new, not yet seen")

    _from_list = model_validator(mode="before")(_row("wod_id", "custom_id", "value", "is_new"))

    @field_validator("is_new", mode="before")
    @classmethod
    def _new(cls, value: Any) -> bool:
        return value == 1


class StoredUniqueDecoration(BasePayload):
    """
    A unique decoration in storage, one per entry; sent as ``[wod_id, unique_id, fusion_xp, is_new]``.

    Client: ``DecoStorageUniqueDecoVO.parseData`` (bundle line 141743)
    """

    wod_id: Annotated[EnumOrInt["Building"], BeforeValidator(js_int)] = Field(description="The decoration's type")
    unique_id: ClientInt = Field(description="The decoration's own id, to place or sell it")
    fusion_xp: ClientInt = Field(default=0, description="Fusion experience it has gathered")
    is_new: bool = Field(default=False, description="Whether it is new, not yet seen")

    _from_list = model_validator(mode="before")(_row("wod_id", "unique_id", "fusion_xp", "is_new"))

    @field_validator("is_new", mode="before")
    @classmethod
    def _new(cls, value: Any) -> bool:
        return value == 1


class DecorationStorage(BasePayload):
    """
    One decoration storage: the main one, a castle's area inventory, or an event kingdom's.

    Client: ``DecoStorageData.parseSIN`` and ``DecoStorageVO.parseSIN`` (bundle lines 141430, 141501)
    """

    storage_id: DecorationStorageKey = Field(validation_alias="SID", description="Which storage")
    decorations: list[StoredDecoration] = Field(
        validation_alias="RD", default_factory=list, description="Regular decorations, by type"
    )
    custom_decorations: list[StoredCustomDecoration] = Field(
        validation_alias="CD", default_factory=list, description="Custom decorations"
    )
    unique_decorations: list[StoredUniqueDecoration] = Field(
        validation_alias="UD", default_factory=list, description="Unique decorations"
    )

    @field_validator("storage_id", mode="before")
    @classmethod
    def _storage_id(cls, value: Any) -> DecorationStorageKey:
        return known(_STORAGE_ENUMS, js_int(value), warn=False)

    @field_validator("decorations", mode="before")
    @classmethod
    def _decorations(cls, value: Any) -> list[StoredDecoration]:
        return readable_list(StoredDecoration, value, warn=logger, what="stored decorations")

    @field_validator("custom_decorations", mode="before")
    @classmethod
    def _custom(cls, value: Any) -> list[StoredCustomDecoration]:
        return readable_list(StoredCustomDecoration, value, warn=logger, what="stored custom decorations")

    @field_validator("unique_decorations", mode="before")
    @classmethod
    def _unique(cls, value: Any) -> list[StoredUniqueDecoration]:
        return readable_list(StoredUniqueDecoration, value, warn=logger, what="stored unique decorations")


def _storages(value: Any) -> list[DecorationStorage]:
    return readable_list(DecorationStorage, value, warn=logger, what="decoration storages")


DecorationStorages = Annotated[list[DecorationStorage], BeforeValidator(_storages)]
"""A ``sin`` block: the storages it names, each replacing the one of the same id."""


class ShowInventoryRequest(BaseRequest):
    """
    Read the decoration storages.

    Command: sin
    Payload: none; the client sends the command with no parameter at all.

    Client: ``C2SShowInventoryVO`` (bundle line 77729), sent by ``CastleDecoShopPanel.show`` (bundle line 9302)
    through ``BasicSmartfoxClient.sendEmptyCommandVO`` (dll line 7176)
    """

    command = "sin"

    def to_packet(self, zone: str = DEFAULT_ZONE, room_id: int = NO_ROOM) -> str:
        """The frame with no parameter, as ``sendEmptyCommandVO`` sends it."""
        return build_command(zone, self.command, [], room_id)


class DecorationStorageResponse(BaseResponse):
    """
    The decoration storages, the ``sin`` reply.

    Command: sin
    Payload: [{"SID": storage_id, "RD": [..], "CD": [..], "UD": [..]}, ...]

    Client: ``SINCommand.exec`` (bundle line 124638), ``DecoStorageData.parseSIN`` (bundle line 141430)
    """

    command = "sin"

    storages: DecorationStorages = Field(default_factory=list, description="The storages sent")

    @model_validator(mode="before")
    @classmethod
    def _from_list(cls, data: Any) -> Any:
        return {"storages": data} if isinstance(data, list) else data


class MarkStorageSeenRequest(BaseRequest):
    """
    Mark one storage's new decorations as seen.

    Command: mbs
    Payload: {"SID": storage_id}

    Client: ``C2SMarkBuildingInStorageVO`` (bundle line 101113), sent for each storage shown by
    ``SendMarkedBuildingsInStorage.execute`` (bundle line 101099)
    """

    command = "mbs"

    storage_id: DecorationStorageKey = Field(validation_alias="SID", description="The storage")


class MarkStorageSeenResponse(BaseResponse):
    """
    The marking was accepted; the reply carries nothing the client reads.

    Command: mbs

    Client: ``MBSCommand.executeCommand`` (bundle line 124621)
    """

    command = "mbs"


class StoreBuildingRequest(BaseRequest):
    """
    Put a decoration of the joined castle into the storage.

    Command: sob
    Payload: {"OID": object_id}

    Client: ``C2SIsoStoreObjectVO`` (bundle line 63844), sent by
    ``IsoServerCommands.storeBuildingToLocalInventory`` (bundle line 63795)
    """

    command = "sob"

    object_id: int = Field(validation_alias="OID", description="The decoration's object id in the joined castle")


class StoreBuildingResponse(BaseResponse):
    """
    The stored decoration and the storages after.

    Command: sob
    Payload: {"OID": object_id, "sin": [..]}

    Client: ``SOBCommand.executeCommand`` (bundle line 124651), ``AreaDataUpdater.parseSOB``
    (bundle line 131569)
    """

    command = "sob"

    object_id: ClientInt = Field(validation_alias="OID", default=-1, description="Object id of the stored decoration")
    storages: DecorationStorages = Field(validation_alias="sin", default_factory=list, description="The storages after")


class SellStoredDecorationRequest(BaseRequest):
    """
    Sell decorations from the storage.

    Command: sds
    Payload: {"WID": wod_id, "AMT": amount, "UID": unique_id}

    Client: ``C2SellStoredDeco`` (bundle line 77781), sent by ``CastleConstructionSellDialog.onClick``
    (bundle line 28636) with ``getUniqueId`` (bundle line 28638), the decoration's unique id or -1
    """

    command = "sds"

    wod_id: EnumOrInt["Building"] = Field(validation_alias="WID", description="The decoration's type")
    amount: int = Field(validation_alias="AMT", description="How many to sell")
    unique_id: int = Field(validation_alias="UID", default=-1, description="A unique decoration's id, -1 for none")


class SellStoredDecorationResponse(BaseResponse):
    """
    Coins and the storages after the sale.

    Command: sds
    Payload: {"gcu": {..}, "sin": [..]}

    Client: ``SDSCommand.executeCommand`` (bundle line 131786)
    """

    command = "sds"

    currencies: CurrencyBlock = Field(validation_alias="gcu", default=None, description="Coins and rubies after")
    storages: DecorationStorages = Field(validation_alias="sin", default_factory=list, description="The storages after")


class PlaceStoredDecorationRequest(BaseRequest):
    """
    Place a custom or unique decoration from the storage in the joined castle.

    The client sends it for a stored decoration with its own id; a regular one goes out
    as a build (``ebu``) of its type.

    Command: pio
    Payload: {"COID": decoration_id, "X": x, "Y": y, "R": rotation}

    Client: ``C2SIsoPlaceCustomInventoryObjectVO`` (bundle line 63827), sent by
    ``IsoServerCommands.placeCustomInventoryObject`` (bundle line 63790) when the dragged
    decoration's ``uniqueBuildingId`` is 0 or more (bundle line 64041)
    """

    command = "pio"

    decoration_id: int = Field(
        validation_alias="COID", description="The custom or unique decoration's own id from the storage"
    )
    x: int = Field(validation_alias="X", description="Castle grid x")
    y: int = Field(validation_alias="Y", description="Castle grid y")
    rotation: int = Field(validation_alias="R", default=0, description="Rotation")


class PlaceStoredDecorationResponse(BaseResponse):
    """
    The placed decoration and the storages after.

    Command: pio
    Payload: {"NO": row, "sin": [..]}

    Client: ``PIOCommand.executeCommand`` (bundle line 123181), ``AreaDataUpdater.parseNewIsoObject``
    (bundle line 131572)
    """

    command = "pio"

    building: BuildingRow | None = Field(validation_alias="NO", default=None, description="The placed decoration")
    storages: DecorationStorages = Field(validation_alias="sin", default_factory=list, description="The storages after")

    _building = field_validator("building", mode="before")(building_or_none)


__all__ = [
    "DecorationStorage",
    "DecorationStorageKey",
    "DecorationStorageResponse",
    "DecorationStorages",
    "MarkStorageSeenRequest",
    "MarkStorageSeenResponse",
    "PlaceStoredDecorationRequest",
    "PlaceStoredDecorationResponse",
    "SellStoredDecorationRequest",
    "SellStoredDecorationResponse",
    "ShowInventoryRequest",
    "StoreBuildingRequest",
    "StoreBuildingResponse",
    "StoredCustomDecoration",
    "StoredDecoration",
    "StoredUniqueDecoration",
]
