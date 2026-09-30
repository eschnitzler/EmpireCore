"""Movement tracking: gam and its pushes, arrival, removal and the movement queries."""

import inspect
import logging
import math
import time
from collections.abc import Callable
from typing import Any

from empire_core.movements.models import MovementArea, MovementOwner, MovementWrapper
from empire_core.movements.tracked import DAIMYO_TOWNSHIP_PLAYER_ID, Movement, MovementResources
from empire_core.protocol.base import read_or_none, readable_list
from empire_core.state.base import MovementEventCallback, StateBase

logger = logging.getLogger(__name__)

# A drifted movement schema would fail on every packet, so the warning is
# rate-limited to one per this interval; the rest go to debug.
MOVEMENT_PARSE_WARN_INTERVAL = 60.0


class MovementState(StateBase):
    # Registration and removal happen on user threads while the receive
    # thread iterates the listener lists, so every access goes through
    # self._lock — CPython's per-op atomicity is not a guarantee to build
    # on and does not hold on free-threaded builds. The dispatch paths
    # iterate a snapshot taken under the lock; the callbacks themselves run
    # on the thread pool, outside it.

    def on_incoming_attack(self, callback: Callable[[Movement], None]) -> None:  # type: ignore[misc]
        """Register a callback for new hostile attack movements.

        Fires once per newly seen attack that is not the local player's own,
        is not on its way home and had not already landed when first seen.
        That covers attacks on you and every other attack the server shares
        with you, which includes your alliance members' own attacks (#58).

        Fires once per attack movement id, also across a reconnect: an attack
        still on its way when the connection drops is not announced again when
        the next login lists it. The record of an attack is dropped when it
        arrives, when the server removes it, or once its travel time is over.

        Runs on the callback thread, in packet order (see :class:`GameState`).
        """
        with self._lock:
            self._incoming_attack_callbacks.append(callback)

    def remove_incoming_attack_callback(self, callback: Callable[[Movement], None]) -> None:
        """Unregister an incoming attack callback."""
        with self._lock:
            self._incoming_attack_callbacks.remove(callback)

    def on_movement_recalled(self, callback: MovementEventCallback) -> None:  # type: ignore[misc]
        """Register a callback for your own recalled movements.

        Fires on the ``mcm`` reply to a recall, with the movement as it now
        stands: on its way home (``is_returning``). A plain removal (``mrm``)
        fires :meth:`on_movement_removed` instead.

        Accepts either signature (see :meth:`on_movement_arrived`)::

            def on_recalled(movement_id: int) -> None: ...
            def on_recalled(movement_id: int, movement: Movement | None) -> None: ...

        Runs on the callback thread, in packet order (see :class:`GameState`).
        """
        entry = (callback, self._accepts_movement(callback))
        with self._lock:
            self._movement_recalled_callbacks.append(entry)

    def remove_movement_recalled_callback(self, callback: MovementEventCallback) -> None:
        """Unregister a movement recalled callback."""
        with self._lock:
            self._remove_listener(self._movement_recalled_callbacks, callback)

    def on_movement_arrived(self, callback: MovementEventCallback) -> None:  # type: ignore[misc]
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
        entry = (callback, self._accepts_movement(callback))
        with self._lock:
            self._movement_arrived_callbacks.append(entry)

    def remove_movement_arrived_callback(self, callback: MovementEventCallback) -> None:
        """Unregister a movement arrived callback."""
        with self._lock:
            self._remove_listener(self._movement_arrived_callbacks, callback)

    def on_movement_removed(self, callback: MovementEventCallback) -> None:  # type: ignore[misc]
        """Register a callback for movements the server removes (``mrm``).

        The server does not say why: a battle ending, a finished recall and a
        support sent home all look the same. ``movement`` is ``None`` if state
        was not tracking it. Accepts either signature (see
        :meth:`on_movement_arrived`).

        Runs on the callback thread, in packet order (see :class:`GameState`).
        """
        entry = (callback, self._accepts_movement(callback))
        with self._lock:
            self._movement_removed_callbacks.append(entry)

    def remove_movement_removed_callback(self, callback: MovementEventCallback) -> None:
        """Unregister a movement removed callback."""
        with self._lock:
            self._remove_listener(self._movement_removed_callbacks, callback)

    @staticmethod
    def _accepts_movement(callback: Callable[..., Any]) -> bool:
        """True if ``callback`` takes the Movement as a second positional arg.

        Decided once, at registration. Callables whose signature cannot be
        inspected (some builtins/C functions) are treated as id-only, which is
        the historical behavior.
        """
        try:
            parameters = inspect.signature(callback).parameters.values()
        except (TypeError, ValueError):
            return False
        positional = 0
        for param in parameters:
            if param.kind is inspect.Parameter.VAR_POSITIONAL:
                return True
            if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
                positional += 1
        return positional >= 2

    @staticmethod
    def _remove_listener(
        listeners: list[tuple[MovementEventCallback, bool]],
        callback: MovementEventCallback,
    ) -> None:
        """Remove the first registration of ``callback`` (``list.remove`` semantics)."""
        for index, (registered, _) in enumerate(listeners):
            if registered == callback:
                del listeners[index]
                return
        raise ValueError(f"callback {callback!r} is not registered")

    def _dispatch_movement_event(
        self,
        listeners: list[tuple[MovementEventCallback, bool]],
        mid: int,
        mov: Movement | None,
    ) -> None:
        """Fire arrival/recall listeners, passing the Movement to those that want it."""
        with self._lock:
            snapshot = list(listeners)
        for callback, wants_movement in snapshot:
            if wants_movement:
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
            self._dispatch_movement_event(self._movement_recalled_callbacks, mov.movement_id, mov)

    def _apply_movement_wrappers(self, wrappers: Any, owners: Any) -> list[Movement]:
        """Parse and store ``gam``-style movement wrappers; return the ones stored.

        Client: ``CastleArmyData.parseMapMovementArray``.
        """
        owner_info = {record.player_id: record for record in readable_list(MovementOwner, owners)}

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

    def _is_attack_on_us(self, mov: Movement) -> bool:
        """A new attack aimed at the local player or at a member of their alliance.

        Client: ``CastleArmyData.checkAllAttackMovements``. An attack on you
        (``isAttackingMovement``: the target is you, or the daimyo township,
        which the client files under your own owner record) counts whoever
        sends it. An attack on an alliance member other than you
        (``isAllyAttackingMovement``) counts only when
        ``showAsAllianceAttackWarning`` holds: the attacker is a player
        (``isNPCPlayer`` is ``id < 0``) whose owner record is known. The member
        list is matched through the target's owner record, whose alliance id
        comes with every movement.
        """
        if not mov.is_attack or mov.is_mine or mov.is_returning or mov.movement_id in self._arrival_dispatched:
            return False
        me = mov.local_player_id
        if me == -1:
            return False
        if mov.target_id in (me, DAIMYO_TOWNSHIP_PLAYER_ID):
            return True
        if mov.owner is None or mov.owner_id < 0:
            return False
        alliance = self.local_player.alliance if self.local_player else None
        return alliance is not None and alliance.id > 0 and mov.target_alliance_id == alliance.id

    def _store_movement(self, mov: Movement) -> None:
        """Insert or merge a parsed movement; fire callbacks for new attacks."""
        mid = mov.movement_id
        existing = self.movements.get(mid)

        if existing is None:
            mov.created_at = time.time()
            # Arrived before we saw it (a stationed support after login):
            # there is no arrival to report.
            if mov.estimated_arrival <= mov.created_at:
                self._arrival_dispatched.add(mid)
            if self._is_attack_on_us(mov) and mid not in self._announced_attacks:
                end = mov.estimated_end
                self._announced_attacks[mid] = end
                self._announced_prune_at = min(self._announced_prune_at, end)
                with self._lock:
                    attack_callbacks = list(self._incoming_attack_callbacks)
                for cb in attack_callbacks:
                    self._dispatch_callback(cb, mov)
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
        if now >= self._announced_prune_at:
            self._announced_attacks = {mid: end for mid, end in self._announced_attacks.items() if now < end}
            self._announced_prune_at = min(self._announced_attacks.values(), default=math.inf)
        if now < self._next_movement_due:
            return
        arrived = []
        next_due = math.inf
        dispatched = self._arrival_dispatched
        for mid, mov in list(self.movements.items()):
            times = self._movement_times.get(mid)
            if times is None:
                times = self._schedule_movement(mid, mov)
            if mid not in dispatched and now >= times[0]:
                dispatched.add(mid)
                self._announced_attacks.pop(mid, None)
                arrived.append(mov)
            if now >= times[1]:
                del self.movements[mid]
                del self._movement_times[mid]
                dispatched.discard(mid)
            else:
                due = times[1] if mid in dispatched else times[0]
                if due < next_due:
                    next_due = due
        self._next_movement_due = next_due
        for mov in arrived:
            self._dispatch_movement_event(self._movement_arrived_callbacks, mov.movement_id, mov)

    def _handle_mrm(self, data: dict[str, Any]) -> None:
        """Handle mrm, the server removing a movement.

        The removed Movement is passed to callbacks that take it: it is gone
        from state by the time they run.

        Client: ``CastleArmyData.parse_MRM``.
        """
        mid = data.get("MID")
        if mid is None:
            return
        mov = self.movements.pop(mid, None)
        self._movement_times.pop(mid, None)
        self._arrival_dispatched.discard(mid)
        self._announced_attacks.pop(mid, None)
        self._dispatch_movement_event(self._movement_removed_callbacks, mid, mov)

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
                fields["commander_equipment"] = list(info.commander.equipment)
                fields["commander_effects"] = list(info.commander.area_effects)

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
        """Other players' armies heading to the local player (see ``Movement.is_incoming``)."""
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

    def get_movement_by_id(self, movement_id: int) -> Movement | None:
        """Get a tracked movement by its ``Movement.movement_id``, as ``client.movements.get_movements()`` lists it."""
        with self._lock:
            self._advance_movements()
            return self.movements.get(movement_id)
