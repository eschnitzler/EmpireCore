"""Sending spy missions and plague doctors."""

from __future__ import annotations

import logging
import math
import threading
from typing import TYPE_CHECKING

from empire_core.enums import Kingdom, SpyOutcome, SpyStep, SpyType
from empire_core.exceptions import EmpireError
from empire_core.movements.models import NO_HORSE
from empire_core.spy.models import SendPlagueDoctorsRequest, SendPlagueDoctorsResponse, SendSpyRequest, SendSpyResponse
from empire_core.spy.risk import (
    MAX_ACCURACY,
    MAX_DAMAGE,
    MAX_DEPLOYABLE_PLAGUE_DOCTORS,
    MAX_RISK_SPY,
    MIN_DAMAGE,
    plan_mission,
)
from empire_core.spy.service.reports import ReportsMixin
from empire_core.spy.service.results import SpyHandle, SpyResult
from empire_core.spy.service.spies import SpiesMixin
from empire_core.spy.service.tracking import _REPORT_MARGIN, ReportTrackingMixin
from empire_core.utils.cancel import sleep_unless_cancelled

if TYPE_CHECKING:
    from empire_core.gamedata import Horse

logger = logging.getLogger(__name__)

_SSI_POLL_DELAY = 2.0


class MissionsMixin(SpiesMixin, ReportsMixin, ReportTrackingMixin):
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
        horse_booster_id: Horse | None = None,
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
            spy_type: MILITARY, ECO or SABOTAGE; plague doctors are not sent this way
            spies: How many spies to send
            accuracy_or_damage: Accuracy percent (50-100), or damage percent (10-50) for sabotage
            horse_booster_id: A horse to speed the spies up, None for none
            feathers: Use the instant spy horse and pay for it with feathers; wins over ``horse_booster_id``
            slowdown: Seconds to delay the arrival by; costs rubies
            spend_rubies: Allow a horse or slowdown that costs rubies

        Raises:
            ValueError: For ``SpyType.PLAGUE``
            ValueError: The horse or slowdown costs rubies and ``spend_rubies`` is False
            GameDataNotLoadedError: A horse is picked without feathers and the game data cannot be loaded
            CommandError: The server refused the mission

        Client: ``CastlePostSpyDialog.spyCastle`` (bundle line 38459), ``C2SCreateSpyMovementVO``
        (bundle line 100126)
        """
        if spy_type == SpyType.PLAGUE:
            raise ValueError("the client sends plague doctors with cpm, not csm")
        self._require_spend_rubies(spend_rubies, self._travel_ruby_cost(horse_booster_id, feathers, slowdown))
        request = SendSpyRequest(
            castle_id=source_castle_id,
            target_x=target_x,
            target_y=target_y,
            spy_count=spies,
            spy_type=spy_type,
            accuracy_or_damage=accuracy_or_damage,
            horse_booster_id=NO_HORSE if horse_booster_id is None else horse_booster_id,
            target_kingdom=target_kingdom,
            feathers=1 if feathers else 0,
            slowdown=slowdown,
        )
        return self.request(request, SendSpyResponse)

    def send_plague_doctors(
        self,
        target_x: int,
        target_y: int,
        target_kingdom: Kingdom = Kingdom.GREEN,
        *,
        doctors: int,
        damage: int,
        timeout: float = 5.0,
    ) -> SendPlagueDoctorsResponse:
        """
        Send plague doctors to a target and return the server's reply.

        Args:
            target_x: Target X coordinate
            target_y: Target Y coordinate
            target_kingdom: Target kingdom
            doctors: How many plague doctors to send, 1 up to 20 and no more than are at home
            damage: Damage percent, 10-50 as for a sabotage
            timeout: Timeout in seconds

        Raises:
            ValueError: A count or damage the client's dialog would not send, or more doctors
                than :attr:`plague_doctors` has at home, before anything is sent
            CommandError: The server refused the doctors

        Client: ``CastleSpyDialogPlagueState.spyCastle`` (bundle line 72160) refuses when no monk
        is at home; ``updateSpyVO`` (bundle line 72141) offers up to
        ``min(availablePlagueMonks, MAX_DEPLOYABLE_PLAGUEMONKS)`` and a damage from
        ``ACastleSpyDialogState.updateSliderForDamage`` (bundle line 34370)
        """
        if not 1 <= doctors <= MAX_DEPLOYABLE_PLAGUE_DOCTORS:
            raise ValueError(f"send 1-{MAX_DEPLOYABLE_PLAGUE_DOCTORS} plague doctors, not {doctors}")
        if not MIN_DAMAGE <= damage <= MAX_DAMAGE:
            raise ValueError(f"plague doctor damage must be {MIN_DAMAGE}-{MAX_DAMAGE}, got {damage}")
        known = self.plague_doctors
        if known is not None and doctors > known.available_plague_doctors:
            raise ValueError(f"{known.available_plague_doctors} plague doctors are at home, not {doctors}")
        request = SendPlagueDoctorsRequest(
            target_x=target_x, target_y=target_y, target_kingdom=target_kingdom, doctors=doctors, damage=damage
        )
        return self.request(request, SendPlagueDoctorsResponse, timeout=timeout)

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
        horse_booster_id: Horse | None = None,
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
            horse_booster_id: A horse to speed the spies up, None for none
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
            GameDataNotLoadedError: A horse is picked without feathers and the game data cannot be loaded
        """
        if spy_type not in (SpyType.MILITARY, SpyType.ECO):
            raise ValueError(f"send_instant_spy sends MILITARY or ECO missions, not {spy_type!r}")
        self._require_spend_rubies(spend_rubies, self._travel_ruby_cost(horse_booster_id, feathers, slowdown))
        handle = SpyHandle(target_x, target_y, target_kingdom, spy_type, cancel_event=cancel or threading.Event())
        max_risk = risk_tolerance if risk_tolerance is not None else MAX_RISK_SPY

        available = 0
        plan = None
        screen = None
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
            handle.result = SpyResult(SpyOutcome.CANCELLED, screen=screen)
            return handle
        if available <= 0:
            handle.result = SpyResult(SpyOutcome.NO_SPIES_AVAILABLE, screen=screen)
            return handle
        if plan is None:
            handle.result = SpyResult(SpyOutcome.RISK_OVER_BUDGET, screen=screen)
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
