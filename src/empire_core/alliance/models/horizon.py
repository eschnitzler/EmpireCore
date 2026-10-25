"""Beyond the Horizon: alliance tower buffs, towers, centers of power, influence and performance.

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
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import Field, field_validator

from empire_core.enums import AllianceRank, PerformanceStatistic
from empire_core.gamedata.ids.events import Event
from empire_core.gamedata.lenient import EnumOrInt
from empire_core.map.models.areas import MapObject
from empire_core.map.models.items import MapAreaItem, parse_area_rows
from empire_core.map.models.owners import OwnerCrest
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, readable_list
from empire_core.protocol.js import ClientInt, js_int, js_truthy

if TYPE_CHECKING:
    from empire_core.gamedata.ids import Effect

logger = logging.getLogger(__name__)


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

    tower_effect_id: ClientInt = Field(
        validation_alias="TEID", default=0, description="The alliance tower effect, an allianceTowerEffectID"
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
    towers: ClientInt = Field(validation_alias="TWM", default=0, description="Kings' towers your alliance holds")
    tower_player_limit: ClientInt = Field(
        validation_alias="TPL", default=0, description="Kings' towers a member may hold"
    )
    tower_alliance_limit: ClientInt = Field(
        validation_alias="TAL", default=0, description="Kings' towers your alliance may hold"
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
    influence, a kings' tower's percent bonus.

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
    percent_boost: ClientInt = Field(validation_alias="PB", default=0, description="A kings' tower's percent bonus")

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
