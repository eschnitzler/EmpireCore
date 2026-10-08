"""
No model field is a bare id list or a raw row: ids are enums, rewards and goods are Collectables.

A field typed ``Any``, or a list, tuple or set of ``int`` or ``Any`` (nested ones too), or a dict
keyed by a bare ``int``, fails
unless :data:`ALLOWED` names it with a reason: player ids, coordinates, a request's wire shape,
counters, a value that is opaque. ``EnumOrInt[...]`` is an enum, not an int, and ``int | float``
a number, not an id. The ``#320`` entries
are older fields that issue still has to type; the list is the remaining debt, so an entry
whose field is gone or typed fails too. A game-data row field named ``*_id`` that is a plain int
fails as well, unless :data:`GAME_DATA_SCALAR_IDS` says why no enum types it.
"""

import importlib
import pkgutil
import types
import typing
from typing import TYPE_CHECKING, Annotated, Any, get_args, get_origin

from pydantic import BaseModel, PlainValidator

import empire_core
from empire_core.enums import Kingdom
from empire_core.gamedata import (
    CurrencyAmounts,
    EnumOrInt,
    RewardId,
    SupportToolSlots,
    UnitOrTool,
    WodAmounts,
    WodAmountSlots,
)
from empire_core.gamedata.lenient import LenientEnum

if TYPE_CHECKING:
    from empire_core.gamedata import QuestId

_CONTAINERS = (list, tuple, set, frozenset)

ALLOWED: dict[str, str] = {
    "alliance.models.bookmarks.AddBookmarkRequest.attacker_ids": "player ids",
    "alliance.models.bookmarks.BookmarkAttackOrder.assigned_attacker_ids": "player ids",
    "alliance.models.bookmarks.DeleteAllianceBookmarkRequest.entries": "request wire shape: [bookmark_id, notify] rows",
    "alliance.models.bookmarks.DeleteBookmarkRequest.positions": "request wire shape: [kingdom, x, y] rows",
    "events.models.GetEventPointsResponse.max_points": "points, one per score the event keeps; not ids",
    "events.models.GetEventPointsResponse.own_points": "points, one per score the event keeps; not ids",
    "events.models.GetEventPointsResponse.own_ranks": "ranks, one per score the event keeps; not ids",
    "gamedata.data.GameData.alliance_buffs": "keyed by alliance buff id: alliance buffs have no name for an enum",
    "gamedata.data.GameData.attack_slots": "keyed by attack slot id: attack slots have no name for an enum",
    "gamedata.data.GameData.default_lords": "keyed by lord id: default commanders have no name for an enum",
    "gamedata.data.GameData.effect_caps": "keyed by effect cap id: effect caps have no name for an enum",
    "gamedata.data.GameData.equipment_effects": (
        "keyed by equipment effect id: equipment effects have no name for an enum"
    ),
    "gamedata.data.GameData.equipment_sets": "keyed by equipment set id: equipment sets have no name for an enum",
    "gamedata.data.GameData.relic_effects": "keyed by relic effect id: relic effects have no name for an enum",
    "gamedata.data.GameData.tool_categories": (
        "keyed by toolCategoryID, the row id of the items' toolCategories table, which the client never reads; "
        "a unit names its category by text (BasicUnitVO.toolCategory, bundle line 19343), typed as ToolCategory"
    ),
    "gamedata.data.GameData.vip_levels": "keyed by VIP level number, 1 and up; not ids",
    "gamedata.collectables.Collectable.value": "opaque: the entry as sent, for OTHER and the kinds not read here",
    "gamedata.models.ToolStats.slot_types": "attack-screen slot types: the client names none of them",
    "gamedata.tables.BuildingDef.available_in_map_ids": "map ids: no items table names maps",
    "gamedata.tables.BuildingDef.construction_item_group_ids": "construction item groups have no name",
    "gamedata.tables.BuildingDef.low_level_build_durations": "durations in seconds, not ids",
    "gamedata.tables.BuildingDef.low_level_main_castle_cost_rubies": "ruby amounts, not ids",
    "quests.models.DailyQuest.progress": "counters, one per condition of the quest",
    "quests.models.Quest.progress": "counters, one per condition of the quest",
    "alliance.models.chronicle.AllianceChronicleEntry.action_values": "#320",
    "state.models.Player.castles": "keyed by (kingdom, castle id); castle ids are the player's areas, not game data",
    "commanders.models.equipment.EquipmentBonus.values": "laid out by the effect type's value class (bundle line 1294)",
    "commanders.models.equipment.RelicBonus.values": "laid out by the effect type's value class (bundle line 1294)",
    "commanders.models.roster.CommanderEffect.values": "laid out by the effect type's value class (bundle line 1294)",
    "map.models.items.MapAreaItem.protector_positions": "opaque: the client reads only its length",
    "map.models.items.MapAreaItem.raw_data": (
        "the row held by reference so a map scan stays fast (#343, #354); typed accessors parse it as the client does"
    ),
    "messages.models.battle_logs.ForwardBattleLogRequest.player_ids": "player ids",
    "messages.models.mailbox.DeleteMessagesRequest.message_ids": "message ids",
    "messages.models.mailbox.DeleteMessagesResponse.message_ids": "message ids",
    "messages.models.mailbox.ForwardSpyLogRequest.player_ids": "player ids",
    "player.models.progress.TopTitleRanking.thresholds": "points, one per top-X title of the system; not ids",
}


GAME_DATA_SCALAR_IDS: dict[str, str] = {
    "gamedata.models.AllianceBuffDef.alliance_buff_id": "alliance buffs have no name to make an enum of",
    "gamedata.models.AllianceBuffDef.series_id": "alliance buff series have no table",
    "gamedata.models.AttackSlotDef.slot_id": "attack slots have no name to make an enum of",
    "gamedata.models.ConstructionItemDef.effect_group_id": "construction item effect groups have no table",
    "gamedata.models.ConstructionItemDef.group_id": "construction item groups have no name",
    "gamedata.models.ConstructionItemDef.rareness_id": "not established that it shares the equipment Rareness ids",
    "gamedata.models.ConstructionItemDef.slot_type_id": "construction item slot types: the client names none",
    "gamedata.models.DefaultLordDef.lord_id": "default commanders have no name to make an enum of",
    "gamedata.models.DungeonDefence.lord_id": "a default commander id, which has no enum",
    "gamedata.models.EffectCapDef.cap_id": "effect caps have no name to make an enum of",
    "gamedata.models.EffectDef.cap_id": "effect caps have no name to make an enum of",
    "gamedata.models.EquipmentEffectDef.equipment_effect_id": "equipment effects have no name to make an enum of",
    "gamedata.models.EquipmentEffectValue.equipment_effect_id": "equipment effects have no name to make an enum of",
    "gamedata.models.EquipmentSetDef.row_id": "a row number, not referenced",
    "gamedata.models.EquipmentSetDef.set_id": "equipment sets have no name to make an enum of",
    "gamedata.models.EventCampDef.camp_id": "daimyo ranks have no name to make an enum of",
    "gamedata.models.GemDef.set_id": "equipment sets have no name to make an enum of",
    "gamedata.models.GeneralAbilityDef.ability_attack_effect_id": "a generalAbilityEffects row, which has no enum",
    "gamedata.models.GeneralAbilityDef.ability_defense_effect_id": "a generalAbilityEffects row, which has no enum",
    "gamedata.models.GeneralAbilityDef.ability_group_id": "ability groups have no table",
    "gamedata.models.GeneralAbilityDef.ability_trigger_id": "ability triggers: the client names none",
    "gamedata.models.GeneralDef.rarity_id": "general rarities have no name to make an enum of",
    "gamedata.models.GeneralSkillDef.skill_group_id": "skill groups have no table",
    "gamedata.models.LeagueBracketDef.league_type_id": "a league is a level band per event, not one row",
    "gamedata.models.LegendSkillDef.skill_group_id": "skill groups have no table",
    "gamedata.models.LegendSkillDef.skill_tree_id": "skill trees have no table",
    "gamedata.models.NpcCampDefence.lord_id": "a default commander id, which has no enum",
    "gamedata.models.RelicEffectDef.relic_effect_id": "relic effects have no name to make an enum of",
    "gamedata.models.SceatSkillDef.skill_group_id": "skill groups have no table",
    "gamedata.models.SceatSkillDef.skill_tree_id": "skill trees have no table",
    "gamedata.models.ToolCategoryDef.tool_category_id": "the row id; categories are typed by name (ToolCategory)",
    "gamedata.models.VipLevelDef.vip_level_id": "a VIP level number",
    "gamedata.models._UnitRow.wod_id": "the base of UnitStats and ToolStats, which type it as Unit and Tool",
    "gamedata.tables.AchievementDef.series_id": "achievement series have no table",
    "gamedata.tables.AllianceCrestLayoutDef.effect_icon_id": "an icon, not a row",
    "gamedata.tables.BuildingDef.district_type_id": "district types have no table",
    "gamedata.tables.EquipmentGroupDef.pic_id": "a picture, not a row",
    "gamedata.tables.ConstructionItemRecipeDef.blueprint_id": "blueprints have no table; their recipes name them",
    "gamedata.tables.ConstructionItemRecipeDef.recipe_id": "recipes have no name to make an enum of",
    "gamedata.tables.LootBoxDef.key_tombola_id": "tombolas have no name to make an enum of",
    "gamedata.tables.LootBoxDef.tombola_id": "tombolas have no name to make an enum of",
    "gamedata.tables.QuestDef.map_id": "no items table names maps",
    "gamedata.tables.QuestDef.quest_giver_id": "quest givers: the client names only the selected hero",
    "gamedata.tables.QuestDef.questbook_tab_id": "quest book tabs have no table",
    "gamedata.tables.QuestDef.series_id": "quest series have no table",
    "gamedata.tables.ResearchDef.group_id": "research groups have no table",
    "gamedata.tables.ScalingCampDef.scaling_camp_id": "scaling camps have no name to make an enum of",
}
"""Game-data row fields named ``*_id`` that hold a plain int, each with why no enum types it."""


def _is_lenient(annotation: Any) -> bool:
    return get_origin(annotation) is Annotated and any(
        isinstance(meta, PlainValidator) and isinstance(meta.func, LenientEnum) for meta in annotation.__metadata__
    )


def _bare(annotation: Any, *, inside: bool = False) -> bool:
    """Whether the annotation is Any, or holds an int or Any in a list, tuple or set."""
    if annotation is Any:
        return True
    if _is_lenient(annotation):
        return False
    origin = get_origin(annotation)
    if origin is Annotated:
        return _bare(get_args(annotation)[0], inside=inside)
    if origin in (typing.Union, types.UnionType):
        if set(get_args(annotation)) - {type(None)} == {int, float}:
            return False
        return any(_bare(arg, inside=inside) for arg in get_args(annotation))
    if origin in _CONTAINERS:
        return any(_bare(arg, inside=True) for arg in get_args(annotation) if arg is not Ellipsis)
    if origin is dict:
        return _bare(get_args(annotation)[0], inside=True)
    return inside and annotation is int


def _models() -> list[type[BaseModel]]:
    for info in pkgutil.walk_packages(empire_core.__path__, "empire_core."):
        importlib.import_module(info.name)
    found, todo = [], list(BaseModel.__subclasses__())
    while todo:
        model = todo.pop()
        todo += model.__subclasses__()
        if model.__module__.startswith("empire_core."):
            found.append(model)
    return found


def _bare_fields() -> set[str]:
    bare = set()
    for model in _models():
        for name, field in model.model_fields.items():
            owner = next(c for c in model.__mro__ if name in getattr(c, "__annotations__", {}))
            if _bare(field.annotation):
                bare.add(f"{owner.__module__.removeprefix('empire_core.')}.{owner.__qualname__}.{name}")
    return bare


def test_no_model_field_is_a_bare_id_list_or_a_raw_row():
    bare = _bare_fields()
    unlisted = sorted(bare - set(ALLOWED))
    assert not unlisted, (
        "type these with an enum (EnumOrInt) or Collectable, or allow them with a reason:\n" + "\n".join(unlisted)
    )
    stale = sorted(set(ALLOWED) - bare)
    assert not stale, "these are typed or gone now; drop them from ALLOWED:\n" + "\n".join(stale)


def _scalar_game_data_ids() -> set[str]:
    found = set()
    for model in _models():
        if not model.__module__.startswith("empire_core.gamedata."):
            continue
        for name, field in model.model_fields.items():
            lenient = any(isinstance(m, PlainValidator) and isinstance(m.func, LenientEnum) for m in field.metadata)
            annotation = field.annotation
            args = (
                set(get_args(annotation)) if get_origin(annotation) in (typing.Union, types.UnionType) else {annotation}
            )
            if name.endswith("_id") and not lenient and args - {type(None)} == {int}:
                owner = next(c for c in model.__mro__ if name in getattr(c, "__annotations__", {}))
                found.add(f"{owner.__module__.removeprefix('empire_core.')}.{owner.__qualname__}.{name}")
    return found


def test_no_game_data_id_is_a_plain_int():
    found = _scalar_game_data_ids()
    unlisted = sorted(found - set(GAME_DATA_SCALAR_IDS))
    assert not unlisted, "type these with GameDataId, or allow them with a reason:\n" + "\n".join(unlisted)
    stale = sorted(set(GAME_DATA_SCALAR_IDS) - found)
    assert not stale, "these are typed or gone now; drop them from GAME_DATA_SCALAR_IDS:\n" + "\n".join(stale)
    assert all(reason.strip() for reason in GAME_DATA_SCALAR_IDS.values())


def test_every_allowed_field_has_a_reason():
    assert all(reason.strip() for reason in ALLOWED.values())


def test_the_check_finds_bare_fields():
    assert _bare(Any)
    assert _bare(list[int]) and _bare(tuple[int, ...]) and _bare(list[Any]) and _bare(tuple[Any, ...])
    assert _bare(list[list[int]]) and _bare(list[tuple[int, int]]) and _bare(list[int] | None)
    assert _bare(Annotated[tuple[int, ...], "meta"]) and _bare(tuple[Annotated[int, "meta"], ...])
    assert not _bare(int) and not _bare(str) and not _bare(dict[str, int]) and not _bare(tuple[int | float, ...])
    assert not _bare(tuple[EnumOrInt[Kingdom], ...])
    assert _bare(dict[int, int]) and _bare(dict[tuple[Kingdom, int], str])
    assert not _bare(dict[Kingdom, int]) and not _bare(WodAmounts) and not _bare(WodAmountSlots)
    assert not _bare(SupportToolSlots) and not _bare(CurrencyAmounts) and not _bare(tuple[UnitOrTool, ...])
    assert not _bare(tuple[EnumOrInt["QuestId"], ...])
    assert not _bare(tuple[RewardId, ...])
    assert not _bare(tuple[int | float | None, ...])
