"""
Treasure maps: the treasure hunt's map and the season events' maps, their nodes, storage and transfers.

Commands:
- tmp: The treasure maps, a login section of ``gbd``, a reply, and inside the treasure map replies
- thi: Which map the treasure hunt is on, a login section of ``gbd``, a push, and inside ``tfm``
- tbm: Buy missing pieces of a treasure map
- tfm: Finish a treasure map whose end node fell
- tcn: A treasure map node's state after a click; the client has no request for it
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import BeforeValidator, ConfigDict, Field, field_validator

from empire_core.enums import TreasureMapProgress
from empire_core.gamedata import CollectableRows, EnumOrInt, WodAmounts
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    TimedPayload,
    object_or_none,
    readable_list,
)
from empire_core.protocol.js import ClientInt, ClientNumber, js_int, js_loose_equals, js_truthy


class TreasureMapNode(TimedPayload):
    """
    One node of a treasure map as the server sends it, an entry of a map's ``N``.

    The node's place, level and unlock rules come from the game's ``tmapnodes`` data, which the
    library does not read.

    Client: ``TreasureMapVO.loadFromParamObject`` (bundle line 140557) marks a node with ``A`` 1 as
    defeated; ``TMapNodeVO.parseParamObject`` (bundle line 26940) reads the rest. The ruby prices pay
    the parts of the node's obstacle (``CastleTreasureMapUnlockObstacleDialog``, bundle line 67833)
    """

    node_id: ClientInt = Field(validation_alias="NID", default=0, description="The node on the treasure map")
    defeated: bool = Field(validation_alias="A", default=False, description="Whether the node has fallen")
    cooldown_seconds: ClientNumber = Field(
        validation_alias="CD",
        default=0,
        description="Seconds until the node can be attacked again when the values were read; 0 or less for none",
    )
    paid_goods: CollectableRows = Field(
        validation_alias="G", default=(), description="Goods already paid towards the node's obstacle"
    )
    coins_in_rubies: ClientInt = Field(
        validation_alias="C1C2",
        default=0,
        description="Rubies that pay the obstacle's coins instead, before ruby discounts; 0 when it cannot",
    )
    stone_in_rubies: ClientInt = Field(
        validation_alias="SC2",
        default=0,
        description="Rubies that pay the obstacle's stone instead, before ruby discounts; 0 when it cannot",
    )
    wood_in_rubies: ClientInt = Field(
        validation_alias="WC2",
        default=0,
        description="Rubies that pay the obstacle's wood instead, before ruby discounts; 0 when it cannot",
    )

    @field_validator("defeated", mode="before")
    @classmethod
    def _defeated(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)

    def remaining_cooldown_seconds(self, now: float | None = None) -> float:
        """Seconds until the node can be attacked again, 0 at least."""
        return max(0.0, self.cooldown_seconds - self._elapsed(now)) if self.cooldown_seconds > 0 else 0.0


class TreasureMapGoodsTransfer(TimedPayload):
    """
    Goods on their way to a treasure map, a map's ``RT``.

    Client: ``TreasureMapVO.parseGoodsTransfer`` (bundle line 140631), which reads ``G`` with
    ``CollectableParserS2CParamList``
    """

    seconds: ClientNumber = Field(
        validation_alias="RS", default=0, description="Seconds until they arrive when the values were read"
    )
    goods: CollectableRows = Field(validation_alias="G", default=(), description="The goods on their way")

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds until they arrive, 0 at least."""
        return max(0.0, self.seconds - self._elapsed(now))


class TreasureMapUnitTransfer(TimedPayload):
    """
    Units on their way to a treasure map, a map's ``UT``.

    Client: ``TreasureMapVO.parseTroopsTransfer`` (bundle line 140633), which reads ``I`` with
    ``fillFromWodAmountArray``
    """

    seconds: ClientNumber = Field(
        validation_alias="RS", default=0, description="Seconds until they arrive when the values were read"
    )
    units: WodAmounts = Field(validation_alias="I", default_factory=dict, description="The units on their way")

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds until they arrive, 0 at least."""
        return max(0.0, self.seconds - self._elapsed(now))


class TreasureMapStorage(BasePayload):
    """
    A treasure map camp's storage for units and resources, a map's ``S``; all 0 when none is sent.

    Client: ``TreasureMapVO.parseStorage`` (bundle line 140575)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    unit_capacity: ClientInt = Field(validation_alias="MU", default=0, description="Units the camp holds at most")
    unit_count: ClientInt = Field(validation_alias="U", default=0, description="Units in the camp")
    food_capacity: ClientInt = Field(validation_alias="MRF", default=0, description="Food the camp holds at most")
    wood_capacity: ClientInt = Field(validation_alias="MRW", default=0, description="Wood the camp holds at most")
    stone_capacity: ClientInt = Field(validation_alias="MRS", default=0, description="Stone the camp holds at most")
    food: ClientInt = Field(validation_alias="F", default=0, description="Food in the camp")
    wood: ClientInt = Field(validation_alias="W", default=0, description="Wood in the camp")
    stone: ClientInt = Field(validation_alias="S", default=0, description="Stone in the camp")

    @property
    def free_unit_slots(self) -> int:
        """Units the camp still takes. Client: ``TreasureMapVO.freeUnitSlots`` (bundle line 140689)"""
        return max(0, self.unit_capacity - self.unit_count)


class TreasureMap(TimedPayload):
    """
    One treasure map's progress, an entry of a ``tmp``'s ``TM``.

    The map's pieces, node layout and costs come from the game's ``tmaps`` data, which the library
    does not read.

    Client: ``TreasureMapVO.loadFromParamObject`` (bundle line 140557)
    """

    map_id: ClientInt = Field(validation_alias="MID", default=0, description="The treasure map")
    nodes: tuple[TreasureMapNode, ...] = Field(
        validation_alias="N", default=(), description="The nodes the server sent, in its order"
    )
    pieces_found: ClientInt = Field(validation_alias="PF", default=0, description="Map pieces found so far")
    progress: EnumOrInt[TreasureMapProgress] = Field(
        validation_alias="PT", default=TreasureMapProgress.NONE, description="The last step the map took"
    )
    goods_transfer: TreasureMapGoodsTransfer | None = Field(
        validation_alias="RT", default=None, description="Goods on their way to the map; None for none"
    )
    unit_transfer: TreasureMapUnitTransfer | None = Field(
        validation_alias="UT", default=None, description="Units on their way to the map; None for none"
    )
    storage: TreasureMapStorage = Field(
        validation_alias="S", default_factory=TreasureMapStorage, description="The map camp's storage"
    )
    morality: ClientInt = Field(validation_alias="M", default=0, description="Your army's morality on the map")
    units: WodAmounts = Field(validation_alias="I", default_factory=dict, description="Units in the map's camp")
    end_seconds: ClientNumber = Field(
        validation_alias="RS",
        default=-1,
        description="Seconds until the map closes when the values were read; 0 or -1 when it does not close",
    )

    @field_validator("nodes", mode="before")
    @classmethod
    def _nodes(cls, value: Any) -> Any:
        return tuple(readable_list(TreasureMapNode, value, accept=lambda entry: isinstance(entry, dict)))

    @field_validator("progress", mode="before")
    @classmethod
    def _progress(cls, value: Any) -> int:
        return js_int(value)

    @field_validator("goods_transfer", "unit_transfer", mode="before")
    @classmethod
    def _transfer(cls, value: Any) -> Any:
        return object_or_none(value)

    @field_validator("storage", mode="before")
    @classmethod
    def _storage(cls, value: Any) -> Any:
        return value if js_truthy(value) and isinstance(value, dict | TreasureMapStorage) else {}

    def node(self, node_id: int) -> TreasureMapNode | None:
        """One node, None when the server sent none for it."""
        return next((node for node in self.nodes if node.node_id == node_id), None)

    def remaining_seconds(self, now: float | None = None) -> float | None:
        """Seconds until the map closes, 0 at least; None when it does not close."""
        if not js_truthy(self.end_seconds) or self.end_seconds <= -1:
            return None
        return max(0.0, self.end_seconds - self._elapsed(now))


class GetTreasureMapsRequest(BaseRequest):
    """
    Ask for your treasure maps.

    Command: tmp
    Payload: {"MID": map_id}

    The client sends -1 when it opens the quest book and while a transfer to a map is on its way,
    and a season's map when it opens that season's dialog.

    Client: ``C2STreasureMapsVO`` (bundle line 24131), sent by ``CastleQuestDialog.showLoaded``
    (bundle line 23972), ``CastleTreasureMapData.executeUpdate`` (bundle line 140424) and
    ``CastleHandleSeasonDialog.showLoaded`` (bundle line 38286)
    """

    command = "tmp"

    map_id: int = Field(
        validation_alias="MID", default=-1, description="A season's treasure map, or -1 as the client sends otherwise"
    )


class TreasureMapsResponse(BaseResponse):
    """
    Your treasure maps' progress.

    A full list replaces every map known; otherwise each map sent replaces the one with its id, and
    ``client.map.treasure_maps`` does the same.

    Command: tmp, as a login section of ``gbd``, a reply, and inside the ``tcn``, ``tfm``, ``tgt``,
    ``tut``, ``tkt`` and ``msm`` replies
    Payload: {"UA": 0 or 1, "TM": [map, ...]}

    Client: ``TMPCommand`` (bundle line 129103), ``CastleTreasureMapData.parse_TMP`` (bundle line 140451),
    which starts the maps over when it holds none yet or ``UA`` is 1
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "tmp"

    is_full_list: bool = Field(
        validation_alias="UA", default=False, description="Whether the maps sent replace every map known"
    )
    maps: tuple[TreasureMap, ...] = Field(validation_alias="TM", default=(), description="The maps sent")

    @field_validator("is_full_list", mode="before")
    @classmethod
    def _full_list(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)

    @field_validator("maps", mode="before")
    @classmethod
    def _maps(cls, value: Any) -> Any:
        if not js_truthy(value):
            return ()
        return tuple(readable_list(TreasureMap, value, accept=lambda entry: isinstance(entry, dict)))


TreasureMapsBlock = Annotated[TreasureMapsResponse | None, BeforeValidator(object_or_none)]
"""A ``tmp`` block inside another reply, or None when it sends none."""


class TreasureHuntInfoResponse(BaseResponse):
    """
    Which map the treasure hunt is on.

    Command: thi, as a login section of ``gbd``, a push, and inside the ``tfm`` reply
    Payload: {"MID": map_id}

    Client: ``THICommand`` (bundle line 128993), ``CastleTreasureHuntData.parse_THI`` (bundle line 112870);
    ``CastleTreasureMapData.NO_MORE_MAPS`` is -1 (bundle line 140486)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "thi"

    map_id: ClientInt = Field(
        validation_alias="MID", default=0, description="The treasure hunt's current map; -1 once no map is left"
    )


class BuyTreasureMapPiecesRequest(BaseRequest):
    """
    Buy missing pieces of a treasure map with rubies.

    Command: tbm
    Payload: {"A": amount, "MID": map_id}

    Client: ``C2SBuyTreasureMapPieceVO`` (bundle line 67961), sent by
    ``CastleTreasureBuyPieceDialog.onClick`` (bundle line 67949), which charges
    ``costPiece`` rubies a piece (bundle line 67945)
    """

    command = "tbm"

    amount: int = Field(validation_alias="A", description="Pieces to buy")
    map_id: int = Field(validation_alias="MID", description="The treasure map")


class BuyTreasureMapPiecesResponse(BaseResponse):
    """
    The pieces were bought; the reply carries nothing.

    Command: tbm

    Client: ``TBMCommand.executeCommand`` (bundle line 129025) reads nothing
    """

    command = "tbm"


class FinishTreasureMapRequest(BaseRequest):
    """
    Close a treasure map whose end node fell, for the treasure hunt's next map.

    The client sends it itself once the treasure hunt's map reports ``DESTROYED_END_NODE``, and
    when you leave a season's map.

    Command: tfm
    Payload: {"MID": map_id}

    Client: ``C2STreasureFinishMap`` (bundle line 57493), sent by
    ``CastleTreasureMapData.parse_TMP`` (bundle line 140458) and from bundle line 105973
    """

    command = "tfm"

    map_id: int = Field(validation_alias="MID", description="The treasure map")


class FinishTreasureMapResponse(BaseResponse):
    """
    The treasure hunt's next map, and your maps after.

    Command: tfm
    Payload: {"thi": {...}, "tmp": {...}}

    Client: ``TFMCommand.executeCommand`` (bundle line 129053)
    """

    command = "tfm"

    treasure_hunt: TreasureHuntInfoResponse | None = Field(
        validation_alias="thi", default=None, description="Which map the treasure hunt is on now"
    )
    treasure_maps: TreasureMapsBlock = Field(validation_alias="tmp", default=None, description="Your maps after")

    @field_validator("treasure_hunt", mode="before")
    @classmethod
    def _hunt(cls, value: Any) -> Any:
        return object_or_none(value)


class TreasureNodeClickResponse(BaseResponse):
    """
    Your treasure maps after a node was clicked.

    The client has no request class for ``tcn``: it only reads this reply.

    Command: tcn
    Payload: {"tmp": {...}}

    Client: ``TCNCommand.executeCommand`` (bundle line 129038)
    """

    command = "tcn"

    treasure_maps: TreasureMapsBlock = Field(validation_alias="tmp", default=None, description="Your maps after")


__all__ = [
    "BuyTreasureMapPiecesRequest",
    "BuyTreasureMapPiecesResponse",
    "FinishTreasureMapRequest",
    "FinishTreasureMapResponse",
    "GetTreasureMapsRequest",
    "TreasureHuntInfoResponse",
    "TreasureMap",
    "TreasureMapGoodsTransfer",
    "TreasureMapNode",
    "TreasureMapStorage",
    "TreasureMapUnitTransfer",
    "TreasureMapsBlock",
    "TreasureMapsResponse",
    "TreasureNodeClickResponse",
]
