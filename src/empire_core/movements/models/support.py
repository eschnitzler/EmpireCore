"""Sending support to a castle, and troops between your own areas.

Commands:
- cds: Send support
- tde: Send support to a Beyond the Horizon tower
- cdd: Send support to a daimyo township
- cat: Send troops to another of your own areas
- sti: Travel pre-calculation for troops sent to another of your own areas
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from empire_core.commanders.models.roster import CommanderEffects
from empire_core.enums import Kingdom
from empire_core.gamedata import WodAmounts, WodAmountSlots
from empire_core.map.models.areas import MapObject
from empire_core.map.models.items import TargetRow
from empire_core.movements.models.movement import NO_HORSE, HorseBoosterId, SentMovementResponse
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse
from empire_core.protocol.js import js_truthy, movement_targets

# =============================================================================
# CDS - Send Support (Create Deployment - Support)
# =============================================================================


class SendSupportRequest(BaseRequest):
    """
    Send support troops to a castle.

    Command: cds
    Payload: {
        "SID": source_castle_id,
        "TX": target_x,
        "TY": target_y,
        "LID": commander_id,
        "WT": wait_time,
        "HBW": horse_booster_id (-1 when PTT is set),
        "BPC": use_premium_commander,
        "PTT": feathers,
        "SD": slowdown,
        "A": [[unit_id, count], ...]
    }

    The client sends no kingdom id. Fields follow its key order. ``BPC`` is
    1 only when the premium commander (``LID`` -14,
    ``TravelConst.COMMANDER_PREMIUM``) leads the army, which uses one of the
    player's premium commanders or, when none are left, costs rubies
    (``CastlePostAttackDialog.startAttack`` sends ``sendMovement(0)`` for any
    other commander). ``PTT`` 1 pays for the movement with feathers.

    ``A`` carries units only: ``CastleSupportDefenceVO.getArmy`` sends the filled
    slots of its one container, whose slots are all soldier slots.

    Client: ``C2SCreateDefenceSupportMovementVO`` (bundle line 133942), built
    by ``CastleAttackData.sendSupport`` (bundle line 133904) from
    ``CastleSupportDefenceVO.getArmy`` (bundle line 140121); its ``ITEM_TYPES``
    (bundle line 140167) are all ``ToolUnitVO.SLOTTYPE_SOLDIER`` (bundle line 6661)
    """

    command = "cds"

    source_castle_id: int = Field(
        validation_alias="SID",
        description=(
            "One of your castles, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    target_x: int = Field(validation_alias="TX")
    target_y: int = Field(validation_alias="TY")
    commander_id: int = Field(
        validation_alias="LID",
        description=(
            "A Commander.commander_id from client.commanders.get_commanders(); "
            "0 is the free starting commander, -14 the premium one"
        ),
    )
    wait_time: int = Field(validation_alias="WT", default=12, ge=0, le=12)
    horse_booster_id: HorseBoosterId = Field(
        validation_alias="HBW",
        default=NO_HORSE,
        description="The horse booster, NO_HORSE for none or when paid with feathers",
    )
    use_premium_commander: int = Field(
        validation_alias="BPC", default=0, description="1 when the premium commander leads"
    )
    feathers: int = Field(
        validation_alias="PTT",
        default=0,
        description="1 when the horse is paid with feathers",
    )
    slowdown: int = Field(validation_alias="SD", default=0, description="Seconds the arrival is delayed by")
    units: WodAmountSlots = Field(validation_alias="A", description="The units, one pair per filled slot")

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a cds reply is the movement this sent: its target area (``A.M.TA``) is ``TX``/``TY``.

        Client: ``CDSCommand`` (bundle line 125939) reads the new movement from ``A``,
        whose ``TA`` is the target area (``BasicMapmovementVO``). An army heading home
        targets your own castle and is not taken.
        """
        return isinstance(payload, dict) and movement_targets(payload.get("A"), self.target_x, self.target_y)


class SendSupportResponse(SentMovementResponse):
    """
    The support on its way.

    Command: cds
    Payload: {"gcu": {...}, "O": [owner, ...], "A": movement}

    Client: ``CDSCommand.executeCommand`` (bundle line 125973)
    """

    command = "cds"


class SendTowerSupportRequest(SendSupportRequest):
    """
    Send support troops to a Beyond the Horizon tower.

    Command: tde
    Payload: {"SID": source_castle_id, "TX": target_x, "TY": target_y, "LID": commander_id,
              "WT": wait_time, "HBW": horse_booster_id, "BPC": use_premium_commander,
              "PTT": feathers, "SD": slowdown, "A": [[unit_id, count], ...]}

    The client builds it with the same arguments as a ``cds``, in the same key
    order, when the target's area type is ``AREA_TYPE_ALLIANCE_BATTLE_GROUND_TOWER``.

    Client: ``C2SCreateAllianceTowerSupportMovementVO`` (bundle line 133968), built by
    ``CastleAttackData.sendSupport`` (bundle line 133904)
    """

    command = "tde"


class SendTowerSupportResponse(SendSupportResponse):
    """
    The support on its way to a Beyond the Horizon tower.

    Command: tde
    Payload: {"gcu": {...}, "O": [owner, ...], "A": movement}

    Client: ``TDECommand.executeCommand`` (bundle line 126120)
    """

    command = "tde"


# =============================================================================
# CDD - Support a daimyo township
# =============================================================================


class SendTownshipSupportRequest(BaseRequest):
    """
    Send support troops to a daimyo township.

    Command: cdd
    Payload: {"SID": source_castle_id, "TX": target_x, "TY": target_y, "A": [[unit_id, count], ...]}

    The client sends no commander, horse, wait time or slowdown: it sends this
    straight from the support screen when the target's area type is
    ``AREA_TYPE_DAIMYO_TOWNSHIP``, without the travel dialog.

    Client: ``C2SCreateDaimyoDefenseMovementVO`` (bundle line 99735), sent by
    ``OpenPostAttackDialogCommand.execute`` (bundle line 99685) for
    ``ACTION_TYPE_SUPPORTDEFENSE_TOWNSHIP``, which ``CastleSupportDefenceDialog.closeScreen``
    (bundle line 122483) picks; the army from ``CastleSupportDefenceVO.getArmy`` (bundle line 140121)
    """

    command = "cdd"

    source_castle_id: int = Field(
        validation_alias="SID",
        description=(
            "One of your castles, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    target_x: int = Field(validation_alias="TX", description="The township's map x")
    target_y: int = Field(validation_alias="TY", description="The township's map y")
    units: WodAmountSlots = Field(validation_alias="A", description="The units, one pair per filled slot")

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a cdd reply is the movement this sent: its target area (``A.M.TA``) is ``TX``/``TY``.

        Client: ``CDDCommand`` (bundle line 128264) reads the new movement from ``A``.
        """
        return isinstance(payload, dict) and movement_targets(payload.get("A"), self.target_x, self.target_y)


class SendTownshipSupportResponse(SentMovementResponse):
    """
    The support on its way to a daimyo township.

    Command: cdd
    Payload: {"gcu": {...}, "O": [owner, ...], "A": movement}

    Client: ``CDDCommand.executeCommand`` (bundle line 128264)
    """

    command = "cdd"


# =============================================================================
# CSS - Siege movement (reply only)
# =============================================================================


class SiegeMovementResponse(SentMovementResponse):
    """
    A siege movement the server created.

    Command: css
    Payload: {"gcu": {...}, "O": [owner, ...], "A": movement}

    The client has no request that sends ``css``; it only reads this reply.

    Client: ``CSSCommand.executeCommand`` (bundle line 126045)
    """

    command = "css"


# =============================================================================
# CAT - Send Troops (Create Army Travel movement)
# =============================================================================


class SendTroopsRequest(BaseRequest):
    """
    Send troops from one of your areas to another of your own areas, where they stay.

    Command: cat
    Payload: {
        "SX": source_x,
        "SY": source_y,
        "TX": target_x,
        "TY": target_y,
        "KID": kingdom_id,
        "LID": commander_id,
        "WT": 0,
        "HBW": horse_booster_id (-1 when PTT is set),
        "BPC": use_premium_commander,
        "PTT": feathers,
        "SD": slowdown,
        "A": [[wod_id, amount], ...]
    }

    Fields follow the client's key order: the constructor initialises SX to SD
    and sets A after them. The source is named by its map position, not its
    id. ``KID`` is the target's kingdom, and the source must sit in the same
    one. ``A`` lists the units, then the tools. The client always sends ``WT``
    0: only a support sets a wait time. A support (``cds``) to your own area is
    refused with NO_SELF_DESTRUCTION (92); this is the command the client uses
    for it.

    Client: ``C2SCreateArmyTravelMovementVO`` (bundle line 99772), built by
    ``CastleTroopSupportData.sendTroops`` (bundle line 38420) from
    ``CastlePostAttackDialog.sendTroops`` (bundle line 38373); the army from
    ``CastleTroopSupportVO.getArmy`` (bundle line 99737)
    """

    command = "cat"

    source_x: int = Field(validation_alias="SX", description="Map x of the area the troops leave from")
    source_y: int = Field(validation_alias="SY", description="Map y of the area the troops leave from")
    target_x: int = Field(validation_alias="TX", description="Map x of the area they go to")
    target_y: int = Field(validation_alias="TY", description="Map y of the area they go to")
    kingdom_id: Kingdom = Field(
        validation_alias="KID",
        default=Kingdom.GREEN,
        description="The kingdom both areas sit in",
    )
    commander_id: int = Field(
        validation_alias="LID",
        description=(
            "A Commander.commander_id from client.commanders.get_commanders(); "
            "0 is the free starting commander, -14 the premium one"
        ),
    )
    wait_time: int = Field(validation_alias="WT", default=0, description="Wait time at the target")
    horse_booster_id: HorseBoosterId = Field(
        validation_alias="HBW",
        default=NO_HORSE,
        description="The horse booster, NO_HORSE for none or when paid with feathers",
    )
    use_premium_commander: int = Field(
        validation_alias="BPC", default=0, description="1 when the premium commander leads"
    )
    feathers: int = Field(
        validation_alias="PTT",
        default=0,
        description="1 when the horse is paid with feathers",
    )
    slowdown: int = Field(validation_alias="SD", default=0, description="Seconds the arrival is delayed by")
    units: WodAmountSlots = Field(
        validation_alias="A", description="The units, then any tools, one pair per filled slot"
    )

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a cat reply is the movement this sent: its target area (``A.M.TA``) is ``TX``/``TY``.

        Client: ``CATCommand`` (bundle line 125924) reads the new movement from ``A``,
        whose ``TA`` is the target area (``BasicMapmovementVO``). An army heading home
        targets its source and is not taken.
        """
        return isinstance(payload, dict) and movement_targets(payload.get("A"), self.target_x, self.target_y)


class SendTroopsResponse(SentMovementResponse):
    """
    The troops on their way.

    Command: cat
    Payload: {"O": [owner, ...], "A": movement, "gcu": {...}}

    Client: ``CATCommand.executeCommand`` (bundle line 125958)
    """

    command = "cat"


# =============================================================================
# STI - Troop travel pre-calculation (Troop Support Info)
# =============================================================================


class GetTravelInfoRequest(BaseRequest):
    """
    Ask for the pre-calculation of troops sent from one of your areas to another of your own.

    Command: sti
    Payload: {"SX": source_x, "SY": source_y, "TX": target_x, "TY": target_y, "KID": kingdom_id}

    Keys follow the client's order: the constructor initialises SX, SY, TX, TY
    and KID, though it takes the target first. ``KID`` is the target's kingdom.

    Client: ``C2STroopSupportInfoVO`` (bundle line 72087), sent by
    ``CastleStartAttackDialog`` (bundle line 14831)
    """

    command = "sti"

    source_x: int = Field(validation_alias="SX", description="Map x of the area the troops would leave from")
    source_y: int = Field(validation_alias="SY", description="Map y of the area the troops would leave from")
    target_x: int = Field(validation_alias="TX", description="Map x of the area they would go to")
    target_y: int = Field(validation_alias="TY", description="Map y of the area they would go to")
    kingdom_id: Kingdom = Field(
        validation_alias="KID",
        default=Kingdom.GREEN,
        description="The kingdom both areas sit in",
    )


class TravelTargetArea(BasePayload):
    """
    The target's map row and its owner, the ``gaa`` block of an ``sti`` reply.

    Unlike an attack pre-calculation's, ``OI`` is one owner record, not a
    list: the client reads it with ``parseOwnerInfo``, which takes no record
    without an ``OID``.

    Client: ``CastleTroopSupportVO.fillFromParamObject`` (bundle line 99736),
    ``CastleOtherPlayerData.parseOwnerInfo`` (bundle line 138996)
    """

    area: TargetRow = Field(validation_alias="AI", default=None, description="The target's map row")
    owner: MapObject | None = Field(
        validation_alias="OI",
        default=None,
        description="The target's owner; None when not named",
    )

    @field_validator("owner", mode="before")
    @classmethod
    def _owner_record(cls, value: object) -> object:
        if isinstance(value, dict) and not js_truthy(value.get("OID")):
            return None
        return value if isinstance(value, dict | MapObject) else None


class TravelUnits(BasePayload):
    """
    Your units and tools at the source, the ``gui`` block of an ``sti`` reply.

    Client: ``CastleTroopSupportVO.fillFromParamObject`` (bundle line 99736) reads ``I``
    into a ``UnitInventoryDictionary`` and ``SHI`` into a ``StrongholdUnitInventory``
    """

    units: WodAmounts = Field(validation_alias="I", default_factory=dict, description="Units and tools at the source")
    stronghold: WodAmounts = Field(
        validation_alias="SHI",
        default_factory=dict,
        description="Units stored in its stronghold",
    )


class GetTravelInfoResponse(BaseResponse):
    """
    The pre-calculation of troops sent between your own areas.

    Command: sti
    Payload::

        {"SCID": source_castle_id, "KID": ..,
         "gaa": {"AI": [target map row], "OI": {owner record}},
         "gui": {"I": [[wod_id, count], ...], "SHI": [[wod_id, count], ...]},
         "AE": [[effect_id, [value], source_tag], ...],
         "gli": {"C": [...], "B": [...]}}

    ``gli`` (your commanders) updates ``client.state``; ``AE``, the area
    effects on the movement, is read as an attack pre-calculation's is. The
    reply carries no travel time or cost: the client works them out from the
    distance and the units picked. A source that is not one of your castles is refused with
    ``NOT_IN_OWNED_CASTLE``.

    Client: ``STICommand.executeCommand`` (bundle line 129099), which passes
    ``gli`` to ``CastleLordData.parse_GLI``; ``CastleTroopSupportData.parse_STI``
    (bundle line 38417); ``CastleTroopSupportVO.fillFromParamObject`` (bundle
    line 99736), whose base ``CastleFightScreenVO.fillFromParamObject`` reads
    ``AE`` (bundle line 30501)
    """

    command = "sti"

    source_castle_id: int = Field(
        validation_alias="SCID",
        default=0,
        description="The castle the troops would leave from",
    )
    kingdom_id: Kingdom = Field(
        validation_alias="KID",
        default=Kingdom.GREEN,
        description="The source castle's kingdom",
    )
    target_area: TravelTargetArea = Field(
        validation_alias="gaa",
        default_factory=lambda: TravelTargetArea(),
        description="The target's map row and owner",
    )
    units: TravelUnits = Field(
        validation_alias="gui",
        default_factory=lambda: TravelUnits(),
        description="Your units and tools at the source",
    )
    area_effects: CommanderEffects = Field(
        validation_alias="AE",
        default_factory=list,
        description="Area effects on the movement",
    )


__all__ = [
    "GetTravelInfoRequest",
    "GetTravelInfoResponse",
    "TravelTargetArea",
    "TravelUnits",
    "SendSupportRequest",
    "SendSupportResponse",
    "SendTowerSupportRequest",
    "SendTowerSupportResponse",
    "SendTownshipSupportRequest",
    "SendTownshipSupportResponse",
    "SendTroopsRequest",
    "SendTroopsResponse",
    "SiegeMovementResponse",
]
