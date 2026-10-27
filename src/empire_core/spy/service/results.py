"""A spy mission's result, and the handle of a mission awaiting its report."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from empire_core.army.spy_army import SpyArmy
from empire_core.enums import Kingdom, SpyLogType, SpyOutcome, SpyStep, SpyType
from empire_core.exceptions import EmpireError
from empire_core.messages.models import MessageInfo, SpyLogHeader, SpyReportResponse
from empire_core.movements.models import MovementRecord
from empire_core.spy.models import SendSpyResponse, SpyScreenInfoResponse

# Mission types and log subtypes are numbered differently (ClientConstCastle.SPYTYPE_*, MessageConst.SUBTYPE_SPY_*).
# A military log is DEFENCE: its success lists the army (hasDetailedSpyLog, bundle lines 137642, 137672),
# and a live military mission's log header began "1+".
_LOG_TYPE_OF_MISSION = {SpyType.MILITARY: SpyLogType.DEFENCE, SpyType.ECO: SpyLogType.ECO}

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
        screen: The last ``ssi`` spy screen read, when nothing was sent (no
            spies, risk over budget, cancelled); None otherwise or before a read.
    """

    outcome: SpyOutcome
    step: SpyStep | None = None
    error: EmpireError | None = None
    message_id: int | None = None
    report: SpyReportResponse | None = None
    mission: SendSpyResponse | None = None
    screen: SpyScreenInfoResponse | None = None

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
