"""
Army movement models: gam, the recall (mcm), and the movement wrappers pushed with abr and asr.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from empire_core.commanders.models.roster import Commander
from empire_core.enums import AttackAdvisorType, MapItemType, SpyType
from empire_core.gamedata import CollectableRows, EnumOrInt, SupportToolSlots, WodAmounts
from empire_core.map.models.owners import OwnerCastlePosition, OwnerCrest, OwnerFaction, owner_positions
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    Position,
    enum_or_none,
    object_or_none,
    read_or_none,
)
from empire_core.protocol.js import (
    ClientInt,
    js_loose_equals,
    js_parse_int,
    js_parse_int_or_zero,
    js_same_number,
    js_truthy,
)


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
        return Position(x=self.x, y=self.y)

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
    horse_booster_id: int = Field(
        alias="HBW", default=-1, description="The horse booster's wod id, -1 for none or when paid with feathers"
    )
    target_area: MovementArea | None = Field(alias="TA", default=None, description="Target area")
    source_area: MovementArea | None = Field(alias="SA", default=None, description="Source area")

    @property
    def is_returning(self) -> bool:
        """Client: ``BasicMapmovementVO.isReturnHome``."""
        return self.direction == 1


class MovementArmy(BasePayload):
    """A visible army: three flanks plus the courtyard wave, each ``{Unit or Tool: amount}``.

    Client: ``CastleCompactArmyVO.parseSimpleArmy`` / ``parseYardWave`` (bundle lines 67525,
    67529) read each into a ``UnitInventoryDictionary``, which adds up an id sent twice.
    """

    left: WodAmounts = Field(alias="L", default_factory=dict, description="Left flank")
    middle: WodAmounts = Field(alias="M", default_factory=dict, description="Middle")
    right: WodAmounts = Field(alias="R", default_factory=dict, description="Right flank")
    courtyard: WodAmounts = Field(alias="RW", default_factory=dict, description="Courtyard (yard) wave")


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
    advisor_type: EnumOrInt[AttackAdvisorType] = Field(
        alias="AAT", default=AttackAdvisorType.NONE, description="The attack advisor that sent the attack"
    )
    advisor_movement_count: int = Field(alias="AAC", default=0, description="Attacks in the advisor series")
    advisor_movement_number: int = Field(alias="AAN", default=0, description="This attack's place in the series")
    advisor_is_last: int = Field(alias="AAL", default=0, description="1 on the series' last attack")

    @field_validator("commander", mode="before")
    @classmethod
    def _readable_commander(cls, value: Any) -> Any:
        """An unreadable commander costs only itself, not the wait and advisor details."""
        return read_or_none(Commander.model_validate, value) if value else None


class MovementMarket(BasePayload):
    """A market transport's cargo: a wrapper's ``MM``.

    Client: ``MarketMapmovementVO.parse_MM`` (bundle line 43706), which reads ``G`` with
    ``CollectableParserS2CParamList.createList`` (bundle line 40560)
    """

    carriages: int = Field(alias="C", default=0, description="Market carriages used")
    goods: CollectableRows = Field(alias="G", default=(), description="Goods carried")


class MovementSpy(BasePayload):
    """A spy mission's details: a wrapper's ``S``.

    Client: ``SpyMapmovementVO.parseSpyInfo`` (bundle line 43748), which reads each through ``int()``.
    """

    spy_type: ClientInt = Field(alias="ST", default=0, description="Kind of spy mission, a SpyType value")
    accuracy_or_damage: ClientInt = Field(
        alias="SA", default=0, description="Accuracy percent, or damage percent for sabotage"
    )
    spy_count: ClientInt = Field(alias="SC", default=0, description="Spies sent")
    risk: ClientInt = Field(alias="SR", default=0, description="Risk of being caught, percent")

    @property
    def spy_type_enum(self) -> SpyType | None:
        """``spy_type`` as a :class:`SpyType`, None for a value the client does not define."""
        return enum_or_none(SpyType, self.spy_type)

    @property
    def is_sabotage(self) -> bool:
        return self.spy_type == SpyType.SABOTAGE


class MovementWrapper(BasePayload):
    """One entry of ``gam``'s ``M`` list, and the ``A`` of an ``abr``/``asr`` push or an ``mcm`` reply.

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
    support_tools: SupportToolSlots = Field(
        alias="AST",
        default=(),
        description="Support tools sent along, as the attack sent them; None for an empty slot",
    )
    auto_skip_cooldown_type: int = Field(alias="ASCT", default=0, description="Auto-skip cooldown type")
    travel_units: WodAmounts = Field(
        alias="A", default_factory=dict, description="Units and tools of a travel movement"
    )
    travel_goods: CollectableRows = Field(
        alias="G",
        default=(),
        description="Loot a travel movement carries (ArmyTravelMapMovementVO.loadFromParamObject, bundle line 26798)",
    )
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

    @field_validator("castle_positions", "village_positions", mode="before")
    @classmethod
    def _position_rows(cls, value: Any) -> Any:
        return owner_positions(value)

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


class CancelMovementRequest(BaseRequest):
    """
    Recall one of your movements, turning it back home.

    Command: mcm
    Payload: {"MID": movement_id}

    The client sends it from its retreat dialog, from "send home" for your
    supports stationed at an area (one per support), and from the attack
    advisor's cancel dialog (one per advisor attack). The retreat button is
    enabled only where the movement's class allows it:

    - attacks (every attack type but alien attacks, which never): your own,
      heading to the target, from level 5, and no more than 600 seconds after
      leaving, unless the movement is force-cancelable (``FC``), attacks
      nomads while the alliance nomad invasion is not running, or attacks a
      faction tower
    - supports: your own, in either direction
    - travel between your areas: your own, heading to the target, from a
      source area that is still yours
    - spies, market transports and occupations: your own, heading to the target
    - treasure hunts and plague monks: never

    The movement list also disables it while the source area is under
    conquer control. The advisor's overview cancels every advisor attack
    that is not the series' last, returning ones too, without these checks.
    The server's refusals include INVALID_STARTAREA_FOR_CANCEL_MOVEMENT
    (189); the client handles none itself and shows its generic server error.

    Client: ``C2SCancelMovementVO`` (bundle line 33049); sent by
    ``CastleAskRetreatDialog.onClick`` (bundle line 33234),
    ``SupportOverviewDialog.onClickRetreat`` (bundle line 33984) and
    ``AdvisorAttackOverviewCancelDialog.cancelAttacks`` (bundle line 21965),
    fed by ``AdvisorAttackOverviewDialog.getCancellableAdvisorMovements``
    (bundle line 57303); ``canBeRetreated`` on ``ArmyAttackMapmovementVO``
    (bundle line 14379), ``ArmyTravelMapMovementVO`` (bundle line 26818),
    ``SupportDefenceMapmovementVO`` (bundle line 43782), ``SpyMapmovementVO``
    (bundle line 43759), ``MarketMapmovementVO`` (bundle line 43707),
    ``SiegeMapmovementVO`` (bundle line 33183) and the always-false ones
    (bundle lines 33079, 43733, 43805); ``ArmyAttackMapmovementVO.tooLateToBeRetreated``
    (bundle line 14382) with ``TravelConst.MAX_FALLBACK_TIME`` (ggs.dll line
    19828); ``ClientConstLevelRestrictions.MIN_LEVEL_RETREAT_MOVEMENTS`` (bundle
    line 2139) through ``CastleUserData.hasLevelFor`` (bundle line 10027);
    ``AMovementRenderStrategy.initRetreatButton`` (bundle line 14347);
    ``MapmovementFactory.parseMapMovement`` (bundle line 133793)
    """

    command = "mcm"

    movement_id: int = Field(alias="MID", description="The movement to recall")

    def accepts_reply(self, payload: Any) -> bool:
        """Whether an mcm reply is the movement this recalled: its ``A.M.MID``, when sent, is ``MID``.

        Client: ``MCMCommand.executeCommand`` (bundle line 126041) reads the recalled
        movement from ``A``.
        """
        wrapper = payload.get("A") if isinstance(payload, dict) else None
        movement = wrapper.get("M") if isinstance(wrapper, dict) else None
        if not isinstance(movement, dict) or "MID" not in movement:
            return True
        return js_same_number(movement["MID"], self.movement_id)


class CancelMovementResponse(BaseResponse):
    """
    The reply to a recall: the movement as it now stands.

    Command: mcm
    Payload: {"A": wrapper}

    ``A`` is read as one ``gam`` entry, replacing the tracked movement. The
    client reads it unconditionally, so a reply without one is malformed.

    Client: ``MCMCommand.executeCommand`` (bundle line 126041), which hands
    ``[A]`` to ``CastleArmyData.parseMapMovementArray`` (bundle line 133626)
    """

    command = "mcm"

    movement: MovementWrapper = Field(alias="A", description="The recalled movement")


__all__ = [
    "CancelMovementRequest",
    "CancelMovementResponse",
    "GetMovementsRequest",
    "GetMovementsResponse",
    "MovementArea",
    "MovementArmy",
    "MovementMarket",
    "MovementOwner",
    "MovementRecord",
    "MovementSpy",
    "MovementUnitInfo",
    "MovementWrapper",
]
