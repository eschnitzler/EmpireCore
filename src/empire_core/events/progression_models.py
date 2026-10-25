"""
Event progress: the samurai invasion's daimyo, the nomad khan camp, part-paid unlocks, season maps and
event difficulties.

Commands:
- gda: The daimyo castles and townships
- gdc: Your alliance's daimyo contracts
- gdw: Your war efforts against the daimyo
- aic: An alliance invasion camp's alliance rage (push)
- ule: Pay towards an obstacle or slum level priced in parts
- sje: Tell the server you opened a season event's map
- sede: Choose an event's difficulty
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field, field_serializer, field_validator, model_validator

from empire_core.enums import Kingdom
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, TimedPayload, readable_list
from empire_core.protocol.js import ClientInt, ClientNumber, js_int, js_truthy

# Daimyo


class DaimyoArea(TimedPayload):
    """
    A daimyo castle or township of the samurai invasion.

    Client: ``SamuraiDaimyoAreaVO.parseServerData`` (bundle line 142638)
    """

    x: ClientInt = Field(validation_alias="PX", default=0, description="The area's x on the map")
    y: ClientInt = Field(validation_alias="PY", default=0, description="The area's y on the map")
    rank: ClientInt = Field(validation_alias="R", default=0, description="The area's rank, its place in the line")
    level: ClientInt = Field(validation_alias="L", default=0, description="The area's level")
    shogun_points: ClientInt = Field(
        validation_alias="SP", default=0, description="Shogun points the area has towards its next level"
    )
    cooldown_seconds: ClientNumber = Field(
        validation_alias="CD", default=0, description="Seconds until the area can be attacked again when read"
    )
    cooldown_count: ClientInt = Field(validation_alias="CDC", default=0, description="How often it went on cooldown")
    scaling_camp_id: ClientInt = Field(
        validation_alias="DDCID",
        default=-1,
        description="The area's row in the event auto scaling camps table, -1 without difficulty scaling",
    )

    def remaining_cooldown_seconds(self, now: float | None = None) -> float:
        """Seconds until the area can be attacked again, 0 at least."""
        return max(0.0, self.cooldown_seconds - self._elapsed(now))


def _areas(value: Any) -> Any:
    return sorted(readable_list(DaimyoArea, value), key=lambda area: area.rank) if js_truthy(value) else None


class GetDaimyoAreasRequest(BaseRequest):
    """
    Ask for the samurai invasion's daimyo castles and townships (``gda``).

    Client: ``C2SGetDaimyoAreasEventVO`` (bundle line 142621), sent by ``SamuraiDaimyoDataServer.requestGDA``
    as the invasion dialog's daimyo tab shows (bundle line 99060)
    """

    command: ClassVar[str] = "gda"


class DaimyoAreasResponse(BaseResponse):
    """
    The samurai invasion's daimyo castles and townships, each by rank; a list not sent stays as it was.

    Client: ``GDACommand.executeCommand`` (bundle line 128283), ``SamuraiDaimyoDataServer.parseGDA``
    (bundle line 142540)
    """

    command: ClassVar[str] = "gda"

    castles: tuple[DaimyoArea, ...] | None = Field(
        validation_alias="DC", default=None, description="The daimyo castles by rank; None when not sent"
    )
    townships: tuple[DaimyoArea, ...] | None = Field(
        validation_alias="DT", default=None, description="The daimyo townships by rank; None when not sent"
    )

    @field_validator("castles", "townships", mode="before")
    @classmethod
    def _sorted(cls, value: Any) -> Any:
        return _areas(value)

    def merged_into(self, previous: DaimyoAreasResponse | None) -> DaimyoAreasResponse:
        """These areas over ``previous``, keeping a list this reply did not send."""
        if previous is None:
            return self
        return self.model_copy(
            update={
                "castles": self.castles if self.castles is not None else previous.castles,
                "townships": self.townships if self.townships is not None else previous.townships,
            }
        )


class DaimyoContractProgress(BasePayload):
    """
    Your alliance's progress on a daimyo contract, a ``[contract_id, points]`` row.

    Client: ``SamuraiDaimyoContractProgressVO.parseServerData`` (bundle line 142665)
    """

    contract_id: ClientInt = Field(default=0, description="The contract's row in its daimyo contracts table")
    points: ClientInt = Field(default=0, description="The shogun points your alliance has on it")

    @model_validator(mode="before")
    @classmethod
    def _from_row(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"contract_id": data[0] if data else 0, "points": data[1] if len(data) > 1 else 0}
        return data


def _contracts(value: Any) -> Any:
    rows = readable_list(DaimyoContractProgress, value)
    return sorted(rows, key=lambda contract: contract.contract_id) if js_truthy(value) else None


class GetDaimyoContractsRequest(BaseRequest):
    """
    Ask for your alliance's daimyo contracts (``gdc``).

    Client: ``C2SGetDaimyoAllianceContractsEventVO`` (bundle line 142613), sent by
    ``SamuraiDaimyoDataServer.requestGDC`` (bundle line 99060)
    """

    command: ClassVar[str] = "gdc"


class DaimyoContractsResponse(BaseResponse):
    """
    Your alliance's daimyo castle and township contracts, by contract; a list not sent stays as it was.

    Client: ``GDCCommand.executeCommand`` (bundle line 128298), ``SamuraiDaimyoDataServer.parseGDC``
    (bundle line 142527)
    """

    command: ClassVar[str] = "gdc"

    castle_contracts: tuple[DaimyoContractProgress, ...] | None = Field(
        validation_alias="DCC", default=None, description="The castle contracts; None when not sent"
    )
    township_contracts: tuple[DaimyoContractProgress, ...] | None = Field(
        validation_alias="DTC", default=None, description="The township contracts; None when not sent"
    )

    @field_validator("castle_contracts", "township_contracts", mode="before")
    @classmethod
    def _sorted(cls, value: Any) -> Any:
        return _contracts(value)

    def merged_into(self, previous: DaimyoContractsResponse | None) -> DaimyoContractsResponse:
        """These contracts over ``previous``, keeping a list this reply did not send."""
        if previous is None:
            return self
        return self.model_copy(
            update={
                "castle_contracts": (
                    self.castle_contracts if self.castle_contracts is not None else previous.castle_contracts
                ),
                "township_contracts": (
                    self.township_contracts if self.township_contracts is not None else previous.township_contracts
                ),
            }
        )


def _efforts(value: Any) -> dict[int, int]:
    efforts: dict[int, int] = {}
    for row in value if isinstance(value, list) else []:
        if isinstance(row, list) and len(row) > 1:
            efforts[js_int(row[0])] = js_int(row[1])
    return efforts


class GetDaimyoWarEffortsRequest(BaseRequest):
    """
    Ask for your war efforts against the daimyo (``gdw``).

    Client: ``C2SGetDaimyoWarEffortsEventVO`` (bundle line 142629), sent by
    ``SamuraiDaimyoDataServer.requestGDW`` (bundle line 99060)
    """

    command: ClassVar[str] = "gdw"


class DaimyoWarEffortsResponse(BaseResponse):
    """
    Your war efforts against the daimyo: your rank and points, and your effort on each castle and township.

    Client: ``GDWCommand.executeCommand`` (bundle line 128313), ``SamuraiDaimyoDataServer.parseGDW``
    (bundle line 142515); ``CastleAllianceSamuraiInvasionDaimyoTooltip.update`` (bundle line 99152) looks an
    area's effort up by its rank
    """

    command: ClassVar[str] = "gdw"

    own_rank: ClientInt = Field(validation_alias="OR", default=0, description="Your rank")
    own_points: ClientInt = Field(validation_alias="TWE", default=0, description="Your total war effort")
    castle_efforts: dict[int, int] = Field(
        validation_alias="CWES", default_factory=dict, description="Your war effort on each daimyo castle, by rank"
    )
    township_efforts: dict[int, int] = Field(
        validation_alias="TWES", default_factory=dict, description="Your war effort on each township, by rank"
    )

    @field_validator("castle_efforts", "township_efforts", mode="before")
    @classmethod
    def _by_rank(cls, value: Any) -> Any:
        return value if isinstance(value, dict) else _efforts(value)


# Alliance invasion camps


class AllianceCampInfo(BasePayload):
    """
    An alliance invasion camp's state, an entry of an ``aic``'s ``AC``.

    Client: ``AICCommand.executeCommand`` (bundle line 128188) with the ``CommKeys`` ``EVENT_ID``,
    ``ALLIANCE_CAMP_ID`` and ``ALLIANCE_RAGE`` (``EID``, ``ACID``, ``AR``)
    """

    event_id: ClientInt = Field(validation_alias="EID", default=0, description="The event the camp belongs to")
    camp_id: ClientInt = Field(
        validation_alias="ACID", default=0, description="The camp's row in the alliance invasion camps table"
    )
    alliance_rage: ClientInt = Field(validation_alias="AR", default=0, description="The camp's alliance rage")


class AllianceCampInfoResponse(BaseResponse):
    """
    An alliance invasion camp changed, pushed to its alliance's members.

    Client: ``AICCommand.executeCommand`` (bundle line 128188) reads the first entry and hands it to the running
    event's ``parse_AIC``, which only ``AllianceNomadInvasionEventVO`` has (bundle line 114370)
    """

    command: ClassVar[str] = "aic"

    camps: tuple[AllianceCampInfo, ...] = Field(validation_alias="AC", default=(), description="The camps")

    @field_validator("camps", mode="before")
    @classmethod
    def _camps(cls, value: Any) -> Any:
        return readable_list(AllianceCampInfo, value)


# Part-paid unlocks


class UnlockEventRequest(BaseRequest):
    """
    Pay towards something priced in parts (``ule``): a season map's obstacle, a treasure map node or a slum level.

    Either pays goods, or with ``pay_with_rubies`` pays one resource's missing amount in rubies, the resource
    marked 1 in ``wood``, ``stone`` or ``coins``.

    Client: ``C2SUnlockEventVO`` (bundle line 19543), sent by ``CastleSlumDonateDialog.onClick`` (bundle line
    87707) with the joined castle, ``CastleTreasureMapDonateDialog.onClick`` (bundle line 67887) with your main
    castle in the hunt's kingdom, and ``CastleSeasonBaseRepairDialog.onClick`` (bundle line 37624) and
    ``CastleTreasureMapUnlockObstacleDialog.onClick`` (bundle line 67849) with no castle, in the green
    kingdom, and ``SC`` 1 for their ruby buttons
    """

    command: ClassVar[str] = "ule"

    castle_id: int = Field(validation_alias="SCID", default=-1, description="The castle that pays, -1 for none")
    kingdom: Kingdom = Field(validation_alias="SKID", default=Kingdom.GREEN, description="The paying castle's kingdom")
    wood: int = Field(validation_alias="W", default=0, description="Wood to pay")
    stone: int = Field(validation_alias="S", default=0, description="Stone to pay")
    food: Literal[0] = Field(validation_alias="F", default=0, description="Always 0: food is never paid")
    coins: int = Field(validation_alias="C1", default=0, description="Coins to pay")
    part_price_id: int = Field(validation_alias="IID", description="The row of the part pay prices table paid towards")
    pay_with_rubies: bool = Field(
        validation_alias="SC", default=False, description="The marked resource's missing amount is paid in rubies"
    )

    @field_serializer("pay_with_rubies")
    def _flag(self, value: bool) -> int:
        return int(value)


class UnlockEventResponse(BaseResponse):
    """
    The reply to ``ule``, which carries nothing the client reads.

    Client: ``ULECommand.executeCommand`` (bundle line 129307), which shows no error for ``ALREADY_UNLOCKED``
    and ``NO_EVENT``
    """

    command: ClassVar[str] = "ule"


# Season maps


class SeasonJoinEventRequest(BaseRequest):
    """
    Tell the server you opened a season event's map (``sje``); the client reads no answer.

    Client: ``C2SSeasonJoinEventVO`` (bundle line 108705), sent by ``CastleSeasonMapScreen.show``
    (bundle line 108619) with the screen's treasure map
    """

    command: ClassVar[str] = "sje"

    map_id: int = Field(validation_alias="MID", description="The season event's treasure map")


# Event difficulties


class SelectEventDifficultyRequest(BaseRequest):
    """
    Choose a running event's difficulty (``sede``).

    Client: ``C2SSelectEventDifficultyVO`` (bundle line 55790), sent by ``EventDifficultyConfirmDialog.onClick``
    (bundle line 98770) with the difficulty picked and ``C2U`` set from a locked difficulty's unlock button
    (``DifficultyScalingSelectDialog.onClick``, bundle line 30389), whose price is the difficulty's
    ``rentC2Cost`` (``EventAutoScalingDifficultyVO.parseXML``, bundle line 145390); and by
    ``EventDifficultyConfirmRewardsDialog.onClick`` (bundle line 98787) with difficulty 0
    """

    command: ClassVar[str] = "sede"

    event_id: int = Field(validation_alias="EID", description="The event")
    difficulty_id: int = Field(
        validation_alias="EDID",
        description="The row of the event auto scaling difficulties table; 0 for the event without scaling",
    )
    unlock_with_rubies: bool = Field(
        validation_alias="C2U", default=False, description="A locked difficulty is unlocked for its ruby price"
    )

    @field_serializer("unlock_with_rubies")
    def _flag(self, value: bool) -> int:
        return int(value)


class SelectEventDifficultyResponse(BaseResponse):
    """The reply to ``sede``, which carries nothing the client reads. Client: ``SEDECommand`` (bundle line 128462)"""

    command: ClassVar[str] = "sede"


__all__ = [
    "AllianceCampInfo",
    "AllianceCampInfoResponse",
    "DaimyoArea",
    "DaimyoAreasResponse",
    "DaimyoContractProgress",
    "DaimyoContractsResponse",
    "DaimyoWarEffortsResponse",
    "GetDaimyoAreasRequest",
    "GetDaimyoContractsRequest",
    "GetDaimyoWarEffortsRequest",
    "SeasonJoinEventRequest",
    "SelectEventDifficultyRequest",
    "SelectEventDifficultyResponse",
    "UnlockEventRequest",
    "UnlockEventResponse",
]
