"""Awaiting a mission's report, instant spying and sabotage."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from empire_core.enums import Kingdom, SpyOutcome, SpyStep, SpyType
from empire_core.exceptions import EmpireError
from empire_core.spy.risk import (
    MAX_ACCURACY,
    MAX_DAMAGE,
    MAX_RISK_SABOTAGE,
    MIN_DAMAGE,
    max_sabotage_damage,
    plan_sabotage,
)
from empire_core.spy.service.missions import MissionsMixin
from empire_core.spy.service.results import SpyHandle, SpyResult
from empire_core.spy.service.tracking import _REPORT_MARGIN

if TYPE_CHECKING:
    from empire_core.gamedata import Horse


class InstantSpyMixin(MissionsMixin):
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
        horse_booster_id: Horse | None = None,
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
            horse_booster_id: A horse to speed the spies up, None for none; sent as none whenever
                feathers are used, as the client does
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
        horse_booster_id: Horse | None = None,
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
            horse_booster_id: A horse to speed the spies up, None for none
            feathers: Use the instant spy horse and pay for it with feathers
            slowdown: Seconds to delay the arrival by; costs rubies
            spend_rubies: Allow a horse or slowdown that costs rubies; see "Spending rubies" in the guides

        Raises:
            ValueError: A damage the client would not send, or the horse or slowdown costs rubies
                and ``spend_rubies`` is False, before anything is sent
            GameDataNotLoadedError: A horse is picked without feathers and the game data cannot be loaded

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
            return SpyResult(SpyOutcome.NO_SPIES_AVAILABLE, screen=screen)
        plan = plan_sabotage(screen.guard_count, screen.available_spies, damage, max_risk)
        if plan is None:
            return SpyResult(SpyOutcome.RISK_OVER_BUDGET, screen=screen)
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
