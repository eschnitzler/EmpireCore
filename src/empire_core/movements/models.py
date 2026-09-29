"""
Army movement models: the gam reply and the movement wrappers pushed with abr, asr and mcm.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from empire_core.commanders.models.roster import Commander
from empire_core.enums import MapItemType, SpyType
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    Position,
    enum_or_none,
    object_or_none,
    read_or_none,
)
from empire_core.protocol.js import ClientInt, js_loose_equals, js_parse_int, js_parse_int_or_zero, js_truthy


class GetMovementsRequest(BaseRequest):
    """
    Get all active troop movements.

    Command: gam
    Payload: {}

    Client: ``C2SGetAllMovementsVO`` (bundle line 129713, no fields)
    """

    command = "gam"


_AREA_LAYOUTS: dict[int, tuple[int | None, int | None, int | None]] = {
    MapItemType.CASTLE: (3, 4, 10),
    MapItemType.CAPITAL: (3, 4, 10),
    MapItemType.OUTPOST: (3, 4, 10),
    MapItemType.KINGDOM_CASTLE: (3, 4, 10),
    MapItemType.METROPOL: (3, 4, 10),
    MapItemType.VILLAGE: (3, 4, None),
    MapItemType.FACTION_VILLAGE: (None, 3, None),
    MapItemType.FACTION_TOWER: (None, 3, None),
    MapItemType.FACTION_CAPITAL: (None, 3, None),
    MapItemType.KINGS_TOWER: (3, 4, 7),
    MapItemType.ISLE_RESOURCE: (3, 4, 6),
    MapItemType.MONUMENT: (3, 4, 9),
    MapItemType.LABORATORY: (3, 4, 8),
    MapItemType.ALLIANCE_BATTLE_GROUND_TOWER: (3, None, 4),
}


class MovementArea(BasePayload):
    """A movement's ``TA`` or ``SA`` area row.

    Only the first three positions mean the same for every area type
    (``BasicMapobjectVO.parseAreaInfo``); ``object_id``, ``owner_id`` and
    ``name`` read the positions the area type's own parser uses. A castle
    row of four or fewer entries is a castle being relocated and has none.

    Client: ``WorldmapObjectFactory.parseWorldMapArea``, ``InteractiveMapobjectVO``,
    ``KingstowerMapobjectVO``, ``MonumentMapobjectVO``, ``LaboratoryMapobjectVO``,
    ``ResourceIsleMapobjectVO``, ``VillageMapobjectVO``, ``Faction*MapobjectVO``
    and ``ABGAllianceTowerMapobjectVO`` ``.parseAreaInfo``.
    """

    area_type: int = Field(description="Area type")
    x: int = Field(description="Map x")
    y: int = Field(description="Map y")
    row: list[Any] = Field(description="The whole row, whose layout depends on area_type")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, list) and len(data) >= 3:
            return {"area_type": data[0], "x": data[1], "y": data[2], "row": data}
        return data

    @property
    def position(self) -> Position:
        return Position(X=self.x, Y=self.y)

    def _at(self, slot: int) -> Any:
        layout = _AREA_LAYOUTS.get(self.area_type)
        if layout is None or (self.area_type == MapItemType.CASTLE and len(self.row) <= 4):
            return None
        index = layout[slot]
        return self.row[index] if index is not None and index < len(self.row) else None

    @property
    def object_id(self) -> int | None:
        value = self._at(0)
        return value if isinstance(value, int) else None

    @property
    def owner_id(self) -> int | None:
        value = self._at(1)
        return value if isinstance(value, int) else None

    @property
    def name(self) -> str:
        value = self._at(2)
        return value if isinstance(value, str) else ""


class MovementRecord(BasePayload):
    """The movement itself: the ``M`` inside each ``gam`` wrapper.

    Client: ``BasicMapmovementVO.loadFromParamObject``.
    """

    movement_id: int = Field(alias="MID", description="Movement id")
    movement_type: int = Field(alias="T", default=0, description="MovementType value")
    progress_time: int = Field(alias="PT", default=0, description="Seconds travelled when the reply was sent")
    total_time: int = Field(alias="TT", default=0, description="Seconds the trip takes")
    direction: int = Field(alias="D", default=0, description="1 = returning home, 0 = heading to the target")
    target_id: int = Field(alias="TID", default=-1, description="Player id owning the target area")
    kingdom_id: int = Field(alias="KID", default=0, description="Kingdom id")
    source_id: int = Field(alias="SID", default=-1, description="Player id owning the source area")
    owner_id: int = Field(alias="OID", default=-1, description="Player id owning the movement")
    horse_booster_id: int = Field(alias="HBW", default=-1, description="Horse booster item id, -1 for none")
    target_area: MovementArea | None = Field(alias="TA", default=None, description="Target area")
    source_area: MovementArea | None = Field(alias="SA", default=None, description="Source area")

    @property
    def is_returning(self) -> bool:
        """Client: ``BasicMapmovementVO.isReturnHome``."""
        return self.direction == 1


class MovementArmy(BasePayload):
    """A visible army: three flanks of ``[unit_id, count]`` pairs plus the courtyard wave.

    Client: ``CastleCompactArmyVO.parseSimpleArmy`` / ``parseYardWave``.
    """

    left: list[list[int]] = Field(alias="L", default_factory=list, description="Left flank")
    middle: list[list[int]] = Field(alias="M", default_factory=list, description="Middle")
    right: list[list[int]] = Field(alias="R", default_factory=list, description="Right flank")
    courtyard: list[list[int]] = Field(alias="RW", default_factory=list, description="Courtyard (yard) wave")


class MovementUnitInfo(BasePayload):
    """Commander and wait details: a wrapper's ``UM``.

    Client: ``BasicMapmovementVO.parseUnitMovement`` (bundle line 19385), which hands ``L`` to
    ``LordFactory.createLord`` (bundle line 26399).
    """

    commander: Commander | None = Field(
        alias="L", default=None, description="Commander leading the army; None when there is none"
    )
    wait_passed: int = Field(alias="PWD", default=0, description="Seconds of the wait at the target already passed")
    wait_total: int = Field(alias="TWD", default=0, description="Seconds the army waits at its target")
    advisor_type: int = Field(alias="AAT", default=0, description="Attack advisor type, 0 for none")
    advisor_movement_count: int = Field(alias="AAC", default=0, description="Attacks in the advisor series")
    advisor_movement_number: int = Field(alias="AAN", default=0, description="This attack's place in the series")
    advisor_is_last: int = Field(alias="AAL", default=0, description="1 on the series' last attack")

    @field_validator("commander", mode="before")
    @classmethod
    def _readable_commander(cls, value: Any) -> Any:
        """An unreadable commander costs only itself, not the wait and advisor details."""
        return read_or_none(Commander.model_validate, value) if value else None


MovementGoods = list[tuple[str | int, int]] | list[int]


class MovementMarket(BasePayload):
    """A market transport's cargo: a wrapper's ``MM``.

    Client: ``MarketMapmovementVO.parse_MM``.
    """

    carriages: int = Field(alias="C", default=0, description="Market carriages used")
    goods: MovementGoods = Field(alias="G", default_factory=list, description="Goods carried")


class MovementSpy(BasePayload):
    """A spy mission's details: a wrapper's ``S``.

    Client: ``SpyMapmovementVO.parseSpyInfo``.
    """

    spy_type: int = Field(alias="ST", default=0, description="Kind of spy mission, a SpyType value")
    accuracy_or_damage: int = Field(
        alias="SA", default=0, description="Accuracy percent, or damage percent for sabotage"
    )
    spy_count: int = Field(alias="SC", default=0, description="Spies sent")
    risk: int = Field(alias="SR", default=0, description="Risk of being caught, percent")

    @property
    def spy_type_enum(self) -> SpyType | None:
        """``spy_type`` as a :class:`SpyType`, None for a value the client does not define."""
        return enum_or_none(SpyType, self.spy_type)

    @property
    def is_sabotage(self) -> bool:
        return self.spy_type == SpyType.SABOTAGE


class MovementWrapper(BasePayload):
    """One entry of ``gam``'s ``M`` list, and the ``A`` of an ``abr``/``asr``/``mcm`` push.

    Which of the optional blocks are present depends on the movement type and
    on what the receiving player may see. Keys this model does not name are
    kept, as on every payload.

    Client: ``MapmovementFactory.parseMapMovement`` and the ``loadFromParamObject``
    of each movement class.
    """

    movement: MovementRecord = Field(alias="M", description="The movement record")
    full_army: MovementArmy | None = Field(alias="FA", default=None, description="The full army, preferred over army")
    army: MovementArmy | None = Field(alias="GA", default=None, description="Army")
    army_size: int | None = Field(alias="GS", default=None, description="Estimated army size when the army is hidden")
    unit_info: MovementUnitInfo | None = Field(alias="UM", default=None, description="Commander and wait details")
    attack_type: int | None = Field(alias="ATT", default=None, description="AttackType value of an attack")
    is_shadow: bool = Field(alias="SM", default=False, description="Shadow movement")
    force_cancelable: bool = Field(alias="FC", default=False, description="The movement can be force-cancelled")
    support_tools: list[int] = Field(alias="AST", default_factory=list, description="Support tool ids sent along")
    auto_skip_cooldown_type: int = Field(alias="ASCT", default=0, description="Auto-skip cooldown type")
    travel_units: list[list[int]] = Field(
        alias="A", default_factory=list, description="Units of a travel movement as [unit_id, count]"
    )
    travel_goods: MovementGoods = Field(alias="G", default_factory=list, description="Loot a travel movement carries")
    market: MovementMarket | None = Field(alias="MM", default=None, description="Market transport cargo")
    spy: MovementSpy | None = Field(alias="S", default=None, description="Spy mission details")

    @field_validator("spy", mode="before")
    @classmethod
    def _no_spy_details(cls, value: Any) -> Any:
        return object_or_none(value)

    @property
    def visible_army(self) -> MovementArmy | None:
        """``FA`` if sent, else ``GA``, as the client picks."""
        return self.full_army or self.army


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


class MovementOwner(BasePayload):
    """An owner record: one entry of ``O`` in ``gam``, ``abr`` and ``asr``.

    Client: ``WorldMapOwnerInfoVO.fillFromParamObject``.
    """

    player_id: int = Field(alias="OID", description="Player id")
    name: str = Field(alias="N", default="")
    crest: OwnerCrest | None = Field(alias="E", default=None)
    level: int = Field(alias="L", default=0)
    legend_level: int = Field(alias="LL", default=0)
    beginner_protection_seconds: int = Field(alias="RNP", default=-1, description="-1 when not protected")
    honor: int = Field(alias="H", default=0)
    might: int = Field(alias="MP", default=0)
    top_x: int = Field(alias="TOPX", default=-1, description="Top-ranking placement, -1 for none")
    is_ruin: bool = Field(alias="R", default=False, description="The owner record is flagged as a ruin")
    alliance_id: int = Field(alias="AID", default=-1, description="-1 for no alliance")
    alliance_rank: int = Field(alias="AR", default=0)
    alliance_name: str = Field(alias="AN", default="")
    is_searching_alliance: bool = Field(alias="SA", default=False)
    peace_seconds: int = Field(alias="RPT", default=0, description="Remaining peace time")
    castle_positions: list[OwnerCastlePosition] = Field(alias="AP", default_factory=list)
    village_positions: list[OwnerCastlePosition] = Field(alias="VP", default_factory=list)
    has_premium: bool = Field(alias="PF", default=False)
    has_vip: bool = Field(alias="VF", default=False)
    is_dummy: bool = Field(alias="DUM", default=False, description="The owner record is a dummy")
    achievement_points: int = Field(alias="AVP", default=0)
    relocation_seconds: int = Field(alias="RRD", default=0, description="Seconds until a relocation ends")
    faction: OwnerFaction | None = Field(alias="FN", default=None)
    title_prefix_id: int | None = Field(alias="PRE", default=None)
    title_suffix_id: int | None = Field(alias="SUF", default=None)
    via_refer_a_friend: bool = Field(alias="IRF", default=False)

    @field_validator("is_searching_alliance", "has_premium", "has_vip", mode="before")
    @classmethod
    def _truthy_flag(cls, value: Any) -> bool:
        return js_truthy(value)

    @field_validator("is_ruin", mode="before")
    @classmethod
    def _parsed_one_flag(cls, value: Any) -> bool:
        return js_parse_int(value) == 1

    @field_validator("is_dummy", mode="before")
    @classmethod
    def _one_flag(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)

    @field_validator("via_refer_a_friend", mode="before")
    @classmethod
    def _parsed_truthy_flag(cls, value: Any) -> bool:
        return js_parse_int_or_zero(value) != 0


class GetMovementsResponse(BaseResponse):
    """
    Response containing active movements.

    Command: gam
    Payload: {"M": [wrapper, ...], "O": [owner record, ...]}

    Client: ``CastleArmyData.parse_GAM``.
    """

    command = "gam"

    movements: list[MovementWrapper] = Field(alias="M", default_factory=list, description="Movement wrappers")
    owners: list[MovementOwner] = Field(
        alias="O", default_factory=list, description="Owner records for every player the movements name"
    )


__all__ = [
    "GetMovementsRequest",
    "GetMovementsResponse",
    "MovementArea",
    "MovementArmy",
    "MovementGoods",
    "MovementMarket",
    "MovementOwner",
    "MovementRecord",
    "MovementSpy",
    "MovementUnitInfo",
    "MovementWrapper",
    "OwnerCastlePosition",
    "OwnerCrest",
    "OwnerFaction",
]
