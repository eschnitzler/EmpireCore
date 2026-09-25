"""Castle tracking: the castle list (gcl) and castle details (dcl)."""

import logging
import time
from typing import Any

from pydantic import ValidationError

from empire_core.protocol.models.castle import (
    DetailedCastleInfo,
    ResourceProduction,
    SafeAmount,
    StorageCapacity,
)
from empire_core.state.base import StateBase
from empire_core.state.models import Castle, Resources

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
        """
        gcl = data.get("gcl")
        if not isinstance(gcl, dict) or self.local_player is None:
            return
        kingdoms = gcl.get("C")
        if not isinstance(kingdoms, list):
            return

        owned: dict[int, Castle] = {}
        entries = 0
        skipped = 0
        for k_data in kingdoms:
            if not isinstance(k_data, dict):
                entries += 1
                skipped += 1
                logger.debug(f"Skipping malformed gcl kingdom entry: {k_data!r}")
                continue
            kid = k_data.get("KID", 0)
            for area_entry in k_data.get("AI", []):
                entries += 1
                if not isinstance(area_entry, dict):
                    skipped += 1
                    logger.debug(f"Skipping malformed gcl area entry: {area_entry!r}")
                    continue
                raw_ai = area_entry.get("AI")
                if not (isinstance(raw_ai, list) and len(raw_ai) > 10):
                    skipped += 1
                    logger.debug(f"Skipping malformed gcl area entry: {area_entry!r}")
                    continue
                x, y, area_id, owner_id, name = raw_ai[1], raw_ai[2], raw_ai[3], raw_ai[4], raw_ai[10]
                if owner_id != self.local_player.id:
                    continue
                existing = self.castles.get(area_id)
                if existing is not None:
                    # Identity preserved for user-held references, but the
                    # fields land in one swap (see _swap_model_fields):
                    # written one at a time, a castle mid-relocation would
                    # be observably at (new_x, old_y).
                    merged = dict(existing.__dict__)
                    merged.update({"name": name, "kingdom_id": kid, "x": x, "y": y})
                    self._swap_model_fields(existing, merged, {"name", "kingdom_id", "x", "y"})
                    owned[area_id] = existing
                else:
                    owned[area_id] = Castle(OID=area_id, N=name, KID=kid, X=x, Y=y)

        if skipped and skipped == entries:
            logger.warning(
                f"gcl castle section unreadable: skipped {skipped}/{entries} malformed entries "
                f"(server schema drift?); keeping the existing castle list"
            )
            return

        # Drop castles no longer owned (lost/traded since the last update)
        for stale_id in set(self.castles) - set(owned):
            # A re-acquired castle must not inherit the old freshness stamp
            self._castle_details_at.pop(stale_id, None)
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
            for castle_data in k_data.get("AI", []):
                if not isinstance(castle_data, dict):
                    continue
                aid = castle_data.get("AID")
                if aid is None or aid not in self.castles:
                    continue
                castle = self.castles[aid]
                try:
                    info = DetailedCastleInfo.model_validate(
                        {**castle_data, "KID": k_data.get("KID", castle.kingdom_id)}
                    )
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
                self._castle_details_at[aid] = time.time()

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
