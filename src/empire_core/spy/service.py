"""
Spy service for high-level espionage operations.
"""

from __future__ import annotations

import logging
import math
import queue
import time
from dataclasses import dataclass

from pydantic import ValidationError

from empire_core.army.spy_army import SpyArmy
from empire_core.enums import Kingdom, SpyLogType, SpyOutcome, SpyStep, SpyType
from empire_core.exceptions import CommandError, EmpireError
from empire_core.messages.models import (
    ForwardSpyLogRequest,
    GetSpyReportRequest,
    MessageInfo,
    SpyLogHeader,
    SpyReportResponse,
    SystemNotificationEvent,
)
from empire_core.movements.models import MovementRecord
from empire_core.protocol.base import parse_response
from empire_core.protocol.errors import GGEError
from empire_core.protocol.packet import Packet
from empire_core.services.base import BaseService

from .models import (
    AutoSpyRequest,
    AutoSpyResponse,
    SendSpyRequest,
    SendSpyResponse,
    SpyScreenInfoRequest,
    SpyScreenInfoResponse,
)
from .risk import (
    MAX_ACCURACY,
    MAX_DAMAGE,
    MAX_RISK_SABOTAGE,
    MAX_RISK_SPY,
    MIN_DAMAGE,
    max_sabotage_damage,
    plan_mission,
    plan_sabotage,
)

logger = logging.getLogger(__name__)

# BSDCommand.executeCommand (bundle line 125223) shows "no spy data" for these
_NO_REPORT_ERRORS = frozenset({GGEError.NO_SPY_DATA, GGEError.NO_SUCH_MESSAGE})
_REPORT_MARGIN = 10.0
# Mission types and log subtypes are numbered differently (ClientConstCastle.SPYTYPE_*, MessageConst.SUBTYPE_SPY_*).
# A military log is DEFENCE: its success lists the army (hasDetailedSpyLog, bundle lines 137642, 137672),
# and a live military mission's log header began "1+".
_LOG_TYPE_OF_MISSION = {SpyType.MILITARY: SpyLogType.DEFENCE, SpyType.ECO: SpyLogType.ECO}
_POLL_SECONDS = 1.0
_SSI_POLL_DELAY = 2.0


@dataclass
class SpyResult:
    """
    Outcome of a spy mission.

    Attributes:
        outcome: How the mission ended; ``success`` is ``outcome is SpyOutcome.SUCCESS``.
        step: The command the mission ended at; None when it ended between
            commands (no spies, risk) or was read to the end.
        error: The exception that ended the mission, for ``COMMAND_FAILED``
            and a ``bsd`` without a report; branch on it as on any
            :class:`~empire_core.exceptions.CommandError`.
        message_id: The report's message id, once a report for the mission arrived.
        report: The spy report, when one was read.
        mission: The csm reply for the mission sent, with its movement and risk.
    """

    outcome: SpyOutcome
    step: SpyStep | None = None
    error: EmpireError | None = None
    message_id: int | None = None
    report: SpyReportResponse | None = None
    mission: SendSpyResponse | None = None

    @property
    def success(self) -> bool:
        """Whether the report was read."""
        return self.outcome is SpyOutcome.SUCCESS

    @property
    def army(self) -> SpyArmy | None:
        """The report's defenders by position, or None without a report or army."""
        return self.report.army() if self.report is not None else None


def _names_target(
    header: SpyLogHeader, target: MovementRecord | None, target_kingdom: Kingdom, spy_type: SpyType
) -> bool:
    """
    Whether a spy log's header is for this kind of mission and names its target.

    ``sne`` carries no mission id, so the header's kingdom, owner, area type
    and name are matched against the csm reply's movement; without the
    movement only the kingdom can be compared. The report's position is
    checked once it is read. An empty name in the header is unknown, not a
    mismatch: the client names such an area itself.

    Client: ``MessageSpyPlayerVO.parseSender`` (bundle line 137666)
    """
    if header.result is None or header.kingdom_id is None or header.log_type != _LOG_TYPE_OF_MISSION[spy_type]:
        return False
    if target is None:
        return header.kingdom_id == target_kingdom
    area = target.target_area
    if header.kingdom_id != target.kingdom_id or header.owner_id != target.target_id:
        return False
    if area is not None and header.area_type is not None and header.area_type != area.area_type:
        return False
    return not (area is not None and area.name and header.area_name and header.area_name != area.name)


class SpyService(BaseService):
    """Service for managing spy operations."""

    def forward_report(self, message_id: int, player_ids: list[int]) -> bool:
        """Share a spy report with other players in game.

        Returns False when the server rejects it — a report can age out of the
        mailbox, and the recipients may no longer be reachable. A recipient
        who has the report already (error 167) counts as done, as in the client.

        Args:
            message_id: The report's message id: ``SpyResult.message_id``, or a
                ``MessageInfo.message_id`` of a spy log
            player_ids: The recipients. The client offers the members of your alliance
                other than you, ``AllianceMember.player_id`` from
                ``client.alliance.get_local_members()``

        Client: ``CastleForwardMessageDialog.fillList`` and ``sendMessage`` (bundle lines 60719, 60740),
        ``MFSCommand.executeCommand`` (bundle line 125409)
        """
        if not player_ids:
            return False
        try:
            self.client.send(ForwardSpyLogRequest(MID=message_id, PID=list(player_ids)), wait=True)
        except CommandError as e:
            if e.error is GGEError.ALREADY_HAS_SPY_REPORT:
                return True
            logger.warning(f"Action 'mfs' rejected: {e}")
            return False
        return True

    def get_screen_info(
        self, target_x: int, target_y: int, target_kingdom: Kingdom = Kingdom.GREEN
    ) -> SpyScreenInfoResponse:
        """
        What a mission against a target would face: its guards, your free spies and the target's map row.

        Raises:
            CommandError: The server refused, e.g. for a target you cannot spy

        Client: ``C2SGetSpyInfo`` (bundle line 22504), ``CastleSpyData.parse_SSI`` (bundle line 139962)
        """
        return self.request(SpyScreenInfoRequest(TX=target_x, TY=target_y, KID=target_kingdom), SpyScreenInfoResponse)

    def get_report(self, message_id: int) -> SpyReportResponse | None:
        """
        Read any spy report in the mailbox by its message id.

        Returns None when the server has no report for it (error 130
        NO_SPY_DATA or 66 NO_SUCH_MESSAGE), which the client shows as "no spy data".

        Args:
            message_id: A spy log's ``MessageInfo.message_id`` from an ``sne`` push or the
                mailbox, or ``SpyResult.message_id``

        Raises:
            CommandError: The server refused for another reason

        Client: ``CastleSpyData.getSpyLog`` (bundle line 139963), ``BSDCommand.executeCommand``
        (bundle line 125223)
        """
        try:
            return self.request(GetSpyReportRequest(MID=message_id), SpyReportResponse)
        except CommandError as e:
            if e.error in _NO_REPORT_ERRORS:
                return None
            raise

    def auto_spy(self, target_x: int, target_y: int) -> AutoSpyResponse:
        """
        Spy a target at once with the auto-spy subscription: no spies, no movement, no mail.

        The client offers this only while the subscription covers the target;
        what the server answers without it is untested.

        Raises:
            CommandError: The server refused

        Client: ``ButtonAutoSpyComponent.onClick`` (bundle line 109977), ``SSUCommand.executeCommand``
        (bundle line 128568)
        """
        return self.request(AutoSpyRequest(TX=target_x, TY=target_y), AutoSpyResponse)

    def spies_in_use(self) -> int:
        """
        Spies on your own spy movements, as the state tracks them.

        The client counts free spies as all spies minus these; all spies are
        ``MaxSpiesResponse.max_spies`` plus research, title and legend skill
        boosts, which this library does not add up.

        Client: ``CastleSpyData.getNumAvailableSpies`` (bundle line 139970)
        """
        return sum(m.spy.spy_count for m in self.client.state.get_all_movements() if m.is_mine and m.spy is not None)

    def send_spy_mission(
        self,
        source_castle_id: int,
        target_x: int,
        target_y: int,
        target_kingdom: Kingdom = Kingdom.GREEN,
        *,
        spy_type: SpyType,
        spies: int,
        accuracy_or_damage: int,
        horse_booster_id: int = -1,
        feathers: bool = False,
        slowdown: int = 0,
    ) -> SendSpyResponse:
        """
        Send one spy mission as given, without planning it or waiting for its report.

        Args:
            source_castle_id: The castle the spies leave from, one of yours
            target_x: Target X coordinate
            target_y: Target Y coordinate
            target_kingdom: Target kingdom
            spy_type: MILITARY, ECO or SABOTAGE; plague monks are not sent this way
            spies: How many spies to send
            accuracy_or_damage: Accuracy percent (50-100), or damage percent (10-50) for sabotage
            horse_booster_id: A horse's wod id to speed the spies up (-1 = none)
            feathers: Use the instant spy horse and pay for it with feathers; wins over ``horse_booster_id``
            slowdown: Seconds to delay the arrival by

        Raises:
            ValueError: For ``SpyType.PLAGUE``
            CommandError: The server refused the mission

        Client: ``CastlePostSpyDialog.spyCastle`` (bundle line 38459), ``C2SCreateSpyMovementVO``
        (bundle line 100126)
        """
        if spy_type == SpyType.PLAGUE:
            raise ValueError("the client sends plague monks with cpm, not csm")
        request = SendSpyRequest(
            SID=source_castle_id,
            TX=target_x,
            TY=target_y,
            SC=spies,
            ST=spy_type,
            SE=accuracy_or_damage,
            HBW=horse_booster_id,
            KID=target_kingdom,
            PTT=1 if feathers else 0,
            SD=slowdown,
        )
        return self.request(request, SendSpyResponse)

    def execute_instant_spy(
        self,
        source_castle_id: int,
        target_x: int,
        target_y: int,
        target_kingdom: Kingdom = Kingdom.GREEN,
        risk_tolerance: int | None = None,
        accuracy: int = MAX_ACCURACY,
        *,
        spy_type: SpyType = SpyType.MILITARY,
        horse_booster_id: int = -1,
        feathers: bool = False,
        slowdown: int = 0,
        max_wait: float | None = None,
        wait_for_spies: float | None = None,
    ) -> SpyResult:
        """
        Send a military or economy spy mission and read its report.

        Nothing is paid unless asked: by default the spies travel without a
        horse. ``feathers`` uses the instant spy horse, paid with feathers,
        which the client sends as ``HBW`` -1 with ``PTT`` 1 and which wins over
        ``horse_booster_id``, as in the client.

        The mission is costed with the client's risk floor for the target:
        none for an NPC area such as a robber baron camp, 5% for a player's
        area and for NPCs the game fights like players. Where the ``ssi``
        reply does not tell whose area it is (see
        :func:`~empire_core.spy.risk.row_risk_flags`), the 5% floor is kept:
        the mission may then be planned at a higher risk than the client
        shows, and a ``risk_tolerance`` under 5 skips it.

        The report arrives as an ``sne`` push once the spies get there. Every
        ``sne`` in the wait is looked at without being taken from other
        listeners; only a spy log whose header names this mission's target
        (kingdom, owner, area type and name, from the csm reply's movement)
        and whose report, a caught mission's too, is for the target's position
        counts; the rest are skipped. ``sne`` carries no mission id, so two
        missions to the same target at once cannot be told apart.

        Asks ``ssi`` once: with no spy at home, or no mission within
        ``risk_tolerance``, it returns at once, as the client's spy dialog
        shows the pool as it is. ``wait_for_spies`` asks again every 2s for up
        to that many seconds, for spies still on their way home. Then it
        blocks until the spies arrive (the csm reply's travel time) plus 10s
        for the report, or ``max_wait`` if that is shorter; do not call this
        from a state callback.

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
            spy_type: MILITARY for the army, ECO for the resources. The client
                offers ECO only for castles and other players' outposts.
            horse_booster_id: A horse's wod id to speed the spies up (-1 = none);
                sent as -1 whenever feathers are used, as the client does
            feathers: Use the instant spy horse and pay for it with feathers
            slowdown: Seconds to delay the arrival by
            max_wait: Most seconds to wait for the report after the csm reply;
                None waits for the trip plus 10s
            wait_for_spies: Most seconds to keep asking ``ssi`` while no spy is at
                home or the risk is over ``risk_tolerance``; None asks once

        Client: ``CastlePostSpyDialog.spyCastle`` (bundle line 38459),
        ``CastleStartSpyVO.setSpyValues`` (bundle line 140004),
        ``CastleSpyDialogSpyState.fillSpyTypeList`` (bundle line 72238),
        ``HorseTravelboosterVO.isPayedWithPegasusTickets`` (bundle line 118825)

        Returns:
            SpyResult with the report or why there is none.
        """
        if spy_type not in (SpyType.MILITARY, SpyType.ECO):
            raise ValueError(f"execute_instant_spy sends MILITARY or ECO missions, not {spy_type!r}")
        max_risk = risk_tolerance if risk_tolerance is not None else MAX_RISK_SPY

        available = 0
        plan = None
        attempts = 1 + (math.ceil(wait_for_spies / _SSI_POLL_DELAY) if wait_for_spies and wait_for_spies > 0 else 0)
        for attempt in range(attempts):
            try:
                screen = self.get_screen_info(target_x, target_y, target_kingdom)
            except EmpireError as e:
                return SpyResult(SpyOutcome.COMMAND_FAILED, SpyStep.SSI, error=e)

            available = screen.available_spies
            if available > 0:
                flags = screen.risk_flags(target_x, target_y)
                dungeon, player_target = flags if flags is not None else (False, True)
                plan = plan_mission(
                    guards=screen.guard_count,
                    available=available,
                    accuracy=accuracy,
                    max_risk=max_risk,
                    player_target=player_target,
                    dungeon=dungeon,
                )
                if plan is not None:
                    break

            # Spies still walking home. A fuller pool lowers the achievable
            # risk, so waiting can bring an over-budget target into range.
            if attempt < attempts - 1:
                time.sleep(_SSI_POLL_DELAY)

        if available <= 0:
            return SpyResult(SpyOutcome.NO_SPIES_AVAILABLE)
        if plan is None:
            return SpyResult(SpyOutcome.RISK_OVER_BUDGET)

        # Subscribed before csm is sent so the report can't slip past; a
        # subscriber sees every sne without taking it from anyone else.
        notifications: queue.Queue[Packet] = queue.Queue()
        connection = self.client.connection
        connection.subscribe("sne", notifications.put)
        try:
            try:
                mission = self.send_spy_mission(
                    source_castle_id,
                    target_x,
                    target_y,
                    target_kingdom,
                    spy_type=spy_type,
                    spies=plan.spies,
                    # The plan may have traded detail for risk; send what it settled on.
                    accuracy_or_damage=plan.accuracy,
                    horse_booster_id=horse_booster_id,
                    feathers=feathers,
                    slowdown=slowdown,
                )
            except EmpireError as e:
                return SpyResult(SpyOutcome.COMMAND_FAILED, SpyStep.CSM, error=e)

            movement = mission.spy_movement.movement if mission.spy_movement else None
            if movement is None:
                logger.warning(
                    "The csm reply has no readable movement; waiting only %ss for the report", _REPORT_MARGIN
                )
            wait = (mission.seconds_until_arrival or 0) + _REPORT_MARGIN
            if max_wait is not None:
                wait = min(wait, max_wait)
            return self._await_report(
                notifications,
                time.monotonic() + wait,
                mission,
                movement,
                target_x,
                target_y,
                target_kingdom,
                spy_type=spy_type,
            )
        finally:
            connection.unsubscribe("sne", notifications.put)

    def send_sabotage(
        self,
        source_castle_id: int,
        target_x: int,
        target_y: int,
        target_kingdom: Kingdom = Kingdom.GREEN,
        damage: int = MIN_DAMAGE,
        risk_tolerance: int | None = None,
        *,
        horse_booster_id: int = -1,
        feathers: bool = False,
        slowdown: int = 0,
    ) -> SpyResult:
        """
        Send a sabotage mission with the fewest spies that reach the pool's lowest risk.

        Sabotage spies travel at a ninth of a spy's speed (``TRAVELSPEED_SABOTAGE``
        50 against 450). The report is not waited for: the outcome is
        ``SENT`` with the csm reply in ``mission``. The damage is checked
        against what the target's owner level allows when the ``ssi`` reply
        carries the owner's record; the client's other refusals (target kind,
        protection, cooldown) are left to the server.

        Args:
            source_castle_id: The castle the spies leave from, one of yours
            target_x: Target X coordinate
            target_y: Target Y coordinate
            target_kingdom: Target kingdom
            damage: Damage percent, 10 up to ``max_sabotage_damage(owner_level)``
            risk_tolerance: Ceiling on the chance of being caught, as a percentage
            horse_booster_id: A horse's wod id to speed the spies up (-1 = none)
            feathers: Use the instant spy horse and pay for it with feathers
            slowdown: Seconds to delay the arrival by

        Raises:
            ValueError: A damage the client would not send

        Client: ``CastleSpyDialogSabotageState.updateSpyVO`` and ``spyCastle`` (bundle lines
        72203-72205), ``ACastleSpyDialogState.updateSliderForDamage`` (bundle line 34360),
        ``CastleStartSpyVO.setSabotageValues`` (bundle line 140006)
        """
        if not MIN_DAMAGE <= damage <= MAX_DAMAGE:
            raise ValueError(f"sabotage damage must be {MIN_DAMAGE}-{MAX_DAMAGE}, got {damage}")
        max_risk = risk_tolerance if risk_tolerance is not None else MAX_RISK_SABOTAGE
        try:
            screen = self.get_screen_info(target_x, target_y, target_kingdom)
        except EmpireError as e:
            return SpyResult(SpyOutcome.COMMAND_FAILED, SpyStep.SSI, error=e)
        owner = screen.target_owner(target_x, target_y)
        if owner is not None and damage > (cap := max_sabotage_damage(owner.level)):
            raise ValueError(f"a level {owner.level} owner allows at most {cap} sabotage damage, not {damage}")
        if screen.available_spies <= 0:
            return SpyResult(SpyOutcome.NO_SPIES_AVAILABLE)
        plan = plan_sabotage(screen.guard_count, screen.available_spies, damage, max_risk)
        if plan is None:
            return SpyResult(SpyOutcome.RISK_OVER_BUDGET)
        try:
            mission = self.send_spy_mission(
                source_castle_id,
                target_x,
                target_y,
                target_kingdom,
                spy_type=SpyType.SABOTAGE,
                spies=plan.spies,
                accuracy_or_damage=plan.damage,
                horse_booster_id=horse_booster_id,
                feathers=feathers,
                slowdown=slowdown,
            )
        except EmpireError as e:
            return SpyResult(SpyOutcome.COMMAND_FAILED, SpyStep.CSM, error=e)
        return SpyResult(SpyOutcome.SENT, mission=mission)

    def _await_report(
        self,
        notifications: queue.Queue[Packet],
        deadline: float,
        mission: SendSpyResponse,
        target: MovementRecord | None,
        target_x: int,
        target_y: int,
        target_kingdom: Kingdom,
        *,
        spy_type: SpyType,
    ) -> SpyResult:
        """Read ``sne`` pushes until one is this mission's report, or the deadline passes."""
        missed = SpyOutcome.TIMEOUT
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                packet = notifications.get(timeout=min(remaining, _POLL_SECONDS))
            except queue.Empty:
                if not self.client.connection.connected:
                    return SpyResult(SpyOutcome.DISCONNECTED, SpyStep.SNE, mission=mission)
                continue
            for message in _spy_messages(packet):
                header = message.spy_log_header()
                if header is None or not _names_target(header, target, target_kingdom, spy_type):
                    continue
                try:
                    report = self.request(GetSpyReportRequest(MID=message.message_id), SpyReportResponse)
                except CommandError as e:
                    if e.error in _NO_REPORT_ERRORS:
                        return SpyResult(
                            SpyOutcome.NO_SPY_DATA,
                            SpyStep.BSD,
                            error=e,
                            message_id=message.message_id,
                            mission=mission,
                        )
                    return SpyResult(SpyOutcome.COMMAND_FAILED, SpyStep.BSD, error=e, mission=mission)
                except EmpireError as e:
                    return SpyResult(SpyOutcome.COMMAND_FAILED, SpyStep.BSD, error=e, mission=mission)

                area = report.area
                if area is not None and area.x >= 0 and area.y >= 0 and (area.x, area.y) != (target_x, target_y):
                    # Another area with the same owner, e.g. one of many robber barons.
                    missed = SpyOutcome.REPORT_TARGET_MISMATCH
                    continue

                result = SpyResult(SpyOutcome.SUCCESS, message_id=message.message_id, report=report, mission=mission)
                if header.spies_lost:
                    result.outcome = SpyOutcome.SPY_CAUGHT
                elif spy_type == SpyType.MILITARY and not report.has_army:
                    result.outcome = SpyOutcome.NO_SPY_DATA
                return result
        return SpyResult(missed, SpyStep.SNE, mission=mission)


def _spy_messages(packet: Packet) -> list[MessageInfo]:
    """The messages of an ``sne`` push; none when it cannot be read."""
    if packet.error_code != 0 or not isinstance(packet.payload, dict):
        return []
    try:
        event = parse_response("sne", packet.payload)
    except ValidationError:
        return []
    return event.messages if isinstance(event, SystemNotificationEvent) else []


__all__ = ["SpyOutcome", "SpyResult", "SpyService", "SpyStep"]
