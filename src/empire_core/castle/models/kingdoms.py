"""
Your kingdoms: which are unlocked, and the units and goods on their way to one.

Commands:
- kpi: kingdom info, a login section of ``gbd``, a reply, and inside the transfer replies
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import ConfigDict, Field, field_validator

from empire_core.enums import CollectableKind, Kingdom
from empire_core.gamedata import Collectable, CollectableRows, EnumOrInt
from empire_core.protocol.base import BaseResponse, TimedPayload, readable_list
from empire_core.protocol.js import ClientInt, ClientNumber, js_int, js_loose_equals, js_truthy


class KingdomUnlock(TimedPayload):
    """
    One kingdom's unlock, warehouse and slum, an entry of a ``kpi``'s ``UL``.

    Client: ``CastleKingdomVO.parseUnlockInfo`` (bundle line 134696); ``hasContor`` read at bundle line 50209
    """

    kingdom_id: EnumOrInt[Kingdom] = Field(
        validation_alias="KID", serialization_alias="KID", default=-1, description="The kingdom; -1 when not sent"
    )
    is_unlocked: bool = Field(
        validation_alias="U", serialization_alias="U", default=False, description="Whether the kingdom is unlocked"
    )
    has_warehouse: bool = Field(
        validation_alias="C",
        serialization_alias="C",
        default=False,
        description="Whether the kingdom has a warehouse, which its resource villages need",
    )
    slum_level: ClientInt = Field(
        validation_alias="SL", serialization_alias="SL", default=0, description="The kingdom's slum level"
    )
    paid_wood: ClientNumber = Field(
        validation_alias="SPW",
        serialization_alias="SPW",
        default=0,
        description="Wood paid towards the next slum level",
    )
    paid_stone: ClientNumber = Field(
        validation_alias="SPS",
        serialization_alias="SPS",
        default=0,
        description="Stone paid towards the next slum level",
    )
    paid_food: ClientNumber = Field(
        validation_alias="SPF",
        serialization_alias="SPF",
        default=0,
        description="Food paid towards the next slum level",
    )
    paid_coins: ClientNumber = Field(
        validation_alias="SPC1",
        serialization_alias="SPC1",
        default=0,
        description="Coins paid towards the next slum level",
    )
    reset_seconds: ClientNumber = Field(
        validation_alias="KRS",
        serialization_alias="KRS",
        default=0,
        description="Seconds until the kingdom resets when the values were read; 0 for none",
    )
    reward_set: ClientNumber = Field(
        validation_alias="CRS", serialization_alias="CRS", default=0, description="The kingdom's reward set; 0 for none"
    )

    @field_validator("kingdom_id", mode="before")
    @classmethod
    def _kingdom(cls, value: Any) -> Any:
        return js_int(value)

    @field_validator("is_unlocked", "has_warehouse", mode="before")
    @classmethod
    def _flag(cls, value: Any) -> bool:
        return js_loose_equals(value, 1)

    def remaining_reset_seconds(self, now: float | None = None) -> float | None:
        """Seconds until the kingdom resets, 0 at least; None when it does not reset."""
        if not js_truthy(self.reset_seconds):
            return None
        return max(0.0, self.reset_seconds - self._elapsed(now))


class KingdomTransfer(TimedPayload):
    """
    Units or goods on their way to a kingdom, an entry of a ``kpi``'s ``UT`` or ``RT``.

    The units come as ``[wod_id, amount]`` rows, which the client keeps as they are and names by
    their unit (``toolTipText``); here each is a ``UNITS`` collectable, its ``item`` the unit or tool.

    Client: ``CastleKingdomUnitTransferVO.fillFromParamObject`` and ``toolTipText`` (bundle lines 134663,
    134675), ``CastleKingdomGoodsTransferVO.fillFromParamObject`` (bundle line 134640), which reads the
    goods with ``CollectableParserS2CParamList``
    """

    kingdom_id: EnumOrInt[Kingdom] = Field(
        validation_alias="KID", serialization_alias="KID", default=Kingdom.GREEN, description="The kingdom they go to"
    )
    seconds: ClientInt = Field(
        validation_alias="RS",
        serialization_alias="RS",
        default=0,
        description="Seconds until they arrive when the values were read",
    )
    units: tuple[Collectable, ...] = Field(
        validation_alias="I", serialization_alias="I", default=(), description="The units and tools; units only"
    )
    goods: CollectableRows = Field(
        validation_alias="G", serialization_alias="G", default=(), description="The goods; goods only"
    )

    @field_validator("kingdom_id", mode="before")
    @classmethod
    def _kingdom(cls, value: Any) -> Any:
        return js_int(value)

    @field_validator("units", mode="before")
    @classmethod
    def _units(cls, value: Any) -> Any:
        if not isinstance(value, list | tuple):
            return ()
        return tuple(
            row if isinstance(row, Collectable) else Collectable.from_entry(CollectableKind.UNITS.server_key, row)
            for row in value
            if isinstance(row, Collectable | list)
        )

    def remaining_seconds(self, now: float | None = None) -> float:
        """Seconds until they arrive, 0 at least."""
        return max(0.0, self.seconds - self._elapsed(now))


def _transfers(value: Any) -> tuple[KingdomTransfer, ...]:
    return tuple(readable_list(KingdomTransfer, value, accept=lambda entry: isinstance(entry, dict)))


class KingdomInfoResponse(BaseResponse):
    """
    Your kingdoms' unlocks, and the units and goods on their way to them.

    A ``kpi`` updates only the kingdoms it lists; the client keeps the others as they were, and
    ``client.state.get_kingdoms()`` does the same. The transfers are replaced whole. The Berimond
    faction block (``fki``) belongs to the faction event and is not read here.

    Command: kpi, as a login section of ``gbd``, a reply, and inside the ``kgt``, ``kst``, ``kut``, ``msk``
    and ``fjf`` replies.

    Client: ``KPICommand`` (bundle line 124684), ``CastleKingdomData.parse_KPI`` (bundle line 134539)
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    command = "kpi"

    kingdoms: tuple[KingdomUnlock, ...] = Field(
        validation_alias="UL", serialization_alias="UL", default=(), description="The kingdoms this packet lists"
    )
    unit_transfers: tuple[KingdomTransfer, ...] = Field(
        validation_alias="UT", serialization_alias="UT", default=(), description="Units on their way to another kingdom"
    )
    goods_transfers: tuple[KingdomTransfer, ...] = Field(
        validation_alias="RT", serialization_alias="RT", default=(), description="Goods on their way to another kingdom"
    )

    @field_validator("kingdoms", mode="before")
    @classmethod
    def _kingdoms(cls, value: Any) -> Any:
        return tuple(readable_list(KingdomUnlock, value, accept=lambda entry: isinstance(entry, dict)))

    _transfers = field_validator("unit_transfers", "goods_transfers", mode="before")(_transfers)

    def kingdom(self, kingdom_id: Kingdom | int) -> KingdomUnlock | None:
        """One kingdom, None when it is not listed."""
        return next((kingdom for kingdom in self.kingdoms if kingdom.kingdom_id == kingdom_id), None)


__all__ = ["KingdomInfoResponse", "KingdomTransfer", "KingdomUnlock"]
