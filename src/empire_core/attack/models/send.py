"""Sending an attack.

Commands:
- cra: Create/send attack
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, PrivateAttr, ValidatorFunctionWrapHandler, field_validator, model_validator
from pydantic.functional_validators import ModelWrapValidatorHandler

from empire_core.army.models.units import AttackWave
from empire_core.commanders.models.roster import Commander
from empire_core.enums import AttackType, AutoSkipCooldownType, Kingdom, LootPriority
from empire_core.movements.models import MovementOwner, MovementWrapper
from empire_core.protocol.base import BaseRequest, BaseResponse, CurrencyBlock, read_or_none, readable_list
from empire_core.protocol.js import js_truthy, movement_targets

logger = logging.getLogger(__name__)


class CreateAttackRequest(BaseRequest):
    """
    Send an attack to a target.

    Command: cra
    Payload: {"SX": source_x, "SY": source_y, "TX": target_x, "TY": target_y, "KID": kingdom_id,
              "LID": commander_id, "WT": wait_time, "HBW": horses_type, "BPC": use_premium_commander,
              "ATT": attack_type, "AV": share_battle_view, "LP": loot_priority, "FC": send_anyway,
              "PTT": feathers, "SD": slowdown, "ICA": collector_attack, "CD": 99, "A": waves,
              "BKS": collector_booster, "AST": support_tools, "RW": yard_wave,
              "ASCT": auto_skip_cooldown}

    ``KID`` is the attacking castle's kingdom. A horse paid with feathers is
    sent as ``HBW`` -1 with ``PTT`` 1. ``CD`` is always 99.

    Fields follow the client's key order: the constructor initialises SX
    through CD before it sets A, BKS, AST, RW and ASCT.

    Client: ``C2SCreateArmyAttackMovementVO`` (bundle line 60851), filled by
    ``CastleAttackData.sendAttack`` (bundle line 133852) with the fight screen's
    ``collecterBooster``, built by ``CastleFightScreenVO.addCollectorBooster``
    (bundle line 30584) from the booster dialogs' ``boosterKey``, a currency id
    (bundle lines 55905, 100060, 100154, 100189, 100221).
    """

    command = "cra"

    source_x: int = Field(alias="SX", description="Attacking castle's map x")
    source_y: int = Field(alias="SY", description="Attacking castle's map y")
    target_x: int = Field(alias="TX", description="Target map x")
    target_y: int = Field(alias="TY", description="Target map y")
    kingdom_id: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The attacking castle's kingdom")
    commander_id: int = Field(
        alias="LID",
        description=(
            "A Commander.commander_id from client.commanders.get_commanders(); "
            "0 is the free starting commander, -14 the premium one"
        ),
    )
    wait_time: int = Field(alias="WT", default=0, description="Wait time the attack is sent with")
    horses_type: int = Field(alias="HBW", default=-1, description="The horse's wod id, -1 for none or for feathers")
    use_premium_commander: int = Field(
        alias="BPC",
        default=0,
        description=(
            "1 when the premium commander (commander_id -14) leads, which uses a premium commander or"
            " costs rubies; 0 for any other commander"
        ),
    )
    attack_type: AttackType = Field(alias="ATT", default=AttackType.ATTACK, description="The kind of attack")
    share_battle_view: int = Field(alias="AV", default=0, description="1 to let others watch the battle")
    loot_priority: LootPriority = Field(alias="LP", default=LootPriority.NO, description="Resource to loot first")
    send_anyway: int = Field(
        alias="FC",
        default=0,
        description="1 to send although one of your attacks is already on its way there (after ATTACK_IN_PROGRESS)",
    )
    feathers: int = Field(alias="PTT", default=0, description="1 when the horse is paid with feathers")
    slowdown: int = Field(alias="SD", default=0, description="Slowdown offset in seconds")
    collector_attack: int = Field(alias="ICA", default=0, description="1 for a collector event attack")
    countdown: int = Field(alias="CD", default=99, description="Always 99")
    waves: list[AttackWave] = Field(alias="A", default_factory=list, description="The attack waves, front to back")
    collector_booster: list[list[int]] = Field(
        alias="BKS",
        default_factory=list,
        description="Collector event boosters as [currency_id, amount], such as 31 (samurai medal booster)",
    )
    support_tools: list[int] = Field(alias="AST", default_factory=list, description="Support tool wod ids")
    yard_wave: list[list[int]] = Field(
        alias="RW", default_factory=list, description="The courtyard wave as [unit_id, count] pairs"
    )
    auto_skip_cooldown: AutoSkipCooldownType = Field(
        alias="ASCT",
        default=AutoSkipCooldownType.OFF,
        description="How the target's cooldown is skipped when the attack lands",
    )

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a cra reply is the movement this sent: its target area (``AAM.M.TA``) is ``TX``/``TY``.

        Client: ``CRACommand`` (bundle line 125954) reads the new movement from ``AAM``,
        whose ``TA`` is the target area (``BasicMapmovementVO``). An army heading home
        targets your own castle and is not taken.
        """
        return isinstance(payload, dict) and movement_targets(payload.get("AAM"), self.target_x, self.target_y)


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
        alias="AAM", default=None, description="The created movement; None when there is none"
    )
    currencies: CurrencyBlock = Field(
        alias="gcu", default=None, description="Coins and rubies after the send; None when the reply has none"
    )
    owners: list[MovementOwner] = Field(
        alias="O",
        default_factory=list,
        description="Owner records for the movement's areas",
    )
    arrival_seconds: int | float | None = Field(
        alias="TS",
        default=None,
        description="On ATTACK_IN_PROGRESS: seconds until the attack already on its way arrives",
    )
    army_size: int | float | None = Field(
        alias="AS", default=None, description="On ATTACK_IN_PROGRESS: the size of the attack already on its way"
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
        return read_or_none(handler, value, warn=logger, what="the movement created by cra")

    @field_validator("owners", mode="before")
    @classmethod
    def _readable_owners(cls, value: object) -> list[MovementOwner]:
        return readable_list(
            MovementOwner,
            value,
            accept=lambda record: isinstance(record, dict),
            keep=lambda record: js_truthy(record.get("OID")),
            warn=logger,
            what="owner records sent with cra",
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


__all__ = [
    "CreateAttackRequest",
    "CreateAttackResponse",
]
