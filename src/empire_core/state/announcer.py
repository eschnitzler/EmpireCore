"""Announcing movements: which attacks and occupations count as on you, and the events they fire."""

import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from empire_core.enums import MovementType, NPCOwner
from empire_core.movements.tracked import DUNGEON_OWNER_IDS, Movement
from empire_core.utils.callbacks import BoundEvent

# Each packet anchors the arrival on its own receive time and whole seconds of
# PT/TT, so an estimated arrival is only good to about a second either way.
ETA_CHANGE_THRESHOLD = 2.0

UPDATED_ATTACK_FIELDS = (
    "units",
    "estimated_size",
    "target_id",
    "target_area_id",
    "target_x",
    "target_y",
    "commander",
)

# A callback to queue and its arguments
QueuedCall = tuple[Callable[..., object], tuple[Any, ...]]


@dataclass(frozen=True)
class AttackEvents:
    """Incoming attacks: only one removed before it arrives is reported, as withdrawn."""

    announced: BoundEvent[Callable[[Movement], object]]
    updated: BoundEvent[Callable[[Movement, Movement], object]]
    withdrawn: BoundEvent[Callable[[Movement], object]]

    def leaving(self, mov: Movement, arrived: bool) -> list[QueuedCall]:
        """The calls for an announced attack leaving state, at its arrival or removed before it."""
        return [] if arrived else [(callback, (mov,)) for callback in self.withdrawn.calls()]


@dataclass(frozen=True)
class OccupationEvents:
    """Occupations: each one leaving is reported as ended, captured when its time ran out."""

    announced: BoundEvent[Callable[[Movement], object]]
    updated: BoundEvent[Callable[[Movement, Movement], object]]
    ended: BoundEvent[Callable[[Movement, bool], object]]

    def leaving(self, mov: Movement, arrived: bool) -> list[QueuedCall]:
        """The calls for an announced occupation leaving state, at its arrival or removed before it."""
        return [(callback, (mov, arrived)) for callback in self.ended.calls()]


class MovementAnnouncer:
    """The attacks and occupations a state announced, judged as its store reports movements stored, arrived, removed.

    The store calls it under the state lock, and ``fire`` queues an event's
    callbacks on the callback thread. It lives as long as the state, so a
    reconnect does not announce the same movement again.
    """

    def __init__(self, attacks: AttackEvents, occupations: OccupationEvents, fire: Callable[..., None]) -> None:
        self.attacks = attacks
        self.occupations = occupations
        self._fire = fire
        # Movement id -> when it ends (wall clock), in the order announced
        self.announced: dict[int, float] = {}
        self._prune_at = math.inf

    def events_for(self, mov: Movement) -> AttackEvents | OccupationEvents | None:
        """The events of the kind of announced movement ``mov`` is, None if it is neither attack nor occupation."""
        if mov.is_attack:
            return self.attacks
        if mov.is_occupation:
            return self.occupations
        return None

    def stored(self, old: Movement | None, new: Movement, *, arrived: bool, alliance_id: int | None) -> None:
        """Fire the callbacks for a movement a packet stored, ``old`` being the one it replaces.

        ``arrived`` says its arrival is behind it (reported, or past when it was
        first seen); ``alliance_id`` is the local player's alliance, None outside one.

        An attack is judged on every packet that carries it, as the client counts
        its attack warnings anew (``CastleArmyData.checkAllAttackMovements``, bundle
        line 133659), so one whose owner record comes later still fires, once; an
        occupation likewise. A later packet for an announced attack or occupation
        fires the updated callback when it changes what that callback reports.
        """
        mid = new.movement_id
        events = self.events_for(new)
        if mid in self.announced:
            self.announced[mid] = max(self.announced[mid], new.estimated_end)
            if events is not None and old is not None and self._changed(old, new):
                self._fire(events.updated, old, new)
        elif (
            events is not None
            and not arrived
            and (self._is_attack_on_us(new, alliance_id) or self._is_occupation_on_us(new, alliance_id))
        ):
            end = new.estimated_end
            self.announced[mid] = end
            self._prune_at = min(self._prune_at, end)
            self._fire(events.announced, new)

    def arrived(self, mov: Movement) -> list[QueuedCall]:
        """Forget an arrived movement; the calls to queue after its arrival if it was announced."""
        events = self.events_for(mov) if self.announced.pop(mov.movement_id, None) is not None else None
        return events.leaving(mov, arrived=True) if events is not None else []

    def removed(self, mid: int, mov: Movement | None, *, arrived: bool) -> list[QueuedCall]:
        """Forget a movement ``mrm`` removed; the calls to queue after its removal if it was announced.

        ``arrived`` says its arrival is behind it, as for :meth:`stored`. One removed
        within two seconds of its estimated arrival or later counts as arrived.
        """
        leaving: list[QueuedCall] = []
        if mov is not None and mid in self.announced and not arrived:
            events = self.events_for(mov)
            if events is not None:
                leaving = events.leaving(mov, time.time() >= mov.estimated_arrival - ETA_CHANGE_THRESHOLD)
        self.announced.pop(mid, None)
        return leaving

    def prune(self, now: float) -> None:
        """Forget announced movements whose end has passed while no session tracked them."""
        if now >= self._prune_at:
            self.announced = {mid: end for mid, end in self.announced.items() if now < end}
            self._prune_at = min(self.announced.values(), default=math.inf)

    def listed(self, events: AttackEvents | OccupationEvents, movements: Mapping[int, Movement]) -> list[Movement]:
        """The ``movements`` of one kind still announced, in the order announced."""
        tracked = (movements.get(mid) for mid in self.announced)
        return [mov for mov in tracked if mov is not None and self.events_for(mov) is events]

    def reannounce(self, mov: Movement | None) -> bool:
        """Fire the announced callbacks again for a tracked movement if it is announced; False if it is not one."""
        events = self.events_for(mov) if mov is not None and mov.movement_id in self.announced else None
        if mov is None or events is None:
            return False
        self._fire(events.announced, mov)
        return True

    @staticmethod
    def _changed(old: Movement, new: Movement) -> bool:
        """Whether a packet changed what the ``_updated`` callbacks of an attack or occupation report."""
        if abs(new.estimated_arrival - old.estimated_arrival) >= ETA_CHANGE_THRESHOLD:
            return True
        return any(getattr(old, name) != getattr(new, name) for name in UPDATED_ATTACK_FIELDS)

    @staticmethod
    def _is_attack_on_us(mov: Movement, alliance_id: int | None) -> bool:
        """A new attack aimed at the local player or at a member of their alliance.

        Client: ``CastleArmyData.checkAllAttackMovements`` (bundle line 133659).
        An attack on you (``isAttackingMovement``, 14389: the target is you, or
        the daimyo township, which the client files under your own owner
        record; an alien attack only counts on you, 33073) counts whoever sends
        it. An attack on an alliance member other than you
        (``isAllyAttackingMovement``, 14392) counts only when
        ``showAsAllianceAttackWarning`` holds: always for an alien attack
        (33091) and for the alliance nomad camp (14420), else when the attacker
        has owner info and is not a dungeon owner (19456). An NPC always has
        owner info (``getOwnerInfoVO``, 138994; an id the client does not know
        gets a dummy that is not a dungeon owner); a player needs an owner
        record, which is never a dungeon owner, and a movement without an owner
        id (``OID``, which the client reads as 0) has none. The member list is
        matched through the target's owner record, whose alliance id comes with
        every movement.
        """
        if not mov.is_attack or mov.is_mine or mov.is_returning:
            return False
        me = mov.local_player_id
        if me == -1:
            return False
        is_alien = mov.movement_type_enum is MovementType.ALIEN_ATTACK
        if mov.target_id == me or (mov.target_id == NPCOwner.DAIMYO_TOWNSHIP and not is_alien):
            return True
        if alliance_id is None or alliance_id <= 0 or mov.target_alliance_id != alliance_id:
            return False
        if is_alien or mov.owner_id == NPCOwner.ALLIANCE_NOMAD_CAMP:
            return True
        if "owner_id" not in mov.model_fields_set:
            return False
        if mov.owner_id < 0:
            return mov.owner_id not in DUNGEON_OWNER_IDS
        return mov.owner is not None

    @staticmethod
    def _is_occupation_on_us(mov: Movement, alliance_id: int | None) -> bool:
        """A new occupation of the local player's or an alliance member's area (see ``on_occupation_started``)."""
        if not mov.is_occupation or mov.is_mine or mov.is_returning:
            return False
        me = mov.local_player_id
        if me == -1:
            return False
        if mov.target_id in (me, NPCOwner.DAIMYO_TOWNSHIP):
            return True
        return alliance_id is not None and alliance_id > 0 and mov.target_alliance_id == alliance_id
