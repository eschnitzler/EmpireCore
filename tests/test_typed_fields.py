"""
No model field is a bare id list or a raw row: ids are enums, rewards and goods are Collectables.

A field typed ``Any``, or a list, tuple or set of ``int`` or ``Any`` (nested ones too), fails
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
from empire_core.gamedata import EnumOrInt
from empire_core.gamedata.lenient import LenientEnum

if TYPE_CHECKING:
    from empire_core.gamedata import QuestId

_CONTAINERS = (list, tuple, set, frozenset)

ALLOWED: dict[str, str] = {
    "alliance.models.bookmarks.AddBookmarkRequest.attacker_ids": "player ids",
    "alliance.models.bookmarks.BookmarkAttackOrder.assigned_attacker_ids": "player ids",
    "alliance.models.bookmarks.DeleteAllianceBookmarkRequest.entries": "request wire shape: [bookmark_id, notify] rows",
    "alliance.models.bookmarks.DeleteBookmarkRequest.positions": "request wire shape: [kingdom, x, y] rows",
    "events.models.CampaignEvent.reward_ids": "reward ids: the items' rewards rows have no name to make an enum of",
    "events.models.GetEventPointsResponse.max_points": "points, one per score the event keeps; not ids",
    "events.models.GetEventPointsResponse.own_points": "points, one per score the event keeps; not ids",
    "events.models.GetEventPointsResponse.own_ranks": "ranks, one per score the event keeps; not ids",
    "gamedata.collectables.Collectable.value": "opaque: the entry as sent, for OTHER and the kinds not read here",
    "gamedata.models.ToolStats.slot_types": "attack-screen slot types: the client names none of them",
    "gamedata.tables.BuildingDef.available_in_map_ids": "map ids: no items table names maps",
    "gamedata.tables.BuildingDef.construction_item_group_ids": "construction item groups have no name",
    "gamedata.tables.BuildingDef.low_level_build_durations": "durations in seconds, not ids",
    "gamedata.tables.BuildingDef.low_level_main_castle_cost_rubies": "ruby amounts, not ids",
    "quests.models.DailyQuest.progress": "counters, one per condition of the quest",
    "quests.models.Quest.progress": "counters, one per condition of the quest",
    "quests.models.QuestBook.announced_quest_ids": "main quest ids: the items' mainquests rows have no name",
    "quests.models.QuestBook.finished_quest_ids": "main quest ids: the items' mainquests rows have no name",
    "quests.models.QuestBook.running_quest_ids": "main quest ids: the items' mainquests rows have no name",
    "alliance.models.chronicle.AllianceChronicleEntry.action_values": "#320",
    "alliance.models.info.CrestLayout.colors": "#320",
    "alliance.models.info.CrestLayout.layout_id": "#320",
    "army.models.units.WaveFlank.tools": "#320",
    "army.models.units.WaveFlank.units": "#320",
    "attack.models.info.AttackInfoResponse.defender_legend_skill_ids": "#320",
    "attack.models.info.AttackInfoResponse.spy_data": "#320",
    "attack.models.presets.PresetArmy.left_tools": "#320",
    "attack.models.presets.PresetArmy.left_units": "#320",
    "attack.models.presets.PresetArmy.middle_tools": "#320",
    "attack.models.presets.PresetArmy.middle_units": "#320",
    "attack.models.presets.PresetArmy.right_tools": "#320",
    "attack.models.presets.PresetArmy.right_units": "#320",
    "attack.models.presets.PresetArmy.support_tools": "#320",
    "attack.models.send.CreateAttackRequest.collector_booster": "#320",
    "attack.models.send.CreateAttackRequest.support_tools": "#320",
    "attack.models.send.CreateAttackRequest.yard_wave": "#320",
    "castle.models.details.DetailedCastleInfo.raw_hospital_units": "#320",
    "castle.models.details.DetailedCastleInfo.raw_stronghold_units": "#320",
    "castle.models.details.DetailedCastleInfo.raw_travelling_units": "#320",
    "castle.models.details.DetailedCastleInfo.raw_units": "#320",
    "castle.models.market.CreateMarketMovementRequest.goods": "#320",
    "castle.models.objects.BuildingRow.raw_data": "#320",
    "castle.models.objects.CastleBuildings.construction_items": "#320",
    "castle.models.objects.ConstructionList.object_ids": "#320",
    "castle.models.permanent.CastleUnitUnlocks.locked_unit_ids": "#320",
    "castle.models.permanent.CastleUnitUnlocks.unlocked_unit_ids": "#320",
    "castle.models.permanent.PermanentCastle.horse_ids": "#320",
    "castle.models.support.SendSupportRequest.units": "#320",
    "castle.models.support.SendTroopsRequest.units": "#320",
    "castle.models.transfers.KingdomUnitTransferRequest.units": "#320",
    "combat.solver.FilledAttack.yard": "#320",
    "commanders.models.equipment.Equipment.alien_string": "#320",
    "commanders.models.equipment.EquipmentBonus.values": "#320",
    "commanders.models.equipment.RelicBonus.values": "#320",
    "commanders.models.roster.CommanderEffect.values": "#320",
    "commanders.models.roster.LeaderBase.alien_equipment": "#320",
    "commanders.models.roster.LeaderBase.alien_gem_ids": "#320",
    "commanders.models.roster.LeaderBase.general_ability_ids": "#320",
    "commanders.models.roster.LeaderBase.general_skill_ids": "#320",
    "commanders.models.roster.LeaderBase.temporary_equipment": "#320",
    "commanders.models.skills.General.skill_ids": "#320",
    "commanders.models.skills.SetGeneralAbilitiesRequest.abilities": "#320",
    "commanders.models.skills.SkillList.legend_skill_ids": "#320",
    "commanders.models.skills.SkillList.sceat_skill_ids": "#320",
    "defense.models.ChangeKeepDefenseRequest.slots": "#320",
    "defense.models.ChangeKeepDefenseRequest.support_tool_slots": "#320",
    "defense.models.ChangeMoatDefenseRequest.left_slots": "#320",
    "defense.models.ChangeMoatDefenseRequest.middle_slots": "#320",
    "defense.models.ChangeMoatDefenseRequest.right_slots": "#320",
    "defense.models.GetDefenseResponse.melee_priority": "#320",
    "defense.models.GetDefenseResponse.range_priority": "#320",
    "defense.models.GetSupportDefenseResponse.defense_positions": "#320",
    "defense.models.KeepDefense.slots": "#320",
    "defense.models.KeepDefense.support_tool_slots": "#320",
    "defense.models.MoatDefense.left_slots": "#320",
    "defense.models.MoatDefense.middle_slots": "#320",
    "defense.models.MoatDefense.right_slots": "#320",
    "defense.models.WallSection.slots": "#320",
    "defense.models.WallSectionSetup.slots": "#320",
    "events.models.LongTermPointEvent.upcoming_event_ids": "#320",
    "events.models.RaidBossEvent.raid_boss_ids": "#320",
    "map.models.items.MapAreaItem.abg_connections": "#320",
    "map.models.items.MapAreaItem.abg_tower_connection": "#320",
    "map.models.items.MapAreaItem.protector_positions": "#320",
    "map.models.items.MapAreaItem.raw_data": "#320",
    "map.models.owners.AllianceCrest.color_ids": "#320",
    "messages.models.battle_logs.AbilityWaveValue.flank_name": "#320",
    "messages.models.battle_logs.AbilityWaveValue.value": "#320",
    "messages.models.battle_logs.AbilityWaveValue.wave_id": "#320",
    "messages.models.battle_logs.BattleLogAbility.ability_id": "#320",
    "messages.models.battle_logs.BattleLogMiddleResponse.attacker_legend_skill_ids": "#320",
    "messages.models.battle_logs.BattleLogMiddleResponse.attacker_triggered_gems": "#320",
    "messages.models.battle_logs.BattleLogMiddleResponse.defender_legend_skill_ids": "#320",
    "messages.models.battle_logs.BattleLogMiddleResponse.defender_triggered_gems": "#320",
    "messages.models.battle_logs.BattleLogShortResponse.advisor_movement_count": "#320",
    "messages.models.battle_logs.BattleLogShortResponse.advisor_movement_number": "#320",
    "messages.models.battle_logs.BattleLogShortResponse.advisor_type": "#320",
    "messages.models.battle_logs.BattleLogShortResponse.auto_skip_costs": "#320",
    "messages.models.battle_logs.BattleLogShortResponse.auto_skip_type": "#320",
    "messages.models.battle_logs.BattleLogShortResponse.found_equipment": "#320",
    "messages.models.battle_logs.BattleLogShortResponse.found_gem": "#320",
    "messages.models.battle_logs.BattleLogShortResponse.found_minute_skip": "#320",
    "messages.models.battle_logs.BattleLogShortResponse.supporters_wounded": "#320",
    "messages.models.battle_logs.BattleParticipant.loot": "#320",
    "messages.models.battle_logs.ForwardBattleLogRequest.player_ids": "#320",
    "messages.models.mailbox.DeleteMessagesRequest.message_ids": "#320",
    "messages.models.mailbox.DeleteMessagesResponse.message_ids": "#320",
    "messages.models.mailbox.ForwardSpyLogRequest.player_ids": "#320",
    "messages.models.mailbox.ReadMessageResponse.extra": "#320",
    "messages.models.mailbox.SpyReportResponse.legend_skill_ids": "#320",
    "messages.models.mailbox.SpyReportResponse.resources": "#320",
    "messages.models.mailbox.SpyReportResponse.spy_data": "#320",
    "movements.models.MovementArea.row": "#320",
    "movements.models.MovementArmy.courtyard": "#320",
    "movements.models.MovementArmy.left": "#320",
    "movements.models.MovementArmy.middle": "#320",
    "movements.models.MovementArmy.right": "#320",
    "movements.models.MovementMarket.goods": "#320",
    "movements.models.MovementWrapper.support_tools": "#320",
    "movements.models.MovementWrapper.travel_goods": "#320",
    "movements.models.MovementWrapper.travel_units": "#320",
    "movements.tracked.Movement.goods": "#320",
    "movements.tracked.Movement.support_tool_ids": "#320",
    "player.models.progress.AchievementsResponse.finished_achievement_ids": "#320",
    "player.models.progress.AllianceCityTitle.player_id": "#320",
    "player.models.progress.AllianceCityTitle.title_id": "#320",
    "player.models.progress.BoosterInfoResponse.premium_type": "#320",
    "player.models.progress.IslandTitle.title_id": "#320",
    "player.models.progress.RelocationInfoResponse.relocation_mode": "#320",
    "player.models.progress.ResearchInfoResponse.bought_research_ids": "#320",
    "player.models.progress.TitleRanksResponse.prefix_system": "#320",
    "player.models.progress.TitleRanksResponse.suffix_system": "#320",
    "player.models.progress.TopTitleRanking.thresholds": "#320",
    "player.models.progress.TopTitleRanking.top_player_id": "#320",
    "ranking.models.GetHighscoreResponse.raw_list": "#320",
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
    "gamedata.models.GemDef.gem_id": "gems have no name to make an enum of",
    "gamedata.models.GemDef.set_id": "equipment sets have no name to make an enum of",
    "gamedata.models.GeneralAbilityDef.ability_attack_effect_id": "a generalAbilityEffects row, which has no enum",
    "gamedata.models.GeneralAbilityDef.ability_defense_effect_id": "a generalAbilityEffects row, which has no enum",
    "gamedata.models.GeneralAbilityDef.ability_group_id": "ability groups have no table",
    "gamedata.models.GeneralAbilityDef.ability_trigger_id": "ability triggers: the client names none",
    "gamedata.models.GeneralDef.rarity_id": "general rarities have no name to make an enum of",
    "gamedata.models.GeneralSkillDef.skill_group_id": "skill groups have no table",
    "gamedata.models.HorseStats.wod_id": "horses have no generated enum yet",
    "gamedata.models.LeagueBracketDef.league_type_id": "a league is a level band per event, not one row",
    "gamedata.models.LegendSkillDef.skill_group_id": "skill groups have no table",
    "gamedata.models.LegendSkillDef.skill_tree_id": "skill trees have no table",
    "gamedata.models.NpcCampDefence.lord_id": "a default commander id, which has no enum",
    "gamedata.models.RelicEffectDef.relic_effect_id": "relic effects have no name to make an enum of",
    "gamedata.models.SceatSkillDef.skill_group_id": "skill groups have no table",
    "gamedata.models.SceatSkillDef.skill_id": "sceat skills have no name to make an enum of",
    "gamedata.models.SceatSkillDef.skill_tree_id": "skill trees have no table",
    "gamedata.models.ToolCategoryDef.tool_category_id": "the row id; categories are typed by name (ToolCategory)",
    "gamedata.models.VipLevelDef.vip_level_id": "a VIP level number",
    "gamedata.models._UnitRow.wod_id": "the base of UnitStats and ToolStats, which type it as Unit and Tool",
    "gamedata.tables.BuildingDef.district_type_id": "district types have no table",
    "gamedata.tables.BuildingDef.sceat_skill_id": "sceat skills have no name to make an enum of",
    "gamedata.tables.EquipmentGroupDef.pic_id": "a picture, not a row",
    "gamedata.tables.LootBoxDef.key_tombola_id": "tombolas have no name to make an enum of",
    "gamedata.tables.LootBoxDef.tombola_id": "tombolas have no name to make an enum of",
    "gamedata.tables.QuestDef.map_id": "no items table names maps",
    "gamedata.tables.QuestDef.quest_giver_id": "quest givers: the client names only the selected hero",
    "gamedata.tables.QuestDef.questbook_tab_id": "quest book tabs have no table",
    "gamedata.tables.QuestDef.series_id": "quest series have no table",
    "gamedata.tables.ResearchDef.group_id": "research groups have no table",
    "gamedata.tables.ScalingCampDef.scaling_camp_id": "scaling camps have no name to make an enum of",
    "gamedata.tables.TitleDef.previous_title_id": "titles have no name to make an enum of",
    "gamedata.tables.TitleDef.reward_id": "the items' rewards rows have no name to make an enum of",
    "gamedata.tables.TitleDef.title_id": "titles have no name to make an enum of",
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
    assert not _bare(tuple[EnumOrInt[empire_core.enums.Kingdom], ...])
    assert not _bare(tuple[EnumOrInt["QuestId"], ...])
    assert not _bare(tuple[int | float | None, ...])
