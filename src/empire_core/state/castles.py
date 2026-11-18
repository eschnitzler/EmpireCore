"""Castle tracking: the castle list (gcl), castle details (dcl), castle resources (grc), units received (rue),
the open-gate counter reset (kik), unlocked units and horses (gpc), and your royal towers, monuments,
laboratories and villages (gkl, gml, gll, kgv) with the landmark resets (mre, lrr)."""

import logging
import time
from typing import Any

from empire_core.castle.models.castles import GetCastlesResponse
from empire_core.castle.models.details import (
    GetDetailedCastleResponse,
    ResourceProduction,
    SafeAmount,
    StorageCapacity,
)
from empire_core.castle.models.gates import OpenGateResponse
from empire_core.castle.models.landmarks import (
    LaboratoryListResponse,
    LaboratoryResetResponse,
    MonumentListResponse,
    MonumentResetResponse,
    RoyalTowerListResponse,
)
from empire_core.castle.models.permanent import PermanentCastle, PermanentCastleDataResponse
from empire_core.castle.models.updates import NewDay, UnitsReceived
from empire_core.castle.models.villages import VillageListResponse
from empire_core.enums import Kingdom, Weekday
from empire_core.protocol.base import enum_or_none, read_or_none
from empire_core.state.base import StateBase, read_section
from empire_core.state.login_data import LoginDataResponse
from empire_core.state.models import Castle, Resources

logger = logging.getLogger(__name__)

# ClientConstCollectable.GROUP_LIST_RESOURCES (bundle line 3073)
_STOCK = ("wood", "stone", "food", "coal", "oil", "glass", "iron", "aquamarine", "honey", "mead", "beef")


AREA_LIST_SECTIONS = ("gkl", "gml", "gll", "kgv", "mre", "lrr")


class CastleState(StateBase):
    def _parse_area_lists(self, login: LoginDataResponse) -> set[str]:
        """Apply the royal tower, monument, laboratory and village lists and the landmark resets of a gbd,
        or the one a push, a reply or an ``mir`` carries; return those not applied.

        Client: ``GBDCommand.exec`` (bundle line 129430) hands ``gkl``, ``gml``, ``gll`` and ``kgv`` to
        ``CastleKingstowerList.parseGKL``, ``CastleMonumentList.parseGML``, ``CastleLaboratoryList.parseGLL``
        and ``CastleUserData.parse_KGV`` (bundle lines 73493, 73545, 73521, 9889), which skip a falsy one, and a
        truthy ``mre`` and ``lrr`` to ``CastleMonumentData.parseMRE`` and ``CastleLaboratoryData.parseLRR``
        (bundle lines 46192, 134899), which ignore a time of 0 and keep the countdown only for a positive one
        """
        applied: set[str] = set()
        if login.royal_towers is not None:
            self.royal_towers = login.royal_towers
            applied.add("gkl")
        if login.monuments is not None:
            self.monuments = login.monuments
            applied.add("gml")
        if login.laboratories is not None:
            self.laboratories = login.laboratories
            applied.add("gll")
        if login.villages is not None:
            self.villages = login.villages
            applied.add("kgv")
        if (monument_reset := login.monument_reset) is not None:
            if monument_reset.seconds > 0:
                self.monument_reset = monument_reset
            if monument_reset.seconds != 0:
                applied.add("mre")
        if (laboratory_reset := login.laboratory_reset) is not None:
            if laboratory_reset.seconds > 0:
                self.laboratory_reset = laboratory_reset
            if laboratory_reset.seconds != 0:
                applied.add("lrr")
        return (login.sent_sections & set(AREA_LIST_SECTIONS)) - applied

    def get_royal_towers(self) -> RoyalTowerListResponse | None:
        """Your royal towers, from the last ``gkl``; None until one arrived."""
        with self._lock:
            return self.royal_towers

    def get_monuments(self) -> MonumentListResponse | None:
        """Your monuments, from the last ``gml``; None until one arrived."""
        with self._lock:
            return self.monuments

    def get_monument_reset(self) -> MonumentResetResponse | None:
        """When the monuments reset next, from the last ``mre`` that counted down; None until one arrived."""
        with self._lock:
            return self.monument_reset

    def get_villages(self) -> VillageListResponse | None:
        """Your villages and private resource villages, from the last ``kgv``; None until one arrived."""
        with self._lock:
            return self.villages

    def get_laboratories(self) -> LaboratoryListResponse | None:
        """Your laboratories, from the last ``gll``; None until one arrived."""
        with self._lock:
            return self.laboratories

    def get_laboratory_reset(self) -> LaboratoryResetResponse | None:
        """When the laboratories reset next, from the last ``lrr`` that counted down; None until one arrived."""
        with self._lock:
            return self.laboratory_reset

    def _parse_castles(self, listed: GetCastlesResponse) -> None:
        """Keep the castles of yours a castle list names.

        A list that carries a castle section (``C``) is authoritative: castles it does not list are no
        longer owned, even when it lists none at all (the player just lost their last castle). A list
        without that section says nothing about ownership and leaves the castles alone, and so does
        one none of whose rows could be read, which is logged by the model.

        Castles are keyed by id, a server-wide area id. A row's own kingdom wins over its block's ``KID``.

        Client: ``CastleUserData.parse_GCL`` (split.js line 53997), ``CastleListVO.parseCastleList``
        (split.js line 73142); see :class:`GetCastlesResponse`
        """
        player = self.local_player
        if player is None or "castles" not in listed.model_fields_set:
            return
        if listed.unreadable_rows and not listed.castles:
            return

        owned: dict[int, Castle] = {}
        now = time.monotonic()
        for row in listed.castles:
            if row.owner_id != player.id:
                continue
            fields: dict[str, Any] = {
                "name": row.castle_name,
                "x": row.x,
                "y": row.y,
                "castle_type": row.castle_type,
                "open_gate_counter": row.open_gate_counter,
                "open_gate_end": now + row.open_gate_seconds if row.open_gate_seconds > 0 else None,
            }
            existing = self.castles.get(row.castle_id)
            if existing is not None:
                # One swap keeps a castle mid-relocation from reading as (new x, old y)
                self._swap_model_fields(existing, {**existing.__dict__, **fields}, set(fields))
                owned[row.castle_id] = existing
            else:
                owned[row.castle_id] = Castle(id=row.castle_id, kingdom_id=row.kingdom_id, **fields)

        for stale_id in set(self.castles) - set(owned):
            # A re-acquired castle must not inherit the old freshness stamp
            self._castle_details_at.pop(stale_id, None)
        # Swapped, not mutated: readers hold state.castles and local_player.castles unlocked
        self.castles = owned
        player.castles = dict(owned)
        logger.debug(f"Parsed {len(owned)} castles")

    def _handle_dcl(self, data: Any) -> None:
        """Apply a ``dcl`` reply: the details of every castle it lists.

        Client: ``DCLCommand.executeCommand`` (split.js line 650927)
        """
        if (details := read_section(GetDetailedCastleResponse, data, "a dcl reply")) is not None:
            self._apply_castle_details(details)

    def _apply_castle_details(self, details: GetDetailedCastleResponse) -> None:
        """Replace each listed castle's resources, units and details whole.

        get_castles() hands out live Castle objects, so editing them in place would let readers see a
        half-updated castle. Only a castle in the castle list, in the kingdom it is listed under, is updated.

        Client: ``CastleUserCastleListDetailed.parseData`` (split.js line 700798)
        """
        for info in details.castles:
            castle = self.castles.get(info.castle_id)
            if castle is None or castle.kingdom_id != enum_or_none(Kingdom, info.kingdom_id):
                continue
            area = info.production_area
            castle.resources = Resources(
                wood=info.wood,
                stone=info.stone,
                food=info.food,
                coal=info.coal,
                oil=info.oil,
                glass=info.glass,
                iron=info.iron,
                aquamarine=info.aquamarine,
                honey=info.honey,
                mead=info.mead,
                beef=info.beef,
                capacity=area.storage_capacity if area else StorageCapacity(),
                production=area.production if area else ResourceProduction(),
                safe=area.safe_amount if area else SafeAmount(),
            )
            if info.units:
                castle.units = info.units
            castle.details = info
            self._castle_details_at[castle.id] = time.time()

    def _parse_castle_resources(self, login: LoginDataResponse) -> bool:
        """Apply a ``grc`` block to its castle's stock; whether it was applied.

        Every resource is set, one the block leaves out to 0; capacity, production and the
        plunder-safe amount stay as the last ``dcl`` and ``gpa`` left them. Only a castle already
        read from a ``dcl`` is updated; its details time (:meth:`get_castle_last_updated`) is not
        stamped, as the units are not refreshed, and ``get_last_packet_time("grc")`` dates the block.

        Client: ``AreaDataUpdater.parseGRC`` (split.js line 659020) hands every truthy block to
        ``CastleUserCastleListDetailed.updateDetailVO`` (split.js line 700866), which finds the castle by
        ``AID`` and ``KID`` among those with details and sets each of ``GROUP_LIST_RESOURCES`` to the
        block's amount or 0. Only the joined area's own storage also checks ``AID`` against the joined
        area; the library keeps no storage of its own for the joined area.
        """
        block = login.castle_resources
        if block is None:
            return False
        kingdom = enum_or_none(Kingdom, block.kingdom_id)
        if kingdom is None:
            return False
        castle = self.castles.get(block.castle_id)
        if castle is None or castle.kingdom_id != kingdom or block.castle_id not in self._castle_details_at:
            return False
        castle.resources = castle.resources.model_copy(update={name: getattr(block, name) for name in _STOCK})
        return True

    def _handle_rue(self, data: Any) -> None:
        """Apply units received: the castle's new count of one unit, which drops it at 0 or below.

        ``SID`` is the castle's kingdom. A castle not in the castle list is left
        alone; the client also leaves one it has no dcl for, the library does not.

        Client: ``CastleUserCastleListDetailed.parse_rue`` (bundle line 140918),
        ``UnitInventoryDictionary.setUnit`` (bundle line 5538)
        """
        if not isinstance(data, dict):
            return
        received = read_or_none(UnitsReceived.model_validate, data, warn=logger, what="a rue push")
        if received is None:
            return
        castle = self.castles.get(received.castle_id)
        if castle is None or castle.kingdom_id != enum_or_none(Kingdom, received.kingdom_id):
            return
        units = dict(castle.units)
        if received.amount <= 0:
            units.pop(received.wod_id, None)
        else:
            units[received.wod_id] = received.amount
        castle.units = units

    def _handle_kik(self, data: Any) -> None:
        """On a Monday's ``kik``, set every castle's open-gate counter to 0.

        Client: ``KIKCommand.executeCommand`` (bundle line 123151), ``DOW == TimeConst.MONDAY``;
        ``CastleListVO.resetOpenGateCounter`` (bundle line 13735)
        """
        if not isinstance(data, dict):
            return
        new_day = read_or_none(NewDay.model_validate, data, warn=logger, what="a kik push")
        if new_day is None or new_day.day_of_week != Weekday.MONDAY:
            return
        for castle in self.castles.values():
            if castle.open_gate_counter:
                merged = {**castle.__dict__, "open_gate_counter": 0}
                self._swap_model_fields(castle, merged, {"open_gate_counter"})

    def _handle_mos(self, data: Any) -> None:
        """Set an own castle's Open Gate from an ``mos`` reply, counting an opening (or extension) once.

        Client: ``CastleUserData.parse_MOS`` (bundle line 9897): ``remainingOpenGateTime = RPT``, and
        ``openGateCounter++`` when it is positive
        """
        if not isinstance(data, dict):
            return
        reply = read_or_none(OpenGateResponse.model_validate, data, warn=logger, what="an mos reply")
        castle = self.castles.get(reply.castle_id) if reply is not None else None
        if reply is None or castle is None or castle.kingdom_id != reply.kingdom:
            return
        opened = reply.open_seconds > 0
        fields = {
            "open_gate_end": time.monotonic() + reply.open_seconds if opened else None,
            "open_gate_counter": castle.open_gate_counter + 1 if opened else castle.open_gate_counter,
        }
        self._swap_model_fields(castle, {**castle.__dict__, **fields}, set(fields))

    def _parse_permanent_castles(self, listed: PermanentCastleDataResponse) -> None:
        """Apply a gpc section or push: each castle it names is replaced, the others kept.

        Client: ``CastlePermanentCastleData.parseGPC`` (bundle line 139128)
        """
        castles = listed.castles
        if not castles:
            return
        merged = dict(self.permanent_castles)
        for castle in castles:
            merged[castle.castle_id] = castle
        self.permanent_castles = merged

    def get_permanent_castle(self, castle_id: int) -> PermanentCastle | None:
        """One of your castles' unlocked units and horses, from the last gpc that named it.

        ``None`` when the castle is not in the castle list or no gpc named it in
        the castle's own kingdom.

        Client: ``CastlePermanentCastleData.getCastleByWorldAreaId`` (bundle line 139145),
        keyed by ``getDicKey`` (bundle line 139147) as kingdom and castle id
        """
        with self._lock:
            castle = self.castles.get(castle_id)
            permanent = self.permanent_castles.get(castle_id)
        if castle is None or permanent is None or permanent.kingdom_id != castle.kingdom_id:
            return None
        return permanent

    def get_castles(self) -> list[Castle]:
        """Get a snapshot of the player's castles.

        The list itself is current, but each castle's ``resources``, ``units``
        and other dcl-only detail fields are as old as the last dcl packet for
        that castle — frequently the one from login, and all-zero when no dcl
        ever arrived. Check :meth:`get_castle_last_updated` /
        :meth:`get_castle_age` before treating them as live.
        """
        with self._lock:
            return list(self.castles.values())

    def get_castle_last_updated(self, castle_id: int) -> float | None:
        """When this castle's detail data (resources, units) was last refreshed.

        Only a ``dcl`` stamps it. A reply carrying the castle's ``grc`` (``client.castle.get_resources``,
        building, recruiting, starting research, ...) updates its resources without stamping this;
        ``get_last_packet_time("grc")`` says when the last one came.

        Returns a wall-clock ``time.time()`` timestamp, or ``None`` if no dcl
        packet ever refreshed this castle — in which case ``resources`` and
        ``units`` are defaults, not measurements. Refresh with
        ``client.castle.get_details(castle_id)``.
        """
        with self._lock:
            return self._castle_details_at.get(castle_id)

    def get_castle_age(self, castle_id: int) -> float | None:
        """Seconds since this castle's detail data was refreshed, or ``None``.

        ``None`` means never refreshed (see :meth:`get_castle_last_updated`),
        so treat it as infinitely stale rather than as zero.
        """
        with self._lock:
            stamp = self._castle_details_at.get(castle_id)
        if stamp is None:
            return None
        return max(0.0, time.time() - stamp)
