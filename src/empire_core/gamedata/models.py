"""
Typed rows from the GGE items payload.

Values arrive as strings, so every numeric field relies on pydantic coercion.
Tables whose meaning is not yet established are kept raw by
:class:`~empire_core.gamedata.data.GameData` instead of being modeled here on
a guess.
"""

from __future__ import annotations

from contextvars import ContextVar

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from empire_core.protocol.js import js_falsy, js_parse_int

# BasicUnitVO.FIGHTTYPE_OFF / FIGHTTYPE_DEF (bundle line 19345)
FIGHT_TYPE_OFFENSIVE = 0
FIGHT_TYPE_DEFENSIVE = 1

# effecttypes sortCategory 7 is economy; combat filter strategies exclude it.
ECONOMY_SORT_CATEGORY = 7


def parse_stacks(value: str | None) -> list[tuple[int, int]]:
    """
    Parse the ``wodID+count#wodID+count`` encoding used for camp defenses.

    Unparseable segments are skipped rather than failing the row.
    """
    stacks: list[tuple[int, int]] = []
    for part in str(value or "").split("#"):
        part = part.strip()
        if not part:
            continue
        wod_id, _, count = part.partition("+")
        try:
            stacks.append((int(wod_id), int(count or 0)))
        except ValueError:
            continue
    return stacks


def parse_ids(value: str | None) -> tuple[int, ...]:
    """Parse a comma-separated ID list."""
    ids = []
    for part in str(value or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return tuple(ids)


READING_CACHE: ContextVar[bool] = ContextVar("reading_game_data_cache", default=False)
"""True while GameData reads its own cache, whose ints are already parsed values."""


def _parse_int_or_default(value: object, default: int) -> int:
    """
    ``parseInt(CastleXMLUtils.getValueOrDefault(key, node, default))``.

    A missing or empty value reads as the default, as ``getValueOrDefault``
    (bundle line 1027) returns it for any falsy value. Otherwise the leading
    integer of the text counts, so ``"12abc"`` reads as 12. Text with no
    leading integer is NaN to the client, which no int can hold; it reads as
    the default.
    """
    if READING_CACHE.get() and isinstance(value, int) and not isinstance(value, bool):
        return value
    if js_falsy(value):
        return default
    parsed = js_parse_int(value)
    return default if parsed is None else parsed


class _Row(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class _UnitRow(_Row):
    """
    What ``AVisualVO.parseXmlNode`` and ``BasicUnitVO.parseXmlNode`` read for every unit and tool.

    Client: ``AVisualVO.parseXmlNode`` (bundle line 17800), ``BasicUnitVO.parseXmlNode`` (bundle line 19211)
    """

    wod_id: int = Field(alias="wodID", description="Unit or tool id; required")
    source: str = Field(
        alias="name",
        default="",
        description="The row's name, e.g. Barracks or Eventtool",
    )
    level: int = Field(default=-1, description="Upgrade level; -1 when the row has none")
    speed: int = Field(default=0, description="Base travel speed, before research bonuses")
    fight_type: int = Field(
        alias="fightType",
        default=FIGHT_TYPE_OFFENSIVE,
        description="0 offensive, 1 defensive",
    )

    @field_validator("wod_id", mode="before")
    @classmethod
    def _int_attribute(cls, value: object) -> object:
        # CastleWodData.parseVOFromWODXml keys the row by parseInt(wodID); a row
        # with no such id fails here, so GameData.parse skips just that row.
        parsed = None if js_falsy(value) else js_parse_int(value)
        if parsed is None:
            raise ValueError(f"wodID {value!r} has no leading integer")
        return parsed

    @field_validator("level", "speed", "fight_type", mode="before")
    @classmethod
    def _parse_int(cls, value: object, info: ValidationInfo) -> object:
        return _parse_int_or_default(value, cls.model_fields[str(info.field_name)].default)

    @field_validator("source", mode="before")
    @classmethod
    def _string_attribute(cls, value: object) -> object:
        # getStringAttribute: a missing or empty value reads as ""
        return value or ""

    @staticmethod
    def _type_attribute(value: object) -> object:
        # AVisualVO.parseXmlNode: "-" is read as no type
        value = value or ""
        return "" if value == "-" else value


class UnitStats(_UnitRow):
    """
    A combat unit.

    ``GameData.parse`` takes the ``units`` rows without ``slotTypes`` as
    units. The client picks a row's class from ``name`` and ``group``
    instead (``CastleWodData.getClassName``, bundle line 2057): Barracks,
    Eventunit, Keep, Kingdomunit and QuickAttack rows are ``SoldierUnitVO``s,
    while an ``Unknown`` row is a bare ``BasicUnitVO`` that reads no soldier
    columns.

    Client: ``SoldierUnitVO.parseXmlNode`` (bundle line 12531), after ``BasicUnitVO.parseXmlNode`` (bundle line 19211)
    """

    unit_type: str = Field(alias="type", default="", description="Unit type, e.g. MeadRanger; shared across levels")
    role: str = Field(default="", description="melee or ranged")
    melee_attack: int = Field(alias="meleeAttack", default=0, description="Base melee attack")
    range_attack: int = Field(alias="rangeAttack", default=0, description="Base ranged attack")
    melee_defense: int = Field(alias="meleeDefence", default=0, description="Base defence against melee")
    range_defense: int = Field(alias="rangeDefence", default=0, description="Base defence against ranged")
    loot_value: int = Field(alias="lootValue", default=0, description="Loot one unit carries")
    mead_supply: int = Field(alias="meadSupply", default=0, description="Mead upkeep")
    beef_supply: int = Field(alias="beefSupply", default=0, description="Beef upkeep")
    food_supply: int = Field(
        alias="foodSupply",
        default=0,
        description="Food upkeep, before the global food-consumption effect",
    )
    healing_cost_coins: int = Field(
        alias="healingCostC1", default=0, description="Coin cost to heal one, before cost effects"
    )
    healing_cost_rubies: int = Field(alias="healingCostC2", default=0, description="Ruby cost to heal one")
    hybrid: bool = Field(default=False, description="Fits either flank")

    @field_validator(
        "melee_attack",
        "range_attack",
        "melee_defense",
        "range_defense",
        "loot_value",
        "mead_supply",
        "beef_supply",
        "food_supply",
        "healing_cost_coins",
        "healing_cost_rubies",
        mode="before",
    )
    @classmethod
    def _parse_int_column(cls, value: object, info: ValidationInfo) -> object:
        return _parse_int_or_default(value, cls.model_fields[str(info.field_name)].default)

    @field_validator("unit_type", mode="before")
    @classmethod
    def _type(cls, value: object) -> object:
        return cls._type_attribute(value)

    @field_validator("role", mode="before")
    @classmethod
    def _role(cls, value: object) -> object:
        return value or ""

    @field_validator("hybrid", mode="before")
    @classmethod
    def _hybrid(cls, value: object) -> object:
        # BasicUnitVO.parseXmlNode: 1 == parseInt(getValueOrDefault("hybrid", t, "0"))
        return value if isinstance(value, bool) else _parse_int_or_default(value, 0) == 1

    @property
    def is_melee(self) -> bool:
        return self.role == "melee"

    @property
    def is_ranged(self) -> bool:
        return self.role == "ranged"

    @property
    def is_allround(self) -> bool:
        """A hybrid unit, which fits either flank (``BasicUnitVO.isAllround``, bundle line 19318)."""
        return self.hybrid

    @property
    def attack_value(self) -> int:
        """
        Raw offence, before any commander or equipment effects.

        The client adds a global-event bonus on top of this
        (EFFECT_TYPE_ATTACK_BONUS_UNIT), which is not modeled yet.
        """
        return max(self.melee_attack, self.range_attack)

    @property
    def is_offensive(self) -> bool:
        """
        Whether the game treats this unit as an attacker (``BasicUnitVO.isOffensive``, bundle line 19316).

        This is the ``fightType`` column, not "has an attack value": a defensive
        unit such as a halberdier carries a small attack value but is never an
        auto-fill candidate.
        """
        return self.fight_type == FIGHT_TYPE_OFFENSIVE


class ToolStats(_UnitRow):
    """
    A siege or defense tool.

    ``GameData.parse`` takes the ``units`` rows with ``slotTypes`` as tools;
    the client's ``ToolUnitVO`` rows are those named Workshop, Dworkshop,
    Elitetool and Eventtool. ``raw_effects`` is kept as the ``effectID&value`` string; resolve it through
    :attr:`~empire_core.gamedata.data.GameData.effects`.

    The ``raw_*_bonus`` columns are percentages. The client scales them by
    0.01 as it parses, so the fractions are the properties of the same name
    without ``raw_``: scaling in a validator would scale again on every cache
    round trip.

    Client: ``ToolUnitVO.parseXmlNode`` (bundle line 6538), after ``BasicUnitVO.parseXmlNode`` (bundle line 19211);
    ``ToolUnitVO.parseEffects`` (bundle line 6644)
    """

    tool_type: str = Field(
        alias="type", default="", description="Tool type, e.g. Ladder; shared across levels, keys the per-wave limit"
    )
    category: str = Field(
        alias="typ",
        default="0",
        description='Attack or Defence; "0" when the row has none',
    )
    raw_slot_types: str = Field(alias="slotTypes", default="", description="Comma-separated slot types the tool fits")
    raw_allowed_to_attack: str = Field(
        alias="allowedToAttack",
        default="",
        description="space+areaType pairs joined by #; see allowed_targets",
    )
    tool_category: str = Field(
        alias="toolCategory",
        default="",
        description="Tool category name in lower case, e.g. basic",
    )
    amount_per_wave: int = Field(
        alias="amountPerWave",
        default=-1,
        description="The row's per-wave limit; -1 when absent. per_wave_limit is the limit that applies",
    )
    can_attack_npc: bool = Field(
        alias="canBeUsedToAttackNPC",
        default=True,
        description="Usable against an NPC target",
    )
    raw_effects: str = Field(
        alias="effects",
        default="",
        description="Comma-separated effectID&value pairs",
    )
    raw_wall_bonus: int = Field(alias="wallBonus", default=0, description="Wall protection cancelled, in percent")
    raw_gate_bonus: int = Field(alias="gateBonus", default=0, description="Gate protection cancelled, in percent")
    raw_moat_bonus: int = Field(alias="moatBonus", default=0, description="Moat protection cancelled, in percent")
    raw_def_range_bonus: int = Field(
        alias="defRangeBonus", default=0, description="Defender ranged strength cancelled, in percent"
    )
    raw_def_melee_bonus: int = Field(
        alias="defMeleeBonus", default=0, description="Defender melee strength cancelled, in percent"
    )
    raw_off_range_bonus: int = Field(alias="offRangeBonus", default=0, description="Ranged attack added, in percent")
    raw_off_melee_bonus: int = Field(alias="offMeleeBonus", default=0, description="Melee attack added, in percent")

    @field_validator(
        "amount_per_wave",
        "raw_wall_bonus",
        "raw_gate_bonus",
        "raw_moat_bonus",
        "raw_def_range_bonus",
        "raw_def_melee_bonus",
        "raw_off_range_bonus",
        "raw_off_melee_bonus",
        mode="before",
    )
    @classmethod
    def _parse_int_column(cls, value: object, info: ValidationInfo) -> object:
        return _parse_int_or_default(value, cls.model_fields[str(info.field_name)].default)

    @field_validator("tool_type", mode="before")
    @classmethod
    def _type(cls, value: object) -> object:
        return cls._type_attribute(value)

    @field_validator("category", mode="before")
    @classmethod
    def _category(cls, value: object) -> object:
        # String(getValueOrDefault("typ", t, "0", true))
        return str(value) if value else "0"

    @field_validator("raw_slot_types", "raw_allowed_to_attack", "raw_effects", mode="before")
    @classmethod
    def _string_column(cls, value: object) -> object:
        return value or ""

    @field_validator("tool_category", mode="before")
    @classmethod
    def _tool_category(cls, value: object) -> object:
        # BasicUnitVO.parseXmlNode: getStringAttribute("toolCategory", t).toLowerCase()
        return str(value or "").lower()

    @field_validator("can_attack_npc", mode="before")
    @classmethod
    def _can_attack_npc(cls, value: object) -> object:
        # 1 == parseInt(getValueOrDefault("canBeUsedToAttackNPC", t, "1"))
        return value if isinstance(value, bool) else _parse_int_or_default(value, 1) == 1

    @property
    def wall_bonus(self) -> float:
        """Wall protection this tool cancels, as a fraction."""
        return self.raw_wall_bonus * 0.01

    @property
    def gate_bonus(self) -> float:
        """Gate protection this tool cancels, as a fraction."""
        return self.raw_gate_bonus * 0.01

    @property
    def moat_bonus(self) -> float:
        """Moat protection this tool cancels, as a fraction."""
        return self.raw_moat_bonus * 0.01

    @property
    def def_range_bonus(self) -> float:
        """Defender ranged strength this tool cancels, as a fraction."""
        return self.raw_def_range_bonus * 0.01

    @property
    def def_melee_bonus(self) -> float:
        """Defender melee strength this tool cancels, as a fraction."""
        return self.raw_def_melee_bonus * 0.01

    @property
    def off_range_bonus(self) -> float:
        """Ranged attack this tool adds, as a fraction."""
        return self.raw_off_range_bonus * 0.01

    @property
    def off_melee_bonus(self) -> float:
        """Melee attack this tool adds, as a fraction."""
        return self.raw_off_melee_bonus * 0.01

    @property
    def slot_types(self) -> tuple[int, ...]:
        """Attack-screen slot types this tool fits."""
        return parse_ids(self.raw_slot_types)

    @property
    def allowed_targets(self) -> tuple[tuple[int | None, int | None], ...]:
        """
        ``(space_id, area_type)`` pairs this tool may attack.

        An empty list means no restriction, and ``-1`` in either position means
        "any". A position with no leading integer is None, the client's NaN:
        that pair matches no target but still makes the list a restriction.

        Client: ``BasicUnitVO.parseSpaceIdAreaTypeValues`` (bundle line 19214)
        """
        entries = self.raw_allowed_to_attack.split("#")
        if entries[0] == "":
            entries.pop(0)
        pairs = []
        for entry in entries:
            parts = entry.split("+")
            pairs.append((js_parse_int(parts[0]), js_parse_int(parts[1]) if len(parts) > 1 else None))
        return tuple(pairs)

    @property
    def per_wave_limit(self) -> int:
        """
        How many of this tool one wave may carry; 0 or less means no limit.

        An offence support tool - one that fits slot type 10 - is always
        limited to one, whatever the column says.

        Client: ``ToolUnitVO.amountPerWave`` (bundle line 6658)
        """
        return 1 if 10 in self.slot_types else self.amount_per_wave

    def is_allowed_by_attack_target(self, space_id: int | None, area_type: int | None) -> bool:
        """
        Whether the tool may attack this target; no list means allowed anywhere.

        None for the space or area type means it is unknown and matches any
        pair; a pair holding the client's NaN matches nothing.

        Client: ``BasicUnitVO.checkIfTargetIsInArray`` (bundle line 19324)
        """
        allowed = self.allowed_targets
        if not allowed:
            return True
        return any(
            space is not None
            and area is not None
            and (space_id is None or space in (space_id, -1))
            and (area_type is None or area in (area_type, -1))
            for space, area in allowed
        )

    @property
    def is_attack_tool(self) -> bool:
        """``typ`` is ``ClientConstCastle.ATTACK_TOOL``."""
        return self.category == "Attack"

    @property
    def is_defense_tool(self) -> bool:
        """``typ`` is ``ClientConstCastle.DEFENSE_TOOL``."""
        return self.category == "Defence"

    def fits_slot(self, slot_type: int) -> bool:
        """Whether this tool may go in the given slot type (``ToolUnitVO.isToolForSlotType``, bundle line 6541)."""
        return slot_type in self.slot_types


class EffectDef(_Row):
    """
    An effect, e.g. ``relicOffensiveMeleeBonus``.

    An effect names *which* bonus an item grants; the effect type says what it
    modifies, and the cap says what it stacks with.
    """

    effect_id: int = Field(alias="effectID")
    name: str = ""
    effect_type_id: int = Field(alias="effectTypeID", default=0)
    cap_id: int | None = Field(alias="capID", default=None)
    raw_area_type_ids: str = Field(alias="areaTypeID", default="")
    is_pvp_fight: bool = Field(alias="isPvPFight", default=False)
    is_pve_fight: bool = Field(alias="isPvEFight", default=False)
    raw_space_ids: str = Field(alias="spaceIDs", default="")
    player_relation: str = Field(alias="playerRelation", default="")
    raw_raid_boss_ids: str = Field(
        alias="raidBossID",
        default="",
        description="Comma-separated raid boss ids the effect is tied to; empty means any raid boss",
    )

    @property
    def area_type_ids(self) -> tuple[int, ...]:
        """Area types this effect applies to; empty means every area."""
        return parse_ids(self.raw_area_type_ids)

    def applies_to_area(self, area_type: int | None) -> bool:
        """Whether the effect counts against a target of this area type."""
        allowed = self.area_type_ids
        if not allowed or area_type is None:
            return True
        return area_type in allowed

    @property
    def space_ids(self) -> tuple[int, ...]:
        """Castle spaces this effect is limited to; empty means every space."""
        return parse_ids(self.raw_space_ids)

    def applies_to_space(self, space_id: int | None) -> bool:
        """Whether the effect counts in this castle space."""
        allowed = self.space_ids
        if not allowed or space_id is None:
            return True
        return space_id in allowed

    def applies_to_relation(self, relation: str | None) -> bool:
        """
        Whether the effect counts given the relationship to the target.

        Values seen: ``sameAlliance``, ``allianceInWar``, ``samePlayer``. An
        unconditioned effect always counts; passing None leaves conditioned
        ones in, since the relationship is unknown rather than absent.
        """
        if not self.player_relation or relation is None:
            return True
        return self.player_relation == relation

    @property
    def raid_boss_ids(self) -> tuple[int, ...]:
        """
        Raid bosses this effect is tied to; empty means none in particular.

        Client: ``EffectVO.parseXML`` reads ``raidBossID`` as a comma-separated
        int list (bundle line 41702).
        """
        return parse_ids(self.raw_raid_boss_ids)

    def is_for_raid_boss(self, raid_boss_id: int) -> bool:
        """
        Whether the effect counts against this raid boss.

        Client: ``EffectVO.isForRaidBoss`` (bundle line 41705).
        """
        allowed = self.raid_boss_ids
        return not allowed or raid_boss_id in allowed

    def applies_to_raid_boss(self, raid_boss_id: int | None) -> bool:
        """
        Whether the effect counts against this raid boss; None keeps every effect.

        Client: ``EffectVO.isForRaidBoss`` (bundle line 41705) once a boss is
        known.
        """
        if raid_boss_id is None:
            return True
        return self.is_for_raid_boss(raid_boss_id)

    def applies_to_fight(self, *, player_target: bool | None) -> bool:
        """
        Whether the effect counts in this kind of fight.

        Some effects are flagged for player fights only and some for NPC fights
        only; an unflagged effect counts in both.
        """
        if player_target is None or not (self.is_pvp_fight or self.is_pve_fight):
            return True
        return self.is_pvp_fight if player_target else self.is_pve_fight


class EffectTypeDef(_Row):
    """An effect type, e.g. ``fameDefenseBonus``."""

    effect_type_id: int = Field(alias="effectTypeID")
    name: str = ""
    sort_category: int | None = Field(alias="sortCategory", default=None)
    combat_type: int | None = Field(alias="combatType", default=None)

    @property
    def is_economy(self) -> bool:
        """
        Economy effects, which every combat filter strategy drops.

        Category 7 in the client's own grouping.
        """
        return self.sort_category == ECONOMY_SORT_CATEGORY


class EffectCapDef(_Row):
    """
    The ceiling a group of effects stacks up to.

    A row without ``maxTotalBonus`` - cap 99 among them - is uncapped, which is
    why the field is optional rather than defaulting to zero.
    """

    cap_id: int = Field(alias="capID")
    max_total_bonus: float | None = Field(alias="maxTotalBonus", default=None)

    @property
    def is_uncapped(self) -> bool:
        return self.max_total_bonus is None


class EffectSpecRow(_Row):
    """
    Base for tables whose bonuses are an ``effectID&value`` string.

    Construction items, alliance buffs, global effects, sceat skills and
    buildings all encode their bonuses this way, comma separated.
    """

    raw_effects: str = Field(alias="effects", default="")


class ConstructionItemDef(EffectSpecRow):
    """
    A construction item - the decorations placed on castle buildings.

    Their bonuses are real combat bonuses: the flank unit limit item grants
    +2% per level, so a level 15 one is the +30% a player sees on the flanks.
    """

    construction_item_id: int = Field(alias="constructionItemID")
    name: str = ""
    group_id: int = Field(alias="constructionItemGroupID", default=0)
    level: int = 0
    rareness_id: int = Field(alias="rarenessID", default=0)
    slot_type_id: int = Field(alias="slotTypeID", default=0)
    effect_group_id: int = Field(alias="constructionItemEffectGroupID", default=0)


class AllianceBuffDef(EffectSpecRow):
    """One level of an alliance buff."""

    alliance_buff_id: int = Field(alias="allianceBuffID")
    series_id: int = Field(alias="allianceBuffSeriesID", default=0)
    level: int = 0
    max_level: int = Field(alias="maxLevel", default=0)


class GlobalEffectDef(EffectSpecRow):
    """A global (event) effect, active for everyone while its event runs."""

    global_effect_id: int = Field(alias="globalEffectID")
    name: str = ""
    boost_value: float = Field(alias="boostValue", default=0)
    min_level: int = Field(alias="minLevel", default=0)
    max_level: int = Field(alias="maxLevel", default=0)


class SceatSkillDef(EffectSpecRow):
    """One level of a sceat skill, from the Hall of Legends trees."""

    skill_id: int = Field(alias="skillID")
    skill_group_id: int = Field(alias="skillGroupID", default=0)
    level: int = 0
    skill_tree_id: int = Field(alias="skillTreeID", default=0)
    tier: int = 0


class GeneralSkillDef(EffectSpecRow):
    """One level of a general's skill."""

    skill_id: int = Field(alias="skillID")
    general_id: int = Field(alias="generalID", default=0)
    name: str = ""
    skill_group_id: int = Field(alias="skillGroupID", default=0)
    level: int = 0
    tier: int = 0


class FortificationDef(_Row):
    """
    A wall, gate or moat building and the protection it gives.

    The bonuses are the items columns, i.e. percentages: a level 3 castle wall
    reads 70 and protects by 0.70 once scaled.
    """

    wod_id: int = Field(alias="wodID")
    label: str = Field(alias="comment2", default="")
    level: int = 0
    wall_bonus: float = Field(alias="wallBonus", default=0)
    gate_bonus: float = Field(alias="gateBonus", default=0)
    moat_bonus: float = Field(alias="moatBonus", default=0)


class RelicEffectDef(_Row):
    """
    A relic effect, which is a *different id space* from a plain effect.

    A relic item's bonus ids index this table, not ``effects``: id 4 is
    ``perceptionBonus`` as a plain effect but ``gateReduction`` as a relic
    effect. Resolving in the wrong space yields a plausible, wrong answer.
    """

    relic_effect_id: int = Field(alias="id")
    effect_id: int = Field(alias="effectID", default=0)
    minimum_value: float = Field(alias="minimumValue", default=0)
    maximum_value: float = Field(alias="maximumValue", default=0)
    relic_effect_type: str = Field(alias="relicEffectType", default="")


class EquipmentEffectDef(_Row):
    """
    A bonus an equipment item can roll.

    Client: ``XmlEquipmentEffectVO.parseXml`` (bundle line 144158)
    """

    equipment_effect_id: int = Field(alias="equipmentEffectID", description="The id an item's bonus row names")
    effect_id: int = Field(alias="effectID", default=-1, description="The effect it resolves to; -1 when unset")
    bonus: int = Field(default=0, description="Bonus value")
    wearer_id: int = Field(alias="wearerID", default=-1, description="Who can roll it (WearerType); -1 when unset")
    raw_item_group_ids: str = Field(alias="itemGroupID", default="", description="Comma-separated item group ids")
    ignore_cap: bool = Field(alias="ignoreCap", default=False, description="The bonus escapes its effect's cap")

    @field_validator("bonus", mode="before")
    @classmethod
    def _int_attribute(cls, value: object) -> object:
        # int(CastleXMLUtils.getIntAttribute("bonus", e)), int(NaN) being 0
        return _parse_int_or_default(value, 0)

    @field_validator("ignore_cap", mode="before")
    @classmethod
    def _client_boolean(cls, value: object) -> object:
        # CastleXMLUtils.getBooleanAttribute (bundle line 1033): "0" != value
        return value if isinstance(value, bool) else str(value) != "0"

    @property
    def item_group_ids(self) -> tuple[int, ...]:
        return parse_ids(self.raw_item_group_ids)


class GemDef(EffectSpecRow):
    """
    A gem that can be slotted into an equipment item.

    Its ``effects`` name plain effect ids.

    Client: ``CastleGemVO.parseXML`` (bundle line 28287)
    """

    gem_id: int = Field(alias="gemID", description="Gem id, as in Equipment.gem_id")
    set_id: int = Field(alias="setID", default=-1, description="Equipment set the gem counts toward; -1 for none")
    trigger_chance: int = Field(
        alias="triggerChance", default=100, description="Trigger chance; the effect totals do not apply it"
    )


class LegendSkillDef(_Row):
    """One level of a legend skill, e.g. ``gateReduction``."""

    skill_id: int = Field(alias="skillID")
    level: int = 0
    tier: int = 0
    skill_tree_id: int = Field(alias="skillTreeID", default=0)
    skill_group_id: int = Field(alias="skillGroupID", default=0)
    effect_type: str = Field(alias="effectType", default="")
    total_effect_value: float = Field(alias="totalEffectValue", default=0)
    total_cost_skill_points: int = Field(alias="totalCostSkillPoints", default=0)


class AttackSlotDef(_Row):
    """An attack-screen slot and what unlocking it costs."""

    slot_id: int = Field(alias="slotID", description="Attack slot id")
    cost_rubies: int = Field(alias="costC2", default=0, description="Rubies to unlock the slot")


class ToolCategoryDef(_Row):
    """A tool category, e.g. ``basic``."""

    tool_category_id: int = Field(alias="toolCategoryID")
    name: str = ""


class HorseStats(_Row):
    """
    A travel booster - the value behind the ``HBW`` field on movements.

    There is no lookup by name: what tells the horse variants apart is not
    traced yet, so look one up by id with ``GameData.get_horse``.
    """

    wod_id: int = Field(alias="wodID")
    source: str = Field(alias="name", default="")
    label: str = Field(alias="comment2", default="")
    horse_type: str = Field(alias="type", default="")
    unit_boost: float = Field(alias="unitBoost", default=0)
    market_boost: float = Field(alias="marketBoost", default=0)
    spy_boost: float = Field(alias="spyBoost", default=0)


class DefaultLordDef(_Row):
    """
    A default lord.

    These are the negative ``LID`` sentinels: -14 for "no commander" on a
    support movement, -21 for the NPC that holds a camp, and so on.
    """

    lord_id: int = Field(alias="lordID")
    lord_type: str = Field(alias="type", default="")
    wearer_id: int = Field(alias="wearerID", default=0)


class GeneralAbilityDef(_Row):
    """
    One level of a general's ability, the value ``set_abilities`` sends per slot.

    Client: ``GeneralAbilityXmlVO.fillFromParamXml`` (bundle line 113203), keyed by
    ``abilityID`` in ``GeneralsData`` (bundle line 113021)
    """

    ability_id: int = Field(alias="abilityID", default=0, description="Ability id, the value set_abilities sends")
    name: str = Field(default="", description="Ability name, unique per level")
    ability_group_id: int = Field(alias="abilityGroupID", default=0, description="The group the levels share")
    level: int = Field(default=0, description="Ability level")
    ability_trigger_id: int = Field(alias="abilityTriggerID", default=0, description="What triggers the ability")
    trigger_per_wave: int = Field(alias="triggerPerWave", default=0, description="Triggers per wave")
    ability_attack_effect_id: int = Field(
        alias="abilityAttackEffectID", default=0, description="Effect while attacking"
    )
    ability_defense_effect_id: int = Field(
        alias="abilityDefenseEffectID", default=0, description="Effect while defending"
    )

    @field_validator(
        "ability_id", "ability_group_id", "level", "ability_trigger_id", "trigger_per_wave",
        "ability_attack_effect_id", "ability_defense_effect_id", mode="before",
    )  # fmt: skip
    @classmethod
    def _parse_int(cls, value: object) -> int:
        # fillFromParamXml reads each as parseInt(value || "0")
        return _parse_int_or_default(value, 0)


class CurrencyDef(_Row):
    """
    A currency; ``json_key`` is the key the server uses for it in currency lists.

    The caps, rareness and hidden flags the client reads from other tables are
    not parsed.

    Client: ``XmlCurrencyVO.parseXml`` (bundle line 141282), read from the
    ``currencies`` table by ``CurrencyData.parseXml`` (bundle line 141151)
    """

    currency_id: int = Field(alias="currencyID", default=-1, description="Currency id; -1 when unset")
    name: str = Field(alias="Name", default="", description="Internal name")
    json_key: str = Field(alias="JSONKey", default="", description="The key the server uses for it, e.g. GXP1")
    asset_name: str = Field(alias="assetName", default="", description="Icon asset name")

    @field_validator("currency_id", mode="before")
    @classmethod
    def _parse_int(cls, value: object) -> int:
        return _parse_int_or_default(value, -1)


class RaidBossDef(_Row):
    """
    An alliance raid boss.

    Client: ``AllianceRaidbossVO.parseXML`` (bundle line 113835), read from the
    ``raidBosses`` table by ``RaidBossData`` (bundle line 113671)
    """

    raid_boss_id: int = Field(alias="raidBossID", default=0, description="Raid boss id")
    name: str = Field(default="", description="Internal name, unique")
    rarity: int = Field(default=0, description="Rarity")

    @field_validator("raid_boss_id", "rarity", mode="before")
    @classmethod
    def _parse_int(cls, value: object) -> int:
        return _parse_int_or_default(value, 0)


class GeneralDef(_Row):
    """
    A general, the hero assigned to a commander.

    Client: ``GeneralXmlVO.fillFromParamXml`` (bundle line 33102)
    """

    general_id: int = Field(alias="generalID")
    name: str = Field(
        alias="generalName",
        default="",
        description="Internal name, unique per general",
    )
    raw_attack_slots: str = Field(alias="attackSlots", default="")
    raw_defense_slots: str = Field(alias="defenseSlots", default="")
    rarity_id: int = Field(alias="generalRarityID", default=0)
    max_level: int = Field(alias="maxLevel", default=0)
    max_star_level: int = Field(alias="maxStarLevel", default=0)

    @property
    def attack_slots(self) -> tuple[int, ...]:
        return parse_ids(self.raw_attack_slots)

    @property
    def defense_slots(self) -> tuple[int, ...]:
        return parse_ids(self.raw_defense_slots)


class DungeonDefence(_Row):
    """
    What defends an NPC camp at a given victory count.

    The per-flank fields use the ``wodID+count#wodID+count`` encoding; read them
    through the parsed properties.
    """

    count_victories: int = Field(alias="countVictories", default=0)
    kingdom_id: int = Field(alias="kID", default=0)
    lord_id: int = Field(alias="lordID", default=0)
    skip_costs: int = Field(alias="skipCosts", default=0)
    raw_units_left: str = Field(alias="unitsL", default="")
    raw_units_middle: str = Field(alias="unitsM", default="")
    raw_units_right: str = Field(alias="unitsR", default="")
    raw_units_keep: str = Field(alias="unitsK", default="")
    raw_tools_left: str = Field(alias="toolL", default="")
    raw_tools_middle: str = Field(alias="toolM", default="")
    raw_tools_right: str = Field(alias="toolR", default="")

    @property
    def units_left(self) -> list[tuple[int, int]]:
        return parse_stacks(self.raw_units_left)

    @property
    def units_middle(self) -> list[tuple[int, int]]:
        return parse_stacks(self.raw_units_middle)

    @property
    def units_right(self) -> list[tuple[int, int]]:
        return parse_stacks(self.raw_units_right)

    @property
    def units_keep(self) -> list[tuple[int, int]]:
        return parse_stacks(self.raw_units_keep)

    @property
    def tools_left(self) -> list[tuple[int, int]]:
        return parse_stacks(self.raw_tools_left)

    @property
    def tools_middle(self) -> list[tuple[int, int]]:
        return parse_stacks(self.raw_tools_middle)

    @property
    def tools_right(self) -> list[tuple[int, int]]:
        return parse_stacks(self.raw_tools_right)

    def total_units(self) -> int:
        """Defending units across every flank and the keep."""
        return sum(
            count
            for stacks in (
                self.units_left,
                self.units_middle,
                self.units_right,
                self.units_keep,
            )
            for _wod_id, count in stacks
        )


class NpcCampDefence(_Row):
    """
    An event camp's defense, shared shape across the camp tables.

    Covers the nomad, samurai, faction invasion and alliance invasion camps.
    """

    count_victory: int = Field(alias="countVictory", default=0)
    def_strength: int = Field(alias="defStrength", default=0)
    raw_defense_units: str = Field(alias="defenceUnits", default="")
    raw_defense_tools: str = Field(alias="defenceTools", default="")
    wall_bonus: float = Field(alias="wallBonus", default=0)
    gate_bonus: float = Field(alias="gateBonus", default=0)
    lord_id: int = Field(alias="lordID", default=0)
    guards: int = 0
    unit_wall_count: int = Field(alias="unitWallCount", default=0)
    cool_down: int = Field(alias="coolDown", default=0)
    dungeon_level: int = Field(alias="dungeonlevel", default=0)

    @property
    def defense_unit_ids(self) -> tuple[int, ...]:
        return parse_ids(self.raw_defense_units)

    @property
    def defense_tool_ids(self) -> tuple[int, ...]:
        return parse_ids(self.raw_defense_tools)


class EventCampDef(_Row):
    """
    One rank of a daimyo castle or township.

    A map row names the rank rather than the level, so the level, and the
    fortification that comes with it, are looked up here.
    """

    camp_id: int = Field(alias="id", default=0)
    rank: int = 0
    level: int = 0
    wall_bonus: float = Field(alias="wallBonus", default=0)
    gate_bonus: float = Field(alias="gateBonus", default=0)
    moat_bonus: float = Field(alias="moatBonus", default=0)
    guards: int = 0
    unit_wall_count: int = Field(alias="unitWallCount", default=0)


class LeagueBracketDef(_Row):
    """
    A league: the level band an event sorts a player into, a row of ``leaguetypes``.

    Its ``league_type_id`` is the ``LID`` of the highscore commands. Ids repeat
    across events, and within an event across sub types. An invasion camp's
    base level is the band's lower victory count, so this is also what says how
    hard the samurai camps are for a player of a given level.

    Client: ``AScoreEventVO.generateLeagueLevelsList`` (bundle line 14971),
    ``LeagueTypeVO.parseXML`` (bundle line 91460)
    """

    league_type_id: int | None = Field(
        alias="leaguetypeID", default=None, description="League type id; None when the row has none"
    )
    event_id: int | None = Field(
        alias="eventID", default=None, description="The event it belongs to; -1 for none, None when the row has none"
    )
    sub_type: int = Field(alias="subType", default=0, description="The event's sub type, e.g. a Berimond faction")
    min_level: int = Field(alias="minLevel", default=0, description="Lowest player level in the league")
    max_level: int = Field(alias="maxLevel", default=0, description="Highest player level in the league")
    victory_min: int = Field(alias="countVictoryMin", default=0, description="Lower victory count")
    victory_max: int = Field(alias="countVictoryMax", default=0, description="Upper victory count")

    @field_validator("league_type_id", "event_id", mode="before")
    @classmethod
    def _parse_int_or_none(cls, value: object) -> int | None:
        # parseInt(row.eventID || ""): a row without one matches no event
        if READING_CACHE.get() and (value is None or (isinstance(value, int) and not isinstance(value, bool))):
            return value
        return js_parse_int(value)

    @field_validator("sub_type", "min_level", "max_level", "victory_min", "victory_max", mode="before")
    @classmethod
    def _parse_int(cls, value: object, info: ValidationInfo) -> int:
        # parseInt of each value; subType is read with getValueOrDefault("subType", row, "0")
        return _parse_int_or_default(value, cls.model_fields[str(info.field_name)].default)


__all__ = [
    "ECONOMY_SORT_CATEGORY",
    "EventCampDef",
    "FIGHT_TYPE_DEFENSIVE",
    "LeagueBracketDef",
    "FIGHT_TYPE_OFFENSIVE",
    "AttackSlotDef",
    "DefaultLordDef",
    "DungeonDefence",
    "EffectCapDef",
    "EffectDef",
    "EffectTypeDef",
    "EquipmentEffectDef",
    "GeneralDef",
    "HorseStats",
    "LegendSkillDef",
    "AllianceBuffDef",
    "ConstructionItemDef",
    "CurrencyDef",
    "EffectSpecRow",
    "GeneralAbilityDef",
    "RaidBossDef",
    "FortificationDef",
    "GemDef",
    "GeneralSkillDef",
    "GlobalEffectDef",
    "NpcCampDefence",
    "RelicEffectDef",
    "SceatSkillDef",
    "ToolCategoryDef",
    "ToolStats",
    "UnitStats",
    "parse_ids",
    "parse_stacks",
]
