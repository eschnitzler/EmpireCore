"""Tax collection.

Commands:
- txi: Read the tax collection status
- txs: Start a tax collection
- txc: Collect the tax
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from empire_core.enums import TaxStatus
from empire_core.protocol.base import BasePayload, BaseRequest, BaseResponse, CurrencyBlock
from empire_core.protocol.js import js_falsy, js_int, js_parse_int

TAX_DURATIONS: tuple[int, ...] = (600, 1800, 5400, 10800, 21600, 43200, 86400)
"""Seconds each tax type collects for, by tax type 0 to 6.

Client: ``TaxConst.COLLECTOR_DURATION`` (dll line 19772)
"""

TAX_RUBY_COSTS: tuple[int, ...] = (0, 0, 0, 0, 0, 125, 300)
"""Rubies each tax type costs to start before any waiver, by tax type.

Types 5 and 6 cost rubies unless a premium account, a VIP level or the
tax research waives it; types 1 to 4 cost a tenth of their income in coins
and type 0 is free.

Client: ``TaxConst.START_COST_C2``, ``START_COST_C1_PERC``,
``getCollectorC2Costs`` (dll lines 19773-19779)
"""


class TaxInfo(BasePayload):
    """
    The tax collection status, the ``TX`` of a ``txi`` block.

    Client: ``TaxInfoVO.fillFromParamObject`` (bundle line 29538)
    """

    tax_type: int = Field(
        validation_alias="TT",
        serialization_alias="TT",
        default=0,
        description="The running or finished collection's tax type, 0 to 6; -1 for none",
    )
    remaining_seconds: int = Field(
        validation_alias="RT",
        serialization_alias="RT",
        default=0,
        description="Seconds until the collection is done, as of the reply",
    )
    expected_income: int = Field(
        validation_alias="EM",
        serialization_alias="EM",
        default=0,
        description="Coins the collection brings before boosts",
    )
    population: int = Field(
        validation_alias="PO", serialization_alias="PO", default=0, description="The population the income is based on"
    )
    is_boosted: bool = Field(
        validation_alias="IB", serialization_alias="IB", default=False, description="Whether the collector was bribed"
    )
    vip_bonus: int = Field(
        validation_alias="VB", serialization_alias="VB", default=0, description="The VIP tax bonus in percent"
    )

    _ints = field_validator(
        "tax_type", "remaining_seconds", "expected_income", "population", "vip_bonus", mode="before"
    )(js_int)

    @field_validator("is_boosted", mode="before")
    @classmethod
    def _boosted(cls, value: Any) -> bool:
        return bool(js_parse_int(value))

    @property
    def status(self) -> TaxStatus:
        """
        Whether a collection runs or waits to be collected, as of the reply.

        The client keeps the end time, the reply's time plus ``RT``, and counts down to it: a
        collection is collecting while the remaining time is 0 or more, so one with ``RT`` 0 is
        still collecting as of the reply, and ready to collect once the end time has passed.

        Client: ``TaxInfoVO.taxState`` and ``remainingCollectionTimeInSeconds`` (bundle lines
        29542, 29544), ``fillFromParamObject`` (bundle line 29540)
        """
        if self.tax_type <= -1:
            return TaxStatus.NONE
        return TaxStatus.COLLECTING if self.remaining_seconds >= 0 else TaxStatus.WAIT_FOR_COLLECT

    @property
    def duration_seconds(self) -> int | None:
        """How long this tax type collects for; None for no or an unknown tax type."""
        return TAX_DURATIONS[self.tax_type] if 0 <= self.tax_type < len(TAX_DURATIONS) else None


def _tax_info(value: Any) -> Any:
    # fillFromParamObject skips a falsy block and reads undefined from a non-object
    return value if isinstance(value, (dict, TaxInfo)) else {}


def _tax_block(value: Any) -> Any:
    # parse_TXI skips a falsy block
    if js_falsy(value):
        return None
    return value if isinstance(value, (dict, TaxInfoResponse)) else {}


# =============================================================================
# TXI - Read the tax status
# =============================================================================


class GetTaxInfoRequest(BaseRequest):
    """
    Read the tax collection status.

    Command: txi
    Payload: {}

    Client: ``C2SGetTaxInfoVO`` (bundle line 37186), sent by
    ``CastleCollectTaxStartDialog.showLoaded`` (bundle line 52962) and
    ``CastleCollectTaxDialog.showLoaded`` (bundle line 91005)
    """

    command = "txi"


class TaxInfoResponse(BaseResponse):
    """
    The tax collection status: the ``txi`` reply, also nested in ``txs`` and ``txc``.

    Command: txi
    Payload: {"TX": {"TT": .., "RT": .., "EM": .., "PO": .., "IB": .., "VB": ..}}

    Client: ``TXICommand.executeCommand`` (bundle line 128792),
    ``CastleTaxData.parse_TXI`` (bundle line 112797)
    """

    command = "txi"

    tax: TaxInfo = Field(
        validation_alias="TX",
        serialization_alias="TX",
        default_factory=TaxInfo,
        description="The tax collection status",
    )

    _tax = field_validator("tax", mode="before")(_tax_info)


# =============================================================================
# TXS - Start a tax collection
# =============================================================================


class StartTaxRequest(BaseRequest):
    """
    Start a tax collection of one tax type.

    Command: txs
    Payload: {"TT": tax_type, "TX": 3}

    Client: ``C2SStartCollectTaxVO`` (bundle line 91088), sent by
    ``CastleCollectTaxElement.onStartTaxCollection`` (bundle line 91069)
    """

    command = "txs"

    tax_type: int = Field(
        validation_alias="TT", serialization_alias="TT", description="The tax type, 0 to 6, an index into TAX_DURATIONS"
    )
    tx: int = Field(
        validation_alias="TX", serialization_alias="TX", default=3, description="The client's TX value, always 3"
    )


class StartTaxResponse(BaseResponse):
    """
    The tax status after starting a collection.

    Command: txs
    Payload: {"gcu": {...}, "txi": {"TX": {...}}}

    Client: ``TXSCommand.executeCommand`` (bundle line 128807)
    """

    command = "txs"

    currencies: CurrencyBlock = Field(
        validation_alias="gcu", serialization_alias="gcu", default=None, description="Coins and rubies after the start"
    )
    tax_info: TaxInfoResponse | None = Field(
        validation_alias="txi",
        serialization_alias="txi",
        default=None,
        description="The tax status after the start; None when the reply has none",
    )

    _block = field_validator("tax_info", mode="before")(_tax_block)


# =============================================================================
# TXC - Collect the tax
# =============================================================================


class CollectTaxRequest(BaseRequest):
    """
    Collect the tax, also cutting a running collection short.

    Command: txc
    Payload: {"TR": 29}

    Client: ``C2SCollectTaxVO`` (bundle line 41083), sent by
    ``IsoServerCommands.collectTax`` (bundle line 63777) and
    ``CastleCollectTaxDialog.collectTax`` (bundle line 91027)
    """

    command = "txc"

    tr: int = Field(
        validation_alias="TR", serialization_alias="TR", default=29, description="The client's TR value, always 29"
    )


class CollectTaxResponse(BaseResponse):
    """
    The collected tax.

    Command: txc
    Payload: {"gcu": {...}, "txi": {"TX": {...}}, "CT": coins}

    Client: ``TXCCommand.executeCommand`` (bundle line 128747)
    """

    command = "txc"

    currencies: CurrencyBlock = Field(
        validation_alias="gcu", serialization_alias="gcu", default=None, description="Coins and rubies after collecting"
    )
    tax_info: TaxInfoResponse | None = Field(
        validation_alias="txi",
        serialization_alias="txi",
        default=None,
        description="The tax status after collecting; None when the reply has none",
    )
    collected: int = Field(validation_alias="CT", serialization_alias="CT", default=0, description="Coins collected")

    _block = field_validator("tax_info", mode="before")(_tax_block)
    _collected = field_validator("collected", mode="before")(js_int)


__all__ = [
    "TAX_DURATIONS",
    "TAX_RUBY_COSTS",
    "CollectTaxRequest",
    "CollectTaxResponse",
    "GetTaxInfoRequest",
    "StartTaxRequest",
    "StartTaxResponse",
    "TaxInfo",
    "TaxInfoResponse",
]
