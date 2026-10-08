"""
Battle report protocol models.

Commands:
- bls: A battle report's short log, the overview
- blm: Its middle log: the waves per flank, the courtyard and the commanders
- bld: Its detail log: every unit per flank and wave
- mfb: Forward a battle report
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import (
    BeforeValidator,
    Field,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    field_validator,
    model_validator,
)

from empire_core.commanders.models.equipment import Equipment
from empire_core.commanders.models.roster import Castellan, Commander
from empire_core.enums import (
    AttackAdvisorType,
    AutoSkipCooldownType,
    BattleLogAttackType,
    BattleLogFlank,
    CollectableKind,
    LogResult,
    MapItemType,
    MessageType,
)
from empire_core.gamedata import Collectable, CollectableRows, CurrencyIdRows, EnumOrInt, EnumOrStr
from empire_core.gamedata.collectables import MINUTE_SKIP_FIRST_ID
from empire_core.map.models import MapObject
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    enum_or_none,
    int_entries,
    list_or_empty,
    object_or_none,
    read_or_none,
    readable_list,
)
from empire_core.protocol.js import (
    ClientInt,
    ClientNumber,
    js_int,
    js_loose_equals,
    js_number_or_none,
    js_parse_int,
    js_truthy,
)

from .mailbox import SpyReportArea

if TYPE_CHECKING:
    from empire_core.gamedata import Gem, GeneralAbility, LegendSkill

logger = logging.getLogger(__name__)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _row(names: tuple[str, ...], data: Any) -> Any:
    if isinstance(data, list):
        return {name: data[i] if i < len(data) else None for i, name in enumerate(names)}
    return data


def _js_or(value: Any, default: Any) -> Any:
    """JavaScript's ``value || default``."""
    return value if js_truthy(value) else default


def _parsed_one(value: Any) -> bool:
    return js_parse_int(value) == 1


# =============================================================================
# Requests
# =============================================================================


class GetBattleLogShortRequest(BaseRequest):
    """
    Request a battle report's short log.

    Command: bls
    Payload: {"MID": message_id, "IM": 0 or 1}

    With ``IM`` 1 the reply carries the middle and detail logs too, as ``blm``
    and ``bld``. The client itself sends ``IM`` 0.

    Client: ``C2SBattleLogShortVO`` (bundle line 135059), sent by
    ``CastleMessageData.getBattleLogShort`` (bundle line 134905)
    """

    command = "bls"

    message_id: int = Field(alias="MID", description="The battle log's MessageInfo.message_id")
    include_details: int = Field(
        alias="IM", default=0, description="1 to have the reply carry the middle and detail logs too, else 0"
    )

    @field_validator("include_details", mode="before")
    @classmethod
    def _one_or_zero(cls, value: Any) -> int:
        # Client: int(i ? 1 : 0)
        return 1 if js_truthy(value) else 0

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a reply is this message's log: its ``MID``, when sent, is ``MID``."""
        return isinstance(payload, dict) and (
            "MID" not in payload or js_number_or_none(payload["MID"]) == self.message_id
        )


class GetBattleLogMiddleRequest(BaseRequest):
    """
    Request a battle report's middle log.

    Command: blm
    Payload: {"LID": log_id}

    Client: ``C2SBattleLogMiddleVO`` (bundle line 135050), sent by
    ``CastleMessageData.getBattleLogMiddle`` (bundle line 134906)
    """

    command = "blm"

    log_id: int = Field(alias="LID", description="The battle log id: BattleLogShortResponse.log_id")

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a reply is this log's: its ``LID``, when sent, is ``LID``; the client files it under ``int(LID)``."""
        return isinstance(payload, dict) and ("LID" not in payload or js_int(payload["LID"]) == self.log_id)


class GetBattleLogDetailRequest(BaseRequest):
    """
    Request a battle report's detail log.

    Command: bld
    Payload: {"LID": log_id}

    Client: ``C2SBattleLogDetailVO`` (bundle line 135041), sent by
    ``CastleMessageData.getBattleLogDetailed`` (bundle line 134907)
    """

    command = "bld"

    log_id: int = Field(alias="LID", description="The battle log id: BattleLogShortResponse.log_id")

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a reply is this log's: its ``LID``, when sent, is ``LID``; the client files it under ``int(LID)``."""
        return isinstance(payload, dict) and ("LID" not in payload or js_int(payload["LID"]) == self.log_id)


class ForwardBattleLogRequest(BaseRequest):
    """
    Forward a battle report to other players.

    Command: mfb
    Payload: {"MID": message_id, "PID": [player_id, ...]}

    Client: ``C2SForwardBattleLogVO`` (bundle lines 128585-128586), whose
    constructor sets ``MID`` before ``PID``; sent by
    ``CastleForwardMessageDialog.sendMessage`` (bundle line 60740)
    """

    command = "mfb"

    message_id: int = Field(alias="MID", description="The battle log's MessageInfo.message_id")
    player_ids: list[int] = Field(
        alias="PID",
        description=(
            "Recipients, e.g. your alliance's other members: AllianceMember.player_id from "
            "client.alliance.get_local_members()"
        ),
    )


class ForwardBattleLogResponse(BaseResponse):
    """
    The answer to forwarding a battle report; the client reads nothing from it.

    Command: mfb

    Client: ``MFBCommand.executeCommand`` (bundle line 125396)
    """

    command = "mfb"


# =============================================================================
# Shared parts
# =============================================================================

_UNIT_ROW = ("wod_id", "amount", "lost")


class BattleLogUnit(BasePayload):
    """
    One unit or tool type in a battle log: ``[wod_id, amount, lost]``.

    Client: ``LogUnitVO.initByParams`` (bundle line 61363)
    """

    wod_id: ClientInt = Field(description="Unit or tool type id")
    amount: ClientInt = Field(description="How many took part")
    lost: ClientInt = Field(description="How many were lost; the server sends it as 0 or a negative number")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        return _row(_UNIT_ROW, data)


def _units(value: Any) -> list[BattleLogUnit]:
    return readable_list(
        BattleLogUnit, value, accept=lambda e: isinstance(e, list), warn=logger, what="battle log units"
    )


class SideUnits(BasePayload):
    """
    One side's units in a battle log: ``[player_id, [wod_id, amount, lost], ...]``.

    The client keeps the wire order of ``units`` only until it sorts them by
    the game's unit order; this model keeps the wire order.

    Client: ``BattleLogVO.parseYardDetailed`` and ``parseSupportTools`` (bundle lines 138341, 138352)
    skip the first entry and read the rest as ``LogUnitVO`` (bundle line 61363)
    """

    player_id: int | float | None = Field(default=None, description="The side's player id, as the server sends it")
    units: list[BattleLogUnit] = Field(default_factory=list, description="The side's unit or tool types")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"player_id": data[0] if data else None, "units": data[1:]}
        return data

    @field_validator("player_id", mode="before")
    @classmethod
    def _id(cls, value: Any) -> Any:
        return js_number_or_none(value) if _number(value) else None

    @field_validator("units", mode="before")
    @classmethod
    def _readable(cls, value: Any) -> Any:
        return _units(value)


class UnitsBySide(BasePayload):
    """
    The attacker's and the defender's units: ``[attacker_row, defender_row]``, each a :class:`SideUnits` row.

    Client: ``BattleLogVO.parseYardDetailed`` and ``parseSupportTools`` (bundle lines 138341, 138352)
    """

    attacker: SideUnits = Field(default_factory=SideUnits, description="The attacking side")
    defender: SideUnits = Field(default_factory=SideUnits, description="The defending side")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if data is None:
            return {}
        if isinstance(data, list):
            return {
                "attacker": data[0] if len(data) > 0 and isinstance(data[0], list) else [],
                "defender": data[1] if len(data) > 1 and isinstance(data[1], list) else [],
            }
        return data


_FLANK_TOTALS_ROW = ("soldiers", "tools_used", "soldiers_lost")


class FlankTotals(BasePayload):
    """
    One flank's totals in a middle log: ``[soldiers, tools_used, soldiers_lost]``.

    Client: ``FlankInfoVO.initByParams`` (bundle line 61395)
    """

    soldiers: ClientInt = Field(default=0, description="Soldiers that fought")
    tools_used: ClientInt = Field(default=0, description="Tools used")
    soldiers_lost: ClientInt = Field(
        default=0, description="Soldiers lost; the server sends it as 0 or a negative number"
    )

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        return _row(_FLANK_TOTALS_ROW, data)

    @property
    def soldiers_survived(self) -> int:
        """
        ``soldiers`` plus ``soldiers_lost``, as the client counts them.

        Client: ``FlankInfoVO.soldierAmountSurvived`` (bundle line 61402)
        """
        return self.soldiers + self.soldiers_lost


def _flank_totals_or_none(value: Any) -> FlankTotals | None:
    if not isinstance(value, list):
        return None
    return read_or_none(FlankTotals.model_validate, value, warn=logger, what="a battle log flank")


class MiddlePlayerWave(BasePayload):
    """
    One side of a middle log wave: ``[player_id, left, middle, right]``, each flank a :class:`FlankTotals` row.

    A pre-combat wave's sides have no player id: ``[left, middle, right]``.
    A flank the row lacks is None.

    Client: ``MediumPlayerBattleWaveVO.initByParams`` (bundle line 138761)
    """

    player_id: int | float | None = Field(default=None, description="The side's player id; None in a pre-combat wave")
    left: FlankTotals | None = Field(default=None, description="The left flank")
    middle: FlankTotals | None = Field(default=None, description="The middle flank")
    right: FlankTotals | None = Field(default=None, description="The right flank")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return data
        # Client: flanks start at 1 when the first entry is a number, else at 0
        if len(data) <= 1:
            return {}
        start = 1 if _number(data[0]) else 0
        flanks = [data[start + i] if start + i < len(data) else None for i in range(3)]
        return {
            "player_id": data[0] if start else None,
            "left": _flank_totals_or_none(flanks[0]),
            "middle": _flank_totals_or_none(flanks[1]),
            "right": _flank_totals_or_none(flanks[2]),
        }

    @property
    def soldiers_survived(self) -> int:
        """
        Soldiers that survived on all three flanks.

        Client: ``MediumPlayerBattleWaveVO.soldierAmountSurvived`` (bundle line 138774)
        """
        return sum(flank.soldiers_survived for flank in (self.left, self.middle, self.right) if flank is not None)


class MiddleWave(BasePayload):
    """
    One wave of a middle log: ``[attacker, defender]``, each a :class:`MiddlePlayerWave` row.

    Client: ``MediumBattleWaveVO.initByParams`` (bundle line 138735)
    """

    attacker: MiddlePlayerWave = Field(default_factory=MiddlePlayerWave, description="The attacking side")
    defender: MiddlePlayerWave = Field(default_factory=MiddlePlayerWave, description="The defending side")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {
                "attacker": data[0] if len(data) > 0 and isinstance(data[0], list) else [],
                "defender": data[1] if len(data) > 1 and isinstance(data[1], list) else [],
            }
        return data

    @property
    def got_through_wall(self) -> bool:
        """
        Some attacking soldiers survived the wave.

        Client: ``MediumBattleWaveVO.gotThroughWall`` (bundle line 138740)
        """
        return self.attacker.soldiers_survived > 0


class DetailFlank(BasePayload):
    """
    One flank of a detail log wave: ``[soldiers, tools, effects]``.

    ``effects`` is ``[wall_bonus, gate_bonus, moat_bonus]`` and comes only for the
    defending side; without it the three bonuses are None.

    Client: ``FlankVO.initByParams`` and ``parseEffects`` (bundle lines 138694, 138705)
    """

    soldiers: list[BattleLogUnit] = Field(default_factory=list, description="Soldier types")
    tools: list[BattleLogUnit] = Field(default_factory=list, description="Tool types")
    wall_bonus: int | None = Field(default=None, description="The wall's defence bonus, percent")
    gate_bonus: int | None = Field(default=None, description="The gate's defence bonus, percent")
    moat_bonus: int | None = Field(default=None, description="The moat's defence bonus, percent")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return {} if data is None else data
        row: dict[str, Any] = {
            "soldiers": data[0] if len(data) > 0 else [],
            "tools": data[1] if len(data) > 1 else [],
        }
        effects = data[2] if len(data) > 2 else None
        if js_truthy(effects):
            effects = effects if isinstance(effects, list) else []
            for i, name in enumerate(("wall_bonus", "gate_bonus", "moat_bonus")):
                row[name] = js_int(effects[i] if i < len(effects) else None)
        return row

    @field_validator("soldiers", "tools", mode="before")
    @classmethod
    def _readable(cls, value: Any) -> Any:
        return _units(value)


class DetailPlayerWave(BasePayload):
    """
    One side of a detail log wave: ``[player_id, left, middle, right, courtyard]``, each a :class:`DetailFlank` row.

    A flank the row lacks is empty, as the client reads it.

    Client: ``DetailedPlayerBattleWaveVO.initByParams`` (bundle line 138635)
    """

    player_id: int | float | None = Field(default=None, description="The side's player id, as the server sends it")
    left: DetailFlank = Field(default_factory=DetailFlank, description="The left flank")
    middle: DetailFlank = Field(default_factory=DetailFlank, description="The middle flank")
    right: DetailFlank = Field(default_factory=DetailFlank, description="The right flank")
    courtyard: DetailFlank = Field(default_factory=DetailFlank, description="The courtyard")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if not isinstance(data, list):
            return data
        names = ("left", "middle", "right", "courtyard")
        row: dict[str, Any] = {"player_id": data[0] if data and _number(data[0]) else None}
        if len(data) > 1:
            row.update({name: data[1 + i] if 1 + i < len(data) else None for i, name in enumerate(names)})
        return row

    @field_validator("left", "middle", "right", "courtyard", mode="wrap")
    @classmethod
    def _flank(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> DetailFlank:
        flank = read_or_none(handler, value, warn=logger, what="a battle log flank")
        return DetailFlank() if flank is None else flank


class DetailWave(BasePayload):
    """
    One wave of a detail log: ``[attacker, defender]``, each a :class:`DetailPlayerWave` row.

    Client: ``DetailedBattleWaveVO.initByParams`` (bundle line 138614)
    """

    attacker: DetailPlayerWave = Field(default_factory=DetailPlayerWave, description="The attacking side")
    defender: DetailPlayerWave = Field(default_factory=DetailPlayerWave, description="The defending side")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {
                "attacker": data[0] if len(data) > 0 and isinstance(data[0], list) else [],
                "defender": data[1] if len(data) > 1 and isinstance(data[1], list) else [],
            }
        return data


class AbilityWaveValue(BasePayload):
    """
    Where a general's ability took effect: ``[wave_id, value, flank_name]``.

    Client: ``BattleLogAbilityVO.parseFromParamOj`` (bundle line 138588); ``getValueForWave`` and
    ``isTriggerdInWave`` (bundle lines 138593-138595) match the wave and the flank name;
    ``CastleBattleLogPopUpDialog.getFlankNameBattleLog`` (bundle lines 135871-135877) names the flanks
    """

    wave_id: ClientInt = Field(default=0, description="The wave's number in the battle")
    value: ClientNumber = Field(default=0, description="The ability's value in that wave")
    flank_name: EnumOrStr[BattleLogFlank] | None = Field(
        default=None, description="The flank; None when the entry names none"
    )

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        return _row(("wave_id", "value", "flank_name"), data)

    @field_validator("flank_name", mode="before")
    @classmethod
    def _name(cls, value: Any) -> Any:
        return value if isinstance(value, str) else None


class BattleLogAbility(BasePayload):
    """
    A general's ability that took effect in the battle: ``[ability_id, [[wave_id, value, flank_name], ...]]``.

    Client: ``BattleLogAbilityVO.parseFromParamOj`` (bundle line 138584)
    """

    ability_id: EnumOrInt["GeneralAbility"] | None = Field(
        default=None, description="The ability; None when the entry names none"
    )
    wave_values: list[AbilityWaveValue] = Field(default_factory=list, description="Where it took effect")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"ability_id": data[0] if data else None, "wave_values": data[1] if len(data) > 1 else []}
        return data

    @field_validator("wave_values", mode="before")
    @classmethod
    def _readable(cls, value: Any) -> Any:
        return readable_list(AbilityWaveValue, value, accept=lambda e: isinstance(e, list))


def _abilities(value: Any) -> list[BattleLogAbility]:
    # Client: e.AA && e.AA.forEach(...)
    return readable_list(BattleLogAbility, value, accept=lambda e: isinstance(e, list), warn=logger, what="abilities")


def _commander_or_none(value: Any, handler: ValidatorFunctionWrapHandler, what: str) -> Any:
    # Client: e.AL && LordFactory.createLord(e.AL, !0)
    if not js_truthy(value) or not isinstance(value, dict):
        return None
    return read_or_none(handler, value, warn=logger, what=what)


# =============================================================================
# BLS - short log
# =============================================================================

_PARTICIPANT_ROW = (
    "player_id",
    "front",
    "start_army_size",
    "lost_units",
    "loot",
    "fame_points",
    "xp",
    "kingstower_bonus",
    "faction_points",
    "highest_fame_title_bonus",
    "wounded_units",
    "morale_boost",
    "capital_tokens",
    "reputation",
)

ATTACKER_FRONT = 0
"""``BattleParticipant.front`` of an attacking player. Client: ``BattleLogVO.hasWonState`` (bundle line 138387)"""
DEFENDER_FRONT = 1
"""``BattleParticipant.front`` of a defending player. Client: ``BattleLogVO.isDefender`` (bundle line 138388)"""


class BattleParticipant(BasePayload):
    """
    One player in a battle: a ``PBI`` row.

    The client looks each player up among the owner records (``PI``) and stops
    reading the rows at one it has no record for; this model keeps every row.
    Join ``player_id`` to the reply's ``owners`` for the player's record.

    Client: ``BattleLogVO.loadFromParamArrayPBI`` (bundle line 138313), ``BattleParticipantVO``
    (bundle line 138788); ``FactionConst.BLUE_FACTION`` 0 and ``RED_FACTION`` 1 (dll line 19333)
    """

    player_id: ClientInt = Field(default=0, description="Player id; below 0 for an NPC")
    front: ClientInt = Field(default=0, description="0 for an attacking player, 1 for a defending one")
    start_army_size: ClientInt = Field(default=0, description="Soldiers the player brought")
    lost_units: ClientInt = Field(
        default=0, description="Soldiers the player lost; the server sends it as 0 or a negative number"
    )
    loot: CollectableRows = Field(
        default=(),
        description="What the player looted (BattleLogVO.loadFromParamArrayPBI reads it with "
        "CollectableParserS2CParamList.createList, bundle line 138318)",
    )
    fame_points: ClientInt = Field(default=0, description="Glory points won or lost")
    xp: ClientInt = Field(default=0, description="Experience won")
    kingstower_bonus: ClientInt = Field(default=0, description="Bonus from the king's towers")
    faction_points: ClientInt = Field(default=0, description="Berimond faction points")
    highest_fame_title_bonus: ClientInt = Field(default=0, description="Bonus from the highest glory title")
    wounded_units: ClientInt = Field(default=0, description="Soldiers wounded instead of lost")
    morale_boost: ClientInt = Field(default=0, description="Morale boost")
    capital_tokens: ClientInt = Field(default=0, description="Capital tokens won")
    reputation_blue: ClientInt = Field(default=0, description="Reputation won with the blue faction")
    reputation_red: ClientInt = Field(default=0, description="Reputation won with the red faction")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        row = _row(_PARTICIPANT_ROW, data)
        if not isinstance(row, dict):
            return row
        row = dict(row)
        reputation = row.pop("reputation", None)
        if js_truthy(reputation):
            # Client: i[13][FactionConst.BLUE_FACTION], i[13][FactionConst.RED_FACTION]
            if isinstance(reputation, list):
                row["reputation_blue"] = reputation[0] if reputation else None
                row["reputation_red"] = reputation[1] if len(reputation) > 1 else None
            elif isinstance(reputation, dict):
                row["reputation_blue"] = reputation.get("0")
                row["reputation_red"] = reputation.get("1")
        return row

    @property
    def is_defender(self) -> bool:
        """
        The player defended.

        Client: ``BattleLogVO.isDefender`` (bundle line 138388)
        """
        return self.front == DEFENDER_FRONT


class BattleLogArea(SpyReportArea):
    """
    The area fought over, a short log's ``AI`` block.

    The reply's ``SSID``, ``DAR`` and, for an alliance battle ground tower, its
    ``AID``, ``N``, ``ACVC`` and ``E`` are read into this block, as the client
    copies them.

    Client: ``BattleLogVO.fillFromParamObject`` (bundle lines 138294-138303) and
    ``InteractiveMapobjectVO.parseAreaInfoBattleLog`` (bundle line 3638) with its
    overrides (see :class:`SpyReportArea`)
    """

    treasure_map_node_id: ClientInt = Field(
        alias="NID", default=0, description="The treasure map node fought over; 0 or less for none"
    )
    alliance_crest: dict[str, Any] | None = Field(
        alias="E", default=None, description="An alliance tower's alliance crest, as sent"
    )

    @field_validator("alliance_crest", mode="before")
    @classmethod
    def _crest(cls, value: Any) -> Any:
        return object_or_none(value)


def _charge(value: Any) -> int:
    # Client: int(Math.max(e.CPO, 0))
    number = js_number_or_none(value)
    return 0 if number is None else js_int(max(number, 0))


@dataclass(frozen=True)
class BattleLogMeta:
    """
    A short log's ``MS``: ``area_type+attack_type+result[+treasure_map_id[+treasure_map_area_type]]``.

    A battle log's mailbox header starts with the same numbers. A subtype or
    result the client defines no constant for is None.

    Client: ``BattleLogVO.addMetadataFromMessage`` (bundle line 138334) and the
    ``metaData_*`` getters (bundle lines 138461-138469)
    """

    area_type: int
    attack_type: BattleLogAttackType | None
    result: LogResult | None
    treasure_map_id: int = 0
    treasure_map_area_type: str | int = 0

    @classmethod
    def parse(cls, text: str) -> BattleLogMeta:
        """Read ``MS``; a missing number reads as 0, as the client's ``int()`` reads it."""
        parts = text.split("+")
        attack_type = js_int(parts[1] if len(parts) > 1 else None)
        result = js_int(parts[2] if len(parts) > 2 else None)
        return cls(
            area_type=js_int(parts[0]),
            attack_type=enum_or_none(BattleLogAttackType, attack_type),
            result=enum_or_none(LogResult, result),
            treasure_map_id=js_int(parts[3]) if len(parts) > 3 else 0,
            treasure_map_area_type=parts[4] if len(parts) > 4 else 0,
        )


class SupporterWounded(BasePayload):
    """
    Soldiers a supporting player had wounded: a ``WSU`` row, ``[player_id, wounded_units]``.

    Client: ``BattleLogVO.updateSupporterWoundedUnitCount`` (bundle lines 138329-138332)
    """

    player_id: ClientInt = Field(default=0, description="The supporting player")
    wounded_units: ClientInt = Field(default=0, description="Soldiers wounded instead of lost")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        return _row(("player_id", "wounded_units"), data)


class BattleLogShortResponse(BaseResponse):
    """
    A battle report's short log: who fought, who won, the loot and the area.

    Command: bls
    Payload::

        {"MID": message_id, "LID": log_id, "MT": 6, "DW": defender_won, "MS": "area+attack+result",
         "AI": {area}, "PBI": [[player_id, front, army, lost, loot, fame, xp, ...]], "PI": [{owner}],
         "AL": {commander}, "DB": {castellan}, "PS": seconds_since_battle, ...}

    With ``IM`` 1 it carries the middle and detail logs as ``blm`` and ``bld``.
    The server answers error 66 (NO_SUCH_MESSAGE) or 225 (MESSAGEDATA_TOO_OLD)
    for a log it no longer has, which the client shows as a log that does not exist.

    Client: ``BLSCommand.executeCommand`` (bundle lines 125190-125196),
    ``CastleMessageData.parseBattleLogShort`` (bundle line 134992),
    ``BattleLogVO.fillFromParamObject`` (bundle line 138294), which reads ``EQF`` and ``GF`` (bundle
    line 138304) and ``ASCT``, ``AAT``, ``AAC`` and ``AAN`` (bundle line 138312)
    """

    command = "bls"

    message_id: int | None = Field(alias="MID", default=None, description="The battle log's message id")
    log_id: ClientInt = Field(alias="LID", default=0, description="The battle log id, for the middle and detail logs")
    message_type: Annotated[EnumOrInt[MessageType], BeforeValidator(js_int)] = Field(
        alias="MT", default=0, description="The message type: BATTLE_LOG for a battle log"
    )
    defender_won: bool = Field(alias="DW", default=False, description="The defender won")
    meta: str = Field(
        alias="MS", default="", description="area_type+attack_type+result[+treasure_map_id[+map_area_type]]"
    )
    area: BattleLogArea | None = Field(alias="AI", default=None, description="The area fought over")
    participants: list[BattleParticipant] = Field(alias="PBI", default_factory=list, description="The players")
    owners: list[MapObject] = Field(alias="PI", default_factory=list, description="The players' owner records")
    honor: ClientInt = Field(alias="H", default=0, description="Honor won or lost")
    survival_rate: ClientInt = Field(alias="SR", default=0, description="Survival rate, percent")
    found_equipment: Equipment | None = Field(
        alias="EQF", default=None, description="Equipment found in the battle; None for none"
    )
    found_gem: EnumOrInt["Gem"] | None = Field(alias="GF", default=None, description="Gem found in the battle")
    found_minute_skip: Collectable | None = Field(
        alias="MSF", default=None, description="The time skip found in the battle, one of its currency; None for none"
    )
    rage_points: int = Field(alias="RP", default=-1, description="Rage points; -1 when the reply has none")
    jump_disabled: bool = Field(alias="DJ", default=False, description="The client offers no jump to the area")
    seconds_since_battle: int | float | None = Field(
        alias="PS", default=None, description="Seconds since the battle; None when the reply has none"
    )
    attacker_home_castle_id: int | None = Field(alias="AHC", default=None, description="The attacker's home castle")
    attacker_had_hospital: bool = Field(alias="AHH", default=False, description="The attacker had a hospital")
    attacker_hospital_full: bool = Field(alias="AHF", default=False, description="The attacker's hospital was full")
    defender_home_castle_id: int | None = Field(alias="DHC", default=None, description="The defender's home castle")
    defender_had_hospital: bool = Field(alias="DHH", default=False, description="The defender had a hospital")
    defender_hospital_full: bool = Field(alias="DHF", default=False, description="The defender's hospital was full")
    attacker_only_auxiliaries: bool = Field(
        alias="AUA", default=False, description="The attacker fought with auxiliaries only"
    )
    defender_only_auxiliaries: bool = Field(
        alias="DUA", default=False, description="The defender fought with auxiliaries only"
    )
    supporters_wounded: tuple[SupporterWounded, ...] = Field(
        alias="WSU", default=(), description="Soldiers each supporting player had wounded"
    )
    attacking_commander: Commander | None = Field(alias="AL", default=None, description="The attacking commander")
    defending_castellan: Castellan | None = Field(alias="DB", default=None, description="The defending castellan")
    auto_skip_costs: CurrencyIdRows = Field(
        alias="ASMS",
        default=(),
        description="The currencies the auto-skip cost (an amount above 0) or refunded (0 or below), as sent",
    )
    auto_skip_rubies: ClientInt = Field(
        alias="ASC", default=0, description="Rubies the auto-skip cost; 0 or less for none"
    )
    auto_skip_type: EnumOrInt[AutoSkipCooldownType] | None = Field(
        alias="ASCT", default=None, description="How the target's cooldown was skipped; None when the reply has none"
    )
    advisor_type: EnumOrInt[AttackAdvisorType] = Field(
        alias="AAT", default=AttackAdvisorType.NONE, description="The attack advisor that sent the attack"
    )
    advisor_movement_count: ClientInt = Field(alias="AAC", default=0, description="Movements the attack advisor sent")
    advisor_movement_number: ClientInt = Field(alias="AAN", default=0, description="This movement's number among them")
    attacker_alliance_subscribers: ClientInt = Field(
        alias="AAS", default=0, description="Subscribed members of the attacker's alliance"
    )
    attacker_had_subscription: bool = Field(alias="AHP", default=False, description="The attacker had a subscription")
    defender_alliance_subscribers: ClientInt = Field(
        alias="DAS", default=0, description="Subscribed members of the defender's alliance"
    )
    defender_had_subscription: bool = Field(alias="DHP", default=False, description="The defender had a subscription")
    old_charge_points: int = Field(alias="CPO", default=0, description="The attacker's charge points before")
    old_charge_rank: int = Field(alias="CRO", default=0, description="The attacker's charge rank before")
    new_charge_points: int = Field(alias="CPN", default=0, description="The attacker's charge points after")
    new_charge_rank: int = Field(alias="CRN", default=0, description="The attacker's charge rank after")
    defender_old_charge_points: int = Field(alias="DCPO", default=0, description="The defender's charge points before")
    defender_old_charge_rank: int = Field(alias="DCRO", default=0, description="The defender's charge rank before")
    defender_new_charge_points: int = Field(alias="DCPN", default=0, description="The defender's charge points after")
    defender_new_charge_rank: int = Field(alias="DCRN", default=0, description="The defender's charge rank after")
    includes_details: bool = Field(
        alias="IM", default=False, description="The reply carries the middle and detail logs"
    )
    middle: BattleLogMiddleResponse | None = Field(
        alias="blm", default=None, description="The middle log, when includes_details"
    )
    detail: BattleLogDetailResponse | None = Field(
        alias="bld", default=None, description="The detail log, when includes_details"
    )

    @model_validator(mode="before")
    @classmethod
    def _copies_into_the_area(cls, data: Any) -> Any:
        # Client: e.SSID&&(e.AI.SSID=e.SSID), e.DAR&&(e.AI.DAR=e.DAR), and an alliance tower's AID, N, ACVC, E
        if not isinstance(data, dict) or not isinstance(data.get("AI"), dict):
            return data
        area = dict(data["AI"])
        for key in ("SSID", "DAR"):
            if js_truthy(data.get(key)):
                area[key] = data[key]
        if js_int(area.get("AT")) == MapItemType.ALLIANCE_BATTLE_GROUND_TOWER:
            for key in ("AID", "N", "ACVC", "E"):
                area[key] = data.get(key)
        return {**data, "AI": area}

    @field_validator("defender_won", "jump_disabled", mode="before")
    @classmethod
    def _truthy(cls, value: Any) -> bool:
        return js_truthy(value)

    @field_validator("attacker_had_subscription", "defender_had_subscription", "includes_details", mode="before")
    @classmethod
    def _one(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)

    @field_validator(
        "attacker_had_hospital",
        "attacker_hospital_full",
        "defender_had_hospital",
        "defender_hospital_full",
        "attacker_only_auxiliaries",
        "defender_only_auxiliaries",
        mode="before",
    )
    @classmethod
    def _parsed_one(cls, value: Any) -> bool:
        return _parsed_one(value)

    @field_validator("attacker_home_castle_id", "defender_home_castle_id", mode="before")
    @classmethod
    def _castle_id(cls, value: Any) -> Any:
        return js_parse_int(value)

    @field_validator(
        "old_charge_points",
        "old_charge_rank",
        "new_charge_points",
        "new_charge_rank",
        "defender_old_charge_points",
        "defender_old_charge_rank",
        "defender_new_charge_points",
        "defender_new_charge_rank",
        mode="before",
    )
    @classmethod
    def _charge_points(cls, value: Any) -> int:
        return _charge(value)

    @field_validator("rage_points", mode="before")
    @classmethod
    def _rage(cls, value: Any) -> Any:
        # Client: e.RP && (this._ragePoints = parseInt(e.RP))
        if not js_truthy(value):
            return -1
        parsed = js_parse_int(value)
        return -1 if parsed is None else parsed

    @field_validator("seconds_since_battle", mode="before")
    @classmethod
    def _seconds(cls, value: Any) -> Any:
        # Client: e.PS && (timestamp = now - e.PS * 1000)
        return js_number_or_none(value) if js_truthy(value) else None

    @field_validator("meta", mode="before")
    @classmethod
    def _meta(cls, value: Any) -> Any:
        return value if isinstance(value, str) else ""

    @field_validator("auto_skip_costs", mode="before")
    @classmethod
    def _list(cls, value: Any) -> Any:
        return list_or_empty(value)

    @field_validator("supporters_wounded", mode="before")
    @classmethod
    def _supporters(cls, value: Any) -> Any:
        return tuple(
            readable_list(
                SupporterWounded, value, accept=lambda e: isinstance(e, list), warn=logger, what="wounded supporters"
            )
        )

    @field_validator("advisor_type", "advisor_movement_count", "advisor_movement_number", mode="before")
    @classmethod
    def _or_zero(cls, value: Any) -> Any:
        return _js_or(value, 0)

    @field_validator("found_equipment", mode="wrap")
    @classmethod
    def _found_equipment(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Equipment | None:
        # Client: e.EQF && CastleEquipmentFactory.createEquipmentVO(e.EQF)
        if not js_truthy(value) or not isinstance(value, list):
            return None
        return read_or_none(handler, value, warn=logger, what="the equipment found in a battle")

    @field_validator("found_gem", mode="before")
    @classmethod
    def _found_gem(cls, value: Any) -> Any:
        # Client: e.GF && gemData.getGemVO(e.GF)
        return value if js_truthy(value) else None

    @field_validator("participants", mode="before")
    @classmethod
    def _participants(cls, value: Any) -> Any:
        return readable_list(
            BattleParticipant, value, accept=lambda e: isinstance(e, list), warn=logger, what="battle log players"
        )

    @field_validator("owners", mode="before")
    @classmethod
    def _owners(cls, value: Any) -> Any:
        # Client: CastleOtherPlayerData.parseOwnerInfoArray skips a record without an OID
        return readable_list(
            MapObject,
            value,
            accept=lambda record: isinstance(record, dict),
            keep=lambda record: js_truthy(record.get("OID")),
            warn=logger,
            what="battle log owner records",
        )

    @field_validator("area", mode="wrap")
    @classmethod
    def _area(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> BattleLogArea | None:
        value = object_or_none(value)
        if value is None:
            return None
        return read_or_none(handler, value, warn=logger, what="the area of a battle log")

    @field_validator("attacking_commander", "defending_castellan", mode="wrap")
    @classmethod
    def _commander(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        return _commander_or_none(value, handler, "a commander of a battle log")

    @field_validator("middle", "detail", mode="wrap")
    @classmethod
    def _nested_log(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        # Client: parseBattleLogMiddle(i.blm) and parseBattleLogDetail(i.bld) do nothing without a block
        if not isinstance(value, dict):
            return None
        return read_or_none(handler, value, warn=logger, what="a nested battle log")

    @property
    def parsed_meta(self) -> BattleLogMeta:
        """``meta`` read as the client reads it."""
        return BattleLogMeta.parse(self.meta)

    def owner_of(self, participant: BattleParticipant) -> MapObject | None:
        """The owner record for a participant, or None when the reply has none."""
        return next((owner for owner in self.owners if owner.owner_id == participant.player_id), None)

    @property
    def attackers(self) -> list[BattleParticipant]:
        """The attacking players."""
        return [p for p in self.participants if p.front == ATTACKER_FRONT]

    @property
    def defenders(self) -> list[BattleParticipant]:
        """The defending players."""
        return [p for p in self.participants if p.front == DEFENDER_FRONT]

    @property
    def winners(self) -> list[BattleParticipant]:
        """
        The players on the winning side.

        Client: ``BattleLogVO.loadFromParamArrayPBI`` and ``hasWonState`` (bundle lines 138322, 138387)
        """
        return [p for p in self.participants if self._won(p)]

    @property
    def losers(self) -> list[BattleParticipant]:
        """The players on the losing side."""
        return [p for p in self.participants if not self._won(p)]

    def _won(self, participant: BattleParticipant) -> bool:
        return (self.defender_won and participant.front == DEFENDER_FRONT) or (
            not self.defender_won and participant.front == ATTACKER_FRONT
        )

    @field_validator("found_minute_skip", mode="before")
    @classmethod
    def _minute_skip(cls, value: Any) -> Any:
        """
        A number below the minute skips' range counts from its start; one skip either way.

        Client: ``BattleLogVO.fillFromParamObject`` (bundle lines 138304-138305)
        """
        if isinstance(value, Collectable) or not js_truthy(value):
            return value or None
        number = js_number_or_none(value)
        if number is None:
            return None
        return Collectable.of_currency(
            js_int(number + MINUTE_SKIP_FIRST_ID if number < MINUTE_SKIP_FIRST_ID else number)
        )

    @property
    def auto_skip_paid(self) -> tuple[Collectable, ...]:
        """
        What the auto-skip cost: the currencies with an amount above 0, then ``auto_skip_rubies`` when above 0.

        Client: ``BattleLogVO.fillFromParamObject`` (bundle lines 138308-138311), ``_autoSkipCosts[0]``
        """
        paid = tuple(cost for cost in self.auto_skip_costs if cost.amount > 0)
        if self.auto_skip_rubies > 0:
            paid += (Collectable(kind=CollectableKind.RUBIES, key="C2", amount=self.auto_skip_rubies),)
        return paid

    @property
    def auto_skip_refunded(self) -> tuple[Collectable, ...]:
        """
        What the auto-skip refunded: the currencies with an amount of 0 or below, as a positive amount.

        Client: ``BattleLogVO.fillFromParamObject`` (bundle lines 138308-138309), ``_autoSkipCosts[1]``
        """
        return tuple(
            cost.model_copy(update={"amount": abs(cost.amount)}) for cost in self.auto_skip_costs if cost.amount <= 0
        )

    def supporter_wounded_units(self, player_id: int) -> int:
        """
        Soldiers a supporting player had wounded, or -1 when the reply lists none for them.

        Client: ``BattleLogVO.updateSupporterWoundedUnitCount`` (bundle line 138329)
        """
        return next((row.wounded_units for row in self.supporters_wounded if row.player_id == player_id), -1)


# =============================================================================
# BLM - middle log
# =============================================================================


class MiddleCourtyard(BasePayload):
    """
    The courtyard in a middle log: ``[[player_id, troops, lost], [player_id, troops, lost]]``.

    Client: ``BattleLogVO.parseYard`` (bundle line 138375)
    """

    attacker_troops: int = Field(default=0, description="Attacking soldiers that reached the courtyard")
    attacker_lost: int = Field(default=0, description="Of those, lost; the server sends it as 0 or a negative number")
    defender_troops: int = Field(default=0, description="Defending soldiers in the courtyard")
    defender_lost: int = Field(default=0, description="Of those, lost; the server sends it as 0 or a negative number")
    has_defender_info: bool = Field(default=False, description="The log has the defender's numbers")

    @model_validator(mode="before")
    @classmethod
    def _from_rows(cls, data: Any) -> Any:
        if data is None:
            return {}
        if not isinstance(data, list):
            return data
        row: dict[str, Any] = {}
        if not data:
            return row
        attacker = data[0] if isinstance(data[0], list) else []
        row["attacker_troops"] = js_int(attacker[1] if len(attacker) > 1 else None)
        row["attacker_lost"] = js_int(attacker[2] if len(attacker) > 2 else None)
        defender = data[1] if len(data) > 1 else None
        if isinstance(defender, list) and len(defender) > 2:
            row["defender_troops"] = js_int(defender[1])
            row["defender_lost"] = js_int(defender[2])
            row["has_defender_info"] = True
        return row


def _middle_waves(value: Any) -> list[MiddleWave]:
    return readable_list(MiddleWave, value, accept=lambda e: isinstance(e, list), warn=logger, what="battle log waves")


def _detail_waves(value: Any) -> list[DetailWave]:
    return readable_list(DetailWave, value, accept=lambda e: isinstance(e, list), warn=logger, what="battle log waves")


class BattleLogMiddleResponse(BaseResponse):
    """
    A battle report's middle log: the waves per flank, the courtyard, the support tools and the commanders.

    Command: blm
    Payload::

        {"LID": log_id, "Y": [[player_id, troops, lost], ...], "W": [[attacker, defender], ...],
         "PW": [attacker, defender], "SD": [[player_id, [wod_id, amount, lost], ...], ...],
         "RW": [soldiers, tools_used, soldiers_lost], "AL": {commander}, "DB": {castellan},
         "PS": seconds_since_battle, "AA": [abilities], "DA": [abilities], "DUST": used, ...}

    ``W`` sides start with the player id, ``PW`` sides do not. The reply's
    ``S`` and ``EW`` are not read by the client.

    Client: ``BLMCommand.executeCommand`` (bundle line 125173),
    ``CastleMessageData.parseBattleLogMiddle`` (bundle line 135002),
    ``BattleLogVO.parseMiddle`` (bundle line 138369)
    """

    command = "blm"

    log_id: ClientInt = Field(alias="LID", default=0, description="The battle log id")
    courtyard: MiddleCourtyard = Field(alias="Y", default_factory=MiddleCourtyard, description="The courtyard")
    waves: list[MiddleWave] = Field(alias="W", default_factory=list, description="The waves, in order")
    pre_combat_wave: MiddleWave | None = Field(
        alias="PW", default=None, description="What each side brought before the waves; None when not sent"
    )
    support_tools: UnitsBySide = Field(
        alias="SD", default_factory=UnitsBySide, description="Support tools each side used"
    )
    reinforcements: FlankTotals = Field(
        alias="RW", default_factory=FlankTotals, description="The reinforcement wave's totals"
    )
    attacking_commander: Commander | None = Field(alias="AL", default=None, description="The attacking commander")
    defending_castellan: Castellan | None = Field(alias="DB", default=None, description="The defending castellan")
    jump_disabled: bool = Field(alias="DJ", default=False, description="The client offers no jump to the area")
    seconds_since_battle: int | float | None = Field(
        alias="PS", default=None, description="Seconds since the battle; None when the reply has none"
    )
    attacker_triggered_gems: tuple[EnumOrInt["Gem"], ...] = Field(
        alias="AGT", default=(), description="The attacker's gems that triggered"
    )
    defender_triggered_gems: tuple[EnumOrInt["Gem"], ...] = Field(
        alias="DGT", default=(), description="The defender's gems that triggered"
    )
    attacker_legend_skill_ids: tuple[EnumOrInt["LegendSkill"], ...] = Field(
        alias="ALS", default=(), description="The attacker's legend skills"
    )
    defender_legend_skill_ids: tuple[EnumOrInt["LegendSkill"], ...] = Field(
        alias="DLS", default=(), description="The defender's legend skills"
    )
    defender_used_support_tools: bool = Field(
        alias="DUST", default=False, description="The defender used support tools"
    )
    attacker_abilities: list[BattleLogAbility] = Field(
        alias="AA", default_factory=list, description="The attacking general's abilities that took effect"
    )
    defender_abilities: list[BattleLogAbility] = Field(
        alias="DA", default_factory=list, description="The defending general's abilities that took effect"
    )

    @field_validator("waves", mode="before")
    @classmethod
    def _waves(cls, value: Any) -> Any:
        return _middle_waves(value)

    @field_validator("pre_combat_wave", mode="wrap")
    @classmethod
    def _pre_combat(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        if not js_truthy(value) or not isinstance(value, list):
            return None
        return read_or_none(handler, value, warn=logger, what="a battle log wave")

    @field_validator("reinforcements", mode="before")
    @classmethod
    def _reinforcements(cls, value: Any) -> Any:
        # Client: e.RW || [0, 0, 0]
        return value if isinstance(value, list) and js_truthy(value) else [0, 0, 0]

    @field_validator("courtyard", "support_tools", mode="wrap")
    @classmethod
    def _block(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        block = read_or_none(handler, value, warn=logger, what="a battle log block")
        return handler(None) if block is None else block

    @field_validator("attacking_commander", "defending_castellan", mode="wrap")
    @classmethod
    def _commander(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        return _commander_or_none(value, handler, "a commander of a battle log")

    @field_validator("jump_disabled", "defender_used_support_tools", mode="before")
    @classmethod
    def _truthy(cls, value: Any) -> bool:
        return js_truthy(value)

    @field_validator("seconds_since_battle", mode="before")
    @classmethod
    def _seconds(cls, value: Any) -> Any:
        return js_number_or_none(value) if js_truthy(value) else None

    @field_validator(
        "attacker_triggered_gems", "defender_triggered_gems", "attacker_legend_skill_ids", "defender_legend_skill_ids",
        mode="before",
    )  # fmt: skip
    @classmethod
    def _ids(cls, value: Any, info: ValidationInfo) -> Any:
        # Client: e.DGT && (this._defenderTriggeredGems = e.DGT), the same for AGT, DLS and ALS (bundle line
        # 138372); each id is looked up as sent (bundle lines 135787, 26254)
        return int_entries(value, warn=logger, what=f"{info.field_name} of a battle log")

    @field_validator("attacker_abilities", "defender_abilities", mode="before")
    @classmethod
    def _abilities(cls, value: Any) -> Any:
        return _abilities(value)


# =============================================================================
# BLD - detail log
# =============================================================================


class BattleLogDetailResponse(BaseResponse):
    """
    A battle report's detail log: every unit and tool type per flank and wave.

    Command: bld
    Payload::

        {"LID": log_id, "Y": [[player_id, [wod_id, amount, lost], ...], ...],
         "W": [[attacker, defender], ...], "PW": [attacker, defender], "EW": [attacker, defender],
         "RW": [[wod_id, amount, lost], ...]}

    Each side of a wave is ``[player_id, left, middle, right, courtyard]`` and
    each flank ``[soldiers, tools, effects]``. The client sorts the unit lists
    by the game's unit order; these models keep the wire order.

    Client: ``BLDCommand.executeCommand`` (bundle line 125156),
    ``CastleMessageData.parseBattleLogDetail`` (bundle line 135005),
    ``BattleLogVO.parseDetails`` (bundle line 138335)
    """

    command = "bld"

    log_id: ClientInt = Field(alias="LID", default=0, description="The battle log id")
    courtyard: UnitsBySide = Field(alias="Y", default_factory=UnitsBySide, description="Each side's courtyard units")
    waves: list[DetailWave] = Field(alias="W", default_factory=list, description="The waves, in order")
    pre_combat_wave: DetailWave | None = Field(
        alias="PW", default=None, description="What each side brought before the waves; None when not sent"
    )
    post_combat_wave: DetailWave | None = Field(
        alias="EW", default=None, description="What fought after the waves; None when not sent"
    )
    reinforcements: list[BattleLogUnit] = Field(alias="RW", default_factory=list, description="Reinforcement units")

    @field_validator("waves", mode="before")
    @classmethod
    def _waves(cls, value: Any) -> Any:
        return _detail_waves(value)

    @field_validator("pre_combat_wave", "post_combat_wave", mode="wrap")
    @classmethod
    def _extra_wave(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        if not js_truthy(value) or not isinstance(value, list):
            return None
        return read_or_none(handler, value, warn=logger, what="a battle log wave")

    @field_validator("courtyard", mode="wrap")
    @classmethod
    def _block(cls, value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
        block = read_or_none(handler, value, warn=logger, what="a battle log block")
        return handler(None) if block is None else block

    @field_validator("reinforcements", mode="before")
    @classmethod
    def _reinforcements(cls, value: Any) -> Any:
        return _units(value)


BattleLogShortResponse.model_rebuild()


@dataclass(frozen=True)
class BattleReport:
    """
    A battle report as :meth:`MessagesService.get_battle_report` reads it: the short log, and the others asked for.
    """

    short: BattleLogShortResponse
    middle: BattleLogMiddleResponse | None = None
    detail: BattleLogDetailResponse | None = None


__all__ = [
    "ATTACKER_FRONT",
    "DEFENDER_FRONT",
    "AbilityWaveValue",
    "BattleLogAbility",
    "BattleLogArea",
    "BattleLogDetailResponse",
    "BattleLogMeta",
    "BattleLogMiddleResponse",
    "BattleLogShortResponse",
    "BattleLogUnit",
    "BattleParticipant",
    "BattleReport",
    "DetailFlank",
    "DetailPlayerWave",
    "DetailWave",
    "FlankTotals",
    "ForwardBattleLogRequest",
    "ForwardBattleLogResponse",
    "GetBattleLogDetailRequest",
    "GetBattleLogMiddleRequest",
    "GetBattleLogShortRequest",
    "MiddleCourtyard",
    "MiddlePlayerWave",
    "MiddleWave",
    "SideUnits",
    "UnitsBySide",
]
