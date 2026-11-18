"""
Army movement models: gam, the recall (mcm), and the movement wrappers pushed with abr and asr.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import (
    Field,
    ValidationError,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    field_serializer,
    field_validator,
    model_validator,
)

from empire_core.commanders.models.roster import Commander
from empire_core.enums import (
    AttackAdvisorType,
    AttackType,
    AutoSkipCooldownType,
    Kingdom,
    MovementFilter,
    MovementType,
    SpyType,
)
from empire_core.gamedata import CollectableRows, EnumOrInt, SupportToolSlots, WodAmounts
from empire_core.map.models.items import MapAreaItem
from empire_core.map.models.owners import OwnerCrest, OwnerFaction, OwnerPositions
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    CurrencyBlock,
    Position,
    enum_or_none,
    list_or_empty,
    object_or_none,
    read_or_none,
    readable_list,
)
from empire_core.protocol.js import (
    ClientInt,
    js_int,
    js_loose_equals,
    js_parse_int,
    js_parse_int_or_zero,
    js_same_number,
    js_truthy,
    js_whole_number,
)

if TYPE_CHECKING:
    from empire_core.gamedata import Horse, Title

logger = logging.getLogger(__name__)

NO_HORSE = -1
"""The horse a movement request names when it takes none, or pays for its horse with feathers."""

HorseBoosterId = Annotated[Literal[-1] | EnumOrInt["Horse"], Field(union_mode="left_to_right")]
"""A movement request's ``HBW``: a ``Horse``, or ``NO_HORSE``.

Client: ``BasicMapmovementVO`` (bundle lines 19383, 15445) reads -1 as no horse
"""


class GetMovementsRequest(BaseRequest):
    """
    Get all active troop movements.

    Command: gam
    Payload: {}

    Client: ``C2SGetAllMovementsVO`` (bundle line 129713, no fields)
    """

    command = "gam"


class MovementArea(BasePayload):
    """A movement's ``TA`` or ``SA`` area row, read as a map row.

    ``area_type``, ``x`` and ``y`` are the first three positions, which every area type has;
    ``item`` is the whole row read by the area type's own parser, None when the client reads
    no row of that type, or (with a warning) when a value is of the wrong kind. The row carries no kingdom of its own,
    so it is read in the movement's ``KID``: build one from ``{"row": [...], "kingdom": KID}``,
    or from the bare row, read in the green kingdom.

    Client: ``BasicMapmovementVO.loadFromParamObject`` reads ``SA`` and ``TA`` with
    ``WorldmapObjectFactory.parseWorldMapArea`` (bundle lines 19383, 5343), as the map reads its rows
    """

    area_type: int = Field(description="Area type")
    x: int = Field(description="Map x")
    y: int = Field(description="Map y")
    item: MapAreaItem | None = Field(
        default=None, description="The row as its area type's parser reads it; None when it cannot be read"
    )

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        kingdom: Any = None
        if isinstance(data, dict) and "row" in data:
            data, kingdom = data["row"], data.get("kingdom")
        if not isinstance(data, list) or len(data) < 3:
            return data
        try:
            values = MapAreaItem.row_values(data, enum_or_none(Kingdom, js_int(kingdom)) or Kingdom.GREEN)
        except ValueError:
            # parseWorldMapArea reads no row of this type either, and the movement falls back to a dummy area
            return {"area_type": data[0], "x": data[1], "y": data[2]}
        item = read_or_none(lambda row: MapAreaItem(**row), values, warn=logger, what="a movement's area row")
        return {"area_type": data[0], "x": data[1], "y": data[2], "item": item}

    @property
    def position(self) -> Position:
        return Position(x=self.x, y=self.y)

    @property
    def object_id(self) -> int | None:
        """The map object's id, as the area type's row gives it; None when it gives none."""
        return self.item.location_id if self.item is not None else None

    @property
    def owner_id(self) -> int | None:
        """The owner the row names; None when it names none."""
        return self.item.owner_id if self.item is not None else None

    @property
    def name(self) -> str:
        """The object's name; empty when the row has none."""
        return self.item.name or "" if self.item is not None else ""


class MovementRecord(BasePayload):
    """The movement itself: the ``M`` inside each ``gam`` wrapper.

    Client: ``MapmovementFactory.parseMapMovement`` (split.js line 667779) reads ``T`` with ``int()``;
    ``BasicMapmovementVO.loadFromParamObject`` (split.js line 87574) keeps ``MID`` as sent, reads the
    other numbers with ``int()`` and the areas with ``WorldmapObjectFactory.parseWorldMapArea``
    (split.js line 30594), which gives no area for a falsy row
    """

    movement_id: int = Field(validation_alias="MID", description="Movement id")
    movement_type: EnumOrInt[MovementType] = Field(
        validation_alias="T", default=MovementType.ATTACK, description="The movement's type"
    )
    progress_time: ClientInt = Field(
        validation_alias="PT",
        default=0,
        description="Seconds travelled when the reply was sent",
    )
    total_time: ClientInt = Field(validation_alias="TT", default=0, description="Seconds the trip takes")
    direction: ClientInt = Field(
        validation_alias="D",
        default=0,
        description="1 = returning home, 0 = heading to the target",
    )
    target_id: ClientInt = Field(validation_alias="TID", default=-1, description="Player id owning the target area")
    kingdom_id: Kingdom = Field(
        validation_alias="KID", default=Kingdom.GREEN, description="The kingdom the movement is in"
    )
    source_id: ClientInt = Field(validation_alias="SID", default=-1, description="Player id owning the source area")
    owner_id: ClientInt = Field(validation_alias="OID", default=-1, description="Player id owning the movement")
    horse_booster: EnumOrInt["Horse"] | None = Field(
        validation_alias="HBW",
        default=None,
        description="The horse booster; None for none or when paid with feathers",
    )
    target_area: MovementArea | None = Field(
        validation_alias="TA", default=None, description="Target area; None when there is none or it cannot be read"
    )
    source_area: MovementArea | None = Field(
        validation_alias="SA", default=None, description="Source area; None when there is none or it cannot be read"
    )

    @model_validator(mode="before")
    @classmethod
    def _areas_in_the_movements_kingdom(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        rows = {
            key: {"row": data[key], "kingdom": data.get("KID")}
            for key in ("TA", "SA")
            if isinstance(data.get(key), list) and data[key]
        }
        return {**data, **rows}

    @field_validator("movement_type", mode="before")
    @classmethod
    def _type(cls, value: Any) -> Any:
        return js_int(value)

    @field_validator("kingdom_id", mode="before")
    @classmethod
    def _kingdom(cls, value: Any) -> Any:
        # A kingdom Kingdom lacks reads as green, as the movement's areas do (see MovementArea)
        return enum_or_none(Kingdom, js_int(value)) or Kingdom.GREEN

    @field_validator("target_area", "source_area", mode="wrap")
    @classmethod
    def _readable_area(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        return read_or_none(handler, value) if value else None

    @field_validator("horse_booster", mode="before")
    @classmethod
    def _horse(cls, value: Any) -> Any:
        # Client: int(t.HBW), -1 for no horse (BasicMapmovementVO, bundle lines 19383, 15445)
        horse = js_int(value)
        return horse if horse > 0 else None

    @property
    def is_returning(self) -> bool:
        """Client: ``BasicMapmovementVO.isReturnHome``."""
        return self.direction == 1


class MovementArmy(BasePayload):
    """A visible army: three flanks plus the courtyard wave, each ``{Unit or Tool: amount}``.

    Client: ``CastleCompactArmyVO.parseSimpleArmy`` / ``parseYardWave`` (bundle lines 67525,
    67529) read each into a ``UnitInventoryDictionary``, which adds up an id sent twice.
    """

    left: WodAmounts = Field(validation_alias="L", default_factory=dict, description="Left flank")
    middle: WodAmounts = Field(validation_alias="M", default_factory=dict, description="Middle")
    right: WodAmounts = Field(validation_alias="R", default_factory=dict, description="Right flank")
    courtyard: WodAmounts = Field(validation_alias="RW", default_factory=dict, description="Courtyard (yard) wave")


class MovementUnitInfo(BasePayload):
    """Commander and wait details: a wrapper's ``UM``.

    Client: ``BasicMapmovementVO.parseUnitMovement`` (bundle line 19385), which hands ``L`` to
    ``LordFactory.createLord`` (bundle line 26399).
    """

    commander: Commander | None = Field(
        validation_alias="L",
        default=None,
        description="Commander leading the army; None when there is none",
    )
    wait_passed: int = Field(
        validation_alias="PWD",
        default=0,
        description="Seconds of the wait at the target already passed",
    )
    wait_total: int = Field(validation_alias="TWD", default=0, description="Seconds the army waits at its target")
    advisor_type: EnumOrInt[AttackAdvisorType] = Field(
        validation_alias="AAT",
        default=AttackAdvisorType.NONE,
        description="The attack advisor that sent the attack",
    )
    advisor_movement_count: int = Field(validation_alias="AAC", default=0, description="Attacks in the advisor series")
    advisor_movement_number: int = Field(
        validation_alias="AAN", default=0, description="This attack's place in the series"
    )
    advisor_is_last: int = Field(validation_alias="AAL", default=0, description="1 on the series' last attack")

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

    carriages: int = Field(validation_alias="C", default=0, description="Market carriages used")
    goods: CollectableRows = Field(validation_alias="G", default=(), description="Goods carried")


class MovementSpy(BasePayload):
    """A spy mission's details: a wrapper's ``S``.

    Client: ``SpyMapmovementVO.parseSpyInfo`` (bundle line 43748), which reads each through ``int()``.
    """

    spy_type: ClientInt = Field(validation_alias="ST", default=0, description="Kind of spy mission, a SpyType value")
    accuracy_or_damage: ClientInt = Field(
        validation_alias="SA",
        default=0,
        description="Accuracy percent, or damage percent for sabotage",
    )
    spy_count: ClientInt = Field(validation_alias="SC", default=0, description="Spies sent")
    risk: ClientInt = Field(validation_alias="SR", default=0, description="Risk of being caught, percent")

    @property
    def spy_type_enum(self) -> SpyType | None:
        """``spy_type`` as a :class:`SpyType`, None for a value the client does not define."""
        return enum_or_none(SpyType, self.spy_type)

    @property
    def is_sabotage(self) -> bool:
        return self.spy_type == SpyType.SABOTAGE


_WRAPPER_BLOCKS = (
    "full_army",
    "army",
    "army_size",
    "unit_info",
    "attack_type",
    "is_shadow",
    "force_cancelable",
    "support_tools",
    "auto_skip_cooldown_type",
    "travel_units",
    "travel_goods",
    "traded_units",
    "market",
    "spy",
)


class MovementWrapper(BasePayload):
    """One entry of ``gam``'s ``M`` list, and the ``A`` of an ``abr``/``asr`` push or an ``mcm`` reply.

    Which of the optional blocks are present depends on the movement type and
    on what the receiving player may see. A block that cannot be read reads as
    not sent, so it costs only itself. Keys this model does not name are kept,
    as on every payload.

    Client: ``MapmovementFactory.parseMapMovement`` (split.js line 667779) and the
    ``loadFromParamObject`` of each movement class: ``ArmyAttackMapmovementVO`` (split.js line
    77036), ``ArmyTravelMapMovementVO`` (split.js line 114881), ``TradeMapmovementVO`` (split.js
    line 310791), ``MarketMapmovementVO`` (split.js line 225968) and ``SpyMapmovementVO`` (split.js
    line 226172)
    """

    movement: MovementRecord = Field(validation_alias="M", description="The movement record")
    full_army: MovementArmy | None = Field(
        validation_alias="FA", default=None, description="The full army, preferred over army"
    )
    army: MovementArmy | None = Field(validation_alias="GA", default=None, description="Army")
    army_size: ClientInt | None = Field(
        validation_alias="GS",
        default=None,
        description="Estimated army size when the army is hidden",
    )
    unit_info: MovementUnitInfo | None = Field(
        validation_alias="UM", default=None, description="Commander and wait details"
    )
    attack_type: EnumOrInt[AttackType] | None = Field(
        validation_alias="ATT", default=None, description="The kind of attack; None for no attack"
    )
    is_shadow: bool = Field(validation_alias="SM", default=False, description="Shadow movement")
    force_cancelable: bool = Field(
        validation_alias="FC",
        default=False,
        description="The movement can be force-cancelled",
    )
    support_tools: SupportToolSlots = Field(
        validation_alias="AST",
        default=(),
        description="Support tools sent along, as the attack sent them; None for an empty slot",
    )
    auto_skip_cooldown_type: EnumOrInt[AutoSkipCooldownType] = Field(
        validation_alias="ASCT",
        default=AutoSkipCooldownType.OFF,
        description="How the target's cooldown is skipped on arrival",
    )
    travel_units: WodAmounts = Field(
        validation_alias="A",
        default_factory=dict,
        description="Units and tools of a travel movement",
    )
    travel_goods: CollectableRows = Field(
        validation_alias="G", default=(), description="Loot a travel movement carries"
    )
    traded_units: WodAmounts = Field(
        validation_alias="TRU",
        default_factory=dict,
        description="Units an Oasis Settlement trade brings back, among travel_units",
    )
    market: MovementMarket | None = Field(validation_alias="MM", default=None, description="Market transport cargo")
    spy: MovementSpy | None = Field(validation_alias="S", default=None, description="Spy mission details")

    @field_validator("spy", mode="before")
    @classmethod
    def _no_spy_details(cls, value: Any) -> Any:
        return object_or_none(value)

    @field_validator("auto_skip_cooldown_type", mode="before")
    @classmethod
    def _auto_skip(cls, value: Any) -> Any:
        # Client: t.ASCT&&(this._autoSkipCooldownType=t.ASCT), 0 otherwise (ArmyAttackMapmovementVO, bundle line 14369)
        return js_parse_int(value) or AutoSkipCooldownType.OFF

    @field_validator("attack_type", mode="before")
    @classmethod
    def _parsed_attack_type(cls, value: Any) -> Any:
        return js_parse_int(value)

    @field_validator("is_shadow", "force_cancelable", mode="before")
    @classmethod
    def _truthy_flag(cls, value: Any) -> bool:
        return js_truthy(value)

    @field_validator(*_WRAPPER_BLOCKS, mode="wrap")
    @classmethod
    def _block_on_its_own(cls, value: Any, handler: ValidatorFunctionWrapHandler, info: ValidationInfo) -> Any:
        try:
            return handler(value)
        except ValidationError:
            return cls.model_fields[str(info.field_name)].get_default(call_default_factory=True)

    @property
    def visible_army(self) -> MovementArmy | None:
        """``FA`` if sent, else ``GA``, as the client picks."""
        return self.full_army or self.army


def names_a_movement(value: Any) -> bool:
    """Whether a movement slot holds one: a wrapper whose ``M`` is an object with an ``MID``.

    Anything else names no movement and is skipped without a warning.
    """
    if isinstance(value, MovementWrapper):
        return True
    record = value.get("M") if isinstance(value, dict) else None
    return isinstance(record, MovementRecord) or (isinstance(record, dict) and record.get("MID") is not None)


class MovementOwner(BasePayload):
    """An owner record: one entry of ``O`` in ``gam``, ``abr`` and ``asr``.

    Client: ``WorldMapOwnerInfoVO.fillFromParamObject``.
    """

    player_id: int = Field(validation_alias="OID", description="Player id")
    name: str = Field(validation_alias="N", default="")
    crest: OwnerCrest | None = Field(validation_alias="E", default=None)
    level: int = Field(validation_alias="L", default=0)
    legendary_level: int = Field(validation_alias="LL", default=0, description="Legendary level")
    beginner_protection_seconds: int = Field(validation_alias="RNP", default=-1, description="-1 when not protected")
    honor: int = Field(validation_alias="H", default=0)
    might: int = Field(validation_alias="MP", default=0)
    top_x: int = Field(
        validation_alias="TOPX",
        default=-1,
        description="Top-ranking placement, -1 for none",
    )
    is_ruin: bool = Field(
        validation_alias="R",
        default=False,
        description="The owner record is flagged as a ruin",
    )
    alliance_id: int = Field(validation_alias="AID", default=-1, description="-1 for no alliance")
    alliance_rank: int = Field(validation_alias="AR", default=0)
    alliance_name: str = Field(validation_alias="AN", default="")
    is_searching_alliance: bool = Field(validation_alias="SA", default=False)
    peace_seconds: int = Field(validation_alias="RPT", default=0, description="Remaining peace time")
    castle_positions: OwnerPositions = Field(
        validation_alias="AP", default_factory=OwnerPositions, description="The player's castles"
    )
    village_positions: OwnerPositions = Field(
        validation_alias="VP", default_factory=OwnerPositions, description="The player's villages"
    )
    has_premium: bool = Field(validation_alias="PF", default=False)
    has_vip: bool = Field(validation_alias="VF", default=False)
    is_dummy: bool = Field(validation_alias="DUM", default=False, description="The owner record is a dummy")
    achievement_points: int = Field(validation_alias="AVP", default=0)
    relocation_seconds: int = Field(validation_alias="RRD", default=0, description="Seconds until a relocation ends")
    faction: OwnerFaction | None = Field(validation_alias="FN", default=None)
    title_prefix_id: EnumOrInt["Title"] | None = Field(
        validation_alias="PRE",
        default=None,
        description="The title shown before the name; None for none",
    )
    title_suffix_id: EnumOrInt["Title"] | None = Field(
        validation_alias="SUF",
        default=None,
        description="The title shown after the name; None for none",
    )
    via_refer_a_friend: bool = Field(validation_alias="IRF", default=False)

    @field_validator("title_prefix_id", "title_suffix_id", mode="before")
    @classmethod
    def _title(cls, value: Any) -> Any:
        # Client: getTitleByTitleID(e.PRE / e.SUF) looks the id up as sent and finds none for -1 (bundle line 10794)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

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


def _names_an_owner(record: Any) -> bool:
    return isinstance(record, MovementOwner) or (isinstance(record, dict) and js_truthy(record.get("OID")))


class GetMovementsResponse(BaseResponse):
    """
    Response containing active movements.

    Command: gam
    Payload: {"M": [wrapper, ...], "O": [owner record, ...]}

    Each entry is read on its own: one that names no movement (see :func:`names_a_movement`) is
    skipped, and one that cannot be read is left out and its reason kept in ``unreadable_movements``.
    An owner record without an ``OID`` is skipped, as the client skips it.

    Client: ``GAMCommand.executeCommand`` (split.js line 638976) hands ``O`` to
    ``CastleOtherPlayerData.parseOwnerInfoArray`` (split.js line 693182), whose ``parseOwnerInfo``
    (split.js line 693159) reads nothing without an ``OID``, then the reply to ``CastleArmyData.parse_GAM``
    (split.js line 667215), which hands ``M`` to ``parseMapMovementArray`` (split.js line 667169)
    """

    command = "gam"

    movements: list[MovementWrapper] = Field(
        validation_alias="M", default_factory=list, description="Movement wrappers"
    )
    owners: list[MovementOwner] = Field(
        validation_alias="O",
        default_factory=list,
        description="Owner records for every player the movements name",
    )
    unreadable_movements: tuple[str, ...] = Field(
        default=(), description="Why each movement left out of movements could not be read"
    )

    @model_validator(mode="before")
    @classmethod
    def _movements_one_by_one(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "M" not in data:
            return data
        movements: list[MovementWrapper] = []
        unreadable: list[str] = []
        for entry in list_or_empty(data["M"]):
            if not names_a_movement(entry):
                continue
            try:
                movements.append(MovementWrapper.model_validate(entry))
            except ValidationError as error:
                unreadable.append(str(error))
        return {**data, "M": movements, "unreadable_movements": tuple(unreadable)}

    @field_validator("owners", mode="before")
    @classmethod
    def _readable_owners(cls, value: Any) -> list[MovementOwner]:
        return readable_list(MovementOwner, value, keep=_names_an_owner, warn=logger, what="owner records in a gam")


class MovementRemovedResponse(BaseResponse):
    """
    The server removing a movement: it arrived, was recalled home or was cancelled.

    Command: mrm, a push.

    Client: ``MRMCommand.executeCommand`` (bundle line 126109) hands ``MID`` as sent to
    ``CastleArmyData.parse_MRM`` (bundle line 133682) and ``removeArmyMovementById`` (bundle line
    133726), whose map lookup finds only a number
    """

    command = "mrm"

    movement_id: int | None = Field(
        validation_alias="MID",
        default=None,
        description="The movement removed; None when the server sent no whole number, which names none",
    )

    @field_validator("movement_id", mode="before")
    @classmethod
    def _as_sent(cls, value: Any) -> Any:
        return js_whole_number(value)


class MovementForceCancelableResponse(BaseResponse):
    """
    A movement of yours can now be force-cancelled.

    Command: mfc, a push.

    Client: ``MFCCommand.executeCommand`` (bundle line 126094), ``CastleArmyData.parse_MFC`` (bundle
    line 133683), which looks ``MID`` up as sent and sets ``isForceCancelable`` on the movement found
    """

    command = "mfc"

    movement_id: int | None = Field(
        validation_alias="MID",
        default=None,
        description="The movement; None when the server sent no whole number, which names none",
    )

    @field_validator("movement_id", mode="before")
    @classmethod
    def _as_sent(cls, value: Any) -> Any:
        return js_whole_number(value)


class ArmyRadiusPush(BaseResponse):
    """
    An army within a radius of its target: its owner's record and the movement, read as a ``gam`` entry.

    The base of the ``abr`` and ``asr`` pushes, which read the same keys.

    Client: ``ABRCommand.executeCommand`` (split.js line 638456) and ``ASRCommand.executeCommand``
    (split.js line 638501) hand ``O`` to ``CastleOtherPlayerData.parseOwnerInfo`` (split.js line 693159),
    which reads nothing without an object carrying an ``OID``, then the push to ``CastleArmyData.parse_ABR``
    or ``parse_ASR`` (split.js lines 667221, 667218), which hand ``[A]`` to ``parseMapMovementArray``
    (split.js line 667169). For your own record the client also reads its ``AR`` as your alliance rank,
    which the library leaves to ``gal``
    """

    owner: MovementOwner | None = Field(
        validation_alias="O",
        default=None,
        description="The record of the army's owner; None without an object carrying an OID, or when it cannot be read",
    )
    movement: MovementWrapper | None = Field(
        validation_alias="A", default=None, description="The movement; None when the push names none"
    )

    @field_validator("owner", mode="wrap")
    @classmethod
    def _owner_with_id(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> MovementOwner | None:
        if not _names_an_owner(value):
            return None
        return read_or_none(handler, value, warn=logger, what="an army push's owner")

    @field_validator("movement", mode="before")
    @classmethod
    def _wrapper(cls, value: Any) -> Any:
        return value if names_a_movement(value) else None


class ArmyInBigRadiusResponse(ArmyRadiusPush):
    """
    An army has come within the big radius of its target: the movement, now with its details.

    Command: abr, a push.

    Client: ``ABRCommand.executeCommand`` (bundle line 125907), ``CastleArmyData.parse_ABR`` (bundle
    line 133688)
    """

    command = "abr"


class ArmyInSmallRadiusResponse(ArmyRadiusPush):
    """
    An army has come within the small radius of its target.

    Command: asr, a push.

    Client: ``ASRCommand.executeCommand`` (bundle line 125922), ``CastleArmyData.parse_ASR`` (bundle
    line 133687)
    """

    command = "asr"


class MovementFilterResponse(BaseResponse):
    """
    The map's movement filters: which kinds of movement the map shows.

    The client asks for the movement list (``gam``) again after each push, and so does
    ``EmpireClient``.

    Command: mvf, as a login section of ``gbd``, a push and the reply to a :class:`SetMovementFilterRequest`.

    Client: ``MVFCommand.executeCommand`` (bundle line 652365), ``CastleSettingsData.parse_MVF``
    (bundle line 695800), which tests ``CommKeys.ACTIVE_FILTERS`` (``AFS``, dll) for 0, 1 and 2
    with ``indexOf``; the options dialog pairs them with ``toggleMapPVPAttacks``,
    ``toggleMapPvPAttacksAlliance`` and ``toggleMapMarketBarrows``
    """

    command = "mvf"

    active_filters: tuple[EnumOrInt[MovementFilter], ...] = Field(
        validation_alias="AFS", default=(), description="The kinds of movement the map shows"
    )

    @field_validator("active_filters", mode="before")
    @classmethod
    def _numbers(cls, value: Any) -> Any:
        # indexOf compares strictly, so only a number switches a filter on
        if not isinstance(value, list):
            return ()
        return tuple(entry for entry in value if isinstance(entry, int) and not isinstance(entry, bool))

    def shows(self, kind: MovementFilter) -> bool:
        """Whether the map shows that kind of movement."""
        return kind in self.active_filters


class SetMovementFilterRequest(BaseRequest):
    """
    Show or hide one kind of movement on the map; the server answers with the filters as an ``mvf``.

    Command: mvf
    Payload: {"FID": filter, "ACT": 0 or 1}

    Client: ``C2SMovementFilterOptionEvent`` (bundle line 379381), which sends ``ACT`` as 1 or 0, built by
    ``OptionsDialogOptions.toggleMapMarketBarrows``, ``toggleMapPVPAttacks`` and ``toggleMapPvPAttacksAlliance``
    (bundle lines 379324-379353) with ``MovementFilterConst`` (dll)
    """

    command = "mvf"

    kind: MovementFilter = Field(validation_alias="FID", description="The kind of movement")
    show: bool = Field(validation_alias="ACT", description="Show that kind of movement, or hide it")

    @field_serializer("show")
    def _flag(self, value: bool) -> int:
        return int(value)


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
      Berimond watchtower
    - supports: your own, in either direction
    - travel between your areas: your own, heading to the target, from a
      source area that is still yours
    - spies, market transports and occupations: your own, heading to the target
    - treasure hunts and plague doctors: never

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

    movement_id: int = Field(validation_alias="MID", description="The movement to recall")

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

    movement: MovementWrapper = Field(validation_alias="A", description="The recalled movement")


class SentMovementResponse(BaseResponse):
    """
    The reply to a movement you send: the new movement, its owners and your coins and rubies after.

    Payload: {"gcu": {...}, "O": [owner record, ...], "A": wrapper}

    ``A`` is read as one ``gam`` entry and ``O`` skips a record without an ``OID``.
    The send replies that share this shape subclass it with their command.

    Client: ``CDSCommand.executeCommand`` (bundle line 125973) and its siblings hand
    ``i.gcu`` to ``CurrencyData.parseGCU``, ``i.O`` to
    ``CastleOtherPlayerData.parseOwnerInfoArray`` and ``[i.A]`` to
    ``CastleArmyData.parseMapMovementArray``
    """

    movement: MovementWrapper | None = Field(
        validation_alias="A",
        default=None,
        description="The new movement; None when the reply has none",
    )
    owners: list[MovementOwner] = Field(
        validation_alias="O",
        default_factory=list,
        description="Owner records for the movement's areas",
    )
    currencies: CurrencyBlock = Field(
        validation_alias="gcu",
        default=None,
        description="Coins and rubies after the send; None when the reply has none",
    )

    @field_validator("movement", mode="wrap")
    @classmethod
    def _movement_or_none(cls, value: object, handler: ValidatorFunctionWrapHandler) -> MovementWrapper | None:
        if not names_a_movement(value):
            return None
        return read_or_none(handler, value, warn=logger, what=f"the movement in a {cls.__name__}")

    @field_validator("owners", mode="before")
    @classmethod
    def _readable_owners(cls, value: object) -> list[MovementOwner]:
        return readable_list(
            MovementOwner,
            value,
            accept=lambda record: isinstance(record, dict),
            keep=lambda record: js_truthy(record.get("OID")),
            warn=logger,
            what=f"owner records in a {cls.__name__}",
        )

    @property
    def movement_id(self) -> int | None:
        """The new movement's id, or None when the reply has no movement."""
        return self.movement.movement.movement_id if self.movement else None


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
    "SentMovementResponse",
    "SetMovementFilterRequest",
    "names_a_movement",
]
