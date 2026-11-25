"""
Event packages: buying one in an event's shop, and how often you bought each.

Commands:
- sbp: buy an event package; the reply carries what changed
- gbc: how often you bought each package with a stock
"""

from __future__ import annotations

from pydantic import Field, field_serializer, model_validator

from empire_core.army.models.production import ResourcesBlock
from empire_core.castle.models.storage import DecorationStorages
from empire_core.enums import Kingdom, PackageBuyType
from empire_core.gamedata import PackageId
from empire_core.player.models.account import VipStatusResponse
from empire_core.protocol.base import BaseRequest, BaseResponse, CurrencyBlock, EmpireModel, OptionalBlock
from empire_core.protocol.js import ClientInt
from empire_core.spy.models import PlagueDoctorInfoResponse

UNSUPPORTED_BUY_TYPES = frozenset({PackageBuyType.PRIVATE_OFFER, PackageBuyType.GIFT})
"""The buy types this library does not send: a private offer's and a gift's purchases are not modelled."""


class BuyEventPackageRequest(BaseRequest):
    """
    Buy an event package at its fixed price.

    Command: sbp
    Payload: {"PID": package, "BT": buy type, "TID": event, "AMT": amount, "KID": kingdom, "AID": castle or -1,
    "PC2": -1, "BA": 0, "PWR": 0 or 1, "_PO": -1}

    A package whose price depends on your storages (``PC2``), a private offer's and a gift's purchase are refused.

    Client: ``C2SBuyEventPackageVO`` (split.js line 134728), sent by ``AMerchantBuyDialog.onBtnOkClick`` and
    ``ModernPackageShopBuyElementBottomMenu.onOfferAccepted`` (split.js lines 214956, 367863), resent with ``PWR`` 1 by
    ``CastleResourceWaitDialogProperties`` (split.js line 183839)
    """

    command = "sbp"

    package_id: PackageId = Field(validation_alias="PID", description="The package")
    buy_type: PackageBuyType = Field(validation_alias="BT", description="Where it is bought")
    buy_type_id: int = Field(
        validation_alias="TID", default=-1, description="The event it is bought in, for an event's shop; else -1"
    )
    amount: int = Field(validation_alias="AMT", ge=1, description="How many to buy")
    kingdom: Kingdom = Field(validation_alias="KID", description="The kingdom it is bought in")
    castle_id: int = Field(
        validation_alias="AID", default=-1, description="The castle a building goes to; -1 for any other package"
    )
    custom_price_rubies: int = Field(
        validation_alias="PC2", default=-1, description="The price of a package priced by your storages; -1 for none"
    )
    buy_again: bool = Field(
        validation_alias="BA",
        default=False,
        description="Whether it repeats a purchase, as the equipment merchant's buy-again button does",
    )
    pay_with_rubies: bool = Field(
        validation_alias="PWR", default=False, description="Whether the costs you lack are paid in rubies"
    )
    private_offer_id: int = Field(
        validation_alias="_PO", default=-1, description="The private offer the payment uses, -1 for none"
    )

    @model_validator(mode="after")
    def _supported(self) -> BuyEventPackageRequest:
        if self.buy_type in UNSUPPORTED_BUY_TYPES:
            raise ValueError(f"buying with buy type {self.buy_type.name} is not supported")
        if self.custom_price_rubies != -1:
            raise ValueError("a package priced by your storages is not supported")
        return self

    @field_serializer("buy_again", "pay_with_rubies")
    def _flag(self, value: bool) -> int:
        return 1 if value else 0


class BuyEventPackageResponse(BaseResponse):
    """
    What a package bought changed: your currencies, the castle's resources and units, plague doctors, decoration
    storages and VIP, and how often you have bought it.

    Command: sbp
    Payload: {"PID": package, "AMT": bought, "gcu": {...}, "grc": {...}, "cpi": {...}, "sin": [...], "vip": {...},
    "gui": {...}}

    The castle's units (``gui``) are not read. A refusal for lack of an event currency names the package
    (:class:`~empire_core.exceptions.NotEnoughSpecialCurrencyError`).

    Client: ``SBPCommand.executeCommand`` (split.js line 647153), ``CastleEventPackageData.parseBoughtCount``
    (split.js line 670404)
    """

    command = "sbp"

    package_id: PackageId | None = Field(
        validation_alias="PID", default=None, description="The package; None when the reply names none"
    )
    bought_count: ClientInt = Field(
        validation_alias="AMT", default=0, description="How often you have bought the package now"
    )
    currencies: CurrencyBlock = Field(validation_alias="gcu", default=None, description="Coins and rubies after")
    resources: ResourcesBlock = Field(
        validation_alias="grc", default=None, description="The castle's resources after; None when the reply has none"
    )
    plague_doctors: OptionalBlock[PlagueDoctorInfoResponse] = Field(
        validation_alias="cpi", default=None, description="Your plague doctors after; None when the reply has none"
    )
    storages: DecorationStorages = Field(validation_alias="sin", default_factory=list, description="The storages after")
    vip: OptionalBlock[VipStatusResponse] = Field(
        validation_alias="vip", default=None, description="Your VIP after; None when the reply has none"
    )


class GetPackageBuyCountsRequest(BaseRequest):
    """
    Ask how often you bought each package with a stock.

    Command: gbc
    Payload: {"CID": castle, "KID": kingdom}

    Client: ``C2SGetPackageBuyCountVO`` (split.js line 214462), sent for the joined castle by
    ``BuyEventPackagesComponent.requestPackageBuyCountUpdate`` (split.js line 214359)
    """

    command = "gbc"

    castle_id: int = Field(validation_alias="CID", description="The castle")
    kingdom: Kingdom = Field(validation_alias="KID", description="The castle's kingdom")


class PackageBuyCount(EmpireModel):
    """How often you bought one package. Client: ``CastleEventPackageData.parseBoughtCount`` (split.js line 670404)"""

    package_id: PackageId = Field(validation_alias="PID", description="The package")
    bought_count: ClientInt = Field(validation_alias="AMT", default=0, description="How often you bought it")


class PackageBuyCountsResponse(BaseResponse):
    """
    How often you bought each package with a stock; a package the list leaves out you have not bought.

    Command: gbc
    Payload: {"PL": [{"PID": package, "AMT": bought}, ...]}

    Client: ``GBCCommand.executeCommand`` (split.js line 651107), ``CastleEventPackageData.parseGBC`` (split.js
    line 670387), applied only when ``PL`` is sent
    """

    command = "gbc"

    counts: tuple[PackageBuyCount, ...] | None = Field(
        validation_alias="PL", default=None, description="Each package bought; None when the reply sends no list"
    )


__all__ = [
    "UNSUPPORTED_BUY_TYPES",
    "BuyEventPackageRequest",
    "BuyEventPackageResponse",
    "GetPackageBuyCountsRequest",
    "PackageBuyCount",
    "PackageBuyCountsResponse",
]
