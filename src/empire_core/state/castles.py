"""Castle tracking: the castle list (gcl), castle details (dcl) and unlocked units and horses (gpc)."""

import logging
import time
from typing import Any

from pydantic import ValidationError

from empire_core.castle.models.castles import PlayerCastle
from empire_core.castle.models.details import DetailedCastleInfo, ResourceProduction, SafeAmount, StorageCapacity
from empire_core.castle.models.permanent import PermanentCastle, PermanentCastleDataResponse
from empire_core.enums import Kingdom
from empire_core.exceptions import AmbiguousCastleError
from empire_core.protocol.base import enum_or_none
from empire_core.state.base import StateBase
from empire_core.state.models import Castle, CastleKey, Resources

logger = logging.getLogger(__name__)


class CastleState(StateBase):
    def _parse_castles(self, data: dict[str, Any]) -> None:
        """Parse castle list from gcl sub-packet.

        A gcl carrying a castle section ("C") is authoritative: castles it
        does not list are no longer owned, even when it lists none at all
        (the player just lost their last castle). A gcl without that section
        says nothing about ownership and leaves the castle list alone. One
        exception: a section whose entries were *all* skipped as malformed is
        a payload we could not read, not evidence of ownership loss — it is
        reported at WARNING and the existing castle list is kept.

        Castles are keyed by (kingdom, id): ids repeat across kingdoms. A
        row's own kingdom field wins over the block's ``KID``.

        Client: ``CastleListVO.parseCastleList`` (bundle line 13698) keeps a
        list per ``KID``; ``InteractiveMapobjectVO.parseAreaInfo`` (bundle
        line 3637) reads the row's kingdom from field 16
        """
        gcl = data.get("gcl")
        if not isinstance(gcl, dict) or self.local_player is None:
            return
        kingdoms = gcl.get("C")
        if not isinstance(kingdoms, list):
            return

        owned: dict[CastleKey, Castle] = {}
        entries = 0
        skipped = 0
        for k_data in kingdoms:
            if not isinstance(k_data, dict):
                entries += 1
                skipped += 1
                logger.debug(f"Skipping malformed gcl kingdom entry: {k_data!r}")
                continue
            block_kid = k_data.get("KID", 0)
            for area_entry in k_data.get("AI", []):
                entries += 1
                if not isinstance(area_entry, dict):
                    skipped += 1
                    logger.debug(f"Skipping malformed gcl area entry: {area_entry!r}")
                    continue
                try:
                    # A block KID Kingdom lacks fails validation unless the row names its own kingdom
                    row = PlayerCastle.from_list(area_entry.get("AI"), block_kid)
                except (ValueError, TypeError) as e:
                    skipped += 1
                    logger.debug(f"Skipping unreadable gcl area entry {area_entry!r}: {e}")
                    continue
                if row.location_id is None or row.owner_id != self.local_player.id:
                    # A castle is tracked by its object id; a faction capital's row has none
                    continue
                x, y, area_id, name, kingdom = row.x, row.y, row.location_id, row.name or "", row.kingdom
                key = (kingdom, area_id)
                existing = self.castles.get(key)
                if existing is not None:
                    # Identity preserved for user-held references, but the
                    # fields land in one swap (see _swap_model_fields):
                    # written one at a time, a castle mid-relocation would
                    # be observably at (new_x, old_y).
                    merged = dict(existing.__dict__)
                    merged.update({"name": name, "x": x, "y": y})
                    self._swap_model_fields(existing, merged, {"name", "x", "y"})
                    owned[key] = existing
                else:
                    owned[key] = Castle(OID=area_id, N=name, KID=kingdom, X=x, Y=y)

        if skipped and skipped == entries:
            logger.warning(
                f"gcl castle section unreadable: skipped {skipped}/{entries} malformed entries "
                f"(server schema drift?); keeping the existing castle list"
            )
            return

        # Drop castles no longer owned (lost/traded since the last update)
        for stale_key in set(self.castles) - set(owned):
            # A re-acquired castle must not inherit the old freshness stamp
            self._castle_details_at.pop(stale_key, None)
        # Swap, don't mutate: user threads hold state.castles and
        # local_player.castles unlocked, and a reader holding the old dict
        # must keep seeing a consistent snapshot.
        self.castles = owned
        self.local_player.castles = dict(owned)
        logger.debug(f"Parsed {len(owned)} castles")

    def _handle_dcl(self, data: dict[str, Any]) -> None:
        """Handle 'Detailed Castle List' response.

        Each entry is parsed with the protocol model, then the castle's
        resources, units and details are replaced whole: get_castles() hands
        out live Castle objects, so editing them in place would let readers see
        a half-updated castle.

        Client: ``DetailedCastleVO.parseData``.
        """
        for k_data in data.get("C", []):
            if not isinstance(k_data, dict):
                continue
            kid = enum_or_none(Kingdom, k_data.get("KID", 0))
            if kid is None:
                continue
            for castle_data in k_data.get("AI", []):
                if not isinstance(castle_data, dict):
                    continue
                aid = castle_data.get("AID")
                if not isinstance(aid, int) or (kid, aid) not in self.castles:
                    continue
                key: CastleKey = (kid, aid)
                castle = self.castles[key]
                try:
                    info = DetailedCastleInfo.model_validate({**castle_data, "KID": kid})
                except ValidationError as e:
                    # One malformed castle entry must not abort the rest
                    logger.debug(f"Skipping malformed dcl entry for castle {aid}: {e}")
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
                if info.raw_units:
                    castle.units = info.units
                castle.details = info
                self._castle_details_at[key] = time.time()

    def _parse_permanent_castles(self, data: dict[str, Any]) -> None:
        """Apply a gpc section or push: each castle it names is replaced, the others kept.

        Client: ``CastlePermanentCastleData.parseGPC`` (bundle line 139128), keyed
        by ``getDicKey`` (bundle line 139147) as kingdom and castle id
        """
        gpc = data.get("gpc")
        if not isinstance(gpc, dict):
            return
        castles = PermanentCastleDataResponse.model_validate(gpc).castles
        if not castles:
            return
        merged = dict(self.permanent_castles)
        for castle in castles:
            merged[(castle.kingdom_id, castle.castle_id)] = castle
        self.permanent_castles = merged

    def get_permanent_castle(self, castle_id: int) -> PermanentCastle | None:
        """One of your castles' unlocked units and horses, from the last gpc that named it.

        The kingdom is the castle's own, from the castle list. ``None`` when the
        castle is not in the castle list or no gpc named it.

        Raises:
            AmbiguousCastleError: the id repeats across your kingdoms

        Client: ``CastlePermanentCastleData.getCastleByWorldAreaId`` (bundle line 139145)
        """
        with self._lock:
            key = self._castle_key(castle_id)
            return None if key is None else self.permanent_castles.get(key)

    def get_castle_horse_ids(self, castle_id: int) -> list[int] | None:
        """Wod ids of the horses one of your castles can send movements with, as gpc sent them.

        Look each up with ``client.game_data.get_horse``, or use
        ``client.castle.get_horses``. ``None`` when :meth:`get_permanent_castle` is.
        """
        permanent = self.get_permanent_castle(castle_id)
        return None if permanent is None else list(permanent.horse_ids)

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

    def _castle_key(self, castle_id: int) -> CastleKey | None:
        """The key of one of your castles, or None when there is none. Call under the lock."""
        keys = [key for key in self.castles if key[1] == castle_id]
        if len(keys) > 1:
            raise AmbiguousCastleError(castle_id, sorted(key[0] for key in keys))
        return keys[0] if keys else None

    def get_castle_last_updated(self, castle_id: int) -> float | None:
        """When this castle's detail data (resources, units) was last refreshed.

        Returns a wall-clock ``time.time()`` timestamp, or ``None`` if no dcl
        packet ever refreshed this castle — in which case ``resources`` and
        ``units`` are defaults, not measurements. Refresh with
        ``client.castle.get_details(castle_id)``.

        Raises:
            AmbiguousCastleError: the id is listed in several of your kingdoms
        """
        with self._lock:
            key = self._castle_key(castle_id)
            return None if key is None else self._castle_details_at.get(key)

    def get_castle_age(self, castle_id: int) -> float | None:
        """Seconds since this castle's detail data was refreshed, or ``None``.

        ``None`` means never refreshed (see :meth:`get_castle_last_updated`),
        so treat it as infinitely stale rather than as zero.
        """
        with self._lock:
            key = self._castle_key(castle_id)
            stamp = None if key is None else self._castle_details_at.get(key)
        if stamp is None:
            return None
        return max(0.0, time.time() - stamp)
