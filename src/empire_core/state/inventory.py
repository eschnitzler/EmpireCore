"""Inventory and economy sections: gems, loot boxes, inventory space, kingdoms, mercenaries, tax,
construction item expiry and the resource citizen."""

import logging
import time
from typing import Any

from empire_core.alliance.models.forge import ForgeCraftResponse
from empire_core.castle.models.construction_items import (
    ConstructionItemInventory,
    ConstructionItemPlacement,
    ConstructionItemSpace,
    ExpiredConstructionItemsResponse,
)
from empire_core.castle.models.kingdoms import KingdomInfoResponse
from empire_core.castle.models.mercenaries import MercenaryMissionsResponse
from empire_core.castle.models.objects import BuildingConstructionItems
from empire_core.castle.models.storage import DecorationStorage, DecorationStorageKey, DecorationStorageResponse
from empire_core.castle.models.tax import TaxInfo
from empire_core.castle.models.upkeep import ConstructionItemExpiryResponse, ResourcePoolResponse
from empire_core.commanders.models.inventory import GemChange, GemInventoryResponse, GemsChangedResponse, InventorySpace
from empire_core.enums import Kingdom
from empire_core.exceptions import PacketError, ReplyMismatchError
from empire_core.player.models.economy import LootBoxesResponse, LootBoxKeys
from empire_core.protocol.base import read_or_none
from empire_core.state.base import StateBase, read_section
from empire_core.state.login_data import LoginDataResponse

INVENTORY_SECTIONS = ("gii", "csp", "ggm", "gls", "esl", "kpi", "mpe", "txi", "nec", "irc")


class InventoryState(StateBase):
    def _parse_inventory(self, login: LoginDataResponse) -> set[str]:
        """Apply the inventory and economy sections of a gbd, or the one a push or reply carries; return those
        not applied.

        Client: ``GBDCommand.exec`` (split.js line 651188) hands them to ``CastleGemData.parseGGM``,
        ``CastleLootboxData.parse_GLS``, ``CastleEquipmentData.parse_ESL`` and ``CastleGemData.parse_ESL``,
        ``CastleKingdomData.parse_KPI``, ``CastleMercenaryData.parse_MPE``, ``CastleTaxData.parse_TXI`` and
        ``ConstructionItemData.parse_NEC`` (split.js lines 714185, 577582, 711891, 714500, 670927, 150683,
        579393, 120941); ``gii``, ``csp`` and ``irc`` come on their own, to ``ConstructionItemData.updateInventory``,
        ``parse_CSP`` and ``CastleResourcePoolData.parseIRC`` (split.js lines 120812, 120836, 695523)
        """
        applied: set[str] = set()
        if login.construction_item_space is not None:
            self.construction_item_space = login.construction_item_space
            applied.add("csp")
        if (inventory := login.construction_items) is not None:
            self.construction_items = inventory
            self.construction_item_space = (
                None if inventory.space_left is None else ConstructionItemSpace(space_left=inventory.space_left)
            )
            applied.add("gii")
        if login.gems is not None:
            self.gems = login.gems
            applied.add("ggm")
        if login.loot_boxes is not None:
            self._apply_loot_boxes(login.loot_boxes)
            applied.add("gls")
        if login.inventory_space is not None:
            self.inventory_space = login.inventory_space
            applied.add("esl")
        if login.kingdoms is not None:
            self._apply_kingdoms(login.kingdoms)
            applied.add("kpi")
        if login.mercenary_missions is not None:
            self.mercenary_missions = login.mercenary_missions
            applied.add("mpe")
        if login.tax is not None:
            self.tax = login.tax.tax
            applied.add("txi")
        if (expiry := login.construction_item_expiry) is not None:
            self.construction_item_expiry = expiry
            if self.joined_area is not None and expiry.placed_items is not None:
                self.placed_construction_items = expiry.placed_items
                self._placed_construction_item_sequence = self._packet_sequence
            applied.add("nec")
        if login.resource_pool is not None:
            self.resource_pool = login.resource_pool
            applied.add("irc")
        return (login.sent_sections & set(INVENTORY_SECTIONS)) - applied

    def _apply_loot_boxes(self, boxes: LootBoxesResponse) -> None:
        """Keep the loot boxes whole, and key progress over the types known.

        Client: ``CastleLootboxData.parse_GLS`` (split.js line 577582), which sets the progress of each
        type ``KEY`` lists and leaves the others
        """
        if self.loot_boxes is not None:
            keys = {entry.loot_box_type_id: entry for entry in self.loot_boxes.key_progress}
            keys.update((entry.loot_box_type_id, entry) for entry in boxes.key_progress)
            boxes = boxes.model_copy(update={"key_progress": tuple(keys.values())})
        self.loot_boxes = boxes

    def _apply_kingdoms(self, info: KingdomInfoResponse) -> None:
        """Keep the kingdoms a ``kpi`` lists over those known, and the transfers whole.

        Client: ``CastleKingdomData.parse_KPI`` (split.js line 670927), which updates each kingdom in
        ``UL`` and rebuilds the transfer lists
        """
        if self.kingdoms is not None:
            kingdoms = {kingdom.kingdom_id: kingdom for kingdom in self.kingdoms.kingdoms}
            kingdoms.update((kingdom.kingdom_id, kingdom) for kingdom in info.kingdoms)
            info = info.model_copy(update={"kingdoms": tuple(kingdoms.values())})
        self.kingdoms = info

    def _handle_gec(self, data: Any) -> None:
        """Handle a ``gec`` push: gems added to or taken from the inventory.

        Client: ``GECCommand`` (bundle line 123969), ``CastleGemData.parse_GEC`` (bundle line 144432)
        """
        if (change := read_section(GemsChangedResponse, data, "the gem change")) is not None:
            gems = self.gems if self.gems is not None else GemInventoryResponse()
            self.gems = gems.changed(change)

    def _handle_frc(self, data: Any) -> None:
        """Add the gem or relic gem the alliance forge crafted; an equipment item is not kept here.

        Client: ``FRCCommand.executeCommand`` (bundle line 123955) calls ``CastleGemData.parse_FRC``
        (bundle line 144434) without an ``E``, which adds an ``RGEM``, else a ``GEM``
        """
        crafted = read_section(ForgeCraftResponse, data, "the forge's craft")
        if crafted is None or crafted.equipment is not None:
            return
        gems = self.gems if self.gems is not None else GemInventoryResponse()
        if crafted.relic_gem is not None:
            self.gems = gems.model_copy(update={"relic_gems": (*gems.relic_gems, crafted.relic_gem)})
        elif crafted.gem_id is not None:
            self.gems = gems.changed(GemsChangedResponse(changes=(GemChange(gem_id=crafted.gem_id, amount=1),)))

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

    def get_decoration_storages(self) -> dict[DecorationStorageKey, DecorationStorage]:
        """The decoration storages by storage id, from the last ``sin`` that named each; empty until one arrived."""
        with self._lock:
            return dict(self.decoration_storages)

    def _handle_sin(self, data: Any) -> None:
        """Apply a ``sin`` block: each storage it names replaces the one of the same id.

        Client: ``SINCommand.exec`` (split.js line 633846), ``DecoStorageData.parseSIN`` (split.js line 702425)
        """
        read = read_or_none(
            DecorationStorageResponse.model_validate, data, warn=logging.getLogger(__name__), what="a sin block"
        )
        if read is not None:
            self._apply_decoration_storages(read.storages)

    def _apply_decoration_storages(self, read: list[DecorationStorage]) -> None:
        """Keep each storage sent over the one of the same id; see :class:`CarriedDecorationStorages`."""
        if not read:
            return
        storages = dict(self.decoration_storages)
        storages.update((storage.storage_id, storage) for storage in read)
        self.decoration_storages = storages
        self._packet_times["sin"] = time.time()

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

        Bare rpc/cri/ubc replies carry no area identity, so only the scoped service
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
            self.construction_item_space = None

    def get_construction_item_space(self) -> ConstructionItemSpace | None:
        """The last capacity push or the space computed by an inventory reply."""
        with self._lock:
            return self.construction_item_space

    def get_expired_construction_items(self) -> ExpiredConstructionItemsResponse | None:
        """The last complete expired-item list."""
        with self._lock:
            return (
                self.expired_construction_items.model_copy(deep=True)
                if self.expired_construction_items is not None
                else None
            )

    def _handle_aec(self, data: Any) -> None:
        result = read_or_none(
            ExpiredConstructionItemsResponse.model_validate,
            data,
            warn=logging.getLogger(__name__),
            what="expired construction items",
        )
        if result is not None:
            areas = tuple(
                area
                for area in result.areas
                if area.castle_id in self.castles and self.castles[area.castle_id].kingdom_id == area.kingdom_id
            )
            self.expired_construction_items = result.model_copy(update={"areas": areas})
