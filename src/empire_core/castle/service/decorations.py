"""Decoration storage and the decoration fusion forge."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from empire_core.castle.models.fusion_forge import (
    ConvertCatalystRequest,
    ConvertCatalystResponse,
    FuseDecorationRequest,
    FuseDecorationResponse,
    FusionDecoration,
    FusionForge,
    FusionForgesResponse,
    FusionTargetArea,
    FusionTargetsResponse,
    GetFusionForgesRequest,
    GetFusionTargetsRequest,
    LevelUpFusionForgeRequest,
    LevelUpFusionForgeResponse,
    RefillFusionForgeRequest,
    RefillFusionForgeResponse,
)
from empire_core.castle.models.storage import (
    DecorationStorage,
    DecorationStorageKey,
    DecorationStorageResponse,
    MarkStorageSeenRequest,
    PlaceStoredDecorationRequest,
    PlaceStoredDecorationResponse,
    SellStoredDecorationRequest,
    SellStoredDecorationResponse,
    ShowInventoryRequest,
    StoreBuildingRequest,
    StoreBuildingResponse,
)
from empire_core.enums import CatalystConversion, CurrencyId
from empire_core.gamedata import FusionForgeId
from empire_core.services.base import ServiceMixin

if TYPE_CHECKING:
    from empire_core.gamedata import Building


class DecorationsMixin(ServiceMixin):
    # =========================================================================
    # Decoration storage
    # =========================================================================

    @property
    def decoration_storages(self) -> dict[int, DecorationStorage]:
        """The decoration storages by storage id, from the last ``sin`` that named each; empty until one arrived."""
        return self.client.state.get_decoration_storages()

    def get_decoration_storages(self, *, timeout: float = 5.0) -> list[DecorationStorage]:
        """
        Read the decoration storages; they also reach :attr:`decoration_storages`.

        Client: ``CastleDecoShopPanel.show`` (bundle line 9302) sends ``C2SShowInventoryVO`` with no
        parameter; ``SINCommand.exec`` (bundle line 124638)
        """
        return self.request(ShowInventoryRequest(), DecorationStorageResponse, timeout=timeout).storages

    def mark_storage_seen(self, storage_id: DecorationStorageKey, *, timeout: float = 5.0) -> None:
        """
        Mark a storage's new decorations as seen.

        Args:
            storage_id: A ``DecorationStorage.storage_id``

        Client: ``SendMarkedBuildingsInStorage.execute`` (bundle line 101099) sends
        ``C2SMarkBuildingInStorageVO`` for each storage shown
        """
        self.execute(MarkStorageSeenRequest(storage_id=storage_id), timeout=timeout)

    def store_decoration(self, object_id: int, *, timeout: float = 5.0) -> StoreBuildingResponse:
        """
        Put a decoration of the joined castle into the storage.

        Returns:
            The stored object's id and the storages after, which also reach :attr:`decoration_storages`

        Client: ``IsoServerCommands.storeBuildingToLocalInventory`` (bundle line 63795) sends
        ``C2SIsoStoreObjectVO``; ``SOBCommand.executeCommand`` (bundle line 124651)
        """
        return self.request(StoreBuildingRequest(object_id=object_id), StoreBuildingResponse, timeout=timeout)

    def sell_stored_decoration(
        self, wod_id: Building, amount: int = 1, *, unique_id: int = -1, timeout: float = 5.0
    ) -> SellStoredDecorationResponse:
        """
        Sell decorations from the storage for coins; they are gone for good.

        Args:
            wod_id: The decoration's type, a stored decoration's ``wod_id``
            amount: How many to sell
            unique_id: A unique decoration's ``unique_id``, -1 for regular ones

        Returns:
            Coins and rubies, and the storages after, which also reach :attr:`decoration_storages`

        Raises:
            ValueError: ``amount`` is below 1

        Client: ``CastleConstructionSellDialog.onClick`` (bundle line 28636) sends ``C2SellStoredDeco``;
        ``SDSCommand.executeCommand`` (bundle line 131786)
        """
        if amount < 1:
            raise ValueError(f"amount must be at least 1, got {amount}")
        request = SellStoredDecorationRequest(wod_id=wod_id, amount=amount, unique_id=unique_id)
        return self.request(request, SellStoredDecorationResponse, timeout=timeout)

    def place_stored_decoration(
        self, decoration_id: int, x: int, y: int, rotation: int = 0, *, timeout: float = 5.0
    ) -> PlaceStoredDecorationResponse:
        """
        Place a custom or unique decoration from the storage in the joined castle.

        A regular stored decoration is placed with :meth:`build` of its type, as the client does.

        Args:
            decoration_id: A stored ``custom_id`` or ``unique_id``

        Returns:
            The placed decoration and the storages after, which also reach :attr:`decoration_storages`

        Client: ``IsoServerCommands.placeCustomInventoryObject`` (bundle line 63790), sent for a decoration
        with a ``uniqueBuildingId`` (bundle line 64041); ``PIOCommand.executeCommand`` (bundle line 123181)
        """
        request = PlaceStoredDecorationRequest(decoration_id=decoration_id, x=x, y=y, rotation=rotation)
        return self.request(request, PlaceStoredDecorationResponse, timeout=timeout)

    # =========================================================================
    # Fusion forge
    # =========================================================================

    @property
    def fusion_forges(self) -> dict[FusionForgeId | int, FusionForge] | None:
        """The fusion forges by id, as the last ``ffi`` left them; None until one arrived."""
        return self.client.state.get_fusion_forges()

    def get_fusion_forges(
        self, forge_ids: Sequence[FusionForgeId] = (FusionForgeId.DECORATIONS,), *, timeout: float = 5.0
    ) -> tuple[FusionForge, ...]:
        """
        Fusion forges' level and energy; the reply also reaches :attr:`fusion_forges`.

        Client: ``FusionForgeData.onGbdArrived`` (bundle line 142012), ``FusionForgeVO.requestDataFromServer``
        (bundle line 142199)
        """
        request = GetFusionForgesRequest(forge_ids=tuple(forge_ids))
        return self.request(request, FusionForgesResponse, timeout=timeout).forges

    def level_up_fusion_forge(
        self, forge_id: FusionForgeId = FusionForgeId.DECORATIONS, *, timeout: float = 5.0
    ) -> int:
        """
        Level a fusion forge up for decoration dust, and return its new level.

        Client: ``DecorationForgeUpgradeDialog.onLevelUpButtonClicked`` (bundle line 78274),
        ``FusionForgeVO.getCostForForgeLevelUp`` (bundle line 142209)
        """
        request = LevelUpFusionForgeRequest(forge_id=forge_id)
        return self.request(request, LevelUpFusionForgeResponse, timeout=timeout).level

    def refill_fusion_forge(
        self,
        forge_id: FusionForgeId = FusionForgeId.DECORATIONS,
        *,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> int:
        """
        Refill a fusion forge's energy for rubies, and return the energy added.

        The price rises with each refill (``FusionForge.used_ruby_refills``) by the forge's
        ``GameData.fusion_systems`` row (``refill_cost_rubies``, ``refill_cost_factor``).

        Raises:
            ValueError: ``spend_rubies`` is False

        Client: ``DecorationForgeRechargeEnergyDialog`` (bundle line 35619),
        ``FusionForgeVO.getC2PriceForEnergyPremiumSkip`` (bundle line 142206)
        """
        self._require_spend_rubies(spend_rubies, "refilling the fusion forge's energy costs rubies")
        request = RefillFusionForgeRequest(forge_id=forge_id)
        return self.request(request, RefillFusionForgeResponse, timeout=timeout).energy

    def convert_catalysts(
        self,
        catalyst_id: CurrencyId | int,
        amount: int,
        direction: CatalystConversion,
        forge_id: FusionForgeId = FusionForgeId.DECORATIONS,
        *,
        timeout: float = 5.0,
    ) -> ConvertCatalystResponse:
        """
        Assemble fusion catalysts, or disassemble them into decoration dust.

        Client: ``ADecorationForgeCatalystConversionDialogInfoBox.onConfirmButtonClicked`` (bundle line 48367)
        """
        request = ConvertCatalystRequest(forge_id=forge_id, direction=direction, catalyst_id=catalyst_id, amount=amount)
        return self.request(request, ConvertCatalystResponse, timeout=timeout)

    def get_fusion_targets(self, *, timeout: float = 5.0) -> tuple[FusionTargetArea, ...]:
        """
        Your areas with the placed decorations a fusion can target.

        Client: ``DecoStorageData.requestGTD`` (bundle line 141447)
        """
        return self.request(GetFusionTargetsRequest(), FusionTargetsResponse, timeout=timeout).areas

    def fuse_decoration(
        self,
        source_wod_id: Building,
        source_unique_id: int,
        target_area: FusionTargetArea,
        target: FusionDecoration,
        catalyst_id: CurrencyId | int,
        *,
        pay_with_rubies: bool = False,
        spend_rubies: bool = False,
        timeout: float = 5.0,
    ) -> FuseDecorationResponse:
        """
        Fuse a stored decoration into a placed one. The stored decoration is used up.

        The fusion spends the forge's energy and the catalyst, and the fusion currency, or rubies with
        ``pay_with_rubies`` (the premium fusion).

        Args:
            source_wod_id: The stored decoration's building type
            source_unique_id: The stored decoration's unique id
            target_area: The area of :meth:`get_fusion_targets` the target stands in
            target: One of ``target_area.decorations``
            catalyst_id: The catalyst used, a currency
            pay_with_rubies: The premium fusion
            spend_rubies: Allow the premium fusion's rubies
            timeout: Timeout in seconds

        Raises:
            ValueError: ``target`` is not in ``target_area``, or rubies are spent without ``spend_rubies``

        Client: ``DecorationForgeMainDialog.onFuseButtonClicked`` (bundle line 35455)
        """
        if target not in target_area.decorations:
            raise ValueError(f"decoration {target.object_id} is not in area {target_area.castle_id}")
        self._require_spend_rubies(spend_rubies, "the premium fusion costs rubies" if pay_with_rubies else None)
        request = FuseDecorationRequest(
            catalyst_id=catalyst_id,
            pay_with_rubies=pay_with_rubies,
            source_unique_id=source_unique_id,
            source_wod_id=source_wod_id,
            target_object_id=target.object_id,
            target_kingdom=target_area.kingdom,
            target_castle_id=target_area.castle_id,
            target_unique_id=target.unique_id,
            target_wod_id=target.wod_id,
        )
        return self.request(request, FuseDecorationResponse, timeout=timeout)
