"""Spy protocol models.

Commands:
- csm: Send spy mission
- ssi: Spy screen info
- ssu: Auto-spy, a report without sending spies
- gms: Maximum spies, a login section and push
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field, ValidatorFunctionWrapHandler, field_validator, model_validator

from empire_core.enums import Kingdom, SpyType
from empire_core.map.models import KingdomProtection, MapAreaItem, MapObject, parse_area_rows
from empire_core.messages.models import SpyReportResponse
from empire_core.movements.models import MovementOwner, MovementSpy, MovementWrapper
from empire_core.protocol.base import (
    BasePayload,
    BaseRequest,
    BaseResponse,
    CurrencyBlock,
    object_or_none,
    read_or_none,
    readable_list,
)
from empire_core.protocol.js import ClientInt, js_same_number, js_truthy, movement_targets

from .risk import row_risk_flags

logger = logging.getLogger(__name__)

# =============================================================================
# CSM - Send Spy Mission
# =============================================================================


class SendSpyRequest(BaseRequest):
    """
    Send a spy mission to a target.

    Command: csm
    Payload: {"SID": castle_id, "TX": target_x, "TY": target_y, "SC": spy_count, "ST": spy_type,
              "SE": accuracy_or_damage, "HBW": horse_booster_id, "KID": target_kingdom, "PTT": feathers,
              "SD": slowdown}

    The keys follow the client's order. ``SE`` is the damage (10-50) for a
    sabotage mission and the accuracy (50-100) for any other; the client
    sends the slider's value unrounded. A horse paid with feathers goes out as
    ``HBW`` -1 with ``PTT`` 1: with ``feathers`` 1 the horse is sent as
    -1, as the client's constructor does. Plague monks are not sent with
    ``csm``.

    Client: ``C2SCreateSpyMovementVO`` (bundle lines 100126-100127), built by
    ``CastlePostSpyDialog.spyCastle`` (bundle line 38459)
    """

    command = "csm"

    castle_id: int = Field(
        alias="SID",
        description=(
            "One of your castles, CastleInfo.castle_id from client.castle.get_all() or Castle.id from "
            "client.state.get_castles()"
        ),
    )
    target_x: int = Field(alias="TX", description="Target map x")
    target_y: int = Field(alias="TY", description="Target map y")
    spy_count: int = Field(alias="SC", default=1, description="How many spies to send")
    spy_type: SpyType = Field(alias="ST", default=SpyType.MILITARY, description="What the spies are sent to do")
    accuracy_or_damage: int = Field(
        alias="SE", default=100, description="Damage percent for a sabotage mission, accuracy percent for any other"
    )
    horse_booster_id: int = Field(
        alias="HBW", default=-1, description="The horse booster's wod id, -1 for none or when paid with feathers"
    )
    target_kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The target's kingdom")
    feathers: int = Field(alias="PTT", default=0, description="1 when the horse is paid with feathers")
    slowdown: int = Field(alias="SD", default=0, description="Seconds the arrival is delayed by")

    @model_validator(mode="after")
    def _feathers_send_no_horse(self) -> SendSpyRequest:
        # Client: HBW=int(u?-1:l), PTT=int(u?1:0)
        if self.feathers:
            self.horse_booster_id = -1
            self.feathers = 1
        return self

    def accepts_reply(self, payload: Any) -> bool:
        """Whether a csm reply is the movement this sent: its target area (``A.M.TA``) is ``TX``/``TY``.

        Client: ``CSMCommand`` (bundle line 125996) reads the new movement from ``A``,
        whose ``TA`` is the target area (``BasicMapmovementVO``). The spies' way home,
        which the server pushes as a csm too (seen live), targets your own castle and
        is not taken.
        """
        return isinstance(payload, dict) and movement_targets(payload.get("A"), self.target_x, self.target_y)


class SendSpyResponse(BaseResponse):
    """
    The spy mission the server created.

    Command: csm
    Payload::

        {"A": {"M": {movement}, "S": {"ST": spy_type, "SA": accuracy, "SC": spies, "SR": risk}},
         "O": [owner record, ...], "gcu": {currencies}}

    ``A`` is read like a ``gam`` entry; ``gcu`` may be missing.

    Client: ``CSMCommand.executeCommand`` (bundle line 125997), which passes
    ``[i.A]`` to ``CastleArmyData.parseMapMovementArray`` (bundle line 133626),
    ``i.O`` to ``CastleOtherPlayerData.parseOwnerInfoArray`` (bundle line 139005)
    and ``i.gcu`` to ``CurrencyData.parseGCU`` (bundle line 141191);
    ``SpyMapmovementVO.loadFromParamObject`` (bundle line 43747)
    """

    command = "csm"

    spy_movement: MovementWrapper | None = Field(
        alias="A", default=None, description="The spy movement; None when there is none"
    )
    owners: list[MovementOwner] = Field(
        alias="O", default_factory=list, description="Owner records for the movement's areas"
    )
    currencies: CurrencyBlock = Field(
        alias="gcu", default=None, description="Coins and rubies after the send; None when the reply has none"
    )

    @field_validator("spy_movement", mode="wrap")
    @classmethod
    def _movement_or_none(cls, value: object, handler: ValidatorFunctionWrapHandler) -> MovementWrapper | None:
        if not value:
            return None
        return read_or_none(handler, value, warn=logger, what="the movement created by csm")

    @field_validator("owners", mode="before")
    @classmethod
    def _readable_owners(cls, value: object) -> list[MovementOwner]:
        return readable_list(
            MovementOwner,
            value,
            accept=lambda record: isinstance(record, dict),
            keep=lambda record: js_truthy(record.get("OID")),
            warn=logger,
            what="owner records sent with csm",
        )

    @property
    def movement_id(self) -> int | None:
        """The spy movement's id, or None when the reply has no movement."""
        return self.spy_movement.movement.movement_id if self.spy_movement else None

    @property
    def seconds_until_arrival(self) -> int | None:
        """
        Seconds from the reply until the spies arrive: ``TT - PT``, never below 0.

        Client: ``BasicMapmovementVO.loadFromParamObject`` (bundle line 19382)
        """
        if not self.spy_movement:
            return None
        movement = self.spy_movement.movement
        return max(0, movement.total_time - movement.progress_time)

    @property
    def spy(self) -> MovementSpy | None:
        """The mission's spy type, accuracy or damage, spy count and risk."""
        return self.spy_movement.spy if self.spy_movement else None


# =============================================================================
# SSI - Spy Screen Info
# =============================================================================


class SpyScreenInfoRequest(BaseRequest):
    """
    Get what a spy mission against a target would face: its guards and the spies at hand.

    Command: ssi
    Payload: {"TX": target_x, "TY": target_y, "KID": target_kingdom}

    Client: ``C2SGetSpyInfo`` (bundle lines 22504-22505), sent with the target's
    ``absAreaPos`` and ``kingdomID`` when the spy dialog opens (bundle line 14800)
    """

    command = "ssi"

    target_x: int = Field(alias="TX", description="Target map x")
    target_y: int = Field(alias="TY", description="Target map y")
    target_kingdom: Kingdom = Field(alias="KID", default=Kingdom.GREEN, description="The target's kingdom")

    def accepts_reply(self, payload: Any) -> bool:
        """Whether an ssi reply is about this target: its ``TX``/``TY``, when both are set, are the ones asked for.

        Client: ``CastleSpyData.parse_SSI`` (bundle line 139962) passes the reply's
        position only when ``TX`` and ``TY`` are both truthy, and
        ``CastleSpyDialog.onPreSpyInfoUpdate`` (bundle line 16398) ignores a reply
        whose position is not the target's.
        """
        if not isinstance(payload, dict):
            return False
        x, y = payload.get("TX"), payload.get("TY")
        if not (js_truthy(x) and js_truthy(y)):
            return True
        return js_same_number(x, self.target_x) and js_same_number(y, self.target_y)


class SpyTargetArea(BasePayload):
    """
    The target's map rows and owner records, and your own protection: the ``gaa`` block of ``ssi``.

    Client: ``CastleSpyData.parse_SSI`` (bundle line 139962), which reads
    ``uap`` with ``parse_UAP``, ``OI`` with ``parseOwnerInfoArray`` and ``AI``
    with ``parseAreaInfos``, as a map area reply
    """

    kingdom_id: int | None = Field(alias="KID", default=None, description="The target's kingdom")
    protection: KingdomProtection | None = Field(alias="uap", default=None, description="Your own protection")
    owners: list[MapObject] = Field(alias="OI", default_factory=list, description="Owner records of the rows")
    rows: list[MapAreaItem] = Field(alias="AI", default_factory=list, description="The target's map rows")

    @field_validator("protection", mode="before")
    @classmethod
    def _protection_needs_an_object(cls, value: Any) -> Any:
        return object_or_none(value)

    @field_validator("owners", mode="before")
    @classmethod
    def _readable_owners(cls, value: Any) -> list[MapObject]:
        return readable_list(
            MapObject,
            value,
            accept=lambda record: isinstance(record, dict),
            warn=logger,
            what="owner records sent with ssi",
        )

    @field_validator("rows", mode="before")
    @classmethod
    def _readable_rows(cls, value: Any) -> list[MapAreaItem]:
        rows, skipped = parse_area_rows(value)
        if skipped:
            logger.warning(f"Skipped {skipped} unreadable map rows sent with ssi")
        return rows


class SpyScreenInfoResponse(BaseResponse):
    """
    What a spy mission against a target would face, and the spies at hand.

    Command: ssi
    Payload::

        {"AS": available_spies, "GC": guards, "APM": available_plague_monks,
         "TPM": total_plague_monks, "TX": x, "TY": y,
         "gaa": {"KID": kingdom, "uap": {protection}, "OI": [owner records], "AI": [map rows]}}

    The client reads ``gaa.uap`` without a check; a reply without ``gaa``
    still parses here.

    Client: ``SSICommand.executeCommand`` (bundle line 128554),
    ``CastleSpyData.parse_SSI`` (bundle line 139962)
    """

    command = "ssi"

    available_spies: ClientInt = Field(alias="AS", default=0, description="Spies free to send")
    guard_count: ClientInt = Field(alias="GC", default=0, description="Guards at the target")
    available_plague_monks: ClientInt = Field(alias="APM", default=0, description="Plague monks free to send")
    total_plague_monks: ClientInt = Field(alias="TPM", default=0, description="Plague monks owned")
    target_x: int | None = Field(alias="TX", default=None, description="The target's map x; None when not sent")
    target_y: int | None = Field(alias="TY", default=None, description="The target's map y; None when not sent")
    target_area: SpyTargetArea = Field(
        alias="gaa", default_factory=SpyTargetArea, description="The target's map rows and owner records"
    )

    @model_validator(mode="before")
    @classmethod
    def _position_needs_both(cls, data: Any) -> Any:
        # Client: e.TX&&e.TY?[vo,new Point(e.TX,e.TY)]:[vo]
        if isinstance(data, dict) and not (js_truthy(data.get("TX")) and js_truthy(data.get("TY"))):
            data = {key: value for key, value in data.items() if key not in ("TX", "TY")}
        return data

    @field_validator("target_area", mode="before")
    @classmethod
    def _area_needs_an_object(cls, value: Any) -> Any:
        return object_or_none(value) or {}

    def target_row(self, x: int | None = None, y: int | None = None) -> MapAreaItem | None:
        """
        The target's map row: the one at ``x``/``y``, by default the reply's own position.

        Falls back to the only row when there is exactly one, and None otherwise.
        """
        x = self.target_x if x is None else x
        y = self.target_y if y is None else y
        rows = self.target_area.rows
        at = next((row for row in rows if (row.x, row.y) == (x, y)), None)
        if at is not None:
            return at
        return rows[0] if len(rows) == 1 else None

    def target_owner(self, x: int | None = None, y: int | None = None) -> MapObject | None:
        """The owner record of the target's owner, when the target row names a player that has one."""
        row = self.target_row(x, y)
        if row is None or row.owner_id is None or row.owner_id < 0:
            return None
        return next((owner for owner in self.target_area.owners if owner.owner_id == row.owner_id), None)

    def risk_flags(self, x: int | None = None, y: int | None = None) -> tuple[bool, bool] | None:
        """
        The client's ``(isDungeon, isPlayer)`` for the target, or None when its owner cannot be told.

        See :func:`~empire_core.spy.risk.row_risk_flags`.
        """
        row = self.target_row(x, y)
        return row_risk_flags(row.raw_data) if row is not None else None


# =============================================================================
# SSU - Auto-spy
# =============================================================================


class AutoSpyRequest(BaseRequest):
    """
    Spy a target at once, without sending spies: the auto-spy subscription's button.

    Command: ssu
    Payload: {"TX": target_x, "TY": target_y}

    The client offers it only while ``subscriptionData.isAutoSpyActiveForArea``
    holds for the target.

    Client: ``C2SSpySpyUnits`` (bundle lines 42828-42829), sent by
    ``ButtonAutoSpyComponent.onClick`` (bundle line 109977) and
    ``CastleMapobjectInfoComponent.onClickSpyIcon`` (bundle line 66479)
    """

    command = "ssu"

    target_x: int = Field(alias="TX", description="Target map x")
    target_y: int = Field(alias="TY", description="Target map y")


class AutoSpyResponse(SpyReportResponse):
    """
    An auto-spy report, the same shape as a ``bsd`` spy report.

    Command: ssu

    The client builds it with ``CastleSpyLogVO.parseSpyLog`` as ``bsd`` does,
    but does not store the ``OI`` and ``SO`` owner records.

    Client: ``SSUCommand.executeCommand`` (bundle lines 128568-128573)
    """

    command = "ssu"


# =============================================================================
# GMS - Maximum spies
# =============================================================================


class MaxSpiesResponse(BaseResponse):
    """
    How many spies you have, before research, title and legend skill boosts.

    Command: gms, as a login section of ``gbd`` and as a push. The client
    never sends a ``gms`` request.

    Client: ``GMSCommand.executeCommand`` (bundle line 120555),
    ``CastleSpyData.parse_GMS`` (bundle line 139979), read from ``gbd``
    (bundle line 129381)
    """

    command = "gms"

    max_spies: ClientInt = Field(alias="MS", default=0, description="Spies owned, before boosts")
    bonus_spies: ClientInt = Field(alias="BS", default=0, description="Bonus spies, not part of the spy count")


__all__ = [
    "AutoSpyRequest",
    "AutoSpyResponse",
    "MaxSpiesResponse",
    "SendSpyRequest",
    "SendSpyResponse",
    "SpyScreenInfoRequest",
    "SpyScreenInfoResponse",
    "SpyTargetArea",
]
