"""Movement tracking: gam and its pushes, arrival, removal and the movement queries."""

import contextlib
import inspect
import logging
import math
import threading
import time
import weakref
from collections.abc import Callable, Iterable
from typing import Any, TypeVar

from pydantic import ValidationError

from empire_core.commanders.models.roster import Commander
from empire_core.gamedata import UnitOrTool
from empire_core.movements.models import (
    ArmyRadiusPush,
    CancelMovementResponse,
    GetMovementsResponse,
    MovementFilterResponse,
    MovementForceCancelableResponse,
    MovementOwner,
    MovementRecord,
    MovementRemovedResponse,
    MovementWrapper,
)
from empire_core.movements.tracked import Movement, MovementResources
from empire_core.protocol.base import BasePayload
from empire_core.state.announcer import AttackEvents, MovementAnnouncer, OccupationEvents
from empire_core.state.base import MovementEventCallback, StateBase, read_section
from empire_core.utils.callbacks import BoundEvent, Event, EventOf

_POSITIONAL = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
# Whether an arrival, recall or removal callback takes the Movement, by callback, while it lives
_ACCEPTS_MOVEMENT: weakref.WeakKeyDictionary[Callable[..., Any], bool] = weakref.WeakKeyDictionary()

logger = logging.getLogger(__name__)

_Reply = TypeVar("_Reply", bound=BasePayload)

# The Movement field each MovementRecord field fills, where the names differ
_MOVEMENT_FIELDS = {"kingdom_id": "kingdom"}

# A drifted movement schema would fail on every packet, so the warning is
# rate-limited to one per this interval; the rest go to debug.
MOVEMENT_PARSE_WARN_INTERVAL = 60.0

# The movement clock wakes at least this often, as a far-off arrival's wait would overflow Condition.wait
MOVEMENT_CLOCK_MAX_WAIT = 3600.0
# The client drops an ended movement on its army data's next update, at most _updateInterval (1e3 ms) later
RETURN_COMMANDER_HOLD = 1.0


class MovementState(StateBase):
    on_incoming_attack = Event[Movement]()
    """Register a callback for new hostile attack movements.

    Fires once per newly seen attack that is not the local player's own,
    is not on its way home and had not already landed when first seen, and
    is aimed at you or the daimyo township (an alien attack only at you),
    whoever sends it, or at another member of your alliance. An attack on
    an alliance member fires when a player the movement names sends it,
    when an alien attack or the alliance nomad camp does, or when an NPC
    that is not a dungeon owner does (an outpost, capital or metropolis
    owner, the plague doctor, or an NPC id the client does not know); robber
    barons, camps, event dungeons and the other dungeon owners do not fire
    it. An alliance member's attack on someone outside the alliance does
    not fire. Each packet that carries an attack judges it again, with the
    owner records seen so far, so one whose attacker's record comes later
    fires then.

    Fires once per attack movement id, also across a reconnect: an attack
    still on its way when the connection drops is not announced again when
    the next login lists it. The record of an attack is dropped when it
    arrives, when the server removes it, or once its travel time is over.

    Runs on the callback thread, in packet order (see :class:`GameState`).
    """

    on_incoming_attack_updated = Event[Movement, Movement]()
    """Register a callback for changes to an attack :meth:`on_incoming_attack` announced.

    ``callback(old, new)`` fires on a later packet for the same attack that
    changes its army (``units``, ``estimated_size``), its arrival
    (``estimated_arrival``, by two seconds or more, as a speed-up
    does), its target (``target_id``, ``target_area_id``,
    ``target_x``, ``target_y``) or its commander (``commander``, its
    equipment and area effects included). A packet that changes
    none of these does not fire it, nor does the packet that announces the
    attack, nor any packet once the attack has arrived or been removed.
    After a reconnect the first listing of an attack has nothing to compare
    with, so it does not fire either. ``old`` is the Movement as state had
    it before the packet, ``new`` the one it holds now.

    The client keeps no history to compare with: ``parseMapMovementArray``
    (bundle line 133626) replaces a movement's object with each packet, so
    this is derived by comparing the two.

    Runs on the callback thread, in packet order (see :class:`GameState`).
    """

    on_incoming_attack_withdrawn = Event[Movement]()
    """Register a callback for announced attacks the server removes before they arrive.

    Fires once, with the attack as state last had it, when ``mrm`` removes an
    attack that :meth:`on_incoming_attack` announced while its travel time
    is not up yet. An attack removed within two seconds of its estimated
    arrival (``estimated_arrival`` can run a second late), at or after it,
    or one state no longer tracks, does not fire.
    :meth:`on_movement_removed` still fires for the same ``mrm``, first.

    Derived, not reported: the server does not say why it removes a
    movement, and neither does the client. ``CastleArmyData.parse_MRM``
    (bundle line 133633) only drops it, and the client removes an arrived
    movement on its own timer (``updateMapmovements``, bundle line 133670,
    once ``currentProgress`` reaches 1), so a removal before arrival is the
    attack turning back or being called off.

    Runs on the callback thread, in packet order (see :class:`GameState`).
    """

    on_occupation_started = Event[Movement]()
    """Register a callback for occupations of your areas or your alliance members'.

    An occupation (``MovementType.SIEGE`` or ``OCCUPY_FACTION``, both parsed
    as ``SiegeMapmovementVO``, bundle line 133809) follows a capture attack
    that landed and won: the game's movement overview lists it as
    "Occupying forces" (``RenderSiege``, bundle line 67408,
    ``dialog_moveOverview_siege``). Its travel time is the time the
    occupier must hold the area (the battle log's ``dialog_battleLog_youSiege24h``);
    once it runs out the area is captured. It is no attack, so
    :meth:`on_incoming_attack` never reports it; the capture attack before
    it is an ordinary attack (``isConquerMovement``, bundle line 14404).

    Fires once per newly seen occupation that is not the local player's
    own, is not on its way home and had not already ended when first seen,
    and holds an area of yours or the daimyo township, or of another
    member of your alliance, whoever sends it. One on someone outside the
    alliance does not fire. As for attacks, each packet judges it again,
    and it fires once per movement id, also across a reconnect.

    The client raises no attack warning for an occupation:
    ``SiegeMapmovementVO`` (bundle line 33173) is a ``BasicMapmovementVO``,
    and ``CastleArmyData.checkAllAttackMovements`` (bundle line 133659)
    counts only ``ArmyAttackMapmovementVO`` (its type check, 133664). These
    are the occupations its movement list shows: ``FilterAttack`` (bundle
    line 67995) those whose target owner is you, which the daimyo
    township's is (``getOwnerInfoVO``, bundle line 138994), and
    ``FilterAllianceIncoming`` (bundle line 67971) those, not yours, whose
    target owner is another member of your alliance. Leaving out your own
    and returning occupations is the library's choice, as for attacks:
    neither filter checks the direction, and ``FilterAttack`` (67996) does
    not check the sender either.

    Runs on the callback thread, in packet order (see :class:`GameState`).
    """

    on_occupation_updated = Event[Movement, Movement]()
    """Register a callback for changes to an occupation :meth:`on_occupation_started` announced.

    ``callback(old, new)`` fires on the same changes, and with the same
    exceptions, as :meth:`on_incoming_attack_updated` does for an attack:
    a changed ``estimated_arrival`` is a changed end of the occupation
    time. An occupation's army is its ``A`` block
    (``SiegeMapmovementVO.parseArmy``, bundle line 33176), read into
    ``units``.

    Runs on the callback thread, in packet order (see :class:`GameState`).
    """

    on_occupation_ended = Event[Movement, bool]()
    """Register a callback for occupations :meth:`on_occupation_started` announced leaving state.

    ``callback(movement, captured)`` fires once per announced occupation,
    with it as state last had it. ``captured`` is True when its time ran
    out: at its arrival, after :meth:`on_movement_arrived`, or when ``mrm``
    removes it within two seconds of its estimated arrival or later, after
    :meth:`on_movement_removed`. The game then reports the area captured
    ("managed to occupy your outpost for long enough and has now captured
    it", ``dialog_siegeMessage_yourOutpostWasConquered``). ``captured`` is
    False when ``mrm`` removes it earlier, after :meth:`on_movement_removed`:
    the occupation was broken ("Occupying forces driven off!",
    ``dialog_messageHeader_siegeCancelledByPlayer``,
    ``dialog_siegeMessage_siegeCancelled``). One that ends while no session
    is logged in is not reported: state drops it with the session (see
    :meth:`reset`) and the next login does not list it.

    Derived, not reported, as :meth:`on_incoming_attack_withdrawn` is: the
    server does not say why it removes a movement, and the reports above
    come as messages of their own.

    Runs on the callback thread, in packet order (see :class:`GameState`).
    """

    on_movement_recalled = EventOf[MovementEventCallback]()
    """Register a callback for your own recalled movements.

    Fires on the ``mcm`` reply to a recall, with the movement as it now
    stands: on its way home (``is_returning``). A plain removal (``mrm``)
    fires :meth:`on_movement_removed` instead.

    Accepts either signature (see :meth:`on_movement_arrived`)::

        def on_recalled(movement_id: int) -> None: ...
        def on_recalled(movement_id: int, movement: Movement | None) -> None: ...

    Runs on the callback thread, in packet order (see :class:`GameState`).
    """

    on_movement_arrived = EventOf[MovementEventCallback]()
    """Register a callback for movements reaching their target.

    The server sends no arrival packet: as in the game client, a movement
    arrives once its travel time is up (``estimated_arrival``). A timer
    of the state's own fires it then, with no packet needed, and every
    packet and movement query checks too. It fires once per movement, and
    not for a movement first seen after it had already arrived.

    The client checks on its update tick (``CastleArmyData.executeUpdate``,
    bundle line 133669, running ``updateMapmovements``, line 133670); the
    timer is the library's way to the same moment.

    An army that stays at its target (a stationed support) is kept in
    state until its wait is over (``estimated_end``); every other
    movement is removed before callbacks run. An army's way home is a
    movement too, so it fires when the army gets back; check
    ``movement.is_returning`` to tell the two apart.

    Commander availability follows the tracked movements, as in the client.
    An expired outbound movement releases its commander unless another own
    movement references it. Returning commanders remain unavailable for one
    second after estimated end, as long as the client can keep them, and
    outbound attacks get the same margin. Movement expiry and arrival callbacks are not
    delayed. This estimate is not server confirmation.

    Two signatures are supported, picked per callback from its own
    parameter list::

        def on_arrived(movement_id: int) -> None: ...
        def on_arrived(movement_id: int, movement: Movement | None) -> None: ...

    Prefer the second form: the id alone says nothing about what arrived.

    Runs on the callback thread, in packet order (see :class:`GameState`).
    """

    on_movement_removed = EventOf[MovementEventCallback]()
    """Register a callback for movements the server removes (``mrm``).

    The server does not say why: a battle ending, a finished recall and a
    support sent home all look the same; :meth:`on_incoming_attack_withdrawn`
    tells an announced attack removed before it arrives, and
    :meth:`on_occupation_ended` an announced occupation leaving. ``movement`` is
    ``None`` if state was not tracking it. Accepts either signature (see
    :meth:`on_movement_arrived`).

    Runs on the callback thread, in packet order (see :class:`GameState`).
    """

    def __init__(self) -> None:
        super().__init__()
        self._announcer = MovementAnnouncer(
            AttackEvents(self.on_incoming_attack, self.on_incoming_attack_updated, self.on_incoming_attack_withdrawn),
            OccupationEvents(self.on_occupation_started, self.on_occupation_updated, self.on_occupation_ended),
            self._fire,
        )

    def _wake_movement_clock(self) -> None:
        """Set the movement clock for ``_next_movement_due``, starting it for the first one; under the lock.

        The clock waits on the monotonic clock, set from the wall clock here,
        so it keeps time even if the wall clock is moved meanwhile.
        """
        self._movement_clock_at = time.monotonic() + self._next_movement_due - time.time()
        if self._movement_clock_thread is not None:
            self._movement_clock.notify()
        elif self._next_movement_due < math.inf:
            self._movement_clock_thread = threading.Thread(
                target=self._run_movement_clock, name="gge_movement_clock", daemon=True
            )
            self._movement_clock_thread.start()

    def _run_movement_clock(self) -> None:
        """Advance the movements as each one falls due; ends once none is due, or on :meth:`shutdown`."""
        with self._lock:
            while self._movement_clock_thread is threading.current_thread():
                if self._next_movement_due == math.inf:
                    self._movement_clock_thread = None
                    return
                wait = self._movement_clock_at - time.monotonic()
                if wait > 0:
                    self._movement_clock.wait(min(wait, MOVEMENT_CLOCK_MAX_WAIT))
                else:
                    self._advance_movements()
                    self._wake_movement_clock()

    @staticmethod
    def _accepts_movement(callback: Callable[..., Any]) -> bool:
        """True if ``callback`` takes the Movement as a second positional arg; its signature is read once.

        Callables whose signature cannot be inspected (some builtins/C
        functions) are treated as id-only, which is the historical behavior.
        """
        try:
            return _ACCEPTS_MOVEMENT[callback]
        except (KeyError, TypeError):
            pass
        try:
            kinds = [param.kind for param in inspect.signature(callback).parameters.values()]
        except (TypeError, ValueError):
            kinds = []
        accepts = inspect.Parameter.VAR_POSITIONAL in kinds or sum(kind in _POSITIONAL for kind in kinds) >= 2
        # A callable that takes no weak reference is read on every call
        with contextlib.suppress(TypeError):
            _ACCEPTS_MOVEMENT[callback] = accepts
        return accepts

    def _dispatch_movement_event(
        self, callbacks: BoundEvent[MovementEventCallback], mid: int, mov: Movement | None
    ) -> None:
        """Fire arrival/recall listeners, passing the Movement to those that want it."""
        for callback in callbacks.calls():
            if self._accepts_movement(callback):
                self._dispatch_callback(callback, mid, mov)
            else:
                self._dispatch_callback(callback, mid)

    def _handle_gam(self, data: Any) -> None:
        """Handle 'Get Army Movements' response.

        Movements missing from the list are kept, as the client keeps them:
        they leave state when they arrive or when the server removes them.

        Client: ``GAMCommand.executeCommand`` (split.js line 638976); see :class:`GetMovementsResponse`
        """
        if (response := self._read_movement_reply(GetMovementsResponse, data)) is not None:
            self._apply_movement_list(response, response.owners)

    def _apply_movement_list(self, response: GetMovementsResponse, owners: Iterable[MovementOwner]) -> None:
        """Store a movement list with ``owners``, reporting each movement it could not read."""
        for reason in response.unreadable_movements:
            self._log_movement_parse_failure(reason)
        self._apply_movement_wrappers(response.movements, owners)

    def _handle_movement_push(self, data: Any) -> None:
        """Handle abr/asr, pushed as an army comes within range of its target; see :class:`ArmyRadiusPush`."""
        if (push := self._read_movement_reply(ArmyRadiusPush, data)) is not None:
            self._apply_movement_wrappers(
                [push.movement] if push.movement is not None else [],
                [push.owner] if push.owner is not None else [],
            )

    def _handle_mcm(self, data: Any) -> None:
        """Handle mcm, the reply to your own recall: the movement, now heading home.

        Client: ``MCMCommand.executeCommand`` (split.js line 639021); see :class:`CancelMovementResponse`
        """
        if (reply := self._read_movement_reply(CancelMovementResponse, data)) is not None:
            for mov in self._apply_movement_wrappers([reply.movement], ()):
                self._dispatch_movement_event(self.on_movement_recalled, mov.movement_id, mov)

    def _read_movement_reply(self, model: type[_Reply], data: Any) -> _Reply | None:
        """``data`` read as ``model``; None when it is no object, or when it cannot be read, which is logged."""
        if not isinstance(data, dict):
            return None
        try:
            return model.model_validate(data)
        except ValidationError as error:
            self._log_movement_parse_failure(str(error), error)
            return None

    def _apply_movement_wrappers(
        self, wrappers: Iterable[MovementWrapper], owners: Iterable[MovementOwner]
    ) -> list[Movement]:
        """Store the movements of ``wrappers``, after the owner records; return the ones stored.

        The owner records (``O``) are kept for the session, so a movement whose
        owner came in an earlier packet still finds it, as the client's owner list
        does (``CastleOtherPlayerData.getOwnerInfoVO``, split.js line 693146).

        Client: ``CastleArmyData.parseMapMovementArray`` (split.js line 667169).
        """
        sent = {record.player_id: record for record in owners}
        if sent:
            self._owner_records = {**self._owner_records, **sent}

        stored = []
        for wrapper in wrappers:
            if (mov := self._parse_movement(wrapper)) is not None:
                self._store_movement(mov)
                stored.append(mov)
        return stored

    def _store_movement(self, mov: Movement) -> None:
        """Insert or merge a parsed movement, and hand it to the announcer.

        Names, owner records, units, the size estimate and the commander a
        later packet leaves out are kept from the earlier one.
        """
        mid = mov.movement_id
        existing = self.movements.get(mid)

        if existing is None:
            mov.created_at = time.time()
            # Arrived before we saw it (a stationed support after login):
            # there is no arrival to report.
            if mov.estimated_arrival <= mov.created_at:
                self._arrival_dispatched.add(mid)
        else:
            # Preserve metadata that later packets may not include
            mov.created_at = existing.created_at
            mov.force_cancelable = mov.force_cancelable or existing.force_cancelable
            mov.source_player_name = mov.source_player_name or existing.source_player_name
            mov.source_alliance_name = mov.source_alliance_name or existing.source_alliance_name
            mov.target_player_name = mov.target_player_name or existing.target_player_name
            mov.target_alliance_name = mov.target_alliance_name or existing.target_alliance_name
            mov.owner = mov.owner or existing.owner
            mov.target_owner = mov.target_owner or existing.target_owner
            if not mov.units and existing.units:
                mov.units = existing.units
            mov.estimated_size = mov.estimated_size or existing.estimated_size
            mov.commander = mov.commander or existing.commander

        alliance = self.local_player.alliance if self.local_player else None
        self._announcer.stored(
            existing,
            mov,
            arrived=mid in self._arrival_dispatched,
            alliance_id=alliance.alliance_id if alliance else None,
        )
        self.movements[mid] = mov
        self._schedule_movement(mid, mov)

    def _schedule_movement(self, mid: int, mov: Movement) -> tuple[float, float]:
        """Take the movement's arrival and end now, so a packet with nothing due costs no scan."""
        times = self._movement_times[mid] = (mov.estimated_arrival, mov.estimated_end)
        due = times[1] if mid in self._arrival_dispatched else times[0]
        if due < self._next_movement_due:
            self._next_movement_due = due
            self._wake_movement_clock()
        return times

    def _advance_movements(self) -> None:
        """Fire arrivals whose travel time is up and drop movements that are over.

        Runs under the lock on every packet, every movement query and when
        the movement clock reaches the next one due. A movement leaves
        state at ``estimated_end``, which for anything but a stationed army
        is its arrival. Arrival and end are taken when the movement is
        stored, so the movements are scanned only once one of them is due;
        the scan then goes through them in the order they were first seen,
        as the client's does. Commander availability is derived from the
        remaining movements and a one-second margin after returns or attacks end
        (see :meth:`get_away_commanders`).

        Client: ``CastleArmyData.updateMapmovements`` (bundle line 133670).
        """
        now = time.time()
        arrived = []
        if now >= self._next_movement_due:
            next_due = math.inf
            dispatched = self._arrival_dispatched
            for mid, mov in list(self.movements.items()):
                times = self._movement_times.get(mid)
                if times is None:
                    times = self._schedule_movement(mid, mov)
                if mid not in dispatched and now >= times[0]:
                    dispatched.add(mid)
                    arrived.append((mov, self._announcer.arrived(mov)))
                if now >= times[1]:
                    del self.movements[mid]
                    del self._movement_times[mid]
                    dispatched.discard(mid)
                    if mov.is_mine and (mov.is_returning or mov.is_attack) and mov.commander is not None:
                        cid = mov.commander.commander_id
                        hold_until = times[1] + RETURN_COMMANDER_HOLD
                        previous = self._returning_commanders.get(cid)
                        if previous is None or hold_until > previous[1]:
                            self._returning_commanders[cid] = (mov.commander, hold_until)
                else:
                    due = times[1] if mid in dispatched else times[0]
                    if due < next_due:
                        next_due = due
            self._next_movement_due = next_due
            self._wake_movement_clock()
        # After the scan, so an occupation that ends now is still known as announced at its arrival
        self._announcer.prune(now)
        for mov, leaving in arrived:
            self._dispatch_movement_event(self.on_movement_arrived, mov.movement_id, mov)
            for callback, args in leaving:
                self._dispatch_callback(callback, *args)

    def _handle_mrm(self, data: dict[str, Any]) -> None:
        """Handle mrm, the server removing a movement.

        The removed Movement is passed to callbacks that take it: it is gone
        from state by the time they run. An announced attack more than two
        seconds short of its estimated arrival is also reported as withdrawn
        (see :meth:`on_incoming_attack_withdrawn`), and an announced occupation
        as ended (see :meth:`on_occupation_ended`).

        Client: ``MRMCommand.executeCommand`` (bundle line 126109), ``CastleArmyData.parse_MRM`` (bundle
        line 133682); see :class:`MovementRemovedResponse`
        """
        removed = read_section(MovementRemovedResponse, data, "a movement removal")
        if removed is None or removed.movement_id is None:
            return
        mid = removed.movement_id
        mov = self.movements.pop(mid, None)
        self._movement_times.pop(mid, None)
        leaving = self._announcer.removed(mid, mov, arrived=mid in self._arrival_dispatched)
        self._arrival_dispatched.discard(mid)
        self._dispatch_movement_event(self.on_movement_removed, mid, mov)
        for callback, args in leaving:
            self._dispatch_callback(callback, *args)

    def _handle_mfc(self, data: dict[str, Any]) -> None:
        """Handle mfc: the movement can now be force-cancelled.

        Client: ``MFCCommand.executeCommand`` (bundle line 126094), ``CastleArmyData.parse_MFC`` (bundle
        line 133683); see :class:`MovementForceCancelableResponse`
        """
        flagged = read_section(MovementForceCancelableResponse, data, "a force-cancelable movement")
        mov = self.movements.get(flagged.movement_id) if flagged is not None and flagged.movement_id else None
        if mov is not None:
            mov.force_cancelable = True

    def _handle_mvf(self, data: Any) -> None:
        """Keep the map's movement filters; a push also makes the client ask for the movements again.

        Client: ``MVFCommand.executeCommand`` (bundle line 129751), ``CastleSettingsData.parse_MVF`` (bundle
        line 139750), which does nothing for a falsy body
        """
        if (filters := read_section(MovementFilterResponse, data, "the movement filters")) is not None:
            self.movement_filter = filters

    def get_movement_filter(self) -> MovementFilterResponse | None:
        """The map's movement filters, from the login data's ``mvf`` or the last push; None until one arrived."""
        with self._lock:
            return self.movement_filter

    def _parse_movement(self, wrapper: MovementWrapper) -> Movement | None:
        """The tracked Movement a wrapper gives, named from the owner records; None, logged, when it cannot be built."""
        record = wrapper.movement
        # Only the keys sent: the announcer tells a missing OID, which the client reads as 0, by the fields set
        fields: dict[str, Any] = {
            _MOVEMENT_FIELDS.get(name, name): getattr(record, name)
            for name in record.model_fields_set
            if name in MovementRecord.model_fields
        }
        fields.update(last_updated=time.time(), **self._wrapper_fields(wrapper))
        if self.local_player is not None:
            fields["local_player_id"] = self.local_player.PID
        for side, area in (("target", record.target_area), ("source", record.source_area)):
            if area is not None:
                fields[f"{side}_x"] = area.x
                fields[f"{side}_y"] = area.y
                fields[f"{side}_area_id"] = area.object_id if area.object_id is not None else -1
                fields[f"{side}_name"] = area.name
        if record.target_area is not None:
            fields["target_type"] = record.target_area.area_type
        if (owner := self._owner_records.get(record.owner_id)) is not None:
            fields.update(owner=owner, source_player_name=owner.name, source_alliance_name=owner.alliance_name)
        if (target := self._owner_records.get(record.target_id)) is not None:
            fields.update(
                target_owner=target, target_player_name=target.name, target_alliance_name=target.alliance_name
            )
        try:
            return Movement.model_validate(fields)
        except ValidationError as error:
            self._log_movement_parse_failure(str(error), error)
            return None

    @staticmethod
    def _wrapper_fields(wrapper: MovementWrapper) -> dict[str, Any]:
        """The Movement fields the wrapper's army, wait, cargo and flags give.

        Client: ``ArmyAttackMapmovementVO.loadFromParamObject`` (split.js line 77036),
        ``BasicMapmovementVO.parseUnitMovement`` (split.js line 87638), ``ArmyTravelMapMovementVO``
        (split.js line 114881), ``MarketMapmovementVO`` (split.js line 225968) and
        ``SpyMapmovementVO.parseSpyInfo`` (split.js line 226176)
        """
        army = wrapper.visible_army
        parts = [army.left, army.middle, army.right, army.courtyard] if army is not None else [wrapper.travel_units]
        units: dict[UnitOrTool, int] = {}
        for part in parts:
            for unit, amount in part.items():
                units[unit] = units.get(unit, 0) + amount

        goods = wrapper.market.goods if wrapper.market is not None else wrapper.travel_goods
        amounts: dict[str, int] = {}
        for good in goods:
            amounts[good.kind.server_key] = amounts.get(good.kind.server_key, 0) + int(good.amount)

        fields: dict[str, Any] = {
            "units": units,
            "goods": goods,
            "resources": MovementResources.model_validate(amounts),
            "attack_type": wrapper.attack_type,
            "is_shadow": wrapper.is_shadow,
            "force_cancelable": wrapper.force_cancelable,
            "support_tools": wrapper.support_tools,
            "auto_skip_cooldown_type": wrapper.auto_skip_cooldown_type,
            "spy": wrapper.spy,
        }
        if wrapper.army_size is not None:
            fields["estimated_size"] = wrapper.army_size
        if wrapper.market is not None:
            fields["market_carriages"] = wrapper.market.carriages
        if (info := wrapper.unit_info) is not None:
            fields.update(
                wait_total=info.wait_total,
                wait_passed=info.wait_passed,
                advisor_type=info.advisor_type,
                advisor_movement_count=info.advisor_movement_count,
                advisor_movement_number=info.advisor_movement_number,
                advisor_is_last=info.advisor_is_last == 1,
                commander=info.commander,
            )
        return fields

    def _log_movement_parse_failure(self, reason: str, error: ValidationError | None = None) -> None:
        """Report a dropped movement loudly, but at most once a minute.

        Movements — including the incoming attacks this library exists to
        alert on — disappear silently when the schema drifts, so the failure
        must be visible at the default level, with the traceback when there
        is one. Schema drift fails on every packet, so the warning is
        rate-limited and the suppressed count is reported with the next one.
        """
        self._movement_parse_failures += 1
        now = time.time()
        if now < self._movement_parse_warn_at:
            logger.debug(f"Failed to read a movement (warning rate-limited): {reason}")
            return

        suppressed = self._movement_parse_failures - 1
        self._movement_parse_failures = 0
        self._movement_parse_warn_at = now + MOVEMENT_PARSE_WARN_INTERVAL
        extra = f" ({suppressed} further failures suppressed)" if suppressed else ""
        logger.warning(
            f"Failed to read a movement — it is being dropped, incoming attacks may be missed{extra}: {reason}",
            exc_info=error,
        )

    def get_all_movements(self) -> list[Movement]:
        """Get all tracked movements (stale ones pruned first)."""
        with self._lock:
            self._advance_movements()
            return list(self.movements.values())

    def get_away_commanders(self) -> list[Commander]:
        """The commanders your movements keep away, as those movements carry them.

        Returning movements and armies waiting at their target count until
        their estimated end. A returning commander stays unavailable for
        ``RETURN_COMMANDER_HOLD`` seconds after that end, the longest the client
        keeps it busy. Outbound attacks get the same bounded margin to bridge
        the arrival of a return packet; other outbound movements do not.

        Client: ``LordVO.isAvailableForMovement`` (bundle line 140072) is false while an own
        map movement (``BasicMapmovementVO.isMyMovement``, bundle line 87910) has the lord.
        ``CastleArmyData.updateMapmovements`` (bundle line 667375) removes a movement once its
        ``currentProgress`` (bundle line 87668), any waiting duration included, reaches 1, but
        runs only from ``executeUpdate``, which ``BasicData.update`` (ggs.dll.js) calls at most
        once per ``_updateInterval`` of 1e3 ms. ``CastleGame.onEnterFrame`` (bundle line 71137)
        drives that update through ``modelObserverManager``, which ``subscribeCommonModels``
        (bundle line 71859) subscribes the army data to. So the client keeps a commander
        unavailable for up to one second after its movement ends.
        """
        with self._lock:
            self._advance_movements()
            now = time.time()
            self._returning_commanders = {
                cid: held for cid, held in self._returning_commanders.items() if now < held[1]
            }
            away = {cid: commander for cid, (commander, _) in self._returning_commanders.items()}
            for mov in self.movements.values():
                if mov.is_mine and mov.commander is not None:
                    away[mov.commander.commander_id] = mov.commander
            return list(away.values())

    def get_incoming_movements(self) -> list[Movement]:
        """Other players' armies heading to the local player (see ``Movement.is_incoming``); occupations are not.

        :meth:`get_occupations` lists those the library announced.
        """
        with self._lock:
            self._advance_movements()
            return [m for m in self.movements.values() if m.is_incoming]

    def get_outgoing_movements(self) -> list[Movement]:
        """The local player's armies heading to their targets, returns excluded."""
        with self._lock:
            self._advance_movements()
            return [m for m in self.movements.values() if m.is_outgoing]

    def get_incoming_attacks(self) -> list[Movement]:
        """Get all incoming attack movements.

        Attacks whose travel time is up are dropped first, so this never
        reports one that has landed.
        """
        with self._lock:
            self._advance_movements()
            return [m for m in self.movements.values() if m.is_incoming and m.is_attack]

    def get_announced_attacks(self) -> list[Movement]:
        """The attacks :meth:`on_incoming_attack` announced that are still on their way, in the order announced.

        Each is the Movement as state holds it now, from the latest packet that
        carried it. Unlike :meth:`get_incoming_attacks`, which lists the attacks
        aimed at you, this is what the callback reported, attacks on alliance
        members included. An attack leaves it when it arrives or the server
        removes it. After a reconnect, or a ``close()`` and ``login()``, an
        attack is listed again once a packet lists it, without being announced
        again (see :meth:`reannounce`): a client handed to a new holder does
        not announce to it what it announced before.

        Library bookkeeping: the client keeps no record of what it announced.
        """
        with self._lock:
            self._advance_movements()
            return self._announcer.listed(self._announcer.attacks, self.movements)

    def get_occupations(self) -> list[Movement]:
        """The occupations :meth:`on_occupation_started` announced that have not ended, in the order announced.

        Listed as :meth:`get_announced_attacks` lists attacks; an occupation
        leaves the list as :meth:`on_occupation_ended` reports it.
        """
        with self._lock:
            self._advance_movements()
            return self._announcer.listed(self._announcer.occupations, self.movements)

    def reannounce(self, movement_id: int, *, when_listed: bool = False) -> bool:
        """Fire :meth:`on_incoming_attack` or :meth:`on_occupation_started` again for an announced movement.

        For a consumer whose callback could not act on the announcement (an
        alert that failed to send). The callbacks get the Movement as state
        holds it now, on the callback thread, behind those already queued.
        Nothing else changes: the movement stays announced, so no packet
        announces it again. A ``client.listen()`` stream gets it as an
        ordinary ``incoming_attack`` or ``occupation_started`` event.

        After a reconnect, a movement announced before it is known again
        only once a packet lists it: the movement list the server pushes
        after the login. ``on_session_restored`` fires once that list has
        come, or once ``config.request_timeout`` passed without it (a
        warning is logged), so even there it may not be listed yet. Until
        then the callbacks cannot fire. With ``when_listed`` they are queued
        instead, and fire once, with the Movement as the next packet that
        lists it has it, however often this was called. The queued call is
        dropped without firing if no packet lists the movement before its
        travel time is over, the server removes it, or it is listed again
        with its arrival behind it. An :class:`~empire_core.pool.AccountPool`
        release drops it too.

        Args:
            movement_id: The movement to announce again.
            when_listed: Queue the callbacks for an announced movement no
                packet has listed since a reconnect, instead of returning False.

        Returns:
            True if the callbacks were queued, now or with ``when_listed`` for
            the next listing; False if ``movement_id`` is not announced (never
            announced, arrived or ended, or removed), or without
            ``when_listed`` not listed again since a reconnect.

        Library bookkeeping: the client announces nothing (see :meth:`on_incoming_attack`).
        """
        with self._lock:
            self._advance_movements()
            return self._announcer.reannounce(movement_id, self.movements.get(movement_id), when_listed=when_listed)

    def _forget_queued_reannounces(self) -> None:
        """Drop every :meth:`reannounce` ``when_listed`` call still waiting, as the client is handed on."""
        with self._lock:
            self._announcer.reannounce_when_listed.clear()

    def get_movement_by_id(self, movement_id: int) -> Movement | None:
        """Get a tracked movement by its ``Movement.movement_id``, as ``client.movements.get_movements()`` lists it."""
        with self._lock:
            self._advance_movements()
            return self.movements.get(movement_id)
