"""
Typed rows of the currency and price tables: the currency id ranges, each currency's caps, rareness,
minute skip value and hidden flag, the reroll prices, the alien camp reroll chances and the daily
message limits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NewType

from pydantic import Field, ValidationInfo, field_validator, model_validator

from empire_core.enums import CollectableKind, MessageType, RerollType
from empire_core.protocol.js import js_falsy, js_parse_int, js_string

from .collectables import _XML_COST_PREFIX, Collectable
from .lenient import GameDataId, GameDataKey
from .models import _parse_int_or_default, _Row
from .tables import _is_one, row_id

if TYPE_CHECKING:
    from .ids import CurrencyId


CurrencyTypeId = NewType("CurrencyTypeId", int)
"""The ``typeID`` of a ``currencyTypes`` row, a range of currency ids that :attr:`GameData.currency_types` describes.

The client names some by its ``ClientConstCurrency.ID_RANGE_*`` constants (split.js lines 10565-10574), not all.
"""

MINUTE_SKIPS = CurrencyTypeId(1)
"""The currency type of the minute skips: ``ClientConstCurrency.ID_RANGE_MINUTE_SKIP`` (split.js line 10566)."""

RerollCostId = NewType("RerollCostId", int)
"""The id of a ``rerollCosts`` row, one reroll's price that :attr:`GameData.reroll_costs` describes.

The rows have no name, so no generated enum names them; this type marks the id space instead.
"""

AlienRerollChanceId = NewType("AlienRerollChanceId", int)
"""The ``alienRerollChancesID`` of an ``alienRerollChances`` row, which the client never reads.

The rows have no name, so no generated enum names them; this type marks the id space instead.
"""

MessageRestrictionId = NewType("MessageRestrictionId", int)
"""The id of a ``messageRestrictions`` row, a message type's limits :attr:`GameData.message_restrictions` describes.

The rows have no name, so no generated enum names them; this type marks the id space instead.
"""


def _parse_int_or(value: object, default: str) -> int | None:
    """``parseInt(value || default)``: a missing or empty value reads as the default, and NaN as None."""
    return js_parse_int(default if js_falsy(value) else value)


class CurrencyTypeDef(_Row):
    """
    A range of currency ids that belong together, such as the minute skips.

    Client: ``XmlCurrencyRangeVO.parseXml`` (split.js line 702022), keyed by ``typeID`` in ``CurrencyData.parseXml``
    (split.js line 701727); ``ClientConstCurrency.isInIdRange`` (split.js line 10461)
    """

    type_id: CurrencyTypeId = Field(validation_alias="typeID", description="The currency type")
    type_name: str = Field(validation_alias="typeName", default="", description="Its name, e.g. MinuteSkip")
    currency_id_range: tuple[int | None, int | None] = Field(
        validation_alias="currencyIDRange",
        default=(None, None),
        description="The first and the last currency id of the type; None where the column names none",
    )

    @field_validator("type_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("type_name", mode="before")
    @classmethod
    def _text(cls, value: object) -> str:
        return "" if js_falsy(value) else js_string(value)

    @field_validator("currency_id_range", mode="before")
    @classmethod
    def _range(cls, value: object) -> object:
        if isinstance(value, (tuple, list)):
            return value
        parts = ("" if js_falsy(value) else js_string(value)).split("-")
        return (js_parse_int(parts[0]), js_parse_int(parts[1]) if len(parts) > 1 else None)

    def contains(self, currency_id: int) -> bool:
        """Whether ``currency_id`` is in the range, both ends included; a range missing an end holds none."""
        first, last = self.currency_id_range
        return first is not None and last is not None and first <= currency_id <= last


class _CurrencyRow(_Row):
    """A row the client adds to the currency it names, kept only for a ``currencyID`` of 0 or more."""

    currency_id: GameDataId["CurrencyId"] = Field(validation_alias="currencyID", description="The currency")

    @field_validator("currency_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        currency_id = row_id(value)
        if currency_id < 0:
            raise ValueError(f"currency id {currency_id} is below 0")
        return currency_id


class CurrencyCapDef(_CurrencyRow):
    """
    A currency's caps.

    Client: ``XmlCurrencyVO.parseXmlCaps`` (split.js line 702109), read by ``CurrencyData.parseAdditionalXmlNode``
    (split.js line 701750)
    """

    soft_cap: int = Field(validation_alias="softCap", default=-1, description="Its soft cap; -1 for none")
    hard_cap: int = Field(validation_alias="hardCap", default=-1, description="Its hard cap; -1 for none")

    @field_validator("soft_cap", "hard_cap", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)


class CurrencyRarenessDef(_CurrencyRow):
    """
    A currency's rareness, which the game sorts currencies by.

    Client: ``XmlCurrencyVO.parseXmlRareness`` (split.js line 702117), read by
    ``CurrencyData.parseAdditionalXmlNode`` (split.js line 701750)
    """

    rareness: int = Field(default=-1, description="Its rareness; -1 for none")

    @field_validator("rareness", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)


class MinuteSkipDef(_CurrencyRow):
    """
    The minutes a minute skip takes off a timer.

    Client: ``XmlCurrencyVO.parseXmlMinutesSkipValues`` (split.js line 702122), read by
    ``CurrencyData.parseAdditionalXmlNode`` (split.js line 701750); ``CastleMinuteSkipDialog.initialStartIndex``
    (split.js line 42532) turns it into seconds
    """

    minutes: int = Field(validation_alias="MinutesSkipValue", default=-1, description="Minutes it skips; -1 for none")

    @field_validator("minutes", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)


class HiddenCurrencyDef(_CurrencyRow):
    """
    A currency the game leaves out of the inventory it lists.

    Client: ``XmlCurrencyVO.parseXmlHiddenLists`` (split.js line 702127), read by
    ``CurrencyData.parseAdditionalXmlNode`` (split.js line 701750); the inventory skips ``isHidden`` currencies
    (split.js line 442056)
    """


class RerollCostDef(_Row):
    """
    The price of one reroll: of an alien camp, the officers' school's training programs, a charge camp's effect, or
    of prolonging a training program.

    Client: ``RerollCostVO`` (split.js line 439328), grouped by type in ``CastleRerollCostData`` (split.js line
    125744)
    """

    reroll_cost_id: RerollCostId = Field(validation_alias="id", description="The price row")
    reroll_type: GameDataKey[RerollType] = Field(
        validation_alias="type", default="", description="What it prices; empty for none"
    )
    reroll_count: int = Field(
        validation_alias="rerollCount", default=-1, description="The reroll it prices, 1 for the first"
    )
    cost_coins: int = Field(validation_alias="c1Cost", default=-1, description="Coins it costs; -1 for none")
    cost_rubies: int = Field(validation_alias="c2Cost", default=-1, description="Rubies it costs; -1 for none")
    costs: tuple[Collectable, ...] = Field(
        default=(), description="What else it costs: the event currencies, each with its amount, 0 included"
    )

    @model_validator(mode="before")
    @classmethod
    def _read_costs(cls, row: object, info: ValidationInfo) -> object:
        if not isinstance(row, dict) or "costs" in row:
            return row
        currency_ids = (info.context or {}).get("currency_ids", {})
        return {**row, "costs": Collectable.from_columns(row, _XML_COST_PREFIX, currency_ids)}

    @field_validator("reroll_cost_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("reroll_type", mode="before")
    @classmethod
    def _text(cls, value: object) -> str:
        return "" if js_falsy(value) else js_string(value)

    @field_validator("reroll_count", "cost_coins", "cost_rubies", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)

    @property
    def is_free_without_rubies(self) -> bool:
        """
        Whether a reroll at this price costs neither coins nor any event currency.

        Client: ``CastleRerollCostData.getSoftCurrencyFreeRerollCountByType`` (split.js line 125776)
        """
        paid = (cost for cost in self.costs if cost.kind is not CollectableKind.OTHER and cost.amount > 0)
        return self.cost_coins == 0 and next(paid, None) is None


class AlienRerollChanceDef(_Row):
    """
    A chance of how many units an alien camp gains on a reroll, for rerolls paid without rubies or with them.

    Client: ``AlienRerollChanceVO.parseXML`` (split.js line 666948), split by kind and sorted by ``amountUnits`` in
    ``CastleAlienRerollData`` (split.js line 666801); ``CastleRerollAlienDialog.updateMinMaxInfo`` shows the first and
    the last row's units as the range
    """

    chance_id: AlienRerollChanceId = Field(validation_alias="alienRerollChancesID", description="The row")
    added_units: int = Field(validation_alias="amountUnits", description="Units the camp gains")
    chance_thousandths: int = Field(validation_alias="chance", description="Its chance, in thousandths")
    for_soft_rerolls: bool = Field(
        validation_alias="isSoftCurrency", default=False, description="Whether it is a reroll paid without rubies"
    )
    for_ruby_rerolls: bool = Field(
        validation_alias="isHardCurrency", default=False, description="Whether it is a reroll paid with rubies"
    )

    @field_validator("chance_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("added_units", mode="before")
    @classmethod
    def _units(cls, value: object) -> int:
        return _required_int(value, "amountUnits")

    @field_validator("chance_thousandths", mode="before")
    @classmethod
    def _chance(cls, value: object) -> int:
        return _required_int(value, "chance")

    @field_validator("for_soft_rerolls", "for_ruby_rerolls", mode="before")
    @classmethod
    def _flag(cls, value: object) -> bool:
        return _is_one(value)

    @property
    def chance(self) -> float:
        """Its chance as the client keeps it: :attr:`chance_thousandths` over 1000."""
        return self.chance_thousandths / 1000


def _required_int(value: object, column: str) -> int:
    """``parseInt(getValueOrDefault(column, row, "0", true))``: the client throws for a missing or empty value."""
    parsed = None if js_falsy(value) else js_parse_int(value)
    if parsed is None:
        raise ValueError(f"{column} {value!r} is not a number")
    return parsed


class MessageRestrictionDef(_Row):
    """
    A message type's daily limit and the level it can be sent from.

    Client: ``MessageRestrictionVO.fillFromParamXML`` and ``minLevel`` (split.js lines 692322 and 692313), keyed by
    id in ``CastleMessageData.parseRestrictions`` (split.js line 672409)
    """

    restriction_id: MessageRestrictionId = Field(validation_alias="messageRestrictionID", description="The row")
    message_type: GameDataId[MessageType] | None = Field(
        validation_alias="messageType", default=None, description="The message type it limits; None for none"
    )
    daily_limit: int | None = Field(
        validation_alias="dailyLimitPerPlayer",
        default=None,
        description="Messages a player sends a day; None for no limit",
    )
    min_level: int | None = Field(
        validation_alias="minLevel", default=-1, description="The level it is sent from; None for no level"
    )
    min_level_special_server: int | None = Field(
        validation_alias="minLevelGlobalServer",
        default=1,
        description="The level it is sent from on a special server; None for no level",
    )

    @field_validator("restriction_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("message_type", "daily_limit", mode="before")
    @classmethod
    def _number(cls, value: object) -> int | None:
        return _parse_int_or(value, "")

    @field_validator("min_level", mode="before")
    @classmethod
    def _min_level(cls, value: object) -> int | None:
        return _parse_int_or(value, "-1")

    @field_validator("min_level_special_server", mode="before")
    @classmethod
    def _min_level_special_server(cls, value: object) -> int | None:
        return _parse_int_or(value, "1")

    def required_level(self, *, special_server: bool = False) -> int | None:
        """The level it is sent from, on a special server or not; None where no level reaches it."""
        return self.min_level_special_server if special_server else self.min_level

    def limit_reached(self, sent_today: int) -> bool:
        """
        Whether ``sent_today`` messages use up the daily limit.

        Client: ``currentPlayerAmount >= dailyLimit`` in ``CastlePlayerInfoDialog.updateMessageRestrictions``
        (split.js line 21769)
        """
        return self.daily_limit is not None and sent_today >= self.daily_limit


__all__ = [
    "MINUTE_SKIPS",
    "AlienRerollChanceDef",
    "AlienRerollChanceId",
    "CurrencyCapDef",
    "CurrencyRarenessDef",
    "CurrencyTypeDef",
    "CurrencyTypeId",
    "HiddenCurrencyDef",
    "MessageRestrictionDef",
    "MessageRestrictionId",
    "MinuteSkipDef",
    "RerollCostDef",
    "RerollCostId",
]
