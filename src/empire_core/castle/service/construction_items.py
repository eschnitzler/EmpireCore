"""Construction items: equipping, removing, disassembling and boosting them."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeVar

from pydantic import ValidationError

from empire_core.castle.models.construction_items import (
    BoostConstructionItemRequest,
    BoostConstructionItemResponse,
    ConstructionItemInventory,
    ConstructionItemSpace,
    ConstructionItemSpaceRequest,
    DisassembleConstructionItemRequest,
    DisassembleConstructionItemResponse,
    EquipConstructionItemRequest,
    EquipConstructionItemResponse,
    ExpiredConstructionItemsResponse,
    GetConstructionItemsRequest,
    GetExpiredConstructionItemsRequest,
    MarkExpiredConstructionItemsSeenRequest,
    MarkExpiredConstructionItemsSeenResponse,
    MoveConstructionSlotRequest,
    MoveConstructionSlotResponse,
    RemoveConstructionItemRequest,
    RemoveConstructionItemResponse,
)
from empire_core.castle.models.objects import (
    BuildingConstructionItems,
    ConstructionList,
    ShowConstructionListRequest,
    ShowConstructionListResponse,
)
from empire_core.castle.models.upkeep import ConstructionItemExpiryResponse, GetConstructionItemExpiryRequest
from empire_core.castle.service.castles import CastlesMixin
from empire_core.enums import ConstructionItemMode, CurrencyId, Kingdom
from empire_core.exceptions import CommandError, EmpireError, PacketError, ReplyMismatchError
from empire_core.protocol.base import BaseResponse

if TYPE_CHECKING:
    from empire_core.gamedata import ConstructionItem

_ConstructionResponse = TypeVar("_ConstructionResponse", bound=BaseResponse)


class ConstructionItemsMixin(CastlesMixin):
    @property
    def construction_items(self) -> ConstructionItemInventory | None:
        """The last construction inventory received; None before the first inventory reply."""
        return self.client.state.get_construction_items()

    def get_construction_items(self, *, timeout: float = 5.0) -> ConstructionItemInventory:
        """Request all construction items in storage, including an empty inventory.

        Client: ``C2SGetContructionItemsInventoryVO`` and ``GIICommand``
        (bundle lines 28546, 123270).
        """
        return self.request(GetConstructionItemsRequest(), ConstructionItemInventory, timeout=timeout)

    @property
    def placed_construction_items(self) -> tuple[BuildingConstructionItems, ...] | None:
        """Items on the joined castle's buildings; None before joining or after a map read."""
        return self.client.state.get_placed_construction_items()

    def _refresh_construction_items(self, timeout: float) -> None:
        self.client.state.invalidate_construction_items()
        try:
            self.get_construction_items(timeout=timeout)
        except EmpireError as error:
            logging.getLogger(__name__).warning(
                "Construction inventory refresh failed after accepted action: %s", error
            )

    def _request_construction_action(
        self,
        request: EquipConstructionItemRequest
        | RemoveConstructionItemRequest
        | DisassembleConstructionItemRequest
        | BoostConstructionItemRequest,
        response_type: type[_ConstructionResponse],
        timeout: float,
        *,
        area_revision: int | None = None,
    ) -> tuple[_ConstructionResponse, object]:
        packet = self.client.request_packet(request, request.get_response_command(), timeout=timeout)
        if packet.error_code != 0:
            raise CommandError(request.command, packet.error_code, packet.payload)
        if request.command != "ubc":
            self.client.state.invalidate_construction_items()
        if area_revision is not None:
            self.client.state.apply_placed_construction_items(
                None,
                castle_id=request.castle_id,
                kingdom_id=request.kingdom_id,
                area_revision=area_revision,
                command=request.command,
                response_payload=packet.payload,
            )
        try:
            result = response_type.model_validate(packet.payload)
        except ValidationError as error:
            raise PacketError(f"Could not parse '{request.command}' response: {error}") from error
        return result, packet.payload

    def _join_construction_area(self, castle_id: int, kingdom: Kingdom, timeout: float) -> int:
        self.join(castle_id, timeout=timeout)
        revision = self.client.state.area_revision
        area = self.client.state.get_joined_area()
        if area is None or area.castle_id != castle_id or area.kingdom_id != kingdom:
            raise ReplyMismatchError(castle_id, area.castle_id if area and area.castle_id is not None else -1)
        return revision

    def equip_construction_item(
        self,
        castle_id: int,
        object_id: int,
        construction_item_id: ConstructionItem | int,
        slot: int,
        *,
        mode: ConstructionItemMode = ConstructionItemMode.ADD,
        timeout: float = 5.0,
    ) -> EquipConstructionItemResponse:
        """Join a castle and equip an item, returning the server's complete placement.

        ADD fills an empty slot. REPLACE keeps the old item for its coin removal
        cost; OVERWRITE discards it. A failed inventory refresh is logged and
        leaves ``construction_items`` unknown after the accepted placement.

        Client: ``AConstructionItemsActionDialog.sendReplaceCommand`` (bundle 28680),
        ``CastleConstructionItemsOverwriteDialog`` (bundle 79306-79307).
        """
        kingdom = self._require_own_castle(castle_id).kingdom_id
        request = EquipConstructionItemRequest(
            object_id=object_id,
            construction_item_id=construction_item_id,
            slot=slot,
            mode=mode,
            kingdom_id=kingdom,
            castle_id=castle_id,
        )
        with (
            self.client.connection.command_lock("jaa", timeout=timeout),
            self.client.connection.command_lock("gaa", timeout=timeout),
        ):
            revision = self._join_construction_area(castle_id, kingdom, timeout)
            result, payload = self._request_construction_action(
                request, EquipConstructionItemResponse, timeout, area_revision=revision
            )
            self.client.state.apply_placed_construction_items(
                result,
                castle_id=castle_id,
                kingdom_id=kingdom,
                area_revision=revision,
                command=request.command,
                response_payload=payload,
            )
            self._refresh_construction_items(timeout)
            return result

    def remove_construction_item(
        self,
        castle_id: int,
        object_id: int,
        construction_item_id: ConstructionItem | int,
        slot: int,
        *,
        timeout: float = 5.0,
    ) -> RemoveConstructionItemResponse:
        """Join a castle and return an equipped item to storage for its coin removal cost.

        Refusals and transport failures propagate. A failed inventory refresh is
        logged and leaves ``construction_items`` unknown after the accepted removal.

        Client: ``CastleConstructionItemsExtractDialog.onClickAccept`` (bundle 79277),
        ``CRICommand.executeCommand`` (bundle 123255-123256).
        """
        kingdom = self._require_own_castle(castle_id).kingdom_id
        request = RemoveConstructionItemRequest(
            object_id=object_id,
            construction_item_id=construction_item_id,
            slot=slot,
            kingdom_id=kingdom,
            castle_id=castle_id,
        )
        with (
            self.client.connection.command_lock("jaa", timeout=timeout),
            self.client.connection.command_lock("gaa", timeout=timeout),
        ):
            revision = self._join_construction_area(castle_id, kingdom, timeout)
            result, payload = self._request_construction_action(
                request, RemoveConstructionItemResponse, timeout, area_revision=revision
            )
            self.client.state.apply_placed_construction_items(
                result,
                castle_id=castle_id,
                kingdom_id=kingdom,
                area_revision=revision,
                command=request.command,
                response_payload=payload,
            )
            self._refresh_construction_items(timeout)
            return result

    def disassemble_construction_item(
        self,
        castle_id: int,
        construction_item_id: ConstructionItem | int,
        *,
        amount: int = 1,
        lost_and_found_id: int = -1,
        timeout: float = 5.0,
    ) -> DisassembleConstructionItemResponse:
        """Disassemble stored items and resolve their drawn rewards from game data.

        Items are consumed. ``lost_and_found_id=-1`` selects storage. The reply
        exposes the drawn reward ids and their collectables; permanent items'
        recipe materials are not listed by the server. A failed inventory refresh
        is logged and leaves ``construction_items`` unknown after success.

        Client: ``C2SDisassembleConstructionItemVO`` (bundle 79223-79227),
        ``onClickAccept`` / ``onDCIArrived`` (bundle 35727-35729),
        ``showTempCIDisassembling`` (bundle 48984).
        """
        kingdom = self._require_own_castle(castle_id).kingdom_id
        request = DisassembleConstructionItemRequest(
            construction_item_id=construction_item_id,
            kingdom_id=kingdom,
            castle_id=castle_id,
            amount=amount,
            lost_and_found_id=lost_and_found_id,
        )
        game_data = self._require_game_data()
        with (
            self.client.connection.command_lock("jaa", timeout=timeout),
            self.client.connection.command_lock("gaa", timeout=timeout),
        ):
            self._join_construction_area(castle_id, kingdom, timeout)
            result, _ = self._request_construction_action(request, DisassembleConstructionItemResponse, timeout)
            result = result.model_copy(update={"rewards": game_data.reward_list(result.reward_ids, combine=True)})
            self._refresh_construction_items(timeout)
            return result

    @property
    def construction_item_space(self) -> ConstructionItemSpace | None:
        """Free construction storage capacity, from the last inventory or capacity push."""
        return self.client.state.get_construction_item_space()

    def get_construction_item_space(self, *, timeout: float = 5.0) -> ConstructionItemSpace:
        """
        Ask how many more construction items fit in storage; the reply also reaches the state.

        Client: ``C2SConstructionItemInventorySpaceLeftVO`` (bundle line 41293), ``CSPCommand.exec``
        (bundle line 123855)
        """
        return self.request(ConstructionItemSpaceRequest(), ConstructionItemSpace, timeout=timeout)

    def get_construction_item_expiry(self, *, timeout: float = 5.0) -> ConstructionItemExpiryResponse:
        """
        Ask when the next of your construction items expires; the reply also reaches the state.

        Client: ``ConstructionItemData.onCIExpiration`` (bundle line 22993) sends
        ``C2SGetNextExpiringConstructionItemVO``; ``NECCommand.executeCommand`` (bundle line 123336)
        """
        return self.request(GetConstructionItemExpiryRequest(), ConstructionItemExpiryResponse, timeout=timeout)

    @property
    def expired_construction_items(self) -> ExpiredConstructionItemsResponse | None:
        """The last complete list of expired items; None before a successful read."""
        return self.client.state.get_expired_construction_items()

    def get_expired_construction_items(self, *, timeout: float = 5.0) -> ExpiredConstructionItemsResponse:
        """Request expired items across your castles.

        Client: ``C2SGetAllExpiredConstructionItemsVO`` / ``AECCommand`` (bundle 79379 / 123264).
        """
        return self.request(GetExpiredConstructionItemsRequest(), ExpiredConstructionItemsResponse, timeout=timeout)

    def mark_expired_construction_items_seen(
        self, castle_id: int, *, timeout: float = 5.0
    ) -> MarkExpiredConstructionItemsSeenResponse:
        """Mark a castle's expired items as viewed, as closing their list does.

        This acknowledgement does not remove expired records from the cached list.
        Client: assign sublayer hide / switchCastle (bundle 77574 / 77583), MECCommand (123308).
        """
        self._require_own_castle(castle_id)
        return self.request(
            MarkExpiredConstructionItemsSeenRequest(castle_id=castle_id),
            MarkExpiredConstructionItemsSeenResponse,
            timeout=timeout,
        )

    def move_construction_slot(
        self, castle_id: int, old_position: int, new_position: int, *, timeout: float = 5.0
    ) -> ConstructionList:
        """Move a building in its construction queue and read the resulting queue.

        Both positions must contain a building. The move acknowledgement carries no queue;
        a failed follow-up read propagates after the accepted move.
        Client: ``CastleBuildingListComponent`` (bundle 108280-108281), ``MCICommand`` (123383).
        """
        if old_position < 0 or new_position < 0:
            raise ValueError("Queue positions must be nonnegative")
        kingdom = self._require_own_castle(castle_id).kingdom_id
        with (
            self.client.connection.command_lock("jaa", timeout=timeout),
            self.client.connection.command_lock("gaa", timeout=timeout),
        ):
            revision = self._join_construction_area(castle_id, kingdom, timeout)
            queue = self._construction_queue_for_move(timeout)
            if any(
                position >= len(queue.slots) or queue.slots[position].object_id <= 0
                for position in (old_position, new_position)
            ):
                raise ValueError("Both construction queue positions must contain buildings")
            self._check_construction_area(castle_id, kingdom, revision)
            if old_position == new_position:
                return queue
            self.request(
                MoveConstructionSlotRequest(object_id=queue.slots[old_position].object_id, new_position=new_position),
                MoveConstructionSlotResponse,
                timeout=timeout,
            )
            self._check_construction_area(castle_id, kingdom, revision)
            result = self._construction_queue_for_move(timeout)
            self._check_construction_area(castle_id, kingdom, revision)
            return result

    def _construction_queue_for_move(self, timeout: float) -> ConstructionList:
        packet = self.client.request_packet(ShowConstructionListRequest(), "scl", timeout=timeout)
        if packet.error_code != 0:
            raise CommandError("scl", packet.error_code, packet.payload)
        if not isinstance(packet.payload, dict) or not isinstance(packet.payload.get("OIDL"), list):
            raise PacketError("The construction queue reply must contain a building list")
        if any(isinstance(entry, (dict, list)) for entry in packet.payload["OIDL"]):
            raise PacketError("The construction queue reply must contain scalar building ids")
        try:
            return ShowConstructionListResponse.model_validate(packet.payload)
        except ValidationError as error:
            raise PacketError(f"Could not parse construction queue: {error}") from error

    def _check_construction_area(self, castle_id: int, kingdom: Kingdom, revision: int) -> None:
        area = self.client.state.get_joined_area()
        if (
            area is None
            or area.castle_id != castle_id
            or area.kingdom_id != kingdom
            or self.client.state.area_revision != revision
        ):
            raise ReplyMismatchError(castle_id, area.castle_id if area and area.castle_id is not None else -1)

    def boost_construction_item(
        self,
        castle_id: int,
        object_id: int,
        construction_item_id: ConstructionItem | int,
        slot: int,
        *,
        consumable: CurrencyId,
        timeout: float = 5.0,
    ) -> BoostConstructionItemResponse:
        """Consume one selected inventory booster on a temporary equipped item.

        Select currency id 2000 (rare), 2001 (epic) or 2002 (legendary).
        The item must still have time remaining and the selected booster must improve its rarity.
        Client: ``updateBoosterButton`` / ``boostConstructionItem`` (bundle 77588-77591 / 77624-77625),
        ``ConstructionItemConst`` (dll 18989). This command has no ruby purchase branch.
        """
        targets = {2000: 2, 2001: 3, 2002: 4}
        if consumable not in targets:
            raise ValueError("Select a rare, epic or legendary construction item inventory booster")
        if slot < 0 or object_id <= 0:
            raise ValueError("The building and slot must identify an equipped construction item")
        game_data = self._require_game_data()
        item = game_data.construction_items.get(construction_item_id)
        if item is None or item.duration_seconds <= 0 or item.rareness_id >= targets[consumable]:
            raise ValueError("The selected booster must improve a known temporary construction item")
        currency = game_data.currencies.get(consumable)
        if currency is None or self.client.state.get_special_currencies().get(currency.json_key, 0) <= 0:
            raise ValueError("The selected construction item booster is not in inventory")
        kingdom = self._require_own_castle(castle_id).kingdom_id
        request = BoostConstructionItemRequest(
            object_id=object_id,
            consumable_id=consumable,
            slot=slot,
            kingdom_id=kingdom,
            castle_id=castle_id,
            construction_item_id=construction_item_id,
        )
        with (
            self.client.connection.command_lock("jaa", timeout=timeout),
            self.client.connection.command_lock("gaa", timeout=timeout),
        ):
            revision = self._join_construction_area(castle_id, kingdom, timeout)
            placement = self.placed_construction_items
            equipped = next(
                (
                    entry
                    for building in placement or ()
                    if building.object_id == object_id
                    for entry in building.items
                    if entry.slot == slot and entry.construction_item_id == construction_item_id
                ),
                None,
            )
            if equipped is None or equipped.remaining_seconds <= 0:
                raise ValueError("The selected temporary construction item is not equipped or has expired")
            result, payload = self._request_construction_action(
                request, BoostConstructionItemResponse, timeout, area_revision=revision
            )
            self.client.state.apply_placed_construction_items(
                result,
                castle_id=castle_id,
                kingdom_id=kingdom,
                area_revision=revision,
                command=request.command,
                response_payload=payload,
            )
            return result
