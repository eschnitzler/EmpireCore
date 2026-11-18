"""Beyond the Horizon: alliance towers, centers of power, influence, performance and the Jade Desert.

Commands:
- tbi: An alliance tower's buffs
- aatb: Activate an alliance tower's buffs
- iatb: Raise an alliance tower's buff levels
- tie: An alliance's towers
- tpi: The castles linked to an alliance tower
- cpe: Your alliance's centers of power, counted against their limits
- cpd: Your alliance's centers of power, one by one
- gabgap: An alliance's Beyond the Horizon influence
- gabgpp: A player's Beyond the Horizon influence
- gae: Your alliance members' Beyond the Horizon performance
- ajp: Your alliance as Beyond the Horizon will see it, before you join
- bgc: The conditions for entering Beyond the Horizon you do not meet yet
- abgi: The Jade Desert's scoring phase (push)
- jci: Your alliance's Citadel and the enemy citadels in the Jade Desert
- ujc: Upgrade your alliance's Citadel
- cjs: Convert Ancient Jade Statuettes into Restored Jade Statuettes
- jtci: An Oasis Settlement's state
- jtr: Send troops and trading materials to an Oasis Settlement
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BeforeValidator, ConfigDict, Field, PlainSerializer, field_validator

from empire_core.commanders.models.roster import CommanderEffects
from empire_core.enums import (
    AllianceRank,
    HorizonEntryConditionType,
    JadeScoringPhase,
    Kingdom,
    PerformanceStatistic,
)
from empire_core.gamedata import OasisSettlementId, OasisTradeId, WodAmountSlots
from empire_core.gamedata.ids.events import Event
from empire_core.gamedata.lenient import EnumOrInt, EnumOrStr
from empire_core.map.models.areas import MapObject
from empire_core.map.models.items import MapAreaItem, parse_area_rows
from empire_core.map.models.owners import OwnerCrest
from empire_core.movements.models.movement import NO_HORSE, HorseBoosterId, SentMovementResponse
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, EmpireModel, readable_list
from empire_core.protocol.js import ClientInt, js_int, js_truthy, movement_targets

if TYPE_CHECKING:
    from empire_core.gamedata.ids import AllianceTowerEffect, Building, Effect

logger = logging.getLogger(__name__)


def _trade_amounts(value: Any) -> Any:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, list | tuple):
        return {row[0]: row[1] for row in value if isinstance(row, list | tuple) and len(row) == 2}
    return value


OasisTradeAmounts = Annotated[
    dict[OasisTradeId, int],
    BeforeValidator(_trade_amounts),
    PlainSerializer(lambda trades: [[trade_id, amount] for trade_id, amount in trades.items()]),
]
"""How often to make each Oasis Settlement trade, ``[[trade_id, amount], ...]`` on the wire.

Client: ``TradingCampTradeSelectionVO.getTradesParam`` (split.js line 565226)"""


def _area_rows(value: Any, what: str) -> list[MapAreaItem]:
    items, skipped = parse_area_rows(value)
    if skipped:
        logger.warning(f"Skipped {skipped}/{len(value)} unreadable {what}")
    return items


class AllianceTowerBuff(BasePayload):
    """
    One buff an alliance tower has bought, and its level.

    The client matches ``tower_effect_id`` against the event's available tower effects and resets
    those the server does not list to level 0.

    Client: ``CastleAllianceBattleGroundData.parseTBI`` (bundle line 144924) keys the rows by ``TEID``;
    ``ABGAllianceTowerEffectVO.parseServerParams`` (bundle line 144981) reads ``L`` through ``int()``
    """

    tower_effect_id: EnumOrInt["AllianceTowerEffect"] = Field(
        validation_alias="TEID", description="The alliance tower effect, a GameData.alliance_tower_effects row"
    )
    level: ClientInt = Field(validation_alias="L", default=0, description="The buff's current level")


class AllianceTowerBuffs(BasePayload):
    """
    An alliance tower's bought buffs, and whether they are active.

    The client keeps no copy: it builds the tower's buff list from each reply and shows it.

    Client: ``CastleAllianceBattleGroundData.parseTBI`` (bundle line 144924),
    ``ABGAllianceTowerBuffInfoVO`` (bundle line 144947)
    """

    buffs: list[AllianceTowerBuff] = Field(
        validation_alias="TE", default_factory=list, description="The buffs the tower has, with their levels"
    )
    is_active: bool = Field(validation_alias="TEA", default=False, description="The tower's buffs are active")

    @field_validator("buffs", mode="before")
    @classmethod
    def _buff_rows(cls, value: Any) -> list[AllianceTowerBuff]:
        return readable_list(
            AllianceTowerBuff,
            value,
            accept=lambda row: isinstance(row, dict),
            warn=logger,
            what="alliance tower buffs",
        )

    @field_validator("is_active", mode="before")
    @classmethod
    def _active(cls, value: Any) -> bool:
        return js_truthy(value)


class GetAllianceTowerBuffsRequest(BaseRequest):
    """
    Ask for an alliance tower's buffs.

    Sent only on the Beyond the Horizon server, in tower scoring.

    Command: tbi
    Payload: {"XPOS": x, "YPOS": y, "AID": alliance_id}

    Client: ``C2SGetAllianceTowerBuffInfoVO`` (bundle line 32770), sent with the tower's position and
    owning alliance by ``CastleABGTowerEffectsDialog.showLoaded`` (bundle line 71024) and by
    ``CastleDefenceDialog`` for a tower's defence (bundle line 15979)
    """

    command = "tbi"

    x: int = Field(validation_alias="XPOS", description="The tower's map x")
    y: int = Field(validation_alias="YPOS", description="The tower's map y")
    alliance_id: int = Field(validation_alias="AID", description="The alliance holding the tower")


class GetAllianceTowerBuffsResponse(BaseResponse, AllianceTowerBuffs):
    """
    An alliance tower's buffs.

    Command: tbi
    Payload: {"TE": [{"TEID": tower_effect_id, "L": level}, ...], "TEA": is_active}

    Client: ``TBICommand.executeCommand`` (bundle line 127335) hands the reply to
    ``CastleAllianceBattleGroundData.parseTBI`` (bundle line 144924)
    """

    command = "tbi"


class ActivateAllianceTowerBuffsRequest(BaseRequest):
    """
    Activate an alliance tower's buffs, for rubies.

    Sent only on the Beyond the Horizon server, in tower scoring. The price falls as the tower's
    revival nears; the client looks it up in the event's activation table and sends only when you hold
    at least that many rubies.

    Command: aatb
    Payload: {"XPOS": x, "YPOS": y}

    Client: ``C2SActivateAllianceTowerBuffVO`` (bundle line 71011), sent by
    ``CastleABGTowerEffectsActivateDialog.onClick`` (bundle line 70999), priced by
    ``CastleAllianceBattleGroundData.getAllianceTowerEffectActivationCost`` (bundle line 144942)
    """

    command = "aatb"

    x: int = Field(validation_alias="XPOS", description="The tower's map x")
    y: int = Field(validation_alias="YPOS", description="The tower's map y")


class ActivateAllianceTowerBuffsResponse(BaseResponse):
    """
    The tower's buffs after activating them.

    Command: aatb
    Payload: {"tbi": {"TE": [...], "TEA": is_active}}

    Client: ``AATBCommand.executeCommand`` (bundle line 127157) hands ``tbi`` to
    ``CastleAllianceBattleGroundData.parseTBI`` (bundle line 144924)
    """

    command = "aatb"

    tower_buffs: AllianceTowerBuffs = Field(
        validation_alias="tbi", default_factory=AllianceTowerBuffs, description="The tower's buffs now"
    )


class AllianceTowerBuffIncrease(BasePayload):
    """
    One buff to raise on an alliance tower, from its current level to a higher one.

    Client: ``ABGAllianceTowerBuffInfoVO.createServerEffectsArray`` (bundle line 144958) sends one row per
    buff whose selected level is above its current one, ``E`` being the buff's effect
    """

    effect_id: EnumOrInt["Effect"] = Field(validation_alias="E", description="The buff's effect")
    level_before: int = Field(validation_alias="ELBI", description="The buff's current level")
    level_after: int = Field(validation_alias="ELAI", description="The level to raise it to")


class IncreaseAllianceTowerBuffsRequest(BaseRequest):
    """
    Raise an alliance tower's buff levels, for rubies.

    Sent only on the Beyond the Horizon server, in tower scoring. Each level's price comes from
    the event's tower effect table; the client sends only when you hold more rubies than the total.

    Command: iatb
    Payload: {"XPOS": x, "YPOS": y, "TE": [{"E": effect_id, "ELBI": level_before, "ELAI": level_after}, ...]}

    Client: ``C2SIncreaseAllianceTowerBuffVO`` (bundle line 71061), sent by
    ``CastleABGTowerEffectsDialog.onClick`` (bundle line 71048) when at least one buff is raised
    """

    command = "iatb"

    x: int = Field(validation_alias="XPOS", description="The tower's map x")
    y: int = Field(validation_alias="YPOS", description="The tower's map y")
    increases: list[AllianceTowerBuffIncrease] = Field(validation_alias="TE", description="The buffs to raise")


class IncreaseAllianceTowerBuffsResponse(BaseResponse):
    """
    The tower's buffs after raising them.

    Command: iatb
    Payload: {"tbi": {"TE": [...], "TEA": is_active}}

    Client: ``IATBCommand.executeCommand`` (bundle line 127306) hands ``tbi`` to
    ``CastleAllianceBattleGroundData.parseTBI`` (bundle line 144924)
    """

    command = "iatb"

    tower_buffs: AllianceTowerBuffs = Field(
        validation_alias="tbi", default_factory=AllianceTowerBuffs, description="The tower's buffs now"
    )


class GetAllianceTowersRequest(BaseRequest):
    """
    Ask for an alliance's towers.

    Sent only on the Beyond the Horizon server, in tower scoring.

    Command: tie
    Payload: {"AID": alliance_id}

    Client: ``C2SAllianceBattleGroundGetTowerInfoVO`` (bundle line 42876), sent by
    ``CastleAllianceInfoDialogABGTower.show`` (bundle line 66587) for the alliance shown, a tab
    ``CastleAllianceInfoDialog.showLoaded`` shows only when ``ABGHelper.isOnABGAndTower`` (bundle
    line 5561), and for your own alliance by ``CastleAllianceBattlegroundEventDialogPerformanceTower.show``
    (bundle line 71773)
    """

    command = "tie"

    alliance_id: int = Field(validation_alias="AID", description="The alliance whose towers to list")


class GetAllianceTowersResponse(BaseResponse):
    """
    An alliance's towers, as map rows.

    Command: tie
    Payload: {"T": [map row, ...]}

    Client: ``TIECommand.executeCommand`` (bundle line 127365) reads each ``T`` row with
    ``WorldmapObjectFactory.parseWorldMapArea``
    """

    command = "tie"

    towers: list[MapAreaItem] = Field(validation_alias="T", default_factory=list, description="The towers' map rows")

    @field_validator("towers", mode="before")
    @classmethod
    def _tower_rows(cls, value: Any) -> list[MapAreaItem]:
        return _area_rows(value, "alliance tower rows")


class GetAllianceTowerCastlesRequest(BaseRequest):
    """
    Ask for the castles linked to an alliance tower.

    Sent only on the Beyond the Horizon server, in tower scoring.

    Command: tpi
    Payload: {"XPOS": x, "YPOS": y}

    Client: ``C2SAllianceBattleGroundGetTowerCastlesInfoVO`` (bundle line 42941), sent by the tower
    detail dialogs ``CastleABGTowerDetailAllianceDialog.showLoaded`` (bundle line 42887) and
    ``CastleABGTowerDetailDialog.showLoaded`` (bundle line 46066)
    """

    command = "tpi"

    x: int = Field(validation_alias="XPOS", description="The tower's map x")
    y: int = Field(validation_alias="YPOS", description="The tower's map y")


class GetAllianceTowerCastlesResponse(BaseResponse):
    """
    The castles linked to an alliance tower, with their owners.

    Command: tpi
    Payload: {"O": [owner record, ...], "C": [map row, ...]}

    Client: ``TPICommand.executeCommand`` (bundle line 127399) passes each ``O`` record to
    ``CastleOtherPlayerData.parseOwnerInfo`` and reads each ``C`` row with
    ``WorldmapObjectFactory.parseWorldMapArea``
    """

    command = "tpi"

    owners: list[MapObject] = Field(
        validation_alias="O", default_factory=list, description="Owner records of the castles' players"
    )
    castles: list[MapAreaItem] = Field(
        validation_alias="C", default_factory=list, description="The linked castles' map rows"
    )

    @field_validator("owners", mode="before")
    @classmethod
    def _owner_records(cls, value: Any) -> list[MapObject]:
        return readable_list(
            MapObject,
            value,
            accept=lambda record: isinstance(record, dict),
            warn=logger,
            what="owner records of an alliance tower's castles",
        )

    @field_validator("castles", mode="before")
    @classmethod
    def _castle_rows(cls, value: Any) -> list[MapAreaItem]:
        return _area_rows(value, "alliance tower castle rows")


class GetCentersOfPowerRequest(BaseRequest):
    """
    Ask how many centers of power your alliance holds, against their limits.

    Sent only on the Beyond the Horizon server, in alliance collector scoring.

    Command: cpe
    Payload: {"AID": alliance_id}

    Client: ``C2SAllianceBattleGroundGetCentersOfPowerVO`` (bundle line 69056), sent with your
    alliance's id by ``CastleAllianceDialogABG.show`` (bundle line 69043), the alliance tab
    ``CastleAllianceDialog.showLoaded`` shows only when ``ABGHelper.isOnABGAndCollector`` (bundle line 4884)
    """

    command = "cpe"

    alliance_id: int = Field(validation_alias="AID", description="Your alliance's id")


class CentersOfPowerResponse(BaseResponse):
    """
    How many capitals, metropolises and towers your alliance holds, and how many it and each member may.

    Your alliance may hold one capital.

    Command: cpe
    Payload: {"CPA": .., "CPL": .., "CSA": .., "CSPL": .., "CSAL": .., "TWM": .., "TPL": .., "TAL": ..}

    Client: ``CPECommand.executeCommand`` (bundle line 127217); ``CastleAllianceDialogABG.onCPEArrived``
    (bundle line 69044) shows them, the capital as owned of 1
    """

    command = "cpe"

    capitals: ClientInt = Field(validation_alias="CPA", default=0, description="Capitals your alliance holds")
    capital_player_limit: ClientInt = Field(validation_alias="CPL", default=0, description="Capitals a member may hold")
    metropolises: ClientInt = Field(validation_alias="CSA", default=0, description="Metropolises your alliance holds")
    metropolis_player_limit: ClientInt = Field(
        validation_alias="CSPL", default=0, description="Metropolises a member may hold"
    )
    metropolis_alliance_limit: ClientInt = Field(
        validation_alias="CSAL", default=0, description="Metropolises your alliance may hold"
    )
    towers: ClientInt = Field(validation_alias="TWM", default=0, description="Royal towers your alliance holds")
    tower_player_limit: ClientInt = Field(
        validation_alias="TPL", default=0, description="Royal towers a member may hold"
    )
    tower_alliance_limit: ClientInt = Field(
        validation_alias="TAL", default=0, description="Royal towers your alliance may hold"
    )


class GetCentersOfPowerDetailRequest(BaseRequest):
    """
    Ask for your alliance's centers of power one by one.

    Sent only on the Beyond the Horizon server, in alliance collector scoring.

    Command: cpd
    Payload: {"AID": alliance_id}

    Client: ``C2SAllianceBattleGroundGetCentersOfPowerDetailVO`` (bundle line 69090), sent with your
    alliance's id by ``CastleAllianceCentersOfPowerDialog.showLoaded`` (bundle line 69069), opened from
    Beyond the Horizon tab
    """

    command = "cpd"

    alliance_id: int = Field(validation_alias="AID", description="Your alliance's id")


class CenterOfPower(BasePayload):
    """
    One center of power your alliance holds: its map row, its holder and what it yields.

    The client shows the largest of the three numbers: a metropolis's time left, a capital's
    influence, a royal tower's percent bonus.

    Client: ``CastleAllianceCentersOfPowerDialog.onCPDArrived`` (bundle line 69070) reads ``AI`` with
    ``WorldmapObjectFactory.parseWorldMapArea`` and ``max(int(AMT), int(AOT), int(PB))``;
    ``CastleAllianceCentersOfPowerDialogItem.fill`` (bundle line 69102)
    """

    area: MapAreaItem | None = Field(
        validation_alias="AI", default=None, description="Its map row; None when unreadable"
    )
    player_name: str | None = Field(validation_alias="PN", default=None, description="The member holding it")
    amount: ClientInt = Field(validation_alias="AMT", default=0, description="A capital's influence")
    seconds_left: ClientInt = Field(validation_alias="AOT", default=0, description="A metropolis's time left")
    percent_boost: ClientInt = Field(validation_alias="PB", default=0, description="A royal tower's percent bonus")

    @field_validator("area", mode="before")
    @classmethod
    def _area_row(cls, value: Any) -> MapAreaItem | None:
        if not isinstance(value, list):
            return None
        rows = _area_rows([value], "center of power rows")
        return rows[0] if rows else None


class CentersOfPowerDetailResponse(BaseResponse):
    """
    Your alliance's centers of power one by one.

    Command: cpd
    Payload: {"AAI": [{"AI": map row, "PN": player_name, "AMT": .., "AOT": .., "PB": ..}, ...]}

    Client: ``CPDCommand.executeCommand`` (bundle line 127202),
    ``CastleAllianceCentersOfPowerDialog.onCPDArrived`` (bundle line 69070)
    """

    command = "cpd"

    centers: list[CenterOfPower] = Field(
        validation_alias="AAI", default_factory=list, description="Each center of power"
    )

    @field_validator("centers", mode="before")
    @classmethod
    def _center_rows(cls, value: Any) -> list[CenterOfPower]:
        return readable_list(
            CenterOfPower, value, accept=lambda row: isinstance(row, dict), warn=logger, what="centers of power"
        )


class GetAllianceInfluenceRequest(BaseRequest):
    """
    Ask for an alliance's Beyond the Horizon influence.

    Sent only on the Beyond the Horizon server, in alliance collector scoring.

    Command: gabgap
    Payload: {"AID": alliance_id}

    Client: ``C2SAllianceBattleGroundGetAllianceInfluenceVO`` (bundle line 134017), sent by
    ``CastleCollectorEventData.getABGAllianceCollectorAmount`` (bundle line 134003) for the alliance
    holding a capital you are about to attack (``CastleStartAttackDialog``, bundle lines 14708, 14712)
    """

    command = "gabgap"

    alliance_id: int = Field(validation_alias="AID", description="The alliance to ask about")


class AllianceInfluenceResponse(BaseResponse):
    """
    An alliance's Beyond the Horizon influence.

    Command: gabgap
    Payload: {"AID": alliance_id, "AMT": influence}

    Client: ``GABGAPCommand.executeCommand`` (bundle line 127232),
    ``CastleCollectorEventData.parse_GAIP`` (bundle line 134008)
    """

    command = "gabgap"

    alliance_id: ClientInt = Field(validation_alias="AID", default=0, description="The alliance")
    influence: ClientInt = Field(validation_alias="AMT", default=0, description="Its influence")


class GetPlayerInfluenceRequest(BaseRequest):
    """
    Ask for a player's Beyond the Horizon influence.

    Sent only on the Beyond the Horizon server, in alliance collector scoring.

    Command: gabgpp
    Payload: {"PID": player_id}

    Client: ``C2SAllianceBattleGroundGetPlayerInfluenceVO`` (bundle line 134026), sent by
    ``CastleCollectorEventData.getABGCollectorAmount`` (bundle line 134002) for the owner of a castle
    you are about to attack (``CastleStartAttackDialog``, bundle lines 14708, 14714)
    """

    command = "gabgpp"

    player_id: int = Field(validation_alias="PID", description="The player to ask about")


class PlayerInfluenceResponse(BaseResponse):
    """
    A player's Beyond the Horizon influence.

    Command: gabgpp
    Payload: {"PID": player_id, "AMT": influence}

    Client: ``GABGPPCommand.executeCommand`` (bundle line 127247),
    ``CastleCollectorEventData.parse_GPIP`` (bundle line 134006)
    """

    command = "gabgpp"

    player_id: ClientInt = Field(validation_alias="PID", default=0, description="The player")
    influence: ClientInt = Field(validation_alias="AMT", default=0, description="Their influence")


class GetHorizonPerformanceRequest(BaseRequest):
    """
    Ask for your alliance members' Beyond the Horizon performance.

    Sent only on the Beyond the Horizon server, whose event dialog alone shows the performance tab.

    Command: gae
    Payload: {"AID": alliance_id, "EID": event_id}

    Client: ``C2SAllianceBattleGroundGetAlliancePerformanceVO`` (bundle line 45782), sent with your
    alliance's id and ``EventConst.EVENTTYPE_ALLIANCE_BATTLEGROUND`` by the performance tabs
    (bundle lines 71664, 71702), which ``CastleAllianceBattleGroundEventDialog.showLoaded`` shows only
    when ``ABGHelper.isOnABGServer`` (bundle line 8935)
    """

    command = "gae"

    alliance_id: int = Field(validation_alias="AID", description="Your alliance's id")
    event_id: EnumOrInt[Event] = Field(
        validation_alias="EID", default=Event.BEYOND_THE_HORIZON, description="The event, Beyond the Horizon"
    )


class HorizonMemberPerformance(BasePayload):
    """
    One member's Beyond the Horizon performance.

    Client: ``AllianceBattlegroundAlliancePerformanceVO.parseData`` (bundle line 34235) reads the
    numbers through ``int()`` and one ``PST`` row per statistic, ``CrestVO.loadFromParamObject`` the crest
    """

    player_id: ClientInt = Field(validation_alias="PID", default=0, description="The member")
    player_name: str | None = Field(validation_alias="NOM", default=None, description="Their name")
    level: ClientInt = Field(validation_alias="L", default=0, description="Their level")
    influence: ClientInt = Field(validation_alias="AMT", default=0, description="Their current influence points")
    statistics: dict[EnumOrInt[PerformanceStatistic], int] = Field(
        validation_alias="PST", default_factory=dict, description="Each statistic's amount"
    )
    crest: OwnerCrest | None = Field(validation_alias="E", default=None, description="Their crest")

    @field_validator("statistics", mode="before")
    @classmethod
    def _statistic_rows(cls, value: Any) -> dict[Any, int]:
        if not isinstance(value, list):
            return {}
        return {row["PSI"]: js_int(row.get("AMT")) for row in value if isinstance(row, dict) and "PSI" in row}


class HorizonPerformanceResponse(BaseResponse):
    """
    Your alliance members' Beyond the Horizon performance.

    Command: gae
    Payload: {"AME": [{"PID": .., "NOM": .., "L": .., "AMT": .., "PST": [{"PSI": .., "AMT": ..}], "E": crest}]}

    Client: ``GAECommand.executeCommand`` (bundle line 127262),
    ``CastleAllianceBattleGroundData.parseAlliancePerformance`` (bundle line 144898), which keeps the list
    """

    command = "gae"

    members: list[HorizonMemberPerformance] = Field(
        validation_alias="AME", default_factory=list, description="One entry per member"
    )

    @field_validator("members", mode="before")
    @classmethod
    def _member_rows(cls, value: Any) -> list[HorizonMemberPerformance]:
        return readable_list(
            HorizonMemberPerformance,
            value,
            accept=lambda row: isinstance(row, dict),
            warn=logger,
            what="Beyond the Horizon performance rows",
        )


class GetHorizonEntryRequest(BaseRequest):
    """
    Ask how your alliance will enter Beyond the Horizon.

    Sent on your main server, before you buy your way onto Beyond the Horizon.

    Command: ajp
    Payload: {}

    Client: ``C2SAllianceBattleGroundJoinedPlayerVO`` (bundle line 71204), sent by
    ``CastleAllianceBattleGroundBuyInfoDialog.getAlliInfo`` (bundle line 45639)
    """

    command = "ajp"


class HorizonEntryResponse(BaseResponse):
    """
    Your alliance as Beyond the Horizon will take it: its name, members and your rank.

    The client shows the member count against the event's maximum alliance size.

    Command: ajp
    Payload: {"N": alliance_name, "M": member_count, "R": rank}

    Client: ``AJPCommand.executeCommand`` (bundle line 127187),
    ``CastleAllianceBattleGroundBuyInfoDialog.onInfoArrived`` (bundle line 45642)
    """

    command = "ajp"

    alliance_name: str | None = Field(validation_alias="N", default=None, description="Your alliance's name")
    member_count: ClientInt = Field(validation_alias="M", default=0, description="Members who will enter")
    rank: EnumOrInt[AllianceRank] = Field(validation_alias="R", default=0, description="Your alliance rank")


class GetHorizonEntryConditionsRequest(BaseRequest):
    """
    Ask which conditions for entering Beyond the Horizon you do not meet yet.

    Command: bgc
    Payload: {}

    Client: ``C2SAllianceBattleGroundEntryConditionsVO`` (split.js line 716195), sent by
    ``CastleAllianceBattleGroundData.requestEntryConditions`` (split.js line 716008) when the Jade Desert's event
    dialog opens
    """

    command = "bgc"


class HorizonEntryCondition(BasePayload):
    """
    One condition for entering Beyond the Horizon that you do not meet yet.

    Client: ``ABGEntryConditionVO.parseData`` (split.js line 716688) reads ``MBW`` through ``int()``; the dialog
    names each missing building with ``wodData.getBuildingVOById`` (split.js line 474649)
    """

    condition_type: EnumOrStr[HorizonEntryConditionType] = Field(
        validation_alias="ECT", default="", description="What kind of condition it is"
    )
    missing_buildings: list[EnumOrInt["Building"]] = Field(
        validation_alias="MBW", default_factory=list, description="The buildings you still need"
    )

    @field_validator("missing_buildings", mode="before")
    @classmethod
    def _building_ids(cls, value: Any) -> list[int]:
        return [js_int(wod_id) for wod_id in value] if isinstance(value, list) else []


class HorizonEntryConditionsResponse(BaseResponse):
    """
    The conditions for entering Beyond the Horizon that you do not meet yet; none when you may enter.

    Command: bgc
    Payload: {"ENCO": [{"ECT": condition_type, "MBW": [building_wod_id, ...]}, ...]}

    Client: ``BGCCommand.executeCommand`` (split.js line 642786) hands the reply to
    ``CastleAllianceBattleGroundData.parseEntryConditions`` (split.js line 716014)
    """

    command = "bgc"

    conditions: list[HorizonEntryCondition] = Field(
        validation_alias="ENCO", default_factory=list, description="Each condition not met"
    )

    @field_validator("conditions", mode="before")
    @classmethod
    def _condition_rows(cls, value: Any) -> list[HorizonEntryCondition]:
        return readable_list(
            HorizonEntryCondition,
            value,
            accept=lambda row: isinstance(row, dict),
            warn=logger,
            what="Beyond the Horizon entry conditions",
        )

    @property
    def missing_buildings(self) -> list[EnumOrInt["Building"]]:
        """The buildings every building condition still needs, in order."""
        return [
            building
            for condition in self.conditions
            if condition.condition_type is HorizonEntryConditionType.BUILDINGS
            for building in condition.missing_buildings
        ]


class JadePhaseResponse(BaseResponse):
    """
    The Jade Desert's scoring phase, pushed while you play Beyond the Horizon's jade season.

    A key the push leaves out, or sends as 0, keeps the value the client had; only the phase 2 condition goes back
    to none.

    Command: abgi, pushed
    Payload: {"JP": phase, "JPT": seconds_until_phase_2, "JPP": phase_2_condition_percent}

    Client: ``ABGICommand.executeCommand`` (split.js line 643311), which ignores the push with no Beyond the Horizon
    event, hands it to ``AllianceBattleGroundEventVO.parseJadePhaseInfo`` (split.js line 585444)
    """

    command = "abgi"

    phase: EnumOrInt[JadeScoringPhase] | None = Field(
        validation_alias="JP", default=None, description="The scoring phase; None when not sent"
    )
    seconds_until_phase_2: int | None = Field(
        validation_alias="JPT", default=None, description="Seconds until phase 2 starts; None when not sent"
    )
    phase_2_condition_percent: int | None = Field(
        validation_alias="JPP",
        default=None,
        description="Percent of the condition that starts phase 2 early that is met; None when there is none",
    )

    @field_validator("phase", "seconds_until_phase_2", "phase_2_condition_percent", mode="before")
    @classmethod
    def _set_or_none(cls, value: Any) -> int | None:
        return js_int(value) if js_truthy(value) else None


class JadePhase(EmpireModel):
    """
    The Jade Desert's scoring phase as the ``abgi`` pushes so far left it.

    The client starts from the event's own data, which is not read here, so a phase no push has named is None.

    Client: ``AllianceBattleGroundEventVO.parseJadePhaseInfo`` (split.js line 585444), also run by its
    ``parseParamObject``; it turns to phase 2 once the phase 2 time passes (``onJadePhaseTimer``)
    """

    model_config = ConfigDict(frozen=True)

    phase: EnumOrInt[JadeScoringPhase] | None = Field(
        default=None, description="The phase last pushed; None until a push named it"
    )
    phase_2_starts_at: float | None = Field(
        default=None, description="When phase 2 starts, in epoch seconds; None until a push named it"
    )
    phase_2_condition_percent: int | None = Field(
        default=None, description="Percent of the condition that starts phase 2 early that is met; None for none"
    )

    def updated(self, push: JadePhaseResponse, received_at: float) -> JadePhase:
        """This phase with ``push`` applied, received at ``received_at`` epoch seconds."""
        return JadePhase(
            phase=self.phase if push.phase is None else push.phase,
            phase_2_starts_at=(
                self.phase_2_starts_at
                if push.seconds_until_phase_2 is None
                else received_at + push.seconds_until_phase_2
            ),
            phase_2_condition_percent=push.phase_2_condition_percent,
        )

    def current_phase(self, now: float) -> EnumOrInt[JadeScoringPhase] | None:
        """The phase at ``now`` epoch seconds: phase 2 once its start has passed; None while unknown."""
        if self.phase_2_starts_at is not None and now >= self.phase_2_starts_at:
            return JadeScoringPhase.PHASE_2
        return self.phase

    def seconds_until_phase_2(self, now: float) -> float:
        """Seconds from ``now`` until phase 2 starts; 0 once it has, or when no push named it."""
        return max(0.0, self.phase_2_starts_at - now) if self.phase_2_starts_at is not None else 0.0


class GetCitadelsRequest(BaseRequest):
    """
    Ask for your alliance's Citadel and the enemy citadels in the Jade Desert.

    Command: jci
    Payload: {}

    Client: ``C2SGetJadeCitadelInfoVO`` (split.js line 716216), sent by
    ``CastleAllianceBattleGroundData.requestJadeCitadelInfo`` (split.js line 716001) only when
    ``ABGHelper.isOnABGAndJade`` (split.js line 9010)
    """

    command = "jci"


class Citadel(BasePayload):
    """
    An alliance's Citadel in the Jade Desert: where it stands, how far it reaches and the statuettes it holds.

    Its level row is the :attr:`GameData.citadel_levels` row of the highest level whose radius ``radius`` reaches.

    Client: ``ABGCitadelInfoVO.parseData`` (split.js line 716575) reads ``X``, ``Y``, ``CR``, ``ASJ`` and ``RSJ``
    through ``int()``, ``L`` as sent and ``CD`` as ``int(CD) || 0``
    """

    x: ClientInt = Field(validation_alias="X", default=0, description="Its map x")
    y: ClientInt = Field(validation_alias="Y", default=0, description="Its map y")
    radius: ClientInt = Field(validation_alias="CR", default=0, description="Fields it reaches")
    level: ClientInt = Field(validation_alias="L", default=0, description="Its level")
    ancient_jade_statuettes: ClientInt = Field(
        validation_alias="ASJ", default=0, description="Ancient Jade Statuettes it holds"
    )
    restored_jade_statuettes: ClientInt = Field(
        validation_alias="RSJ", default=0, description="Restored Jade Statuettes it holds"
    )
    protection_seconds: ClientInt = Field(
        validation_alias="CD", default=0, description="Seconds its attack protection lasts; 0 for none"
    )


class CitadelsResponse(BaseResponse):
    """
    Your alliance's Citadel and the enemy citadels in the Jade Desert.

    Command: jci
    Payload: {"CI": citadel, "ECI": [citadel, ...]}

    Client: ``JCICommand.executeCommand`` (split.js line 643404) hands the reply to
    ``CastleAllianceBattleGroundData.parseJadeCitadelInfo`` (split.js line 715890)
    """

    command = "jci"

    own: Citadel | None = Field(validation_alias="CI", default=None, description="Your alliance's; None for none")
    enemies: list[Citadel] = Field(validation_alias="ECI", default_factory=list, description="The enemy citadels")

    @field_validator("own", mode="before")
    @classmethod
    def _own_or_none(cls, value: Any) -> Any:
        return value if js_truthy(value) else None

    @field_validator("enemies", mode="before")
    @classmethod
    def _enemy_rows(cls, value: Any) -> list[Citadel]:
        return readable_list(
            Citadel, value, accept=lambda row: isinstance(row, dict), warn=logger, what="enemy citadels"
        )


class UpgradeCitadelRequest(BaseRequest):
    """
    Upgrade your alliance's Citadel to its next level, for the level's Ancient Jade Statuettes.

    Command: ujc
    Payload: {}

    The server answers with no payload; the client reads the citadel's map area again.

    Client: ``C2SUpgradeJadeCitadelVO`` (split.js line 474000), sent by
    ``CastleAllianceBattleGroundEventJadeDialogCitadelManagement.sendUpgrade`` (split.js line 473865);
    ``UJCCommand.executeCommand`` (split.js line 644013)
    """

    command = "ujc"


class ConvertJadeStatuettesRequest(BaseRequest):
    """
    Convert Ancient Jade Statuettes into Restored Jade Statuettes before the event ends.

    Each Restored Jade Statuette takes your citadel level's ``early_conversion_ratio`` Ancient ones.

    Command: cjs
    Payload: {"AMT": restored_amount}

    The server answers with no payload.

    Client: ``C2SConvertJadeStatuettesVO`` (split.js line 474398), sent by
    ``ABGJadeStatuetteConversionComponent.sendConversion`` (split.js line 474233) with ``convertedRestoredAmount``,
    the Ancient statuettes picked divided by the ratio, rounded down; ``CJSCommand.executeCommand``
    (split.js line 643361)
    """

    command = "cjs"

    restored_amount: int = Field(validation_alias="AMT", description="Restored Jade Statuettes to make")


class GetOasisSettlementRequest(BaseRequest):
    """
    Ask for an Oasis Settlement's state: its level, troops left to trade and cooldown.

    Command: jtci
    Payload: {"TX": x, "TY": y, "KID": kingdom}

    Client: ``C2SGetTradingCampInfoVO`` (split.js line 565054), sent with the settlement's position and kingdom by
    ``AllianceBattleGroundJadeTradeDialog`` when it opens (split.js line 564457)
    """

    command = "jtci"

    x: int = Field(validation_alias="TX", description="The settlement's map x")
    y: int = Field(validation_alias="TY", description="The settlement's map y")
    kingdom: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="The settlement's kingdom")


class OasisSettlementResponse(BaseResponse):
    """
    An Oasis Settlement's state: its level, the troops it has left to trade and its cooldown.

    Command: jtci
    Payload: {"X": x, "Y": y, "TCI": settlement_id, "L": level, "TCR": remaining, "CD": cooldown_seconds,
              "AE": [[effect_id, values, source], ...]}

    Client: ``JTCICommand.executeCommand`` (split.js line 643456), ``TradingCampInfoVO.parseParamObject``
    (split.js line 643498) reads the numbers through ``int()`` and ``AE`` with ``SimpleEffectSource.parseEffects``
    (split.js line 159926), the rows a commander's effects have
    """

    command = "jtci"

    x: ClientInt = Field(validation_alias="X", default=0, description="Its map x")
    y: ClientInt = Field(validation_alias="Y", default=0, description="Its map y")
    settlement_id: Annotated[OasisSettlementId, BeforeValidator(js_int)] = Field(
        validation_alias="TCI",
        default=OasisSettlementId(0),
        description="Its level's row, a GameData.oasis_settlements row",
    )
    level: ClientInt = Field(validation_alias="L", default=0, description="Its level")
    remaining: ClientInt = Field(validation_alias="TCR", default=0, description="Troops it has left to trade")
    cooldown_seconds: ClientInt = Field(
        validation_alias="CD", default=0, description="Seconds until it trades again; 0 when it can"
    )
    area_effects: CommanderEffects = Field(
        validation_alias="AE", default_factory=list, description="Effects on trades with it"
    )


class SendOasisTradeRequest(BaseRequest):
    """
    Send troops and trading materials from a castle to an Oasis Settlement to trade.

    Command: jtr
    Payload: {"SX": source_x, "SY": source_y, "TX": target_x, "TY": target_y, "KID": kingdom,
              "LID": commander_id, "BPC": use_premium_commander, "HBW": horse_booster_id,
              "PTT": feathers, "A": [[wod_id, amount], ...], "TR": [[trade_id, amount], ...]}

    ``LID`` is 0 when the premium commander leads (``BPC`` 1). ``HBW`` is -1 and ``PTT`` 1 when the horse is paid
    with feathers.

    Client: ``C2SCreateTradeMovementVO`` (split.js line 566844), sent by
    ``CastlePostTradeHorseDialog.sendTradeMovement`` (split.js line 566640) from the main castle, with the army
    from ``TradingCampArmyVO.getArmyParam`` (split.js line 301804) and the trades from
    ``TradingCampTradeSelectionVO.getTradesParam`` (split.js line 565226), which lists amounts above 0
    """

    command = "jtr"

    source_x: int = Field(validation_alias="SX", description="Map x of the castle the troops leave from")
    source_y: int = Field(validation_alias="SY", description="Map y of the castle the troops leave from")
    target_x: int = Field(validation_alias="TX", description="The settlement's map x")
    target_y: int = Field(validation_alias="TY", description="The settlement's map y")
    kingdom: Kingdom = Field(validation_alias="KID", default=Kingdom.GREEN, description="The settlement's kingdom")
    commander_id: int = Field(
        validation_alias="LID", description="The commander leading them; 0 when the premium commander leads"
    )
    use_premium_commander: int = Field(
        validation_alias="BPC", default=0, description="1 when the premium commander leads"
    )
    horse_booster_id: HorseBoosterId = Field(
        validation_alias="HBW",
        default=NO_HORSE,
        description="The horse booster, NO_HORSE for none or when paid with feathers",
    )
    feathers: int = Field(validation_alias="PTT", default=0, description="1 when the horse is paid with feathers")
    units: WodAmountSlots = Field(validation_alias="A", description="The units, one pair per filled slot")
    trades: OasisTradeAmounts = Field(validation_alias="TR", description="How often to make each trade")

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a jtr reply is the movement this sent: its target area (``A.M.TA``) is ``TX``/``TY``."""
        return isinstance(payload, dict) and movement_targets(payload.get("A"), self.target_x, self.target_y)


class SendOasisTradeResponse(SentMovementResponse):
    """
    The trade on its way to the Oasis Settlement.

    Command: jtr
    Payload: {"O": [owner, ...], "A": movement, "gcu": {...}}

    Client: ``JTRCommand.executeCommand`` (split.js line 643584) hands ``O`` to ``parseOwnerInfoArray``, ``[A]``
    to ``CastleArmyData.parseMapMovementArray`` and ``gcu`` to ``CurrencyData.parseGCU``, as the other send replies
    do; the movement's type is ``MOVEMENTTYPE_ALLIANCE_BATTLE_GROUND_TRADE`` (``TradeMapmovementVO``)
    """

    command = "jtr"


__all__ = [
    "ActivateAllianceTowerBuffsRequest",
    "ActivateAllianceTowerBuffsResponse",
    "AllianceInfluenceResponse",
    "AllianceTowerBuff",
    "AllianceTowerBuffIncrease",
    "AllianceTowerBuffs",
    "HorizonEntryResponse",
    "HorizonMemberPerformance",
    "HorizonPerformanceResponse",
    "CenterOfPower",
    "Citadel",
    "CitadelsResponse",
    "ConvertJadeStatuettesRequest",
    "GetCitadelsRequest",
    "GetHorizonEntryConditionsRequest",
    "GetOasisSettlementRequest",
    "HorizonEntryCondition",
    "HorizonEntryConditionsResponse",
    "JadePhase",
    "JadePhaseResponse",
    "OasisSettlementResponse",
    "OasisTradeAmounts",
    "SendOasisTradeRequest",
    "SendOasisTradeResponse",
    "UpgradeCitadelRequest",
    "CentersOfPowerResponse",
    "CentersOfPowerDetailResponse",
    "GetAllianceInfluenceRequest",
    "GetAllianceTowerBuffsRequest",
    "GetAllianceTowerBuffsResponse",
    "GetAllianceTowerCastlesRequest",
    "GetAllianceTowerCastlesResponse",
    "GetAllianceTowersRequest",
    "GetAllianceTowersResponse",
    "GetHorizonEntryRequest",
    "GetHorizonPerformanceRequest",
    "GetCentersOfPowerDetailRequest",
    "GetCentersOfPowerRequest",
    "GetPlayerInfluenceRequest",
    "IncreaseAllianceTowerBuffsRequest",
    "IncreaseAllianceTowerBuffsResponse",
    "PlayerInfluenceResponse",
]
