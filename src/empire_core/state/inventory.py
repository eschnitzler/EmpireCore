"""Inventory and economy sections: gems, loot boxes, inventory space, kingdoms, mercenaries, tax,
construction item expiry and the resource citizen."""

from typing import Any

from empire_core.castle.models.construction_items import ConstructionItemInventory, ConstructionItemPlacement
from empire_core.castle.models.kingdoms import KingdomInfoResponse
from empire_core.castle.models.mercenaries import MercenaryMissionsResponse
from empire_core.castle.models.objects import BuildingConstructionItems
from empire_core.castle.models.tax import TaxInfo, TaxInfoResponse
from empire_core.castle.models.upkeep import ConstructionItemExpiryResponse, ResourcePoolResponse
from empire_core.commanders.models.inventory import GemInventoryResponse, InventorySpace
from empire_core.enums import Kingdom
from empire_core.exceptions import PacketError, ReplyMismatchError
from empire_core.player.models.economy import LootBoxesResponse, LootBoxKeys
from empire_core.protocol.js import js_truthy
from empire_core.state.base import StateBase, read_section

INVENTORY_SECTIONS = ("gii", "ggm", "gls", "esl", "kpi", "mpe", "txi", "nec", "irc")


class InventoryState(StateBase):
    def _parse_inventory(self, data: dict[str, Any]) -> set[str]:
        """Apply the inventory and economy sections of a gbd, or the one a push or reply carries; return those
        not applied.

        Client: ``GBDCommand.exec`` (bundle line 129381) calls ``parse_GLS``, ``parse_ESL``, ``parse_KPI``,
        ``parse_MPE`` and ``parse_TXI``, each of which skips a falsy block, and ``parseGGM`` and ``parse_NEC``
        only when ``ggm`` and ``nec`` are truthy; ``irc`` comes only as a push (``IRCCommand``, bundle line 123090)
        """
        applied: set[str] = set()
        if "gii" in data:
            if (
                inventory := read_section(ConstructionItemInventory, data["gii"], "the construction inventory")
            ) is not None:
                self.construction_items = inventory
                applied.add("gii")
        if js_truthy(ggm := data.get("ggm")):
            if (gems := read_section(GemInventoryResponse, ggm, "the gems")) is not None:
                self.gems = gems
                applied.add("ggm")
        if js_truthy(gls := data.get("gls")) and self._apply_loot_boxes(gls):
            applied.add("gls")
        if js_truthy(esl := data.get("esl")):
            if (space := read_section(InventorySpace, esl, "the inventory space")) is not None:
                self.inventory_space = space
                applied.add("esl")
        if js_truthy(kpi := data.get("kpi")) and self._apply_kingdoms(kpi):
            applied.add("kpi")
        if js_truthy(mpe := data.get("mpe")):
            if (missions := read_section(MercenaryMissionsResponse, mpe, "the mercenary missions")) is not None:
                self.mercenary_missions = missions
                applied.add("mpe")
        if js_truthy(txi := data.get("txi")):
            if (tax := read_section(TaxInfoResponse, txi, "the tax")) is not None:
                self.tax = tax.tax
                applied.add("txi")
        if js_truthy(nec := data.get("nec")):
            if (expiry := read_section(ConstructionItemExpiryResponse, nec, "the item expiry")) is not None:
                self.construction_item_expiry = expiry
                if self.joined_area is not None and isinstance(nec, dict) and "CI" in nec:
                    placement = read_section(ConstructionItemPlacement, nec, "the expiring construction items")
                    if placement is not None:
                        self.placed_construction_items = placement.items
                        self._placed_construction_item_sequence = self._packet_sequence
                applied.add("nec")
        if "irc" in data and (pool := read_section(ResourcePoolResponse, data["irc"], "the resource pool")) is not None:
            self.resource_pool = pool
            applied.add("irc")
        return {section for section in INVENTORY_SECTIONS if section in data} - applied

    def _apply_loot_boxes(self, body: Any) -> bool:
        """Read a ``gls``: the loot boxes whole, and key progress over the types known.

        Client: ``CastleLootboxData.parse_GLS`` (bundle line 112332), which sets the progress of each
        type ``KEY`` lists and leaves the others
        """
        boxes = read_section(LootBoxesResponse, body, "the loot boxes")
        if boxes is None:
            return False
        if self.loot_boxes is not None:
            keys = {entry.loot_box_type_id: entry for entry in self.loot_boxes.key_progress}
            keys.update((entry.loot_box_type_id, entry) for entry in boxes.key_progress)
            boxes = boxes.model_copy(update={"key_progress": tuple(keys.values())})
        self.loot_boxes = boxes
        return True

    def _apply_kingdoms(self, body: Any) -> bool:
        """Read a ``kpi``: the kingdoms it lists over those known, and the transfers whole.

        Client: ``CastleKingdomData.parse_KPI`` (bundle line 134539), which updates each kingdom in
        ``UL`` and rebuilds the transfer lists
        """
        info = read_section(KingdomInfoResponse, body, "the kingdom info")
        if info is None:
            return False
        if self.kingdoms is not None:
            kingdoms = {kingdom.kingdom_id: kingdom for kingdom in self.kingdoms.kingdoms}
            kingdoms.update((kingdom.kingdom_id, kingdom) for kingdom in info.kingdoms)
            info = info.model_copy(update={"kingdoms": tuple(kingdoms.values())})
        self.kingdoms = info
        return True

    def _handle_gec(self, data: Any) -> None:
        """Handle a ``gec`` push: gems added to or taken from the inventory.

        Client: ``GECCommand`` (bundle line 123927), ``CastleGemData.parse_GEC`` (bundle line 144326)
        """
        if isinstance(data, dict):
            gems = self.gems if self.gems is not None else GemInventoryResponse()
            self.gems = gems.changed(data.get("GEM"))

    def get_gems(self) -> GemInventoryResponse | None:
        """The gems and relic gems in your inventory; None until a ``ggm`` or ``gec`` arrived.

        A ``ggm`` lists them whole, and each ``gec`` push adds or takes some away.
        """
        with self._lock:
            return self.gems

    def get_loot_boxes(self) -> LootBoxesResponse | None:
        """Your loot boxes and key progress; None until a ``gls`` arrived.

        The loot boxes are the last ``gls``'s, and each type's key progress as the last ``gls`` that
        listed it left it.
        """
        with self._lock:
            return self.loot_boxes

    def set_loot_box_keys(self, keys: LootBoxKeys) -> None:
        """Set one loot box type's key progress, as an ``ole`` reply's ``KBS`` does.

        ``client.player.open_loot_box`` calls it. Nothing is set before a ``gls`` arrived.

        Client: ``OLECommand.executeCommand`` (bundle line 124819) calls ``CastleLootboxData.setKeyProgress``
        """
        with self._lock:
            if self.loot_boxes is None:
                return
            progress = {entry.loot_box_type_id: entry for entry in self.loot_boxes.key_progress}
            progress[keys.loot_box_type_id] = keys
            self.loot_boxes = self.loot_boxes.model_copy(update={"key_progress": tuple(progress.values())})

    def get_inventory_space(self) -> InventorySpace | None:
        """The equipment and gem inventory space, from the last ``esl``; None until one arrived."""
        with self._lock:
            return self.inventory_space

    def get_kingdoms(self) -> KingdomInfoResponse | None:
        """Your kingdoms and the transfers to them; None until a ``kpi`` arrived.

        Every kingdom any ``kpi`` listed is there, as the last one that listed it left it; the
        transfers are the last ``kpi``'s.
        """
        with self._lock:
            return self.kingdoms

    def get_mercenary_missions(self) -> MercenaryMissionsResponse | None:
        """The mercenary camp's missions, from the last ``mpe``; None until one arrived."""
        with self._lock:
            return self.mercenary_missions

    def get_tax(self) -> TaxInfo | None:
        """The tax collection, from the last ``txi``; None until one arrived.

        Its ``remaining_seconds`` is as of that packet, ``get_last_packet_time("txi")``.
        A copy: changing it changes nothing in state.
        """
        with self._lock:
            return None if self.tax is None else self.tax.model_copy()

    def get_construction_item_expiry(self) -> ConstructionItemExpiryResponse | None:
        """When the next construction item expires, from the last ``nec``; None until one arrived."""
        with self._lock:
            return self.construction_item_expiry

    def get_resource_pool(self) -> ResourcePoolResponse | None:
        """What the citizen in your castle carries, from the last ``irc`` push; None until one arrived.

        Joining a castle drops it, as in the client (``JAACommand``, bundle line 130194); the citizen being
        collected or leaving does not, so it can be stale until the next ``irc``.
        """
        with self._lock:
            return self.resource_pool

    def get_construction_items(self) -> ConstructionItemInventory | None:
        """The construction inventory from the last successful gii; None before it arrived."""
        with self._lock:
            return self.construction_items

    def get_placed_construction_items(self) -> tuple[BuildingConstructionItems, ...] | None:
        """Items on the joined castle; None before a join or after returning to the map."""
        with self._lock:
            return (
                None
                if self.placed_construction_items is None
                else tuple(item.model_copy(deep=True) for item in self.placed_construction_items)
            )

    def apply_placed_construction_items(
        self,
        placement: ConstructionItemPlacement | None,
        *,
        castle_id: int,
        kingdom_id: Kingdom,
        area_revision: int,
        command: str,
        response_payload: object,
    ) -> None:
        """Apply an action's CI only to the area generation that requested it.

        Bare rpc/cri replies carry no area identity, so only the scoped service
        action applies them. None marks an accepted but unreadable placement unknown.
        A newer expiry placement wins over a delayed caller.
        Client: ``RPCCommand`` / ``CRICommand`` / ``NECCommand`` (bundle 123314/123256/123299)
        apply CI synchronously in receive order.
        """
        with self._lock:
            area = self.joined_area
            if (
                area is None
                or area.castle_id != castle_id
                or area.kingdom_id != kingdom_id
                or self.area_revision != area_revision
            ):
                raise ReplyMismatchError(castle_id, area.castle_id if area and area.castle_id is not None else -1)
            received = self._construction_item_reply_order.get(command)
            if received is None or received[0] is not response_payload:
                raise PacketError("Construction action response receive order is unavailable")
            if received[1] >= self._placed_construction_item_sequence:
                self.placed_construction_items = (
                    None if placement is None else tuple(item.model_copy(deep=True) for item in placement.items)
                )
                self._placed_construction_item_sequence = received[1]

    def invalidate_construction_items(self) -> None:
        """Forget the inventory after an accepted mutation until gii refreshes it."""
        with self._lock:
            self.construction_items = None
