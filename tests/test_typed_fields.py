"""
No model field is a bare id list or a raw row: ids are enums, rewards and goods are Collectables.

A field typed ``Any``, or a list, tuple or set of ``int`` or ``Any`` (nested ones too), fails
unless :data:`ALLOWED` names it with a reason: player ids, coordinates, a request's wire shape,
counters, a value that is opaque. ``EnumOrInt[...]`` is an enum, not an int, and ``int | float``
a number, not an id. The ``#320`` entries
are older fields that issue still has to type; the list is the remaining debt, so an entry
whose field is gone or typed fails too.
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
        if set(get_args(annotation)) == {int, float}:
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
