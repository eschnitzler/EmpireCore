"""
Collectables: one reward, cost or lot of goods, typed by kind, as the client's single parser reads them.

The server sends collectables in two layouts, which the client reads with one key table:

- rows, ``[[key, entry, amount?], ...]`` (a mission's rewards, goods on their way): :data:`CollectableRows`
- an object, ``{key: [entry, ...], "SO": sort order}`` (the login bonus): :data:`CollectableObject`

Each entry's layout depends on its kind (``[unit_id, amount]`` under ``U``, an amount under ``C1``,
``{"ID": booster id, "D": seconds}`` under ``B``, ...); :class:`Collectable` reads it into ``item``,
``amount`` and ``duration_seconds``. An entry under a key the client has no type for is kept as
``CollectableKind.OTHER`` with its key and value, where the client drops it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from enum import Enum
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, PlainValidator

from empire_core.enums import BoosterId, CollectableKind, Rareness
from empire_core.protocol.js import js_int, js_number_or_none, js_parse_int, js_parse_int_or_zero, js_truthy

from .lenient import EnumOrInt, known

if TYPE_CHECKING:
    from .ids import AllianceCrestLayout, Building, ConstructionItem, Currency, CurrencyId, Gem, LootBox, Tool, Unit

    CollectableItem = (
        Unit
        | Tool
        | Building
        | ConstructionItem
        | Currency
        | LootBox
        | Gem
        | AllianceCrestLayout
        | BoosterId
        | Rareness
        | int
        | str
    )
else:

    def _item(value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, int | str):
            raise ValueError(f"{value!r} is no collectable item")
        return value

    CollectableItem = Annotated[int | str, PlainValidator(_item)]

_KINDS_BY_KEY: dict[str, CollectableKind] = {
    variant: kind
    for kind in CollectableKind
    if kind.server_key
    for variant in (kind.server_key, kind.server_key.lower(), kind.server_key[:1].upper() + kind.server_key[1:])
}
"""Each kind by its server key, also lower-cased and with a capital first letter, as the client registers it.

Client: ``CollectableEnum.addObjectToDic`` (bundle line 405)
"""

MINUTE_SKIP_KEY = "MS"
"""A minute skip sent as ``["MS<n>", amount]``: the currency ``MINUTE_SKIP_FIRST_ID + n``."""

MINUTE_SKIP_FIRST_ID = 1000
"""The start of the minute skips' currency id range: items ``currencyTypes`` row ``MinuteSkip`` ("1000-1999").

Client: ``CollectableHelper.getTypeByServerKey`` (bundle lines 1604-1605), ``XmlCurrencyRangeVO.parseXml``
(bundle line 141268)
"""

_PRIME_SALE_BOOSTERS = frozenset(
    {
        BoosterId.OVERSEER_WOOD,
        BoosterId.OVERSEER_STONE,
        BoosterId.OVERSEER_FOOD,
        BoosterId.OVERSEER_HONEY,
        BoosterId.OVERSEER_MEAD,
        BoosterId.OVERSEER_BEEF,
        BoosterId.MARAUDER,
        BoosterId.TAX,
        BoosterId.INSTRUCTOR,
        BoosterId.CARAVAN_OVERLOADER,
        BoosterId.RETURNING_SPEED,
    }
)
"""``BoosterConst.PRIME_SALE_BOOSTER_IDS`` (dll line 18850): boosters that stay plain boosters."""

_BOOSTER_KINDS: dict[int, CollectableKind] = {
    BoosterId.GLORY: CollectableKind.GLORY_BOOSTER,
    BoosterId.PERSONAL_GLORY: CollectableKind.GLORY_BOOSTER,
    BoosterId.KHAN_TABLET: CollectableKind.KHAN_TABLET_BOOSTER,
    BoosterId.XP: CollectableKind.XP_BOOSTER,
    BoosterId.SAMURAI_TOKEN: CollectableKind.SAMURAI_BOOSTER,
    BoosterId.ALLIANCE_COIN: CollectableKind.ALLIANCE_COIN_BOOSTER,
    BoosterId.LONG_TERM_POINT_EVENT: CollectableKind.LONG_TERM_POINT_EVENT_BOOSTER,
    BoosterId.REPUTATION_POINT: CollectableKind.REPUTATION_BOOSTER,
    BoosterId.GALLANTRY_POINTS: CollectableKind.GALLANTRY_BOOSTER,
    BoosterId.RAGE_POINT: CollectableKind.RAGE_POINT_BOOSTER,
    BoosterId.KHAN_MEDAL: CollectableKind.KHAN_MEDAL_POINT_BOOSTER,
}
"""The booster ids the client reads as a kind of their own.

Client: the booster switch of ``CollectableHelper.getTypeByServerKey`` (bundle lines 1606-1626)
"""

_BOOSTER_FAMILY = frozenset({CollectableKind.BOOSTER, *_BOOSTER_KINDS.values()})

_HERO_RARENESSES = frozenset({Rareness.HERO_COMMON, Rareness.HERO_RARE, Rareness.HERO_EPIC, Rareness.HERO_LEGENDARY})

_OLD_GOODS_ORDER: tuple[CollectableKind | int, ...] = (
    CollectableKind.WOOD,
    CollectableKind.STONE,
    CollectableKind.FOOD,
    CollectableKind.COINS,
    CollectableKind.RUBIES,
    CollectableKind.COAL,
    CollectableKind.OIL,
    CollectableKind.GLASS,
    1,
    2,
    3,
    CollectableKind.AQUAMARINE,
    CollectableKind.IRON,
    4,
    5,
    6,
    7,
    9,
    23,
)
"""What each place of an old-style goods list holds: a kind, or a currency id.

Client: ``CollectableParserS2COldGoods.OLD_STYLE_GOODS_ORDER`` (bundle line 62793), ``ClientConstCurrency.ID_*``
(bundle line 1920)
"""


def _is_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _number(value: Any) -> int | float | None:
    return None if isinstance(value, bool) else js_number_or_none(value)


def _at(entry: Any, index: int) -> Any:
    return entry[index] if isinstance(entry, list | tuple) and len(entry) > index else None


def _currency(key: str) -> Any:
    from .ids import Currency

    return Currency._value2member_map_.get(key)


def _currency_of_id(currency_id: int) -> Any:
    from .ids import Currency, CurrencyId

    member = known(CurrencyId, currency_id)
    return Currency(member.json_key) if isinstance(member, CurrencyId) else currency_id


def _unit(entry: Any) -> dict[str, Any]:
    from .ids import Tool, Unit

    return {"item": known((Unit, Tool), js_int(_at(entry, 0))), "amount": _at(entry, 1)}


def _building(entry: Any) -> dict[str, Any]:
    from .ids import Building

    if isinstance(entry, list | tuple):
        return {"item": known(Building, js_int(_at(entry, 0))), "amount": js_int(_at(entry, 1))}
    return {"item": known(Building, js_int(entry))}


def _construction_item(entry: Any) -> dict[str, Any]:
    from .ids import ConstructionItem

    return {"item": known(ConstructionItem, js_int(entry))}


def _loot_box(entry: Any) -> dict[str, Any]:
    from .ids import LootBox

    if isinstance(entry, list | tuple):
        return {"item": known(LootBox, js_int(_at(entry, 0))), "amount": _at(entry, 1)}
    return {"item": known(LootBox, js_int(entry)), "amount": 1}


def _booster(entry: Any) -> dict[str, Any]:
    if isinstance(entry, dict):
        booster = entry.get("ID")
        return {
            "item": known(BoosterId, booster) if _is_id(booster) else None,
            "duration_seconds": _number(entry.get("D")),
            "value": None if "ID" in entry else entry,
        }
    return {"duration_seconds": _number(_at(entry, 1)), "value": entry}


def _gem(entry: Any) -> dict[str, Any]:
    from .ids import Gem

    return {"item": known(Gem, js_int(entry))}


def _crest_layout(layout_id: Any) -> Any:
    from .ids import AllianceCrestLayout

    return known(AllianceCrestLayout, js_int(layout_id))


def _rareness(entry: Any) -> dict[str, Any]:
    if _is_id(entry):
        return {"item": known(Rareness, entry)}
    return {"value": entry}


def _amount(entry: Any) -> dict[str, Any]:
    return {"amount": entry}


def _currency_amount(entry: Any) -> dict[str, Any]:
    return {"amount": _at(entry, 1) if isinstance(entry, list | tuple) and len(entry) >= 2 else entry}


def _id(entry: Any) -> dict[str, Any]:
    return {"item": js_int(entry)}


def _id_and_amount(entry: Any) -> dict[str, Any]:
    return {"item": js_int(_at(entry, 0)), "amount": _at(entry, 1)}


def _opaque(entry: Any) -> dict[str, Any]:
    return {"value": entry}


_GOODS = (
    CollectableKind.WOOD,
    CollectableKind.STONE,
    CollectableKind.FOOD,
    CollectableKind.COAL,
    CollectableKind.OIL,
    CollectableKind.GLASS,
    CollectableKind.IRON,
    CollectableKind.AQUAMARINE,
    CollectableKind.MEAD,
    CollectableKind.BEEF,
    CollectableKind.HONEY,
    CollectableKind.COINS,
    CollectableKind.RUBIES,
)

_READERS: dict[CollectableKind, Callable[[Any], dict[str, Any]]] = {
    **dict.fromkeys(_GOODS, _amount),
    **dict.fromkeys(_BOOSTER_FAMILY, _booster),
    CollectableKind.CURRENCY: _currency_amount,
    CollectableKind.UNITS: _unit,
    CollectableKind.BUILDING: _building,
    CollectableKind.CONSTRUCTION_ITEM: _construction_item,
    CollectableKind.LOOT_BOX: _loot_box,
    CollectableKind.EQUIPMENT_RARENESS: _rareness,
    CollectableKind.HERO_RANDOM: _rareness,
    CollectableKind.GEM: _gem,
    CollectableKind.GEM_RANDOM: lambda entry: {"item": -js_int(entry)},
    CollectableKind.EQUIPMENT_UNIQUE: _id,
    CollectableKind.EQUIPMENT_UNIQUE_ENCHANTED: lambda entry: {"item": js_int(_at(entry, 0)), "value": entry},
    CollectableKind.CREST_SYMBOL: _id,
    CollectableKind.GIFT_PACKAGE: _id_and_amount,
    CollectableKind.MATERIAL_BAG: _id_and_amount,
    CollectableKind.PLAGUE_DOCTORS: _amount,
    CollectableKind.VIP_POINTS: _amount,
    CollectableKind.ACHIEVEMENT_POINTS: _amount,
    CollectableKind.PAYMENT_DOUBLER: _amount,
    CollectableKind.XP: lambda entry: {"amount": _at(entry, 0)},
    CollectableKind.RESOURCE_POINTS: lambda entry: {"amount": _at(entry, 1)},
    CollectableKind.VIP_TIME: lambda entry: {"duration_seconds": _number(entry)},
    CollectableKind.ALLIANCE_CREST_LAYOUT: lambda entry: {
        "item": _crest_layout(entry.get("ACLI")) if isinstance(entry, dict) else None,
        "duration_seconds": _number(entry.get("D")) if isinstance(entry, dict) else None,
    },
}
"""How each kind reads its entry, as its item class's ``parseServerObject`` does; any other kind keeps the entry.

Client: ``ACollectableItemGoodsVO`` (bundle line 40505), ``CollectableItemGenericCurrencyVO`` (5260),
``CollectableItemUnitVO`` (15479), ``CollectableItemBuildingVO`` (10641), ``CollectableItemConstructionItemVO``
(12257), ``ACollectableItemLootBoxVO`` (52235), ``CollectableItemBoosterVO`` (88250),
``ACollectableItemPercentageBoosterVO`` (11931), ``CollectableItemEquipmentRarenessVO`` (25148),
``CollectableItemGemVO`` (34930), ``CollectableItemGemRandomVO`` (40614), ``CollectableItemEquipmentUniqueVO``
(52111), ``CollectableItemEquipmentUniqueEnchantedVO`` (37046), ``CollectableItemCrestSymbolVO`` (88757),
``CollectableItemGiftPackageVO`` (89065), ``CollectableItemMaterialBagVO`` (88909), ``CollectableItemXpVO``
(40650), ``CollectableItemResourcePointVO`` (88714), ``CollectableItemVipTimeVO`` (45720),
``CollectableItemAllianceCrestLayoutVO`` (89334)
"""

_KINDS_BY_XML_KEY: dict[str, CollectableKind] = {
    variant: kind
    for kind in CollectableKind
    for xml_key in kind.xml_keys
    for variant in (xml_key, xml_key.lower(), xml_key[:1].upper() + xml_key[1:])
}
"""Each kind by the items column it comes under, with the variants ``addObjectToDic`` registers.

Client: ``CollectableEnum.getTypeByXmlKey`` (bundle line 401)
"""

_XML_ADD_PREFIX = "add"
"""``ClientConstCollectable.XML_PREFIX_ADD`` (bundle line 3074): ``add<kind or currency name>`` columns."""

_XML_COST_PREFIX = "cost"
"""``ClientConstCollectable.XML_PREFIX_COST`` (bundle line 3074): ``cost<kind or currency name>`` columns."""


def _parts(text: str) -> list[int]:
    return [js_int(part) for part in text.split("+")]


def _xml_item_and_amount(enum: Any) -> Callable[[str], dict[str, Any]]:
    def read(text: str) -> dict[str, Any]:
        parts = _parts(text)
        return {"item": known(enum(), parts[0]), "amount": _at(parts, 1)}

    return read


def _ids() -> Any:
    from . import ids

    return ids


_XML_READERS: dict[CollectableKind, Callable[[str], dict[str, Any]]] = {
    CollectableKind.RELIC_EQUIPMENT: lambda text: {"value": text},
    CollectableKind.BUILDING: lambda text: {"item": known(_ids().Building, js_int(text))},
    CollectableKind.CONSTRUCTION_ITEM: _xml_item_and_amount(lambda: _ids().ConstructionItem),
    CollectableKind.UNITS: _xml_item_and_amount(lambda: (_ids().Unit, _ids().Tool)),
    CollectableKind.LOOT_BOX: _xml_item_and_amount(lambda: _ids().LootBox),
    CollectableKind.EQUIPMENT_RARENESS: lambda text: _rareness(js_int(text)),
    CollectableKind.GEM: _gem,
    CollectableKind.GEM_RANDOM: lambda text: {"item": -js_int(text)},
    CollectableKind.EQUIPMENT_UNIQUE: lambda text: {"item": js_int(text)},
    CollectableKind.EQUIPMENT_UNIQUE_ENCHANTED: lambda text: {"item": _parts(text)[0], "value": text},
    CollectableKind.CREST_SYMBOL: lambda text: {"item": js_int(text)},
    CollectableKind.ALIEN_PROTECTION: lambda text: {"item": js_int(text)},
    CollectableKind.VIP_TIME: lambda text: {"duration_seconds": _number(text)},
    CollectableKind.BOOSTER: lambda text: {
        "item": known(BoosterId, _parts(text)[0]),
        "duration_seconds": _at(_parts(text), 1),
    },
    CollectableKind.LONG_TERM_POINT_EVENT_BOOSTER: lambda text: {
        "duration_seconds": _at(_parts(text), 1),
        "value": text,
    },
    CollectableKind.REPUTATION_BOOSTER: lambda text: {"duration_seconds": _at(_parts(text), 1), "value": text},
    CollectableKind.ALLIANCE_GIFT: lambda text: {"value": text.split("+")[0]},
    CollectableKind.MATERIAL_BAG: lambda text: {
        "item": js_parse_int(text.split("+")[0]),
        "amount": js_parse_int(_at(text.split("+"), 1)),
    },
    CollectableKind.GIFT_PACKAGE: lambda text: {"item": _parts(text)[0], "amount": _at(_parts(text), 1)},
    CollectableKind.ALLIANCE_CREST_LAYOUT: lambda text: {
        "item": _crest_layout(_parts(text)[0]),
        "duration_seconds": _at(_parts(text), 1),
    },
}
"""How each kind reads one ``#``-separated part of its items column, as its item class's ``parseXmlObject``
does; any other kind reads the part as its amount (``ACollectableItemVO.parseXmlObject``, bundle line 3557).

Client: ``CollectableItemRelicVO`` (bundle line 10481), ``CollectableItemBuildingVO`` (10642),
``CollectableItemConstructionItemVO`` (12258), ``CollectableItemUnitVO`` (15480), ``ACollectableItemLootBoxVO``
(52238), ``CollectableItemEquipmentRarenessVO`` (25151), ``CollectableItemGemVO`` (34931),
``CollectableItemGemRandomVO`` (40615), ``CollectableItemEquipmentUniqueVO`` (52113),
``CollectableItemEquipmentUniqueEnchantedVO`` (37047), ``CollectableItemCrestSymbolVO`` (88758),
``CollectableItemAlienProtectionVO`` (88656), ``CollectableItemVipTimeVO`` (45721), ``CollectableItemBoosterVO``
(88251), ``CollectableItemLongTermPointEventBoosterVO`` (88457), ``CollectableItemReputationBoosterVO`` (88480),
``CollectableItemAllianceGiftVO`` (88808), ``CollectableItemMaterialBagVO`` (88910),
``CollectableItemGiftPackageVO`` (89066), ``CollectableItemAllianceCrestLayoutVO`` (89335)
"""

_NEVER_MERGED = frozenset(
    {
        *_BOOSTER_FAMILY,
        CollectableKind.RELIC_EQUIPMENT,
        CollectableKind.EQUIPMENT_RARENESS,
        CollectableKind.HERO_RANDOM,
        CollectableKind.EQUIPMENT_UNIQUE,
        CollectableKind.EQUIPMENT_UNIQUE_ENCHANTED,
        CollectableKind.GEM,
        CollectableKind.GEM_RANDOM,
        CollectableKind.CONSTRUCTION_ITEM_BLUEPRINT,
        CollectableKind.SKIP_DISCOUNT,
        CollectableKind.EXTINGUISH_FIRE,
        CollectableKind.ALIEN_PROTECTION,
        CollectableKind.CREST_SYMBOL,
        CollectableKind.ALLIANCE_GIFT,
        CollectableKind.PERMANENT_UNIT_SLOT,
        CollectableKind.PERMANENT_TOOL_SLOT,
        CollectableKind.GIFT_PACKAGE,
        CollectableKind.OTHER,
    }
)
"""The kinds the client never adds up: their item classes' ``isCombineAbleWith`` is false (bundle lines 10512,
11934, 17778, 21218, 49268, 88255, 88595, 88635, 88660, 88762, 88814, 88840, 88861, 89073). ``OTHER`` has no
item class at all.
"""

_MERGED_BY_ITEM = frozenset(
    {
        CollectableKind.CURRENCY,
        CollectableKind.UNITS,
        CollectableKind.BUILDING,
        CollectableKind.CONSTRUCTION_ITEM,
        CollectableKind.MATERIAL_BAG,
        CollectableKind.ALLIANCE_CREST_LAYOUT,
    }
)
"""The kinds the client adds up only for one item: the overrides comparing ids (bundle lines 5271, 10648, 12267,
15487, 88920, 89340). Every other kind adds up by kind alone (``ACollectableItemVO.isCombineAbleWith``, bundle
line 3569), loot boxes included: ``ACollectableItemLootBoxVO`` keeps that default, so two different boxes add up
into the first one's box.
"""

_MERGED_DURATIONS = frozenset(
    {CollectableKind.VIP_TIME, CollectableKind.DUNGEON_PROTECTION, CollectableKind.ALLIANCE_CREST_LAYOUT}
)
"""The kinds whose ``combineWith`` adds the durations, not the amounts (bundle lines 45722, 37087, 89342)."""


def is_reward_column(column: str) -> bool:
    """Whether a ``rewards`` row column holds a collectable: a kind's items column or an ``add`` column."""
    return column in _KINDS_BY_XML_KEY or column.startswith(_XML_ADD_PREFIX)


class Collectable(BaseModel):
    """
    One collectable: a reward, a cost or a lot of goods, typed by its kind.

    ``item`` is what the entry names, for the kinds that name one: the unit or tool for
    ``UNITS``, the ``Currency`` for ``CURRENCY``, the ``BoosterId`` for a booster, the loot box,
    building, construction item, gem or crest layout, the rareness of a random equipment, or the
    id of an equipment, crest symbol, gift package or material bag, which no enum names.
    ``amount`` is how many; an entry that names an item without a count is 1.

    Client: ``CollectableHelper.getTypeByServerKey`` and ``createVO`` (bundle lines 1603-1629),
    then the item class's ``parseServerObject``
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    kind: CollectableKind = Field(description="What it is")
    key: str = Field(
        description="The server key it came under, as sent (for a game-data reward, its kind's or currency's); "
        "the only name an OTHER entry has"
    )
    amount: int | float = Field(default=1, description="How many")
    item: CollectableItem | None = Field(
        default=None, description="What the entry names; None for a kind that names nothing"
    )
    duration_seconds: int | float | None = Field(
        default=None, description="How long it lasts, for a booster, VIP time or crest layout; None otherwise"
    )
    value: Any = Field(
        default=None,
        description="The entry as sent, for an OTHER entry and a kind whose layout is not read here "
        "(relics, equipment sent whole, alliance gifts); None otherwise",
    )

    @classmethod
    def from_entry(cls, key: str, entry: Any, amount: Any = None) -> Collectable:
        """
        One entry under its server key; ``amount`` is the third place of a row, where it has one.

        Client: ``CollectableParserS2CParamList.createByParamListMethod`` (bundle line 40569),
        ``LostAndFoundListItemVO.parseData`` (bundle line 144545)
        """
        kind, item = cls._kind(key, entry)
        return cls._read(kind, key, item, _READERS.get(kind, _opaque)(entry), amount)

    @classmethod
    def _read(cls, kind: CollectableKind, key: str, item: Any, read: dict[str, Any], amount: Any = None) -> Collectable:
        values: dict[str, Any] = {"kind": kind, "key": key, "item": item}
        if js_truthy(amount) and (count := _number(amount)) is not None:
            values["amount"] = count
        if item is not None:
            read.pop("item", None)
        if "amount" in read:
            count = _number(read.pop("amount"))
            if count is not None:
                values["amount"] = count
        values.update({name: field for name, field in read.items() if field is not None})
        return cls(**values)

    @staticmethod
    def _kind(key: str, entry: Any) -> tuple[CollectableKind, Any]:
        """The kind a key names, and the item the key alone decides (a currency); the client's type lookup."""
        if key == MINUTE_SKIP_KEY:
            first = _at(entry, 0)
            digit = js_int(first[-1]) if isinstance(first, str) and first else None
            return CollectableKind.CURRENCY, None if digit is None else _currency_of_id(MINUTE_SKIP_FIRST_ID + digit)
        kind = _KINDS_BY_KEY.get(key, CollectableKind.OTHER)
        booster = entry.get("ID") if isinstance(entry, dict) else None
        if kind is CollectableKind.BOOSTER and isinstance(booster, int) and booster not in _PRIME_SALE_BOOSTERS:
            kind = _BOOSTER_KINDS.get(booster, kind)
        if kind is CollectableKind.EQUIPMENT_RARENESS and _is_id(entry) and entry in _HERO_RARENESSES:
            kind = CollectableKind.HERO_RANDOM
        if kind is CollectableKind.OTHER and (currency := _currency(key)) is not None:
            return CollectableKind.CURRENCY, currency
        return kind, None

    @classmethod
    def from_object(cls, value: Any) -> tuple[Collectable, ...]:
        """
        A reward object ``{key: [entry, ...], "SO": sort order}`` as its collectables, in the order sent.

        A key whose value is no list is skipped, as the client skips a null one; ``SO`` only sorts the display.

        Client: ``CollectableParserS2CParamObject.createList`` and ``parseSortOrder`` (bundle lines 62810-62818)
        """
        if not isinstance(value, dict):
            return ()
        return tuple(
            cls.from_entry(key, entry)
            for key, entries in value.items()
            if key != "SO" and isinstance(entries, list | tuple)
            for entry in entries
        )

    @classmethod
    def from_rows(cls, value: Any) -> tuple[Collectable, ...]:
        """
        Collectable rows ``[[key, entry, amount?], ...]``, a list of such lists, or an old-style goods list.

        An old-style list holds amounts in a fixed order of goods and currencies, a 0 for none.

        Client: ``CollectableParserS2CParamList.createList`` and ``createByParamListMethod`` (bundle lines
        40560-40573), ``CollectableParserS2COldGoods.createByParamListOldGoods`` (bundle line 62797)
        """
        if not isinstance(value, list | tuple) or not value:
            return ()
        if isinstance(value[0], int | float) and not isinstance(value[0], bool):
            return cls._old_goods(value)
        if isinstance(value[0], list | tuple) and value[0] and isinstance(value[0][0], list | tuple):
            value = [row for rows in value if isinstance(rows, list | tuple) for row in rows]
        return tuple(
            cls.from_entry(row[0], _at(row, 1), _at(row, 2))
            for row in value
            if isinstance(row, list | tuple) and row and isinstance(row[0], str)
        )

    @classmethod
    def _old_goods(cls, amounts: Any) -> tuple[Collectable, ...]:
        found = []
        for place, amount in zip(_OLD_GOODS_ORDER, amounts, strict=False):
            count = js_int(amount)
            if count == 0:
                continue
            if isinstance(place, CollectableKind):
                found.append(cls(kind=place, key=place.server_key, amount=count))
            else:
                found.append(cls.of_currency(place, count))
        return tuple(found)

    @classmethod
    def of_currency(cls, currency_id: int, amount: int | float = 1) -> Collectable:
        """
        A currency named by its ``currencyID``, under its server key (the id itself where the key is unknown).

        Client: ``CollectableItemGenericCurrencyVO`` (bundle line 5258) takes the id and amount
        """
        currency = _currency_of_id(currency_id)
        key = str(currency_id) if isinstance(currency, int) else currency.value
        return cls(kind=CollectableKind.CURRENCY, key=key, amount=amount, item=currency)

    @classmethod
    def from_reward_row(cls, row: Mapping[str, Any], currency_ids: Mapping[str, int]) -> tuple[Collectable, ...]:
        """
        What one ``rewards`` row of the items gives, in the client's order.

        Each column of a kind holds ``#``-separated parts, read as the kind's item class reads them;
        then each ``add<name>`` column adds one more, of the kind ``name`` names or else the currency
        whose ``Name`` it is (``currency_ids``, by name); duplicates the client adds up are added up.
        An ``add`` column naming neither is kept as ``OTHER``, where the client drops it. A random
        equipment of a hero rareness reads as ``HERO_RANDOM``, as a packet's does. The columns no
        parser reads (``comment1``, ``hiddenFood``, ``ignore*`` and the like) give nothing.

        Client: ``CollectableParserX2CRewards.createList`` (bundle line 62897) and
        ``CollectableParserX2CList.createList`` (bundle line 62874) with
        ``CurrencyData.getXmlCurrencyByName`` (bundle line 141193)
        """
        found = [
            cls._from_xml(kind, part)
            for column, text in row.items()
            if (kind := _KINDS_BY_XML_KEY.get(column)) is not None
            for part in str(text).split("#")
        ]
        return cls.merged([*found, *cls.from_columns(row, _XML_ADD_PREFIX, currency_ids)])

    @classmethod
    def from_columns(
        cls, row: Mapping[str, Any], prefix: str, currency_ids: Mapping[str, int]
    ) -> tuple[Collectable, ...]:
        """
        One collectable per ``<prefix><name>`` column of an items row, in the row's order: a research's
        ``cost`` columns, a reward's ``add`` columns.

        ``name`` is a kind's items key (``C2``, ``Wood``) or else the ``Name`` of a currency
        (``LegendaryToken``, by ``currency_ids``). A column naming neither is kept as ``OTHER``, where
        the client drops it.

        Client: ``CollectableParserX2CList.createList`` (bundle lines 62874-62881) with
        ``CurrencyData.getXmlCurrencyByName`` (bundle line 141193)
        """
        found = []
        for column, text in row.items():
            if not column.startswith(prefix):
                continue
            name = column[len(prefix) :]
            if (kind := _KINDS_BY_XML_KEY.get(name)) is not None:
                found.append(cls._from_xml(kind, str(text)))
            elif (currency_id := currency_ids.get(name)) is not None:
                found.append(cls.of_currency(currency_id, js_parse_int_or_zero(text)))
            else:
                found.append(cls(kind=CollectableKind.OTHER, key=column, value=text))
        return tuple(found)

    @staticmethod
    def merged(collectables: Iterable[Collectable]) -> tuple[Collectable, ...]:
        """
        The collectables with the duplicates the client adds up added up, each into the first it adds up with.

        Most kinds add up by kind; currencies, units, buildings, construction items, material bags
        and crest layouts only for the same item; boosters, equipment, gems, relics and the other
        one-off kinds never. VIP time, dungeon protection and crest layouts add their durations, the
        others their amounts. Two different loot boxes add up into the first one's box, as in the
        client. The client also requires the same grant type, which a collectable does not carry:
        the collectables of one reward share theirs, so merge only collectables of one grant type.

        Client: ``CollectableList.combineDuplicatedItems`` (bundle line 1887), ``isCombineAbleWith`` and
        ``combineWith`` of ``ACollectableItemVO`` (bundle lines 3569, 3558) and its overrides
        """
        merged: list[Collectable] = []
        for collectable in collectables:
            same = next(
                (index for index, kept in enumerate(merged) if kept._adds_up_with(collectable)),
                None,
            )
            if same is None:
                merged.append(collectable)
            else:
                merged[same] = merged[same]._added(collectable)
        return tuple(merged)

    def _adds_up_with(self, other: Collectable) -> bool:
        if self.kind is not other.kind or self.kind in _NEVER_MERGED:
            return False
        return self.kind not in _MERGED_BY_ITEM or self.item == other.item

    def _added(self, other: Collectable) -> Collectable:
        if self.kind in _MERGED_DURATIONS:
            if self.duration_seconds is None and other.duration_seconds is None:
                return self
            duration = (self.duration_seconds or 0) + (other.duration_seconds or 0)
            return self.model_copy(update={"duration_seconds": duration})
        return self.model_copy(update={"amount": self.amount + other.amount})

    @classmethod
    def _from_xml(cls, kind: CollectableKind, text: str) -> Collectable:
        read = _XML_READERS.get(kind, lambda part: {"amount": js_int(part)})(text)
        if kind is CollectableKind.EQUIPMENT_RARENESS and read.get("item") in _HERO_RARENESSES:
            kind = CollectableKind.HERO_RANDOM
        return cls._read(kind, kind.server_key, None, read)

    @property
    def send_key(self) -> str:
        """
        The key the client sends for this collectable, as when the login bonus reward is picked.

        A currency goes as its own key, anything else as its kind's key: a booster with a kind of
        its own as that kind's (``PG``, ``XPB``, ...), a hero random equipment as ``RE``.

        Raises:
            ValueError: An OTHER entry, which the client never offers, or a currency whose key is unknown

        Client: ``CollectableHelper.getServerKeyByCollectable`` (bundle line 1646)
        """
        if self.kind is CollectableKind.CURRENCY:
            if isinstance(self.item, Enum):
                return str(self.item.value)
            if isinstance(self.item, str):
                return self.item
            raise ValueError(f"the currency of {self.key!r} has no key this library knows")
        if self.kind is CollectableKind.OTHER:
            raise ValueError(f"{self.key!r} names no collectable the client knows, so it is never sent")
        return self.kind.server_key


def _collectables(read: Callable[[Any], tuple[Collectable, ...]]) -> Callable[[Any], Any]:
    def validate(value: Any) -> Any:
        if isinstance(value, list | tuple) and all(isinstance(item, Collectable) for item in value):
            return tuple(value)
        return read(value)

    return validate


CollectableRows = Annotated[tuple[Collectable, ...], BeforeValidator(_collectables(Collectable.from_rows))]
"""A model field read from collectable rows, ``[[key, entry, amount?], ...]`` (see :meth:`Collectable.from_rows`)."""

CollectableObject = Annotated[tuple[Collectable, ...], BeforeValidator(_collectables(Collectable.from_object))]
"""A model field read from a reward object, ``{key: [entry, ...]}`` (see :meth:`Collectable.from_object`)."""


def _currency_id_rows(value: Any) -> Any:
    """``[[currency_id, amount], ...]`` as currency collectables, in order, each amount as sent."""
    if not isinstance(value, list | tuple) or all(isinstance(item, Collectable) for item in value):
        return value
    return tuple(
        Collectable.of_currency(js_int(row[0]), count)
        for row in value
        if isinstance(row, list | tuple) and len(row) >= 2 and (count := _number(row[1])) is not None
    )


CurrencyIdRows = Annotated[tuple[Collectable, ...], BeforeValidator(_currency_id_rows)]
"""A model field read from ``[[currency_id, amount], ...]`` rows, one currency collectable per row, as sent.

Unlike :data:`CurrencyAmounts`, rows are not added up and an amount keeps its sign.

Client: ``CollectableItemGenericCurrencyVO(e[0], e[1])`` per row (bundle line 138308)
"""


def _currency_rows(value: Any) -> Any:
    """``[[currency_id, amount], ...]`` as ``{currency_id: amount}``; a mapping is taken as it is."""
    if isinstance(value, Mapping) or not isinstance(value, list | tuple):
        return value
    totals: dict[int, int] = {}
    for row in value:
        if isinstance(row, list | tuple) and row:
            currency_id = js_int(row[0])
            totals[currency_id] = totals.get(currency_id, 0) + js_int(row[1] if len(row) > 1 else None)
    return totals


def _rows_of(amounts: dict[CurrencyId | int, int]) -> list[list[int]]:
    return [[currency_id, amount] for currency_id, amount in amounts.items()]


CurrencyAmounts = Annotated[
    dict[EnumOrInt["CurrencyId"], int], BeforeValidator(_currency_rows), PlainSerializer(_rows_of)
]
"""Currencies by id and amount, sent as ``[[currency_id, amount], ...]`` in insertion order.

Unlike :data:`CollectableRows`, the rows name the currency by its ``currencyID``, not a server key.

Client: ``CastleFightScreenVO.addCollectorBooster`` (bundle line 30584) pushes ``[currency_id, amount]``
"""


__all__ = [
    "MINUTE_SKIP_FIRST_ID",
    "CurrencyAmounts",
    "CurrencyIdRows",
    "Collectable",
    "CollectableItem",
    "CollectableObject",
    "CollectableRows",
]
