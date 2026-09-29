"""
Spy service for high-level espionage operations.
"""

import logging
import queue
import time
from dataclasses import dataclass, field

from pydantic import ValidationError

from empire_core.army.spy_army import SpyArmy
from empire_core.commanders.models.roster import Castellan
from empire_core.enums import Kingdom, SpyType
from empire_core.exceptions import CommandError, EmpireError
from empire_core.messages.models import (
    BattleSpyDataRequest,
    BattleSpyDataResponse,
    ForwardSpyLogRequest,
    MessageInfo,
    SpyCastleInfo,
    SystemNotificationEvent,
)
from empire_core.movements.models import MovementRecord
from empire_core.protocol.base import parse_response
from empire_core.protocol.js import js_parse_int
from empire_core.protocol.packet import Packet
from empire_core.services.base import BaseService, register_service

from .models import SendSpyRequest, SendSpyResponse, SpyScreenInfoRequest, SpyScreenInfoResponse
from .risk import MAX_ACCURACY, MAX_RISK_SPY, plan_mission

logger = logging.getLogger(__name__)

# MessageConst in the game client (dll line 19516). A spy log is a loss when
# the attacker failed or the defender succeeded (AMessageSpyVO.isFailedSpyLog).
_MESSAGE_TYPE_SPY_PLAYER = 3
_MESSAGE_TYPE_SPY_NPC = 4
_SUBTYPE_SPY_SABOTAGE = 0
_SUBTYPE_SPY_PLAGUE_MONK = 3
_SUBTYPE_ATTACKER_SUCCESS = 0
_SUBTYPE_DEFENDER_SUCCESS = 1
_SUBTYPE_ATTACKER_FAILED = 2
_SUBTYPE_DEFENDER_FAILED = 3
_LOST_SPY_RESULTS = frozenset({_SUBTYPE_DEFENDER_SUCCESS, _SUBTYPE_ATTACKER_FAILED})
_REPORT_MARGIN = 10.0
_POLL_SECONDS = 1.0


@dataclass(frozen=True)
class _SpyHeader:
    """What a spy log's header names: ``subtypeSpy+subtypeResult+areaType#kingdomID+ownerID+areaName``."""

    subtype_spy: int | None
    result: int | None
    area_type: int | None = None
    kingdom_id: int | None = None
    owner_id: int | None = None
    area_name: str | None = None


def _parse_spy_header(message: MessageInfo) -> _SpyHeader | None:
    """The header of a spy log from an ``sne`` message, or None when the message is no readable spy log.

    A sabotage or plague success names the area by name and id instead of
    kingdom and owner; a military mission never gets that layout.

    Client: ``CastleMessageFactory.parseMessage`` (bundle line 135102),
    ``MessageSpyPlayerVO.parseMessageHeader`` (bundle line 137651),
    ``MessageSpyNpcVO.parseMessageHeader`` (bundle line 137635)
    """
    message_type = message.message_type
    if message_type not in (_MESSAGE_TYPE_SPY_PLAYER, _MESSAGE_TYPE_SPY_NPC):
        return None
    head, _, meta = message.header.partition("#")
    if not meta:
        # MessageSpyPlayerVO reads nothing without the part after '#'; MessageSpyNpcVO throws
        return None
    subtypes = head.split("+")
    area = meta.split("+")
    subtype_spy = js_parse_int(subtypes[0])
    result = js_parse_int(subtypes[1]) if len(subtypes) > 1 else None
    area_type = js_parse_int(subtypes[2]) if len(subtypes) > 2 else None
    if (
        message_type == _MESSAGE_TYPE_SPY_PLAYER
        and subtype_spy in (_SUBTYPE_SPY_SABOTAGE, _SUBTYPE_SPY_PLAGUE_MONK)
        and result in (_SUBTYPE_ATTACKER_SUCCESS, _SUBTYPE_DEFENDER_FAILED)
    ):
        return _SpyHeader(subtype_spy, result, area_type, area_name=area[0])
    return _SpyHeader(
        subtype_spy,
        result,
        area_type,
        kingdom_id=js_parse_int(area[0]),
        owner_id=js_parse_int(area[1]) if len(area) > 1 else None,
        area_name=area[2] if len(area) > 2 else None,
    )


def _names_target(header: _SpyHeader, target: MovementRecord | None, target_kingdom: Kingdom) -> bool:
    """Whether a spy log's header names this mission's target.

    Without the csm movement only the kingdom can be compared; the report's
    position is checked once it is read.
    """
    if header.result is None or header.kingdom_id is None:
        return False
    if target is None:
        return header.kingdom_id == target_kingdom
    area = target.target_area
    if header.kingdom_id != target.kingdom_id or header.owner_id != target.target_id:
        return False
    if area is not None and header.area_type is not None and header.area_type != area.area_type:
        return False
    return not (area is not None and area.name and header.area_name != area.name)


@dataclass
class SpyResult:
    """Outcome of an instant spy mission.

    The payload fields mirror :class:`~empire_core.messages.models.BattleSpyDataResponse`
    and default to empty containers on failure, so callers can read them without
    a ``None`` check.

    Attributes:
        success: whether a spy report was retrieved.
        reason: machine-readable failure tag when ``success`` is False.
        message_id: id of the report message the server created.
        spy_data: the report's ``S`` block -- one entry per defending
            position, each a list of ``[unit_id, count]`` pairs.
        army: the same block split by position (left/middle/right flanks, keep,
            stronghold, support, reserve). None when the report carried nothing
            usable.
        defending_castellan: the castellan defending the spied castle, the
            report's ``B``, or ``None`` if it carried none.
        target: the spied castle, or ``None`` if the server sent no ``AI`` block.
    """

    success: bool
    reason: str | None = None
    message_id: int | None = None
    spy_data: list[list[list[int]]] = field(default_factory=list)
    defending_castellan: Castellan | None = None
    target: SpyCastleInfo | None = None
    army: SpyArmy | None = None


@register_service("spy")
class SpyService(BaseService):
    """Service for managing spy operations."""

    def forward_report(self, message_id: int, player_ids: list[int]) -> bool:
        """Share a spy report with other players in game.

        Returns False when the server rejects it — a report can age out of the
        mailbox, and the recipients may no longer be reachable.

        Args:
            message_id: The report's message id: ``SpyResult.message_id`` from
                :meth:`execute_instant_spy`, or a ``MessageInfo.message_id`` from an ``sne`` push
            player_ids: The recipients. The client offers the members of your alliance
                other than you, ``AllianceMember.player_id`` from
                ``client.alliance.get_local_members()``

        Client: ``CastleForwardMessageDialog.fillList`` and ``sendMessage`` (bundle line 60719)
        """
        if not player_ids:
            return False
        return self.execute(ForwardSpyLogRequest(PID=list(player_ids), MID=message_id))

    def execute_instant_spy(
        self,
        source_castle_id: int,
        target_x: int,
        target_y: int,
        target_kingdom: Kingdom = Kingdom.GREEN,
        risk_tolerance: int | None = None,
        accuracy: int = MAX_ACCURACY,
        horses_type: int = -1,
        feathers: bool = False,
        slowdown: int = 0,
        max_wait: float | None = None,
    ) -> SpyResult:
        """
        Send a military spy mission and read its report.

        Nothing is paid unless asked: by default the spies travel without a
        horse. ``feathers`` uses the instant spy horse, paid with feathers,
        which the client sends as ``HBW`` -1 with ``PTT`` 1 and which wins over
        ``horses_type``, as in the client.

        The report arrives as an ``sne`` push once the spies get there. Every
        ``sne`` in the wait is looked at without being taken from other
        listeners; only a spy log whose header names this mission's target
        (kingdom, owner, area type and name, from the csm reply's movement)
        and whose report is for the target's position counts, the rest are
        skipped. ``sne`` carries no mission id, so two missions to the same
        target at once cannot be told apart.

        Blocks the calling thread for up to ~10s while polling for spy
        availability, then until the spies arrive (the csm reply's travel
        time) plus 10s for the report, or ``max_wait`` if that is shorter —
        do not call this from a state callback.

        Args:
            source_castle_id: The castle the spies leave from, one of yours: ``CastleInfo.castle_id``
                from ``client.castle.get_all()`` or ``Castle.id`` from ``client.state.get_castles()``
            target_x: Target X coordinate
            target_y: Target Y coordinate
            target_kingdom: Target kingdom
            risk_tolerance: Ceiling on the chance of being caught, as a
                percentage. Missions always run at the lowest risk the spy pool
                allows; this only decides whether to send at all, so a target
                that stays above it is skipped rather than spied badly.
            accuracy: Spy accuracy (50-100). Lower values need fewer spies for
                the same risk but return a less complete report.
            horses_type: A horse's wod id to speed the spies up (-1 = none);
                sent as -1 whenever feathers are used, as the client does
            feathers: Use the instant spy horse and pay for it with feathers
            slowdown: Seconds to delay the arrival by
            max_wait: Most seconds to wait for the report after the csm reply;
                None waits for the trip plus 10s

        Client: ``CastlePostSpyDialog.spyCastle`` (bundle line 38457),
        ``C2SCreateSpyMovementVO`` (bundle line 100126),
        ``HorseTravelboosterVO.isPayedWithPegasusTickets`` (bundle line 118825)

        Returns:
            SpyResult with the spy report data or a failure reason.
        """
        _SSI_POLL_ATTEMPTS = 5
        _SSI_POLL_DELAY = 2  # seconds between retries

        ssi_req = SpyScreenInfoRequest(
            TX=target_x,
            TY=target_y,
            KID=target_kingdom,
        )

        max_risk = risk_tolerance if risk_tolerance is not None else MAX_RISK_SPY

        available = 0
        plan = None
        for attempt in range(_SSI_POLL_ATTEMPTS):
            try:
                ssi_resp = self.request(ssi_req, SpyScreenInfoResponse)
            except EmpireError as e:
                return SpyResult(success=False, reason=f"ssi_failed_{_error_tag(e)}")

            available = ssi_resp.available_spies
            if available > 0:
                plan = plan_mission(
                    guards=ssi_resp.guard_count,
                    available=available,
                    accuracy=accuracy,
                    max_risk=max_risk,
                )
                if plan is not None:
                    break

            # Spies still walking home. A fuller pool lowers the achievable
            # risk, so waiting can bring an over-budget target into range.
            if attempt < _SSI_POLL_ATTEMPTS - 1:
                time.sleep(_SSI_POLL_DELAY)

        if available <= 0:
            return SpyResult(success=False, reason="no_spies_available")

        if plan is None:
            # Even the whole pool leaves this target above the risk ceiling.
            return SpyResult(success=False, reason="risk_over_budget")

        csm_req = SendSpyRequest(
            SID=source_castle_id,
            TX=target_x,
            TY=target_y,
            KID=target_kingdom,
            SC=plan.spies,
            ST=SpyType.MILITARY,
            # The plan may have traded detail for risk; send what it settled on.
            SE=plan.accuracy,
            HBW=-1 if feathers else horses_type,
            PTT=1 if feathers else 0,
            SD=slowdown,
        )

        # Subscribed before csm is sent so the report can't slip past; a
        # subscriber sees every sne without taking it from anyone else.
        notifications: queue.Queue[Packet] = queue.Queue()
        connection = self.client.connection
        connection.subscribe("sne", notifications.put)
        try:
            try:
                csm_resp = self.request(csm_req, SendSpyResponse)
            except EmpireError as e:
                return SpyResult(success=False, reason=f"csm_failed_{_error_tag(e)}")

            movement = csm_resp.spy_movement.movement if csm_resp.spy_movement else None
            if movement is None:
                logger.warning(
                    "The csm reply has no readable movement; waiting only %ss for the report", _REPORT_MARGIN
                )
            wait = (csm_resp.seconds_until_arrival or 0) + _REPORT_MARGIN
            if max_wait is not None:
                wait = min(wait, max_wait)
            return self._await_report(
                notifications, time.monotonic() + wait, movement, target_x, target_y, target_kingdom
            )
        finally:
            connection.unsubscribe("sne", notifications.put)

    def _await_report(
        self,
        notifications: "queue.Queue[Packet]",
        deadline: float,
        target: MovementRecord | None,
        target_x: int,
        target_y: int,
        target_kingdom: Kingdom,
    ) -> SpyResult:
        """Read ``sne`` pushes until one is this mission's report, or the deadline passes."""
        missed = "sne_timeout"
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                packet = notifications.get(timeout=min(remaining, _POLL_SECONDS))
            except queue.Empty:
                if not self.client.connection.connected:
                    return SpyResult(success=False, reason="disconnected")
                continue
            for message in _spy_messages(packet):
                header = _parse_spy_header(message)
                if header is None or not _names_target(header, target, target_kingdom):
                    continue
                if header.result in _LOST_SPY_RESULTS:
                    return SpyResult(success=False, reason="spy_caught", message_id=message.message_id)
                try:
                    bsd_resp = self.request(BattleSpyDataRequest(MID=message.message_id), BattleSpyDataResponse)
                except EmpireError as e:
                    return SpyResult(success=False, reason=f"bsd_failed_{_error_tag(e)}")

                report_target = bsd_resp.target
                if report_target is not None and report_target.x >= 0 and report_target.y >= 0:
                    if (report_target.x, report_target.y) != (target_x, target_y):
                        # Another area with the same owner, e.g. one of many robber barons.
                        missed = "report_target_mismatch"
                        continue

                if not bsd_resp.spy_data:
                    # A report with no army block was never read: the castle is not
                    # empty, the mission just brought nothing back.
                    return SpyResult(success=False, reason="no_spy_data", message_id=message.message_id)

                return SpyResult(
                    success=True,
                    army=SpyArmy.from_spy_data(bsd_resp.spy_data),
                    message_id=message.message_id,
                    spy_data=bsd_resp.spy_data,
                    defending_castellan=bsd_resp.defending_castellan,
                    target=bsd_resp.target,
                )
        return SpyResult(success=False, reason=missed)


def _spy_messages(packet: Packet) -> list[MessageInfo]:
    """The messages of an ``sne`` push; none when it cannot be read."""
    if packet.error_code != 0 or not isinstance(packet.payload, dict):
        return []
    try:
        event = parse_response("sne", packet.payload)
    except ValidationError:
        return []
    return event.messages if isinstance(event, SystemNotificationEvent) else []


def _error_tag(e: Exception) -> str:
    """Short machine-readable tag for a failure reason."""
    if isinstance(e, CommandError):
        return str(e.code)
    return type(e).__name__
