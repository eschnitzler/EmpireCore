"""Movement tracking: gam and its pushes, arrival, removal and the movement queries."""

import contextlib
import inspect
import logging
import math
import time
import weakref
from collections.abc import Callable
from typing import Any

from empire_core.movements.models import MovementArea, MovementOwner, MovementWrapper
from empire_core.movements.tracked import Movement, MovementResources
from empire_core.protocol.base import read_or_none, readable_list
from empire_core.state.announcer import AttackEvents, MovementAnnouncer, OccupationEvents
from empire_core.state.base import MovementEventCallback, StateBase
from empire_core.utils.callbacks import BoundEvent, Event, EventOf

_POSITIONAL = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
# Whether an arrival, recall or removal callback takes the Movement, by callback, while it lives
_ACCEPTS_MOVEMENT: weakref.WeakKeyDictionary[Callable[..., Any], bool] = weakref.WeakKeyDictionary()

logger = logging.getLogger(__name__)

# A drifted movement schema would fail on every packet, so the warning is
# rate-limited to one per this interval; the rest go to debug.
MOVEMENT_PARSE_WARN_INTERVAL = 60.0


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
    owner, the plague monk, or an NPC id the client does not know); robber
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
    arrives once its travel time is up. The check runs on every packet
    and every movement query, so a callback fires with the first of those
    after arrival. It fires once per movement, and not for a movement
    first seen after it had already arrived.

    An army that stays at its target (a stationed support) is kept in
    state until its wait is over (``estimated_end``); every other
    movement is removed before callbacks run. An army's way home is a
    movement too, so it fires when the army gets back; check
    ``movement.is_returning`` to tell the two apart.

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

    def _handle_gam(self, data: dict[str, Any]) -> None:
        """Handle 'Get Army Movements' response.

        Movements missing from the list are kept, as the client keeps them:
        they leave state when they arrive or when the server removes them.

        Client: ``CastleArmyData.parse_GAM``.
        """
        self._apply_movement_wrappers(data.get("M", []), data.get("O", []))

    def _handle_movement_push(self, data: dict[str, Any]) -> None:
        """Handle abr/asr, pushed as an army comes within range of its target.

        Client: ``CastleArmyData.parse_ABR`` / ``parse_ASR``.
        """
        self._apply_movement_wrappers([data.get("A")], data.get("O", []))

    def _handle_mcm(self, data: dict[str, Any]) -> None:
        """Handle mcm, the reply to your own recall: the movement, now heading home.

        Client: ``MCMCommand``.
        """
        for mov in self._apply_movement_wrappers([data.get("A")], []):
            self._dispatch_movement_event(self.on_movement_recalled, mov.movement_id, mov)

    def _apply_movement_wrappers(self, wrappers: Any, owners: Any) -> list[Movement]:
        """Parse and store ``gam``-style movement wrappers; return the ones stored.

        The owner records (``O``) are kept for the session, so a movement whose
        owner came in an earlier packet still finds it, as the client's owner list
        does (``CastleOtherPlayerData.getOwnerInfoVO``, bundle line 138994).

        Client: ``CastleArmyData.parseMapMovementArray``.
        """
        sent = {record.player_id: record for record in readable_list(MovementOwner, owners)}
        if sent:
            self._owner_records = {**self._owner_records, **sent}
        owner_info = self._owner_records

        stored = []
        for m_wrapper in wrappers if isinstance(wrappers, list) else []:
            if not isinstance(m_wrapper, dict):
                continue
            m_data = m_wrapper.get("M", {})
            if not m_data or m_data.get("MID") is None:
                continue
            mov = self._parse_movement(m_data, m_wrapper, owner_info)
            if mov:
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
            existing, mov, arrived=mid in self._arrival_dispatched, alliance_id=alliance.id if alliance else None
        )
        self.movements[mid] = mov
        self._schedule_movement(mid, mov)

    def _schedule_movement(self, mid: int, mov: Movement) -> tuple[float, float]:
        """Take the movement's arrival and end now, so a packet with nothing due costs no scan."""
        times = self._movement_times[mid] = (mov.estimated_arrival, mov.estimated_end)
        due = times[1] if mid in self._arrival_dispatched else times[0]
        if due < self._next_movement_due:
            self._next_movement_due = due
        return times

    def _advance_movements(self) -> None:
        """Fire arrivals whose travel time is up and drop movements that are over.

        Runs under the lock on every packet and every movement query. A
        movement leaves state at ``estimated_end``, which for anything but a
        stationed army is its arrival. Arrival and end are taken when the
        movement is stored, so the movements are scanned only once one of
        them is due; the scan then goes through them in the order they were
        first seen, as the client's does.

        Client: ``CastleArmyData.updateMapmovements``.
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
                else:
                    due = times[1] if mid in dispatched else times[0]
                    if due < next_due:
                        next_due = due
            self._next_movement_due = next_due
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

        Client: ``CastleArmyData.parse_MRM``.
        """
        mid = data.get("MID")
        if mid is None:
            return
        mov = self.movements.pop(mid, None)
        self._movement_times.pop(mid, None)
        leaving = self._announcer.removed(mid, mov, arrived=mid in self._arrival_dispatched)
        self._arrival_dispatched.discard(mid)
        self._dispatch_movement_event(self.on_movement_removed, mid, mov)
        for callback, args in leaving:
            self._dispatch_callback(callback, *args)

    def _handle_mfc(self, data: dict[str, Any]) -> None:
        """Handle mfc: the movement can now be force-cancelled.

        Client: ``CastleArmyData.parse_MFC``.
        """
        mid = data.get("MID")
        mov = self.movements.get(mid) if isinstance(mid, int) else None
        if mov is not None:
            mov.force_cancelable = True

    def _parse_movement(
        self,
        m_data: dict[str, Any],
        m_wrapper: dict[str, Any] | None = None,
        owner_info: dict[int, MovementOwner] | None = None,
    ) -> Movement | None:
        """Parse a Movement from packet data, built in one validation."""
        mid = m_data.get("MID")
        if mid is None:
            return None

        try:
            data: dict[str, Any] = dict(m_data)
            data["last_updated"] = time.time()
            if self.local_player is not None:
                data["local_player_id"] = self.local_player.PID
            for key, side in (("TA", "target"), ("SA", "source")):
                area = read_or_none(MovementArea.model_validate, data[key]) if data.get(key) else None
                data[key] = area
                if area is None:
                    continue
                data[f"{side}_x"] = area.x
                data[f"{side}_y"] = area.y
                data[f"{side}_area_id"] = area.object_id if area.object_id is not None else -1
                data[f"{side}_name"] = area.name
                if side == "target":
                    data["target_type"] = area.area_type
            if m_wrapper:
                data.update(self._wrapper_fields(m_wrapper))
            mov = Movement.model_validate(data)

            if owner_info:
                names: dict[str, Any] = {}
                if (owner := owner_info.get(mov.owner_id)) is not None:
                    names.update(owner=owner, source_player_name=owner.name, source_alliance_name=owner.alliance_name)
                if (target := owner_info.get(mov.target_id)) is not None:
                    names.update(
                        target_owner=target, target_player_name=target.name, target_alliance_name=target.alliance_name
                    )
                if names:
                    # Already-validated values, set as pydantic's own __setattr__ would
                    mov.__dict__.update(names)
                    mov.__pydantic_fields_set__.update(names)

            return mov
        except Exception:
            self._log_movement_parse_failure(mid)
            return None

    @staticmethod
    def _wrapper_blocks(m_wrapper: dict[str, Any]) -> Callable[[str], MovementWrapper | None]:
        """The wrapper validated once; if that fails, each block on its own, so a drifted block costs only itself."""
        # The record itself is read into the Movement, so it is not validated here too
        whole = read_or_none(MovementWrapper.model_validate, {**m_wrapper, "M": {"MID": 0}})
        if whole is not None:
            return lambda key: whole if key in m_wrapper else None
        blocks = {
            key: read_or_none(MovementWrapper.model_validate, {"M": {"MID": 0}, key: value})
            for key, value in m_wrapper.items()
            if key != "M"
        }
        return blocks.get

    def _wrapper_fields(self, m_wrapper: dict[str, Any]) -> dict[str, Any]:
        """The Movement fields the wrapper's army, wait, cargo and flags give.

        Client: ``ArmyAttackMapmovementVO.loadFromParamObject``, ``parseUnitMovement``,
        ``ArmyTravelMapMovementVO`` and ``MarketMapmovementVO``.
        """
        block = self._wrapper_blocks(m_wrapper)
        fields: dict[str, Any] = {}

        army = next((b.visible_army for b in (block("FA"), block("GA")) if b and b.visible_army), None)
        if army is not None:
            pairs = [*army.left, *army.middle, *army.right, *army.courtyard]
        elif (travel := block("A")) is not None:
            pairs = travel.travel_units
        else:
            pairs = []
        units: dict[int, int] = {}
        for pair in pairs:
            if len(pair) >= 2:
                units[pair[0]] = units.get(pair[0], 0) + pair[1]
        fields["units"] = units

        if (gs := block("GS")) is not None and gs.army_size is not None:
            fields["estimated_size"] = gs.army_size

        if (um := block("UM")) is not None and um.unit_info is not None:
            info = um.unit_info
            fields.update(
                wait_total=info.wait_total,
                wait_passed=info.wait_passed,
                advisor_type=info.advisor_type,
                advisor_movement_count=info.advisor_movement_count,
                advisor_movement_number=info.advisor_movement_number,
                advisor_is_last=info.advisor_is_last == 1,
            )
            if info.commander is not None:
                fields["commander"] = info.commander

        goods: Any = []
        if (mm := block("MM")) is not None and mm.market is not None:
            fields["market_carriages"] = mm.market.carriages
            goods = fields["goods"] = mm.market.goods
        elif (loot := block("G")) is not None:
            goods = fields["goods"] = loot.travel_goods
        amounts: dict[str, int] = {}
        for entry in goods:
            if isinstance(entry, tuple) and isinstance(entry[0], str):
                amounts[entry[0]] = amounts.get(entry[0], 0) + entry[1]
        fields["resources"] = MovementResources.model_validate(amounts)

        if (att := block("ATT")) is not None:
            fields["attack_type"] = att.attack_type
        if (sm := block("SM")) is not None:
            fields["is_shadow"] = sm.is_shadow
        if (fc := block("FC")) is not None:
            fields["force_cancelable"] = fc.force_cancelable
        if (ast := block("AST")) is not None:
            fields["support_tool_ids"] = ast.support_tools
        if (asct := block("ASCT")) is not None:
            fields["auto_skip_cooldown_type"] = asct.auto_skip_cooldown_type
        # Client: SpyMapmovementVO.parseSpyInfo (bundle line 43748)
        if (spy := block("S")) is not None and spy.spy is not None:
            fields["spy"] = spy.spy
        return fields

    def _log_movement_parse_failure(self, mid: Any) -> None:
        """Report a dropped movement loudly, but at most once a minute.

        Movements — including the incoming attacks this library exists to
        alert on — disappear silently when the schema drifts, so the failure
        must be visible at the default level with a traceback. Schema drift
        fails on every packet, so the warning is rate-limited and the
        suppressed count is reported with the next one.
        """
        self._movement_parse_failures += 1
        now = time.time()
        if now < self._movement_parse_warn_at:
            logger.debug(f"Failed to parse movement {mid} (warning rate-limited)")
            return

        suppressed = self._movement_parse_failures - 1
        self._movement_parse_failures = 0
        self._movement_parse_warn_at = now + MOVEMENT_PARSE_WARN_INTERVAL
        extra = f" ({suppressed} further failures suppressed)" if suppressed else ""
        logger.exception(f"Failed to parse movement {mid} — it is being dropped, incoming attacks may be missed{extra}")

    def get_all_movements(self) -> list[Movement]:
        """Get all tracked movements (stale ones pruned first)."""
        with self._lock:
            self._advance_movements()
            return list(self.movements.values())

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
