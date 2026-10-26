"""Sending an attack.

Commands:
- cra: Create/send attack
- abgcam: Send an attack on Beyond the Horizon
- cam: Send an attack on the Outer Realms
- thm: Send a treasure hunt attack
- ldt: Taunt a daimyo into attacking your township
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, PrivateAttr, ValidatorFunctionWrapHandler, field_validator, model_validator
from pydantic.functional_validators import ModelWrapValidatorHandler

from empire_core.army.models.units import AttackWave, UnitInventoryBlock
from empire_core.commanders.models.roster import Commander
from empire_core.enums import AttackType, AutoSkipCooldownType, Kingdom, LootPriority
from empire_core.gamedata import CurrencyAmounts, SupportToolSlots, WodAmountSlots
from empire_core.movements.models import (
    NO_HORSE,
    HorseBoosterId,
    MovementOwner,
    MovementWrapper,
    SentMovementResponse,
)
from empire_core.protocol.base import BaseRequest, BaseResponse, CurrencyBlock, read_or_none, readable_list
from empire_core.protocol.js import js_truthy, movement_targets

logger = logging.getLogger(__name__)


class _ArmyAttackRequest(BaseRequest):
    """The fields every army attack starts with, ``SX`` to ``ICA`` in the client's key order."""

    source_x: int = Field(validation_alias="SX", description="Attacking castle's map x")
    source_y: int = Field(validation_alias="SY", description="Attacking castle's map y")
    target_x: int = Field(validation_alias="TX", description="Target map x")
    target_y: int = Field(validation_alias="TY", description="Target map y")
    kingdom_id: Kingdom = Field(
        validation_alias="KID",
        default=Kingdom.GREEN,
        description="The attacking castle's kingdom",
    )
    commander_id: int = Field(
        validation_alias="LID",
        description=(
            "A Commander.commander_id from client.commanders.get_commanders(); "
            "0 is the free starting commander, -14 the premium one"
        ),
    )
    wait_time: int = Field(validation_alias="WT", default=0, description="Wait time the attack is sent with")
    horse_booster_id: HorseBoosterId = Field(
        validation_alias="HBW",
        default=NO_HORSE,
        description="The horse booster, NO_HORSE for none or when paid with feathers",
    )
    use_premium_commander: int = Field(
        validation_alias="BPC",
        default=0,
        description=(
            "1 when the premium commander (commander_id -14) leads, which uses a premium commander or"
            " costs rubies; 0 for any other commander"
        ),
    )
    attack_type: AttackType = Field(validation_alias="ATT", default=AttackType.ATTACK, description="The kind of attack")
    share_battle_view: int = Field(validation_alias="AV", default=0, description="1 to let others watch the battle")
    loot_priority: LootPriority = Field(
        validation_alias="LP", default=LootPriority.NO, description="Resource to loot first"
    )
    send_anyway: int = Field(
        validation_alias="FC",
        default=0,
        description="1 to send although one of your attacks is already on its way there (after ATTACK_IN_PROGRESS)",
    )
    feathers: int = Field(
        validation_alias="PTT",
        default=0,
        description="1 when the horse is paid with feathers",
    )
    slowdown: int = Field(validation_alias="SD", default=0, description="Seconds the arrival is delayed by")
    collector_attack: int = Field(validation_alias="ICA", default=0, description="1 for a collector event attack")

    def accepts_reply(self, payload: Any) -> bool:
        """Whether the reply is the movement this sent: its target area (``AAM.M.TA``) is ``TX``/``TY``.

        Client: ``CRACommand`` (bundle line 125988) and ``ABGCAMCommand`` (bundle line 125878)
        read the new movement from ``AAM``,
        whose ``TA`` is the target area (``BasicMapmovementVO``). An army heading home
        targets your own castle and is not taken.
        """
        return isinstance(payload, dict) and movement_targets(payload.get("AAM"), self.target_x, self.target_y)


class CreateAttackRequest(_ArmyAttackRequest):
    """
    Send an attack to a target.

    Command: cra
    Payload: {"SX": source_x, "SY": source_y, "TX": target_x, "TY": target_y, "KID": kingdom_id,
              "LID": commander_id, "WT": wait_time, "HBW": horse_booster_id, "BPC": use_premium_commander,
              "ATT": attack_type, "AV": share_battle_view, "LP": loot_priority, "FC": send_anyway,
              "PTT": feathers, "SD": slowdown, "ICA": collector_attack, "CD": 99, "A": waves,
              "BKS": collector_booster, "AST": support_tools, "RW": yard_wave,
              "ASCT": auto_skip_cooldown}

    ``KID`` is the attacking castle's kingdom. A horse paid with feathers is
    sent as ``HBW`` -1 with ``PTT`` 1. ``CD`` is always 99.

    Fields follow the client's key order: the constructor initialises SX
    through CD before it sets A, BKS, AST, RW and ASCT.

    Client: ``C2SCreateArmyAttackMovementVO`` (bundle line 60874), filled by
    ``CastleAttackData.sendAttack`` (bundle line 133901) with the fight screen's
    ``collecterBooster``, built by ``CastleFightScreenVO.addCollectorBooster``
    (bundle line 30584) from the booster dialogs' ``boosterKey``, a currency id
    (bundle lines 55905, 100060, 100154, 100189, 100221).
    """

    command = "cra"

    countdown: int = Field(validation_alias="CD", default=99, description="Always 99")
    waves: list[AttackWave] = Field(
        validation_alias="A",
        default_factory=list,
        description="The attack waves, front to back",
    )
    collector_booster: CurrencyAmounts = Field(
        validation_alias="BKS",
        default_factory=dict,
        description="Collector event boosters by currency, such as CurrencyId.SAMURAI_MEDAL_BOOSTER",
    )
    support_tools: SupportToolSlots = Field(
        validation_alias="AST",
        default=(),
        description="Support tools, one per slot, None for an empty one; the client sends every slot",
    )
    yard_wave: WodAmountSlots = Field(
        validation_alias="RW",
        default=(),
        description="The courtyard wave's unit slots, [-1, 0] for an empty one",
    )
    auto_skip_cooldown: AutoSkipCooldownType = Field(
        validation_alias="ASCT",
        default=AutoSkipCooldownType.OFF,
        description="How the target's cooldown is skipped when the attack lands",
    )


class HorizonAttackRequest(_ArmyAttackRequest):
    """
    Send an attack on Beyond the Horizon.

    Command: abgcam
    Payload: {"SX": source_x, "SY": source_y, "TX": target_x, "TY": target_y, "KID": kingdom_id,
              "LID": commander_id, "WT": wait_time, "HBW": horse_booster_id, "BPC": use_premium_commander,
              "ATT": attack_type, "AV": share_battle_view, "LP": loot_priority, "FC": send_anyway,
              "PTT": feathers, "SD": slowdown, "ICA": collector_attack, "TCK": 0, "CD": 99, "A": waves,
              "BKS": collector_booster, "AST": support_tools, "RW": yard_wave}

    The client sends it instead of ``cra`` on the Beyond the Horizon server
    while its event scores by alliance collector points, for an attack on a
    castle or capital. It takes the same arguments as ``cra`` but has no
    ``ASCT``; ``TCK`` is initialised to 0 and never set.

    Client: ``C2SCreateAllianceBattleGroundCollectorArmyAttackMovementVO`` (bundle line 133915),
    filled by ``CastleAttackData.sendAttackPlayerAllianceBattleground`` (bundle line 133895), which
    ``CastlePostAttackDialog.sendAttack`` (bundle line 38381) picks when ``ABGHelper.isOnABGAndCollector``
    (bundle line 2033)
    """

    command = "abgcam"

    reserved: int = Field(validation_alias="TCK", default=0, description="Always 0; the client never sets it")
    countdown: int = Field(validation_alias="CD", default=99, description="Always 99")
    waves: list[AttackWave] = Field(
        validation_alias="A",
        default_factory=list,
        description="The attack waves, front to back",
    )
    collector_booster: CurrencyAmounts = Field(
        validation_alias="BKS",
        default_factory=dict,
        description="Collector event boosters by currency, such as CurrencyId.SAMURAI_MEDAL_BOOSTER",
    )
    support_tools: SupportToolSlots = Field(
        validation_alias="AST",
        default=(),
        description="Support tools, one per slot, None for an empty one; the client sends every slot",
    )
    yard_wave: WodAmountSlots = Field(
        validation_alias="RW",
        default=(),
        description="The courtyard wave's unit slots, [-1, 0] for an empty one",
    )


class OuterRealmsAttackRequest(_ArmyAttackRequest):
    """
    Send an attack on the Outer Realms.

    Command: cam
    Payload: {"SX": source_x, "SY": source_y, "TX": target_x, "TY": target_y, "KID": kingdom_id,
              "LID": commander_id, "WT": wait_time, "HBW": horse_booster_id, "BPC": use_premium_commander,
              "ATT": attack_type, "AV": share_battle_view, "LP": loot_priority, "FC": send_anyway,
              "PTT": feathers, "SD": slowdown, "ICA": 0, "CD": 99, "A": waves,
              "BKS": collector_booster, "AST": support_tools, "RW": yard_wave}

    The client sends it instead of ``cra`` on the Outer Realms while its event scores collector
    points, for an attack on a castle. It takes the same arguments as ``cra`` but has no ``ASCT``,
    and its constructor sends ``ICA`` 0 whatever it is given.

    Client: ``C2SCreateArmyAttackMovementTempServerVO`` (bundle line 133933), filled by
    ``CastleAttackData.sendAttackTempServer`` (bundle line 133898), which ``CastlePostAttackDialog.sendAttack``
    (bundle line 38381) picks when ``isOnTemporaryServer`` and the event ``isCollectorScoring``
    """

    command = "cam"

    countdown: int = Field(validation_alias="CD", default=99, description="Always 99")
    waves: list[AttackWave] = Field(
        validation_alias="A",
        default_factory=list,
        description="The attack waves, front to back",
    )
    collector_booster: CurrencyAmounts = Field(
        validation_alias="BKS",
        default_factory=dict,
        description="Collector event boosters by currency, such as CurrencyId.SAMURAI_MEDAL_BOOSTER",
    )
    support_tools: SupportToolSlots = Field(
        validation_alias="AST",
        default=(),
        description="Support tools, one per slot, None for an empty one; the client sends every slot",
    )
    yard_wave: WodAmountSlots = Field(
        validation_alias="RW",
        default=(),
        description="The courtyard wave's unit slots, [-1, 0] for an empty one",
    )


class CreateAttackResponse(BaseResponse):
    """
    Response to attack creation.

    Command: cra
    Payload::

        {"AAM": {
            "M":  {movement},                  # the created movement
            "UM": {"L": {gli entry}, ...},     # the commander leading it
            "FA": {"L": [[unit_id, count]], "M": [...], "R": [...], "RW": []},
            "AST": [...], "ATT": 0, "ASCT": 0, "FC": 0,
        }}

    ``UM.L`` is the same shape as a ``gli`` entry, equipment included, so it is
    what confirms which commander ``LID`` selected. ``FA`` is the army the
    server actually accepted, after it dropped empty flanks.

    A success also carries ``gcu`` and ``O``; the state manager applies both
    with the movement. An ``ATTACK_IN_PROGRESS`` (234) reply carries ``TS`` and
    ``AS`` instead, the countdown and army size of the attack already on its
    way, which the client shows before offering to send anyway with ``FC=1``.
    ``send_attack`` raises that reply as ``AttackInProgressError``, with both
    values read off it.

    ``CRACommand`` hands ``AAM`` to ``CastleArmyData.parseMapMovementArray``
    as ``[i.AAM]``, the same read as a ``gam`` entry or an ``abr`` push, and
    ``O`` to ``CastleOtherPlayerData.parseOwnerInfoArray``, which skips a
    record without an ``OID``.

    Client: ``CRACommand.executeCommand`` (bundle line 125954),
    ``CastleArmyData.parseMapMovementArray`` (bundle line 133626),
    ``MapmovementFactory.parseMapMovement`` (bundle line 133793),
    ``CastleOtherPlayerData.parseOwnerInfo`` (bundle line 138996),
    ``CurrencyData.parseGCU`` (bundle line 141191),
    ``CastlePostPostAttackFactionDialogProperties`` (bundle line 40173),
    ``CastlePostPostAttackFactionDialog.onClick`` (bundle line 40155).
    """

    command = "cra"

    attack_movement: MovementWrapper | None = Field(
        validation_alias="AAM",
        default=None,
        description="The created movement; None when there is none",
    )
    currencies: CurrencyBlock = Field(
        validation_alias="gcu",
        default=None,
        description="Coins and rubies after the send; None when the reply has none",
    )
    owners: list[MovementOwner] = Field(
        validation_alias="O",
        default_factory=list,
        description="Owner records for the movement's areas",
    )
    arrival_seconds: int | float | None = Field(
        validation_alias="TS",
        default=None,
        description="On ATTACK_IN_PROGRESS: seconds until the attack already on its way arrives",
    )
    army_size: int | float | None = Field(
        validation_alias="AS",
        default=None,
        description="On ATTACK_IN_PROGRESS: the size of the attack already on its way",
    )

    _raw_attack_movement: dict[str, Any] = PrivateAttr(default_factory=dict)

    @model_validator(mode="wrap")
    @classmethod
    def _keep_the_raw_movement(
        cls, data: object, handler: ModelWrapValidatorHandler["CreateAttackResponse"]
    ) -> "CreateAttackResponse":
        model = handler(data)
        if isinstance(data, dict) and isinstance(data.get("AAM"), dict):
            model._raw_attack_movement = data["AAM"]
        return model

    @field_validator("attack_movement", mode="wrap")
    @classmethod
    def _movement_or_none(cls, value: object, handler: ValidatorFunctionWrapHandler) -> MovementWrapper | None:
        if not value:
            return None
        return read_or_none(handler, value, warn=logger, what=f"the movement created by {cls.command}")

    @field_validator("owners", mode="before")
    @classmethod
    def _readable_owners(cls, value: object) -> list[MovementOwner]:
        return readable_list(
            MovementOwner,
            value,
            accept=lambda record: isinstance(record, dict),
            keep=lambda record: js_truthy(record.get("OID")),
            warn=logger,
            what=f"owner records sent with {cls.command}",
        )

    @property
    def leader(self) -> Commander | None:
        """The commander leading the attack, as the server echoed it back."""
        if self.attack_movement:
            unit_info = self.attack_movement.unit_info
            return unit_info.commander if unit_info else None
        raw = (self._raw_attack_movement.get("UM") or {}).get("L")
        if not isinstance(raw, dict):
            return None
        return read_or_none(Commander.model_validate, raw, warn=logger, what="the commander echoed back by cra")

    @property
    def movement_id(self) -> int | None:
        """The created movement's ID, or None when the server sent no movement."""
        if self.attack_movement:
            return self.attack_movement.movement.movement_id
        movement = self._raw_attack_movement.get("M")
        if not isinstance(movement, dict):
            return None
        try:
            return int(movement["MID"])
        except (KeyError, TypeError, ValueError):
            return None


class HorizonAttackResponse(CreateAttackResponse):
    """
    Response to an attack sent on Beyond the Horizon.

    Command: abgcam
    Payload: {"gcu": {...}, "O": [owner, ...], "AAM": movement}, read as a ``cra`` reply

    A ``MOVEMENT_HAS_NO_UNITS`` (100) reply carries ``MS``, the fewest units the
    client's message names; an ``ATTACK_IN_PROGRESS`` (234) one ``TS`` and ``AS``
    as for ``cra``.

    Client: ``ABGCAMCommand.executeCommand`` (bundle line 125878)
    """

    command = "abgcam"

    minimum_soldiers: int | None = Field(
        validation_alias="MS",
        default=None,
        description="On MOVEMENT_HAS_NO_UNITS: the fewest units the attack must carry",
    )


class OuterRealmsAttackResponse(CreateAttackResponse):
    """
    Response to an attack sent on the Outer Realms.

    Command: cam
    Payload: {"gcu": {...}, "O": [owner, ...], "AAM": movement}, read as a ``cra`` reply

    A ``MOVEMENT_HAS_NO_UNITS`` (100) reply carries ``MS``, the fewest units the
    client's message names; an ``ATTACK_IN_PROGRESS`` (234) one ``TS`` and ``AS``
    as for ``cra``.

    Client: ``CAMCommand.executeCommand`` (bundle line 125937)
    """

    command = "cam"

    minimum_soldiers: int | None = Field(
        validation_alias="MS",
        default=None,
        description="On MOVEMENT_HAS_NO_UNITS: the fewest units the attack must carry",
    )


# =============================================================================
# THM - Treasure hunt attack
# =============================================================================


class TreasureHuntAttackRequest(BaseRequest):
    """
    Attack a node of a treasure map.

    Command: thm
    Payload: {"LID": commander_id, "BT": horse_booster_id, "BPC": use_premium_commander,
              "MID": map_id, "NID": node_id, "PTT": feathers, "A": waves}

    No source, target or kingdom: the map and node name the target. ``A`` is
    built as a ``cra``'s is, from the complete waves only. A horse paid with
    feathers goes out as ``BT`` -1 with ``PTT`` 1.

    Client: ``C2SCreateTreasureHuntMovementVO`` (bundle line 140494), filled by
    ``CastleTreasureMapData.sendTreasureHuntAttack`` (bundle line 140467) from
    ``CastleAttackArmyVO.getArmyData`` (bundle line 55900)
    """

    command = "thm"

    commander_id: int = Field(
        validation_alias="LID",
        description=(
            "A Commander.commander_id from client.commanders.get_commanders(); "
            "0 is the free starting commander, -14 the premium one"
        ),
    )
    horse_booster_id: HorseBoosterId = Field(
        validation_alias="BT",
        default=NO_HORSE,
        description="The horse booster, NO_HORSE for none or when paid with feathers",
    )
    use_premium_commander: int = Field(
        validation_alias="BPC", default=0, description="1 when the premium commander leads"
    )
    map_id: int = Field(validation_alias="MID", description="The treasure map's id")
    node_id: int = Field(validation_alias="NID", description="The attacked node's id on that map")
    feathers: int = Field(validation_alias="PTT", default=0, description="1 when the horse is paid with feathers")
    waves: list[AttackWave] = Field(
        validation_alias="A",
        default_factory=list,
        description="The attack waves, front to back",
    )


class TreasureHuntAttackResponse(SentMovementResponse):
    """
    The treasure hunt attack on its way.

    Command: thm
    Payload: {"TM": movement, "gcu": {...}, "gui": {"I": [...], "TU": [...], "SHI": [...], "HI": [...]}}

    ``TM`` is read as one ``gam`` entry and ``gui`` as a ``gui`` reply. The
    reply carries no owner records, so ``owners`` stays empty. The client
    ignores a ``CANT_START_NEW_ARMIES`` refusal without a message.

    Client: ``THMCommand.executeCommand`` (bundle line 126135),
    ``CastleMilitaryData.parse_GUI`` (bundle line 138882)
    """

    command = "thm"

    movement: MovementWrapper | None = Field(
        validation_alias="TM",
        default=None,
        description="The new movement; None when the reply has none",
    )
    unit_inventory: UnitInventoryBlock = Field(
        validation_alias="gui",
        default=None,
        description="The units left in the castle the attack left from; None when the reply has none",
    )


# =============================================================================
# LDT - Daimyo taunt
# =============================================================================


class DaimyoTauntRequest(BaseRequest):
    """
    Taunt a daimyo into attacking one of your townships.

    Command: ldt
    Payload: {"TX": township_x, "TY": township_y, "SMK": samurai_medal_boosters, "SPK": shogun_point_boosters}

    ``SMK`` and ``SPK`` are the amounts picked on the dialog's samurai medal
    and shogun point booster sliders, each capped at the boosters you hold
    and the event's limit.

    Client: ``C2SLaunchDaimyoTauntAttackVO`` (bundle line 100120), sent by
    ``SamuraiDaimyoBoosterSelectDialog.onOkButton`` (bundle line 55929); the sliders
    from ``initLoaded`` and ``getSamuraiMedalBooserMax`` (bundle lines 55916, 55919)
    """

    command = "ldt"

    township_x: int = Field(validation_alias="TX", description="The township's map x")
    township_y: int = Field(validation_alias="TY", description="The township's map y")
    samurai_medal_boosters: int = Field(
        validation_alias="SMK", default=0, description="Samurai medal boosters to spend on the attack"
    )
    shogun_point_boosters: int = Field(
        validation_alias="SPK", default=0, description="Shogun point boosters to spend on the attack"
    )


class DaimyoTauntResponse(BaseResponse, MovementWrapper):
    """
    The daimyo's attack the taunt started.

    Command: ldt
    Payload: one movement wrapper, {"M": {movement}, ...}

    The whole body is the movement, read as one ``gam`` entry.

    Client: ``LDTCommand.executeCommand`` (bundle line 128324) hands ``[i]`` to
    ``CastleArmyData.parseMapMovementArray``
    """

    command = "ldt"


__all__ = [
    "HorizonAttackRequest",
    "HorizonAttackResponse",
    "OuterRealmsAttackRequest",
    "OuterRealmsAttackResponse",
    "CreateAttackRequest",
    "CreateAttackResponse",
    "DaimyoTauntRequest",
    "DaimyoTauntResponse",
    "TreasureHuntAttackRequest",
    "TreasureHuntAttackResponse",
]
