"""
Typed rows of the castle and world tables: kingdoms, their villages and slums, castle expansions, resources, mine
types, landmarks, the ruby wishing well, the fusion forge's catalysts, cost sequences, minute skips and shops, and
the officers' school's currencies and unit pairs.

Each model reads the columns its client value object reads, with the same defaults: a column the client reads as
``parseInt(value || "")`` is None where the client has NaN.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NewType

from pydantic import Field, ValidationInfo, field_validator, model_validator

from empire_core.enums import CollectableKind, Kingdom
from empire_core.protocol.js import js_falsy, js_int, js_parse_int, js_truthy

from .collectables import _KINDS_BY_KEY, _KINDS_BY_XML_KEY, _XML_COST_PREFIX, Collectable
from .lenient import GameDataId
from .models import _landmark_int, _parse_int_or_default, _Row
from .tables import PackageId, PartPayPriceId, _client_bool, _int_list, _text, row_id

if TYPE_CHECKING:
    from .ids import Building, CurrencyId, FusionForgeId, PrebuiltCastle, SceatSkill, TreasureMapId, Unit

ExpansionId = NewType("ExpansionId", int)
"""The id of an ``expansions`` row, a castle expansion's price that :attr:`GameData.expansions` describes."""

ResourceId = NewType("ResourceId", int)
"""The id of a ``resources`` row, a resource that :attr:`GameData.resources` names."""

MineTypeId = NewType("MineTypeId", int)
"""The id of a ``mineTypes`` row, a mine's yield that :attr:`GameData.mine_types` describes."""

LandmarkId = NewType("LandmarkId", int)
"""The id of a ``landmarks`` row, a landmark's conquer levels that :attr:`GameData.landmarks` describes."""

WishingWellId = NewType("WishingWellId", int)
"""The ``wodID`` of a ``wishingwells`` row, one level of the ruby wishing well."""

ForgeMinuteSkipId = NewType("ForgeMinuteSkipId", int)
"""The id of a ``forgeMinuteSkips`` row, a minute skip a fusion forge takes."""

FusionCostSequenceId = NewType("FusionCostSequenceId", int)
"""The id of a ``fusionCostSequences`` row, one step of a fusion forge's goods cost cycle."""

FusionShopId = NewType("FusionShopId", int)
"""The id of a ``fusionShops`` row, the packages one of the fusion forge's shops sells."""

OfficersSchoolCurrencyId = NewType("OfficersSchoolCurrencyId", int)
"""The id of an ``officersSchoolCurrencies`` row, a currency the officers' school takes."""

OfficersSchoolUnitPairId = NewType("OfficersSchoolUnitPairId", int)
"""The id of an ``officersSchoolUnitPairs`` row, a pair of units an officers' school level unlocks."""


def _nan_int(value: object) -> int | None:
    """``parseInt(value || "")``: None where the client reads NaN."""
    return _landmark_int(value, "")


def _int_attribute(value: object, default: int) -> int:
    """``int(CastleXMLUtils.getIntAttribute(key, row, default))`` (split.js lines 5862, 5839): NaN reads as 0."""
    parsed = js_parse_int(str(default) if js_falsy(value) else value)
    return 0 if parsed is None else parsed


def _plus_ids(value: object) -> list[int]:
    """The ``+``-joined ids of a column, ``parseInt`` of each; a part the client reads as NaN is left out."""
    return _int_list(value, separator="+")


class KingdomDef(_Row):
    """
    A kingdom: when it unlocks, its travel times and taxes, and how many villages of each kind you can hold in it.

    Client: ``CastleKingdomVO.fillFromParamXML`` (split.js line 671468), keyed by ``kID`` in ``CastleKingdomData``
    (split.js line 670877); the village caps read by ``PrivateResourceVillageShopDialog`` (split.js line 257578)
    """

    kingdom_id: GameDataId[Kingdom] = Field(validation_alias="kID", description="The kingdom")
    name: str = Field(validation_alias="kingdomName", default="", description="The kingdom's internal name")
    unit_travel_seconds: int | None = Field(
        validation_alias="unitTravelTime", default=None, description="Seconds units travel to it; None if unread"
    )
    goods_travel_seconds: int | None = Field(
        validation_alias="resourceTravelTime", default=None, description="Seconds goods travel to it; None if unread"
    )
    min_level: int = Field(validation_alias="minLevel", default=0, description="Player level it unlocks at")
    min_premium_unlock_level: int = Field(
        validation_alias="minC2Level", default=0, description="Player level it can be unlocked at with rubies"
    )
    max_villages: int | None = Field(
        validation_alias="numMaxVillages", default=None, description="The kingdom's village limit; None if unread"
    )
    skip_unit_travel_rubies: int | None = Field(
        validation_alias="skipUnitTravelC2Cost",
        default=None,
        description="Rubies that finish a unit transfer to it; None if unread",
    )
    skip_goods_travel_rubies: int | None = Field(
        validation_alias="skipResourceTravelC2Cost",
        default=None,
        description="Rubies that finish a goods transfer to it; None if unread",
    )
    unit_travel_tax_percent: int | None = Field(
        validation_alias="unitTravelTaxRate", default=None, description="Percent tax on units sent to it"
    )
    goods_travel_tax_percent: int | None = Field(
        validation_alias="resourceTravelTaxRate", default=None, description="Percent tax on goods sent to it"
    )
    beginner_protection_seconds: int | None = Field(
        validation_alias="noobProtectionTime",
        default=None,
        description="Seconds a new castle in it is protected; None if unread",
    )
    required_kingdom_id: GameDataId[Kingdom] | None = Field(
        validation_alias="requiredKingdomID",
        default=None,
        description="The kingdom to unlock first; -1 for none, None if unread",
    )
    village_cap_wood: int | None = Field(
        validation_alias="villageCapWood", default=None, description="Wood villages you can hold in it"
    )
    village_cap_food: int | None = Field(
        validation_alias="villageCapFood", default=None, description="Food villages you can hold in it"
    )
    village_cap_stone: int | None = Field(
        validation_alias="villageCapStone", default=None, description="Stone villages you can hold in it"
    )
    village_cap_coal: int = Field(
        validation_alias="villageCapCoal", default=0, description="Coal villages you can hold in it"
    )
    village_cap_oil: int = Field(
        validation_alias="villageCapOil", default=0, description="Olive oil villages you can hold in it"
    )
    village_cap_glass: int = Field(
        validation_alias="villageCapGlass", default=0, description="Glass villages you can hold in it"
    )
    village_cap_iron: int = Field(
        validation_alias="villageCapIron", default=0, description="Iron villages you can hold in it"
    )

    @field_validator("kingdom_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator("name", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)

    @field_validator(
        "unit_travel_seconds", "goods_travel_seconds", "max_villages", "skip_unit_travel_rubies",
        "skip_goods_travel_rubies", "unit_travel_tax_percent", "goods_travel_tax_percent",
        "beginner_protection_seconds", "required_kingdom_id", "village_cap_wood", "village_cap_food",
        "village_cap_stone",
        mode="before",
    )  # fmt: skip
    @classmethod
    def _nan_column(cls, value: object) -> int | None:
        return _nan_int(value)

    @field_validator(
        "min_level", "min_premium_unlock_level", "village_cap_coal", "village_cap_oil", "village_cap_glass",
        "village_cap_iron",
        mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)


class KingdomVillagesDef(_Row):
    """
    What the villages of a kingdom are built of, and the production boost each kind gives.

    Client: ``KingdomVillagesInfoVO.fillFromParamXML`` (split.js line 671985), set on its kingdom in
    ``CastleKingdomData`` (split.js line 670877); the boosts read by village type at split.js line 119405
    """

    kingdom_id: GameDataId[Kingdom] = Field(validation_alias="kID", description="The kingdom")
    wall_id: GameDataId["Building"] | None = Field(
        validation_alias="wallWodId", default=None, description="The villages' wall; None if unread"
    )
    gate_id: GameDataId["Building"] | None = Field(
        validation_alias="gateWodId", default=None, description="The villages' gate; None if unread"
    )
    keep_id: GameDataId["Building"] | None = Field(
        validation_alias="keepWodId", default=None, description="The villages' keep; None if unread"
    )
    moat_id: GameDataId["Building"] | None = Field(
        validation_alias="moatWodId", default=None, description="The villages' moat; -1 for none, None if unread"
    )
    wall_unit_count: int | None = Field(
        validation_alias="unitWallCount", default=None, description="The unitWallCount column; None if unread"
    )
    peasants: int | None = Field(default=None, description="The peasants column; None if unread")
    guards: int | None = Field(default=None, description="The guards column; None if unread")
    wood_boost: int | None = Field(
        validation_alias="productivityWoodBoost", default=None, description="Production boost a wood village gives"
    )
    stone_boost: int | None = Field(
        validation_alias="productivityStoneBoost", default=None, description="Production boost a stone village gives"
    )
    food_boost: int | None = Field(
        validation_alias="productivityFoodBoost", default=None, description="Production boost a food village gives"
    )
    coal_boost: int = Field(
        validation_alias="productivityCoalBoost", default=0, description="Production boost a coal village gives"
    )
    oil_boost: int = Field(
        validation_alias="productivityOilBoost", default=0, description="Production boost an olive oil village gives"
    )
    glass_boost: int = Field(
        validation_alias="productivityGlassBoost", default=0, description="Production boost a glass village gives"
    )
    iron_boost: int = Field(
        validation_alias="productivityIronBoost", default=0, description="Production boost an iron village gives"
    )

    @field_validator("kingdom_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return row_id(value)

    @field_validator(
        "wall_id", "gate_id", "keep_id", "moat_id", "wall_unit_count", "peasants", "guards", "wood_boost",
        "stone_boost", "food_boost",
        mode="before",
    )  # fmt: skip
    @classmethod
    def _nan_column(cls, value: object) -> int | None:
        return _nan_int(value)

    @field_validator("coal_boost", "oil_boost", "glass_boost", "iron_boost", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)


class SlumLevelDef(_Row):
    """
    A level of a kingdom's slum: the price paid in parts to reach it and the packages it offers.

    Client: ``CastleSlumDataVO.fillFromParamXML`` (split.js line 671897), added to its kingdom's ``slumVOs`` in
    ``CastleKingdomData`` (split.js line 670892)
    """

    kingdom_id: GameDataId[Kingdom] | None = Field(
        validation_alias="kID", default=None, description="The kingdom; None if unread"
    )
    level: int = Field(validation_alias="slumLevel", default=0, description="The slum level")
    part_price_id: PartPayPriceId | None = Field(
        validation_alias="partPayPriceID",
        default=None,
        description="Its price paid in parts, a part_pay_prices row; None for none",
    )
    package_ids: tuple[PackageId, ...] = Field(
        validation_alias="packageIDs", default=(), description="The packages it offers, packages rows"
    )

    @field_validator("kingdom_id", "part_price_id", mode="before")
    @classmethod
    def _nan_column(cls, value: object) -> int | None:
        return _nan_int(value)

    @field_validator("level", mode="before")
    @classmethod
    def _level(cls, value: object) -> int:
        return js_int(value if js_truthy(value) else "")

    @field_validator("package_ids", mode="before")
    @classmethod
    def _packages(cls, value: object) -> list[int]:
        return _plus_ids(value)


class ExpansionDef(_Row):
    """
    The price of a castle's expansion at one level, for the kingdoms and maps it applies to.

    ``costs`` are its ``cost`` columns but rubies, which are ``cost_rubies``: the price of buying it with rubies
    instead.

    Client: ``ExpansionCostsData._getExpansionCostVOList`` (split.js line 579718), which makes one entry per
    space; ``getCurrentExpansionCostsVO`` finds the one for a space and level
    """

    expansion_id: ExpansionId = Field(validation_alias="expansionID", description="The row id")
    space_ids: tuple[GameDataId[Kingdom, "TreasureMapId"], ...] = Field(
        validation_alias="spaceIDs", default=(), description="Where it applies: kingdoms or season event maps"
    )
    level: int = Field(validation_alias="expansionLevel", default=0, description="The expansion it prices")
    costs: tuple[Collectable, ...] = Field(default=(), description="What it costs, without rubies")
    cost_rubies: int = Field(validation_alias="costC2", default=0, description="Rubies it costs instead")
    locked_by_skill_id: GameDataId["SceatSkill"] | None = Field(
        validation_alias="sceatSkillLocked",
        default=None,
        description="The Hall of Legends skill it needs; None for none",
    )

    @model_validator(mode="before")
    @classmethod
    def _read_costs(cls, row: object, info: ValidationInfo) -> object:
        if not isinstance(row, dict) or "costs" in row:
            return row
        currency_ids = (info.context or {}).get("currency_ids", {})
        costs = Collectable.from_columns(row, _XML_COST_PREFIX, currency_ids)
        return {**row, "costs": tuple(cost for cost in costs if cost.kind is not CollectableKind.RUBIES)}

    @field_validator("expansion_id", "level", "cost_rubies", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("space_ids", mode="before")
    @classmethod
    def _spaces(cls, value: object) -> list[int]:
        return _int_list(value)

    @field_validator("locked_by_skill_id", mode="before")
    @classmethod
    def _skill(cls, value: object) -> int | None:
        skill = _parse_int_or_default(value, 0)
        return skill if skill > 0 else None


class ResourceDef(_Row):
    """
    A resource the items name by id.

    Client: ``XmlResourceVO.parseXml`` and ``resourceEnum`` (split.js lines 702216, 702236), keyed by id in
    ``CurrencyData`` (split.js line 701718)
    """

    resource_id: ResourceId = Field(validation_alias="resourceID", description="The resource")
    name: str = Field(default="", description="Its items name, e.g. wood or currency1")

    @field_validator("resource_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _int_attribute(value, -1)

    @field_validator("name", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)

    @property
    def kind(self) -> CollectableKind:
        """The collectable it is, ``OTHER`` for a name no kind has."""
        return _KINDS_BY_XML_KEY.get(self.name, CollectableKind.OTHER)


class MineTypeDef(_Row):
    """
    What a mine yields: coins or rubies a collection, how often, and the influence a Beyond the Horizon one gives.

    Client: ``MineVO.parseXML`` (split.js line 423864), keyed by ``mineTypeID`` in ``CastleMineData.generateData``
    (split.js line 258422); ``reductionDisplay`` shown by ``AABGBoosterBuildingVO`` (split.js line 425871)
    """

    mine_type_id: MineTypeId = Field(validation_alias="mineTypeID", description="The mine type")
    waiting_seconds: int = Field(validation_alias="waitingTime", default=0, description="Seconds between collections")
    coins_per_collect: int = Field(
        validation_alias="amountPerCollectC1", default=0, description="Coins a collection gives; 0 for a ruby mine"
    )
    rubies_per_collect: int = Field(
        validation_alias="amountPerCollectC2", default=0, description="Rubies a collection gives; 0 for a coin mine"
    )
    collections: int = Field(validation_alias="amountLootable", default=0, description="Collections it holds")
    influence_per_minute: int = Field(
        validation_alias="amountInfluencePerMinute", default=0, description="Influence it gives a minute"
    )
    max_influence_points: int = Field(
        validation_alias="maxInfluencePoints", default=0, description="The most influence it holds"
    )
    reduction_display: int = Field(
        validation_alias="reductionDisplay", default=0, description="The influence depletion its info panel shows"
    )

    @field_validator(
        "mine_type_id", "waiting_seconds", "coins_per_collect", "rubies_per_collect", "collections",
        "influence_per_minute", "max_influence_points", "reduction_display",
        mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @property
    def kind(self) -> CollectableKind:
        """What a collection gives: rubies when ``rubies_per_collect`` is above 0, else coins."""
        return CollectableKind.RUBIES if self.rubies_per_collect > 0 else CollectableKind.COINS

    @property
    def amount_per_collect(self) -> int:
        """What a collection gives: the coins, else the rubies."""
        return self.coins_per_collect or self.rubies_per_collect

    @property
    def total_amount(self) -> int:
        """What all its collections give together."""
        return self.amount_per_collect * self.collections


class LandmarkDef(_Row):
    """
    A capital's or metropolis's levels: the client's ``capitalLandmark`` and ``metroLandmark`` are the default row,
    or on a Beyond the Horizon server the row its settings' ``capitalLandmarkID`` names. Not the royal towers,
    monuments and laboratories of :mod:`empire_core.castle.models.landmarks`.

    Client: ``LandmarkVO.parseXML`` (split.js line 717494), keyed by ``landmarkID`` in ``LandmarkData.parseXML``
    (split.js line 717434), ``capitalLandmark`` and ``metroLandmark`` (split.js lines 717452-717472); the minimum
    defense level is the capital's ``minimumOwnerLevel`` (split.js line 100272) and its attack wave's level
    (``CastleAttackArmyVO.addAdditionalWave``, split.js line 286536)
    """

    landmark_id: LandmarkId = Field(validation_alias="landmarkID", description="The landmark")
    empty_min_conquer_level: int = Field(
        validation_alias="emptyMinConquerLevel", default=0, description="The emptyMinConquerLevel column"
    )
    min_defense_level: int = Field(
        validation_alias="minDefenseLevel", default=0, description="The lowest level its owner counts as"
    )
    default_level: int = Field(validation_alias="defaultLevel", default=0, description="Its default level")
    is_default: bool = Field(validation_alias="isDefault", default=False, description="Whether it is the default row")
    prebuilt_castle_id: GameDataId["PrebuiltCastle"] = Field(
        validation_alias="preBuiltCastleID", default=0, description="Its prebuilt castle; 0 for none"
    )

    @field_validator(
        "landmark_id", "empty_min_conquer_level", "min_defense_level", "default_level", "prebuilt_castle_id",
        mode="before",
    )  # fmt: skip
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)

    @field_validator("is_default", mode="before")
    @classmethod
    def _flag(cls, value: object) -> bool:
        return value if isinstance(value, bool) else _parse_int_or_default(value, 0) == 1


class WishingWellLevelDef(_Row):
    """
    A level of the ruby wishing well: what starting it takes, how long it runs and what upgrading to it costs.

    Client: ``CastleRubyWishingWellVO.parseXML`` (split.js line 328993), keyed by level in ``CastleXmlData.parseXML``
    (split.js line 66533) for ``CastleRubyWishingWellData``
    """

    level: int = Field(description="The level")
    wishing_well_id: WishingWellId | None = Field(
        validation_alias="wodID", default=None, description="This level's id; None if unread"
    )
    entry_rubies: int | None = Field(
        validation_alias="entryCosts", default=None, description="Rubies a start throws in; None if unread"
    )
    cost_wood: int | None = Field(validation_alias="costWood", default=None, description="Wood upgrading to it costs")
    cost_stone: int | None = Field(
        validation_alias="costStone", default=None, description="Stone upgrading to it costs"
    )
    lucky_pennies: int | None = Field(
        validation_alias="costWishingWellCoin", default=None, description="Lucky pennies a start takes"
    )
    waiting_seconds: int | None = Field(
        validation_alias="waitingTime", default=None, description="Seconds a start runs; None if unread"
    )
    upgrade_id: WishingWellId | None = Field(
        validation_alias="upgradeWodID",
        default=WishingWellId(-1),
        description="The next level's id; -1 for none, None if unread",
    )
    downgrade_id: WishingWellId | None = Field(
        validation_alias="downgradeWodID",
        default=WishingWellId(-1),
        description="The previous level's id; -1 for none, None if unread",
    )

    @field_validator("level", mode="before")
    @classmethod
    def _level(cls, value: object) -> int:
        level = _nan_int(value)
        if level is None:
            raise ValueError(f"level {value!r} has no leading integer")
        return level

    @field_validator(
        "wishing_well_id", "entry_rubies", "cost_wood", "cost_stone", "lucky_pennies", "waiting_seconds",
        mode="before",
    )  # fmt: skip
    @classmethod
    def _nan_column(cls, value: object) -> int | None:
        return _nan_int(value)

    @field_validator("upgrade_id", "downgrade_id", mode="before")
    @classmethod
    def _neighbour(cls, value: object) -> int | None:
        return _landmark_int(value, "-1")


class CatalystDef(_Row):
    """
    A fusion catalyst: its forge, tier, the fusion levels it serves and the dust it is worth.

    Client: ``XmlCatalystVO.parseXml`` (split.js line 704461), keyed by currency in ``FusionForgeDataXml.parseXml``
    (split.js line 704233); the dust and ``deprecated`` read by the catalyst panel (split.js line 404506)
    """

    currency_id: GameDataId["CurrencyId"] = Field(validation_alias="currencyID", description="The catalyst")
    forge_id: GameDataId["FusionForgeId"] = Field(
        validation_alias="forgeID", default=-1, description="The forge it is used in"
    )
    deprecated: bool = Field(default=False, description="Whether it can no longer be assembled or disassembled")
    max_fusion_level: int = Field(
        validation_alias="maxUsableFusionLevel", default=0, description="The highest fusion level it serves"
    )
    tier: int = Field(default=0, description="Its tier")
    dust_gained: int = Field(
        validation_alias="addDecoDust", default=0, description="Decoration dust disassembling one gives"
    )
    dust_cost: int = Field(
        validation_alias="costDecoDust", default=0, description="Decoration dust assembling one costs"
    )

    @field_validator("currency_id", "forge_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _int_attribute(value, -1)

    @field_validator("deprecated", mode="before")
    @classmethod
    def _flag(cls, value: object) -> bool:
        return _client_bool(value, False)

    @field_validator("max_fusion_level", "tier", "dust_gained", "dust_cost", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _int_attribute(value, 0)


class ForgeMinuteSkipDef(_Row):
    """
    A minute skip a fusion forge takes.

    Client: ``XmlForgeMinuteSkipVO.parseXml`` (split.js line 704550), keyed by id in ``FusionForgeDataXml.parseXml``
    (split.js line 704233)
    """

    minute_skip_id: ForgeMinuteSkipId = Field(validation_alias="id", description="The row id")
    forge_id: GameDataId["FusionForgeId"] = Field(validation_alias="forgeID", default=-1, description="The forge")
    currency_id: GameDataId["CurrencyId"] = Field(
        validation_alias="currencyID", default=-1, description="The minute skip, a currency"
    )

    @field_validator("minute_skip_id", "forge_id", "currency_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _int_attribute(value, -1)


class FusionCostSequenceDef(_Row):
    """
    One step of a fusion forge's cost cycle: the goods a fusion to a target level costs besides dust.

    Client: ``XmlFusionCostSequenceVO.parseXml`` (split.js line 704599), keyed by id in
    ``FusionForgeDataXml.parseXml`` (split.js line 704233); ``getTypeByServerKey`` reads ``costJSONKey``
    (split.js line 185104)
    """

    sequence_id: FusionCostSequenceId = Field(validation_alias="id", description="The row id")
    forge_id: GameDataId["FusionForgeId"] = Field(validation_alias="forgeID", default=-1, description="The forge")
    step: int = Field(
        validation_alias="fusionTargetLevelIterationIndex", default=-1, description="Its place in the cycle, from 1"
    )
    cost_key: str = Field(validation_alias="costJSONKey", default="", description="The goods' server key, e.g. I")
    cost_amount: int = Field(validation_alias="costAmount", default=0, description="How many of the goods")

    @field_validator("sequence_id", "forge_id", "step", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _int_attribute(value, -1)

    @field_validator("cost_amount", mode="before")
    @classmethod
    def _int_column(cls, value: object) -> int:
        return _int_attribute(value, 0)

    @field_validator("cost_key", mode="before")
    @classmethod
    def _text_column(cls, value: object) -> str:
        return _text(value)

    @property
    def cost_kind(self) -> CollectableKind:
        """The goods it costs, ``OTHER`` for a key no kind has."""
        return _KINDS_BY_KEY.get(self.cost_key, CollectableKind.OTHER) if self.cost_key else CollectableKind.OTHER


class FusionShopDef(_Row):
    """
    The packages one of the fusion forge's shops sells: 1 the client's soft currency shop, 2 its hard currency one.

    Client: ``FusionForgeDataXml.parseFusionShopPackages`` (split.js line 704263); the shop ids are
    ``ClientConstPackages.FUSION_SHOP_ID_SOFT`` and ``_HARD`` (split.js line 27640)
    """

    shop_id: FusionShopId = Field(validation_alias="id", description="The shop")
    package_ids: tuple[PackageId, ...] = Field(
        validation_alias="packageIDs", default=(), description="The packages it sells, packages rows"
    )

    @field_validator("shop_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _int_attribute(value, 0)

    @field_validator("package_ids", mode="before")
    @classmethod
    def _packages(cls, value: object) -> list[int]:
        return _plus_ids(value)


class OfficersSchoolCurrencyDef(_Row):
    """
    A currency the officers' school takes.

    A row whose currency the ``currencies`` table lacks is left out; the client fails on it.

    Client: ``OfficersSchoolData`` (split.js line 715023) reads the ``currency`` name with
    ``CurrencyData.getXmlCurrencyByName``
    """

    officers_school_currency_id: OfficersSchoolCurrencyId = Field(validation_alias="id", description="The row id")
    currency_id: GameDataId["CurrencyId"] = Field(validation_alias="currency", description="The currency")

    @field_validator("officers_school_currency_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _int_attribute(value, 0)

    @field_validator("currency_id", mode="before")
    @classmethod
    def _currency(cls, value: object, info: ValidationInfo) -> int:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        name = _text(value)
        currency_id = (info.context or {}).get("currency_ids", {}).get(name)
        if currency_id is None:
            raise ValueError(f"no currency is named {name!r}")
        return currency_id


class OfficersSchoolUnitPairDef(_Row):
    """
    A pair of units an officers' school building unlocks.

    Client: ``OfficersSchoolUnitPairVO.parseXml`` (split.js line 715480), keyed by id in ``OfficersSchoolData``
    (split.js line 715033)
    """

    pair_id: OfficersSchoolUnitPairId = Field(validation_alias="id", description="The row id")
    unit_ids: tuple[GameDataId["Unit"], ...] = Field(validation_alias="wodID", default=(), description="The units")
    unlock_building_id: GameDataId["Building"] = Field(
        validation_alias="unlockBuildingWodID", default=-1, description="The building that unlocks them; -1 for none"
    )

    @field_validator("pair_id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        return _int_attribute(value, -1)

    @field_validator("unit_ids", mode="before")
    @classmethod
    def _units(cls, value: object) -> list[int]:
        return _plus_ids(value)

    @field_validator("unlock_building_id", mode="before")
    @classmethod
    def _building(cls, value: object) -> int:
        return _int_attribute(value, -1)


CASTLE_MODELS = (
    KingdomDef,
    KingdomVillagesDef,
    SlumLevelDef,
    ExpansionDef,
    ResourceDef,
    MineTypeDef,
    LandmarkDef,
    WishingWellLevelDef,
    CatalystDef,
    ForgeMinuteSkipDef,
    FusionCostSequenceDef,
    FusionShopDef,
    OfficersSchoolCurrencyDef,
    OfficersSchoolUnitPairDef,
)
"""The row models of this module, for the game data cache's fingerprint."""


__all__ = [
    "CatalystDef",
    "ExpansionDef",
    "ExpansionId",
    "ForgeMinuteSkipDef",
    "ForgeMinuteSkipId",
    "FusionCostSequenceDef",
    "FusionCostSequenceId",
    "FusionShopDef",
    "FusionShopId",
    "KingdomDef",
    "KingdomVillagesDef",
    "LandmarkDef",
    "LandmarkId",
    "MineTypeDef",
    "MineTypeId",
    "OfficersSchoolCurrencyDef",
    "OfficersSchoolCurrencyId",
    "OfficersSchoolUnitPairDef",
    "OfficersSchoolUnitPairId",
    "ResourceDef",
    "ResourceId",
    "SlumLevelDef",
    "WishingWellId",
    "WishingWellLevelDef",
]
