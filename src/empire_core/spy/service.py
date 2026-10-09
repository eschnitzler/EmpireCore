"""
Espionage: spy missions, sabotage and spy reports.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import ValidationError

from empire_core.army.spy_army import SpyArmy
from empire_core.enums import GGEError, Kingdom, SpyLogType, SpyOutcome, SpyStep, SpyType, TitleSystem
from empire_core.exceptions import CommandError, EmpireError, GameDataNotLoadedError
from empire_core.messages.models import (
    ForwardSpyLogRequest,
    GetSpyReportRequest,
    MessageInfo,
    SpyLogHeader,
    SpyReportResponse,
    SystemNotificationEvent,
)
from empire_core.movements.models import MovementRecord
from empire_core.player.titles import held_titles
from empire_core.protocol.base import parse_response
from empire_core.protocol.packet import Packet
from empire_core.services.base import BaseService
from empire_core.utils.cancel import sleep_unless_cancelled

from .models import (
    AutoSpyRequest,
    AutoSpyResponse,
    SendSpyRequest,
    SendSpyResponse,
    SpyScreenInfoRequest,
    SpyScreenInfoResponse,
)
from .pool import island_title_chain, legend_spy_bonus, research_spy_bonus, title_spy_percent, total_spies
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

if TYPE_CHECKING:
    from empire_core.client.client import EmpireClient

logger = logging.getLogger(__name__)

# BSDCommand.executeCommand (bundle line 125223) shows "no spy data" for these
_NO_REPORT_ERRORS = frozenset({GGEError.NO_SPY_DATA, GGEError.NO_SUCH_MESSAGE})
_REPORT_MARGIN = 10.0
# A handle never awaited or cancelled stops listening this long after its report was due.
_ABANDONED_SECONDS = 600.0
# Mission types and log subtypes are numbered differently (ClientConstCastle.SPYTYPE_*, MessageConst.SUBTYPE_SPY_*).
# A military log is DEFENCE: its success lists the army (hasDetailedSpyLog, bundle lines 137642, 137672),
# and a live military mission's log header began "1+".
_LOG_TYPE_OF_MISSION = {SpyType.MILITARY: SpyLogType.DEFENCE, SpyType.ECO: SpyLogType.ECO}
_POLL_SECONDS = 1.0
_SSI_POLL_DELAY = 2.0
_SpyLog = tuple[MessageInfo, SpyLogHeader]


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
        return self.report.army if self.report is not None else None


@dataclass(eq=False)
class SpyHandle:
    """
    A spy mission sent by :meth:`SpyService.send_instant_spy`, to pass to :meth:`SpyService.await_report`.

    Until it is awaited or cancelled the service listens to ``sne`` and
    keeps the spy logs that may be its report; a handle left alone stops
    listening 10 minutes after its report was due.

    Attributes:
        target_x: Target X coordinate
        target_y: Target Y coordinate
        target_kingdom: Target kingdom
        spy_type: MILITARY or ECO
        cancel_event: Set to cancel the mission's wait, as :meth:`cancel` does;
            the ``cancel`` event given to ``send_instant_spy``, if any
        mission: The csm reply; None when nothing was sent
        arrival_eta: ``time.monotonic()`` when the spies arrive; None when nothing was sent
        result: How the mission ended: set when nothing was sent, when it was
            cancelled before sending, and by ``await_report``, which returns it
            from then on
    """

    target_x: int
    target_y: int
    target_kingdom: Kingdom
    spy_type: SpyType
    cancel_event: threading.Event = field(default_factory=threading.Event)
    mission: SendSpyResponse | None = None
    arrival_eta: float | None = None
    result: SpyResult | None = None
    _reading: _SpyLog | None = field(default=None, init=False, repr=False)
    _declined: set[int] = field(default_factory=set, init=False, repr=False)
    _awaited: bool = field(default=False, init=False, repr=False)
    _on_cancel: Callable[[], None] | None = field(default=None, init=False, repr=False)

    @property
    def movement_id(self) -> int | None:
        """The spy movement's id, for ``client.movements.recall``; None when nothing was sent."""
        return self.mission.movement_id if self.mission is not None else None

    @property
    def target(self) -> MovementRecord | None:
        """The csm reply's movement, whose target area a report is matched against."""
        wrapper = self.mission.spy_movement if self.mission is not None else None
        return wrapper.movement if wrapper is not None else None

    def cancel(self) -> None:
        """
        Stop waiting for this mission: ``await_report`` returns ``CANCELLED`` at once.

        The spies are not recalled. They arrive and their report comes as
        usual: until 10s after their arrival the mission keeps its place in
        the order reports are given out, and the ``sne`` subscription, so its
        report is dropped rather than read as another mission's. To turn them back, recall the movement with
        ``client.movements.recall(handle.movement_id)``, which the client
        allows only for your own spies still heading to the target.

        Client: ``SpyMapmovementVO.canBeRetreated`` (bundle line 43759),
        ``CastleAskRetreatDialog.onClick`` (bundle line 33234)
        """
        self.cancel_event.set()
        if self._on_cancel is not None:
            self._on_cancel()

    def _may_read(self, log: _SpyLog) -> bool:
        """Whether ``log`` can be this mission's report; before the csm reply any log for its kingdom can."""
        message, header = log
        return message.message_id not in self._declined and _names_target(
            header, self.target, self.target_kingdom, self.spy_type
        )


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
    """Spy missions planned for risk, sabotage, and reading spy reports."""

    def __init__(self, client: EmpireClient) -> None:
        super().__init__(client)
        self._logs_changed = threading.Condition()
        self._missions: list[SpyHandle] = []
        self._spy_logs: list[_SpyLog] = []

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

        Raises:
            ValueError: ``player_ids`` is empty; the client's forward button stays
                disabled until a recipient is picked

        Client: ``CastleForwardMessageDialog.fillList`` and ``sendMessage`` (bundle lines 60719, 60740),
        ``checkEnableForwardButton`` (bundle line 60753), ``MFSCommand.executeCommand`` (bundle line 125409)
        """
        if not player_ids:
            raise ValueError("a spy report is forwarded to at least one player")
        try:
            self.client.send(ForwardSpyLogRequest(message_id=message_id, player_ids=list(player_ids)), wait=True)
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
        return self.request(
            SpyScreenInfoRequest(target_x=target_x, target_y=target_y, target_kingdom=target_kingdom),
            SpyScreenInfoResponse,
        )

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
            return self.request(GetSpyReportRequest(message_id=message_id), SpyReportResponse)
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
        return self.request(AutoSpyRequest(target_x=target_x, target_y=target_y), AutoSpyResponse)

    def spies_in_use(self) -> int:
        """
        Spies on your own spy movements, out or on their way home, as the state tracks them.

        Client: ``CastleSpyData.getNumAvailableSpies`` (bundle line 139970), which counts the
        ``spyCount`` of every ``SpyMapmovementVO`` you own
        """
        return sum(
            m.spy.spy_count if m.spy is not None else 0
            for m in self.client.state.get_all_movements()
            if m.is_mine and m.is_spy
        )

    def total_spies(
        self,
        *,
        research_ids: Iterable[int] | None = None,
        legend_skill_ids: Iterable[int] | None = None,
        title_ids: Iterable[int] | None = None,
        island_title_id: int | None = None,
        legend_target: bool = False,
    ) -> int | None:
        """
        All your spies, home or out, counted as the client does: the ``gms`` count plus boosts.

        The count is for the whole account, not one castle. Each boost left as None is read
        from state: your finished research (``rei``), legend skills (``skl``), and the glory,
        Berimond and Storm Islands titles your points and ranks give (``ufa``, ``ufp``, ``uar``).
        Pass a value to count that instead, ``()`` for none. A boost needs
        ``client.load_game_data()``; after login the state's titles always do.

        Args:
            research_ids: Your finished research ids, the ``BR`` of the ``rei`` section
            legend_skill_ids: ``SkillList.legend_skill_ids``; counted only with ``legend_target``
            title_ids: Every glory and Berimond title you hold, each one below your current
                title included, as the client lists them
            island_title_id: Your Storm Islands title, -1 for none; the titles below it count too
            legend_target: Add legend skills: the client does for a target whose owner is a
                legend or that is a landmark, for your own legend status, and always in the
                attack screen's spy alert

        Returns:
            The count, or None before the login gbd brought ``gms``

        Raises:
            GameDataNotLoadedError: A boost counts and ``client.load_game_data()`` has not been called

        Client: ``CastleSpyData.getNumAllSpies`` (bundle line 139976), called with the target's
        ``ownerInfo.isLegend`` (bundle lines 34325, 34342, 127082) or ``userData.isLegend``
        (bundle line 102169); ``CastleTitleSystemHelper.returnTitleEffectValue`` (bundle line 4420)
        over ``CastleTitleData.thisUsersTitles`` (bundle line 21073)
        """
        state = self.client.state
        max_spies = state.get_max_spies()
        if max_spies is None:
            return None
        if research_ids is None:
            research = state.get_research()
            research_ids = research.bought_research_ids if research is not None else ()
        if legend_skill_ids is None:
            skills = state.get_skills()
            legend_skill_ids = skills.legend_skill_ids if skills is not None else ()
        ranks = state.get_title_ranks()
        if island_title_id is None:
            island_title_id = ranks.island_title.held_title_id if ranks is not None else -1
        glory, faction = state.get_glory_points(), state.get_faction_points()
        titles_from_state = title_ids is None
        research_ids, legend_skill_ids = list(research_ids), list(legend_skill_ids)
        title_ids = [] if title_ids is None else list(title_ids)
        points_known = (glory is not None and glory.glory_points is not None) or (
            faction is not None and faction.faction_points is not None
        )
        if not (
            research_ids
            or (legend_target and legend_skill_ids)
            or title_ids
            or island_title_id >= 0
            or (titles_from_state and (points_known or ranks is not None))
        ):
            return total_spies(max_spies.max_spies)
        game_data = self.client.game_data
        if game_data is None:
            raise GameDataNotLoadedError("Spy boosts need the items payload: call client.load_game_data() first")
        if titles_from_state:
            glory_rank = ranks.glory.top_rank if ranks is not None else None
            faction_rank = ranks.faction.top_rank if ranks is not None else None
            title_ids = [
                *held_titles(game_data, TitleSystem.GLORY, glory.glory_points if glory else None, glory_rank),
                *held_titles(game_data, TitleSystem.FACTION, faction.faction_points if faction else None, faction_rank),
            ]
        titles = title_ids + island_title_chain(game_data, island_title_id)
        return total_spies(
            max_spies.max_spies,
            research_bonus=research_spy_bonus(game_data, research_ids),
            legend_bonus=legend_spy_bonus(game_data, legend_skill_ids) if legend_target else 0,
            title_percent=title_spy_percent(game_data, titles),
        )

    def available_spies(
        self,
        *,
        research_ids: Iterable[int] | None = None,
        legend_skill_ids: Iterable[int] | None = None,
        title_ids: Iterable[int] | None = None,
        island_title_id: int | None = None,
        legend_target: bool = False,
    ) -> int | None:
        """
        Spies at home: :meth:`total_spies` less :meth:`spies_in_use`, as the client counts them.

        The client uses this count to offer the spy button. The spy dialog
        itself sends with the ``ssi`` reply's ``available_spies``, as
        :meth:`execute_instant_spy` does.

        Takes the arguments of :meth:`total_spies`, read from state the same way.

        Returns:
            The count, which can be negative as in the client, or None before ``gms`` arrived

        Client: ``CastleSpyData.getNumAvailableSpies`` (bundle line 139970)
        """
        total = self.total_spies(
            research_ids=research_ids,
            legend_skill_ids=legend_skill_ids,
            title_ids=title_ids,
            island_title_id=island_title_id,
            legend_target=legend_target,
        )
        return None if total is None else total - self.spies_in_use()

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
        spend_rubies: bool = False,
    ) -> SendSpyResponse:
        """
        Send one spy mission as given, without planning it or waiting for its report.

        A horse that costs rubies, unless paid with feathers, and a slowdown spend rubies;
        see "Spending rubies" in the guides.

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
            slowdown: Seconds to delay the arrival by; costs rubies
            spend_rubies: Allow a horse or slowdown that costs rubies

        Raises:
            ValueError: For ``SpyType.PLAGUE``
            ValueError: The horse or slowdown costs rubies and ``spend_rubies`` is False
            GameDataNotLoadedError: A horse is picked without feathers and ``client.load_game_data()``
                has not been called
            CommandError: The server refused the mission

        Client: ``CastlePostSpyDialog.spyCastle`` (bundle line 38459), ``C2SCreateSpyMovementVO``
        (bundle line 100126)
        """
        if spy_type == SpyType.PLAGUE:
            raise ValueError("the client sends plague monks with cpm, not csm")
        self._require_spend_rubies(spend_rubies, self._travel_ruby_cost(horse_booster_id, feathers, slowdown))
        request = SendSpyRequest(
            castle_id=source_castle_id,
            target_x=target_x,
            target_y=target_y,
            spy_count=spies,
            spy_type=spy_type,
            accuracy_or_damage=accuracy_or_damage,
            horse_booster_id=horse_booster_id,
            target_kingdom=target_kingdom,
            feathers=1 if feathers else 0,
            slowdown=slowdown,
        )
        return self.request(request, SendSpyResponse)

    def send_instant_spy(
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
        spend_rubies: bool = False,
        wait_for_spies: float | None = None,
        cancel: threading.Event | None = None,
    ) -> SpyHandle:
        """
        Plan and send a military or economy spy mission, without waiting for its report.

        Plans and sends as :meth:`execute_instant_spy` does, which is this and
        :meth:`await_report`. The handle listens for the report from before
        csm is sent, so a report that comes before ``await_report`` is called
        is kept for it.

        Args:
            source_castle_id: The castle the spies leave from, one of yours
            target_x: Target X coordinate
            target_y: Target Y coordinate
            target_kingdom: Target kingdom
            risk_tolerance: Ceiling on the chance of being caught, as a percentage
            accuracy: Spy accuracy (50-100)
            spy_type: MILITARY or ECO
            horse_booster_id: A horse's wod id to speed the spies up (-1 = none)
            feathers: Use the instant spy horse and pay for it with feathers
            slowdown: Seconds to delay the arrival by; costs rubies
            spend_rubies: Allow a horse or slowdown that costs rubies; see "Spending rubies" in the guides
            wait_for_spies: Most seconds to keep asking ``ssi`` while no spy is at
                home or the risk is over ``risk_tolerance``; None asks once
            cancel: Ends the mission's wait when set, as ``SpyHandle.cancel``
                does; looked at between requests (see :mod:`empire_core.utils.cancel`)

        Returns:
            The mission's handle; when nothing was sent, ``handle.result`` says why.

        Raises:
            ValueError: For a spy type other than MILITARY or ECO, or the horse or slowdown costs
                rubies and ``spend_rubies`` is False, before anything is sent
            GameDataNotLoadedError: A horse is picked without feathers and ``client.load_game_data()``
                has not been called
        """
        if spy_type not in (SpyType.MILITARY, SpyType.ECO):
            raise ValueError(f"send_instant_spy sends MILITARY or ECO missions, not {spy_type!r}")
        self._require_spend_rubies(spend_rubies, self._travel_ruby_cost(horse_booster_id, feathers, slowdown))
        handle = SpyHandle(target_x, target_y, target_kingdom, spy_type, cancel_event=cancel or threading.Event())
        max_risk = risk_tolerance if risk_tolerance is not None else MAX_RISK_SPY

        available = 0
        plan = None
        attempts = 1 + (math.ceil(wait_for_spies / _SSI_POLL_DELAY) if wait_for_spies and wait_for_spies > 0 else 0)
        for attempt in range(attempts):
            if handle.cancel_event.is_set():
                break
            try:
                screen = self.get_screen_info(target_x, target_y, target_kingdom)
            except EmpireError as e:
                handle.result = SpyResult(SpyOutcome.COMMAND_FAILED, SpyStep.SSI, error=e)
                return handle

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
                sleep_unless_cancelled(_SSI_POLL_DELAY, handle.cancel_event)

        if handle.cancel_event.is_set():
            handle.result = SpyResult(SpyOutcome.CANCELLED)
            return handle
        if available <= 0:
            handle.result = SpyResult(SpyOutcome.NO_SPIES_AVAILABLE)
            return handle
        if plan is None:
            handle.result = SpyResult(SpyOutcome.RISK_OVER_BUDGET)
            return handle

        self._listen(handle)
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
                spend_rubies=spend_rubies,
            )
        except EmpireError as e:
            handle.result = SpyResult(SpyOutcome.COMMAND_FAILED, SpyStep.CSM, error=e)
            self._release(handle)
            return handle
        except BaseException:
            self._release(handle)
            raise
        if mission.spy_movement is None:
            logger.warning("The csm reply has no readable movement; waiting only %ss for the report", _REPORT_MARGIN)
        self._arm(handle, mission)
        return handle

    def await_report(self, handle: SpyHandle, max_wait: float | None = None) -> SpyResult:
        """
        Wait for a sent mission's report and read it.

        Blocks until the spies arrive plus 10s for the report, or ``max_wait``
        if that is shorter; do not call this from a state callback. Returns
        ``CANCELLED`` once the handle is cancelled: at once through
        :meth:`SpyHandle.cancel`, within a second when its event is set
        directly. A ``bsd`` already asked for is read to the end, so a report
        read while the cancel comes is returned. The handle stops listening
        when this returns, and its result is kept in ``handle.result``: a
        later call returns it at once, and a call made while another waits
        returns what that one does, or ``TIMEOUT`` after its own ``max_wait``.

        ``sne`` carries no mission id. A spy log whose header names a
        mission's target (kingdom, owner, area type and name, from the csm
        reply's movement) goes to the waiting mission for that target whose
        spies arrive first, and one whose report is for another position is
        handed on to the next. Two missions to one target so get the reports
        in the order their spies arrive. A mission that stopped waiting
        without its report, cancelled or at ``max_wait``, keeps its place
        until 10s after its spies arrive, and the report given to it is
        dropped. That is a client-side heuristic: no field ties a report to
        its mission.

        Args:
            handle: From :meth:`send_instant_spy`
            max_wait: Most seconds to wait from now; None waits for the trip plus 10s

        Returns:
            SpyResult with the report or why there is none; ``handle.result``
            as it is when the mission ended before its report wait.
        """
        if handle.result is not None:
            return handle.result
        mission, arrival = handle.mission, handle.arrival_eta
        if mission is None or arrival is None:
            raise ValueError("await_report takes a handle from send_instant_spy")
        deadline = None if max_wait is None else time.monotonic() + max_wait
        with self._logs_changed:
            while handle.result is None and handle._awaited:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return SpyResult(SpyOutcome.TIMEOUT, SpyStep.SNE, mission=mission)
                self._logs_changed.wait(remaining)
            if handle.result is not None:
                return handle.result
            handle._awaited = True
        result = None
        try:
            wait = max(0.0, arrival - time.monotonic()) + _REPORT_MARGIN
            if deadline is not None:
                wait = min(wait, deadline - time.monotonic())
            result = self._read_report(handle, mission, time.monotonic() + wait)
            return result
        finally:
            with self._logs_changed:
                handle.result = result
                handle._awaited = False
                self._release(handle)

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
        spend_rubies: bool = False,
        max_wait: float | None = None,
        wait_for_spies: float | None = None,
        cancel: threading.Event | None = None,
    ) -> SpyResult:
        """
        Send a military or economy spy mission and read its report.

        This is :meth:`send_instant_spy` then :meth:`await_report`; call those
        two to do something else while the spies travel.

        Nothing is paid unless asked: by default the spies travel without a
        horse. ``feathers`` uses the instant spy horse, paid with feathers,
        which the client sends as ``HBW`` -1 with ``PTT`` 1 and which wins over
        ``horse_booster_id``, as in the client. A horse that costs rubies and a
        slowdown need ``spend_rubies``; see "Spending rubies" in the guides.

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
        counts; the rest are skipped. Two missions to one target at once get
        their reports in arrival order (see :meth:`await_report`).

        Asks ``ssi`` once: with no spy at home, or no mission within
        ``risk_tolerance``, it returns at once, as the client's spy dialog
        shows the pool as it is. ``wait_for_spies`` asks again every 2s for up
        to that many seconds, for spies still on their way home. Then it
        blocks until the spies arrive (the csm reply's travel time) plus 10s
        for the report, or ``max_wait`` if that is shorter; do not call this
        from a state callback.

        Setting ``cancel`` ends the call with ``CANCELLED``. It is looked at
        between requests, never during one: a request in flight ends with its
        own reply or timeout, so no waiter is abandoned and no late reply can
        reach the next caller of that command. Spies already sent keep going
        (``result.mission`` is set); ``client.movements.recall`` with its
        ``movement_id`` turns them back.

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
            slowdown: Seconds to delay the arrival by; costs rubies
            spend_rubies: Allow a horse or slowdown that costs rubies
            max_wait: Most seconds to wait for the report after the csm reply;
                None waits for the trip plus 10s
            wait_for_spies: Most seconds to keep asking ``ssi`` while no spy is at
                home or the risk is over ``risk_tolerance``; None asks once
            cancel: Ends the call with ``CANCELLED`` when set

        Client: ``CastlePostSpyDialog.spyCastle`` (bundle line 38459),
        ``CastleStartSpyVO.setSpyValues`` (bundle line 140004),
        ``CastleSpyDialogSpyState.fillSpyTypeList`` (bundle line 72238),
        ``HorseTravelboosterVO.isPayedWithPegasusTickets`` (bundle line 118825)

        Returns:
            SpyResult with the report or why there is none.

        Raises:
            ValueError / GameDataNotLoadedError: See :meth:`send_instant_spy`
        """
        handle = self.send_instant_spy(
            source_castle_id,
            target_x,
            target_y,
            target_kingdom,
            risk_tolerance,
            accuracy,
            spy_type=spy_type,
            horse_booster_id=horse_booster_id,
            feathers=feathers,
            slowdown=slowdown,
            spend_rubies=spend_rubies,
            wait_for_spies=wait_for_spies,
            cancel=cancel,
        )
        return self.await_report(handle, max_wait=max_wait)

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
        spend_rubies: bool = False,
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
            slowdown: Seconds to delay the arrival by; costs rubies
            spend_rubies: Allow a horse or slowdown that costs rubies; see "Spending rubies" in the guides

        Raises:
            ValueError: A damage the client would not send, or the horse or slowdown costs rubies
                and ``spend_rubies`` is False, before anything is sent
            GameDataNotLoadedError: A horse is picked without feathers and ``client.load_game_data()``
                has not been called

        Client: ``CastleSpyDialogSabotageState.updateSpyVO`` and ``spyCastle`` (bundle lines
        72203-72205), ``ACastleSpyDialogState.updateSliderForDamage`` (bundle line 34360),
        ``CastleStartSpyVO.setSabotageValues`` (bundle line 140006)
        """
        if not MIN_DAMAGE <= damage <= MAX_DAMAGE:
            raise ValueError(f"sabotage damage must be {MIN_DAMAGE}-{MAX_DAMAGE}, got {damage}")
        self._require_spend_rubies(spend_rubies, self._travel_ruby_cost(horse_booster_id, feathers, slowdown))
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
                spend_rubies=spend_rubies,
            )
        except EmpireError as e:
            return SpyResult(SpyOutcome.COMMAND_FAILED, SpyStep.CSM, error=e)
        return SpyResult(SpyOutcome.SENT, mission=mission)

    def _listen(self, handle: SpyHandle) -> None:
        """Keep spy logs for ``handle`` from now on; subscribed before csm is sent so the report can't slip past."""
        with self._logs_changed:
            self._prune()
            if not self._missions:
                self.client.connection.subscribe("sne", self._on_sne)
            self._missions.append(handle)
            handle._on_cancel = self._changed

    def _arm(self, handle: SpyHandle, mission: SendSpyResponse) -> None:
        """Give a listening handle its csm reply, from which its reports are matched."""
        with self._logs_changed:
            handle.mission = mission
            handle.arrival_eta = time.monotonic() + (mission.seconds_until_arrival or 0)
            self._prune()
            self._logs_changed.notify_all()

    def _release(self, handle: SpyHandle) -> None:
        """``handle`` no longer reads; it keeps listening only as a cancelled mission's place (see :meth:`_prune`)."""
        with self._logs_changed:
            handle._reading = None
            self._prune()
            self._logs_changed.notify_all()

    def _changed(self) -> None:
        """Wake the waits and settle the logs after a handle was cancelled."""
        with self._logs_changed:
            self._prune()
            self._logs_changed.notify_all()

    def _on_sne(self, packet: Packet) -> None:
        """Receive-thread subscriber: keep the spy logs of an ``sne`` push for the missions waiting."""
        logs = [(message, header) for message in _spy_messages(packet) if (header := message.spy_log_header())]
        with self._logs_changed:
            self._spy_logs.extend(logs)
            self._prune()
            self._logs_changed.notify_all()

    @staticmethod
    def _listening(handle: SpyHandle, now: float) -> bool:
        """
        Whether ``handle`` still takes spy logs.

        A handle waiting for its csm reply does, and an armed one until its
        result is known or, never awaited, until ``_ABANDONED_SECONDS`` after
        its report was due. A mission whose spies were sent and which left
        its wait without reading its report (cancelled, ``max_wait``) stays
        until 10s after they arrive, so the report routed to it is dropped
        instead of reaching a mission whose spies arrive later.
        """
        if handle.mission is None or handle.arrival_eta is None:
            return handle.result is None
        if handle._reading is not None:
            return True
        due = handle.arrival_eta + _REPORT_MARGIN
        if handle.result is None:
            return now < due + (0 if handle.cancel_event.is_set() else _ABANDONED_SECONDS)
        return handle.result.step is SpyStep.SNE and now < due

    def _prune(self) -> None:
        """
        Settle the missions and kept logs; called under ``_logs_changed``.

        Drops the handles no longer listening (one left alone gets a
        ``TIMEOUT`` result), each mission that stopped reading together with
        the log routed to it, and the logs no handle can take; unsubscribes
        once no handle is left.
        """
        now = time.monotonic()
        for handle in self._missions:
            if not self._listening(handle, now) and handle.result is None:
                handle.result = SpyResult(SpyOutcome.TIMEOUT, SpyStep.SNE, mission=handle.mission)
        self._missions = [h for h in self._missions if self._listening(h, now)]
        for log, handle in list(self._routes()):
            if handle.cancel_event.is_set() or handle.result is not None:
                self._spy_logs.remove(log)
                self._missions.remove(handle)
        self._spy_logs = [log for log in self._spy_logs if any(h._may_read(log) for h in self._missions)]
        if not self._missions:
            self.client.connection.unsubscribe("sne", self._on_sne)

    def _routes(self) -> Iterator[tuple[_SpyLog, SpyHandle]]:
        """
        The kept spy logs with the mission each goes to now; called under ``_logs_changed``.

        Logs go in the order they came, each to the free mission whose spies
        arrive first among those whose target its header names and which have
        not turned it down; a mission reading a log is not free, and each
        mission gets one log at a time. A log a mission still waiting for its
        csm reply could take is held, and so are the missions it could go to,
        since the waiting one may arrive first (a feathered mission arrives
        with the reply).
        """
        taken: set[int] = set()
        for log in self._spy_logs:
            armed = [h for h in self._missions if h.mission is not None and id(h) not in taken and h._may_read(log)]
            if any(h.mission is None and h._may_read(log) for h in self._missions):
                taken.update(id(h) for h in armed)
                continue
            free = [h for h in armed if h._reading is None]
            if free:
                first = min(free, key=lambda h: h.arrival_eta or 0.0)
                taken.add(id(first))
                yield log, first

    def _take_log(self, handle: SpyHandle, deadline: float) -> _SpyLog | SpyOutcome:
        """Wait for the next spy log ``handle`` should read, or the outcome that ends the wait."""
        with self._logs_changed:
            while (remaining := deadline - time.monotonic()) > 0:
                if handle.cancel_event.is_set():
                    return SpyOutcome.CANCELLED
                self._prune()
                log = next((log for log, h in self._routes() if h is handle), None)
                if log is not None:
                    self._spy_logs.remove(log)
                    handle._reading = log
                    return log
                if not self.client.connection.connected:
                    return SpyOutcome.DISCONNECTED
                self._logs_changed.wait(min(remaining, _POLL_SECONDS))
        return SpyOutcome.TIMEOUT

    def _decline(self, handle: SpyHandle, log: _SpyLog) -> None:
        """Hand back a report for another position, for the next mission whose target its header names."""
        with self._logs_changed:
            handle._declined.add(log[0].message_id)
            handle._reading = None
            self._spy_logs.append(log)
            self._prune()
            self._logs_changed.notify_all()

    def _read_report(self, handle: SpyHandle, mission: SendSpyResponse, deadline: float) -> SpyResult:
        """Read the spy logs given to ``handle`` until one is its report, or the deadline passes."""
        missed = SpyOutcome.TIMEOUT
        while True:
            log = self._take_log(handle, deadline)
            if isinstance(log, SpyOutcome):
                return SpyResult(missed if log is SpyOutcome.TIMEOUT else log, SpyStep.SNE, mission=mission)
            message, header = log
            try:
                report = self.request(GetSpyReportRequest(message_id=message.message_id), SpyReportResponse)
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
            target = (handle.target_x, handle.target_y)
            if area is not None and area.x >= 0 and area.y >= 0 and (area.x, area.y) != target:
                # Another area with the same owner, e.g. one of many robber barons.
                missed = SpyOutcome.REPORT_TARGET_MISMATCH
                self._decline(handle, log)
                continue

            result = SpyResult(SpyOutcome.SUCCESS, message_id=message.message_id, report=report, mission=mission)
            if header.spies_lost:
                result.outcome = SpyOutcome.SPY_CAUGHT
            elif handle.spy_type == SpyType.MILITARY and not report.has_army:
                result.outcome = SpyOutcome.NO_SPY_DATA
            return result


def _spy_messages(packet: Packet) -> list[MessageInfo]:
    """The messages of an ``sne`` push; none when it cannot be read."""
    if packet.error_code != 0 or not isinstance(packet.payload, dict):
        return []
    try:
        event = parse_response("sne", packet.payload)
    except ValidationError:
        return []
    return event.messages if isinstance(event, SystemNotificationEvent) else []


__all__ = ["SpyHandle", "SpyOutcome", "SpyResult", "SpyService", "SpyStep"]
