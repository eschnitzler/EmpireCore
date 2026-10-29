---
description: Read units, buildings, researches, quests and the other game-data tables by their generated ids.
---

# Game data

The game's static data (unit stats, buildings, researches, quests, effects, ...)
comes from the items file. `GameData` holds it as typed tables, each keyed by its
[generated id enum](game-data-ids.md):

```python
from empire_core.gamedata import Building, DailyQuestId, Event, General, QuestId, Research, Unit

data = client.load_game_data()

data.units[Unit.MEAD_RANGER_L6].range_attack              # UnitStats
data.buildings[Building.KEEP_L1].might_value              # BuildingDef
data.researches[Research.STRENGTH_TRAINING_L1].level  # ResearchDef
data.events[Event.NOMAD_INVASION_5].kingdoms                # EventDef
data.quests[QuestId.BUY_RUBIES].conditions                # QuestDef
data.daily_quests[DailyQuestId.LOGIN].trigger_kingdom     # DailyQuestDef
data.generals[General.TORIL].max_level                    # GeneralDef
```

The enums are `IntEnum`s, so a plain id from a packet indexes a table too
(`data.buildings[171]`), and `.get()` returns `None` for an id the data lacks.
A row whose id the enum does not have yet (items newer than the library) is
still loaded, keyed by its plain int; loading such items logs one warning for
the version. Several rows at once are a comprehension:
`[data.units[u] for u in (Unit.MEAD_RANGER_L6, Unit.VETERAN_SABERSLASHER)]`.

Every table keyed by a generated enum is a read-only `Table` that validates a
row the first time it is read, so loading the game data stays cheap:
`data.buildings[171]` validates one building, while iterating a table or
taking its `len()` validates every row once. Besides the ones above, these are
`tools`, `effects`, `effect_types`, `currencies` (by `CurrencyId`),
`general_abilities`, `general_skills`, `legend_skills`, `raid_bosses`,
`global_effects`, `construction_items`, `loot_boxes`, `loot_box_types`,
`equipment_groups`, `difficulty_types`, `titles`, `gems`, `sceat_skills`,
`horses`, `achievements`, `alliance_crest_layouts` and `alliance_crest_colors`.
`scaling_camps` is a `Table` keyed by plain id, and so are
`daimyo_castle_contracts` and `daimyo_township_contracts`, the daimyo event's
alliance contracts (`DaimyoContractDef`) in the items' order.

`rewards` is a `Table` by `RewardId`: each `RewardDef` holds the `Collectable`s
a reward gives, read from the items' reward columns as the client reads them.
`data.reward_list(ids)` gives what several rewards hold, in order, as the
client's `getListByIdArray` does. A campaign and a title turn their rewards
into collectables with it:

```python
campaign.rewards()                  # (Collectable(kind=UNITS, item=Unit..., amount=5), ...)
data.titles[title].rewards()
data.reward_list([40054, 170])          # any reward ids
```

Public calculators, reward readers and effect formatters use the process's game
data automatically. For an offline or separately parsed dataset, pass the optional
`game_data=data` keyword. For example, `campaign.rewards(game_data=saved_data)`.

Cached player reads are available directly as `client.player.spent_skill_points`,
`client.player.available_skill_points`, and `client.player.title_ids`. They use
that client's configured game data and send no game requests. The point reads
are `None` until a skill list arrives; title reads require login data.

The cache keeps each table as JSON text until the table is first read, so
loading from the cache does not build rows nobody reads.

`relic_effects` and `alliance_buffs` are plain dicts by plain id, validated at
load, as the game names none of their rows. An alliance buff's `series_id` is
the `AllianceBuffType` it is a level of. `equipment_effects` is keyed by
`EquipmentEffect`, named from the effect each gives, its bonus and its wearer;
`daimyo_castles` and `daimyo_townships` by `DaimyoCastle` and `DaimyoTownship`,
and the Battle for Berimond's `berimond_special_camps` by `BerimondSpecialCamp`.
`raw("bossdungeons")` returns a table that is not modeled yet, exactly as the
items file has it.

A row's bonuses are its `effects`, typed `EffectValue`s: the effect and the
numbers of its value, one tuple per `#`-separated part.
`empire_core.combat.effect_value_bonuses` turns them into the `Bonus`es the
combat maths reads:

```python
from empire_core.gamedata import ConstructionItem

item = data.construction_items[ConstructionItem.KEEP_UNIT_WALL_COUNT_G6_L1]
[(e.effect_id, e.value) for e in item.effects]   # [(Effect.UNIT_WALL_ABSOLUTE_AMOUNT, 3)]
```

Text columns the client compares against fixed values are enums from
`empire_core.enums`: a unit's `role` is a `UnitRole`, a tool's `category` a
`ToolSide` and `tool_category` a `ToolCategory`, a building's `group` a
`BuildingGroup`, a quest condition's `condition_type` a `QuestConditionType`,
and so on. A value the client does not name (a newer release, or a type only the
server reads) stays plain text, so `data.units_by_role(UnitRole.MELEE)` and
comparisons keep working.

Nothing has to be loaded first: an API that needs the data loads it on first
use (`GameData.require()`), from the disk cache when present and from the CDN
otherwise, and raises `GameDataNotLoadedError` (with the failure as its cause)
only when it cannot be loaded. That first use may wait on a large download, so
call `client.load_game_data()` before timing-sensitive work to take the cost up
front. It calls `GameData.load`, which keeps the data for the process: a process
downloads it once per game version, caches it on disk (safe for several
processes sharing the cache directory), and after a failed download leaves the
CDN alone for five minutes. When the CDN is down, a load returns the data
already in memory and raises `NetworkError` only when there is none.
`refresh=True` downloads it again.

Everything else reads that one copy:

- `client.game_data` is what the process loaded, so a `GameData.load()` made
  without the client (in a script with no client yet, say) serves its services
  too. Assigning `client.game_data` attaches data of your own, such as
  `GameData.parse` of a saved payload, to that client only.
- `GameData.loaded()` returns it, or `None`, without touching the network.
- `get_troop_ids()`, `count_troops()` and `Movement.troop_count` read it, and
  load it on first use when nothing has been loaded yet.

!!! warning "Shared and read-only"

    Every `GameData.load()` in the process, `client.game_data` and the troop
    counts share one instance. Read from it, never change its tables or rows:
    a change shows up for every other caller.

## Lookups by name

For data newer than the generated enums, look a row up by the key that names it:

```python
toril = data.general("Toril")           # None when no general has that name
if toril is not None:
    client.commanders.assign_general(commander_id=3, general=toril)
    skill = data.general_skill(toril.general_id, "AspectoftheDragon", 1)

surge = data.general_ability("PowerSurge", 1)
tablets = data.currency("KT")            # by JSONKey
boss = data.raid_boss("Necromancer")
data.legend_skill(0, 1, 1)               # tree, group, level
data.effect_type("fameDefenseBonus")
data.unit("MeadRanger", 6)               # type and level
```

A miss returns `None`. A key that matches several rows raises
`AmbiguousLookupError`, whose `ids` lists them:

```python
from empire_core import AmbiguousLookupError

try:
    data.global_effect("SpeedBoost")
except AmbiguousLookupError as e:
    print(e.ids)                          # two global effects share that name
```

Units and tools have no unique name either. Their type repeats across levels,
and event variants share a type with no level to tell them apart. Horses have
no named lookup: the game tells them apart only by their place in the travel
dialog, so use `get_horse` or the `Horse` enum.

**API:** [`GameData`](../reference/gamedata.md#empire_core.gamedata.data.GameData)

## Migrating explicit game-data arguments

Calculators and formatters no longer require a positional dataset. For example,
`commander_bonuses(data, commander)` becomes `commander_bonuses(commander)`;
`skills.available_points(data)` becomes `client.player.available_skill_points`.
To keep a separately parsed dataset, use `commander_bonuses(commander, game_data=data)`
or `skills.available_points(game_data=data)`. The same keyword applies to title,
chronicle, reward, tooltip and wave-filling helpers.

The `EffectResolver` constructor also loads data automatically when omitted.
Tool-strategy callbacks still receive their calculator's resolved dataset, so
custom strategies work with the same data as the rest of a fill.

## Unit and tool asset paths

```python
from empire_core.gamedata import AssetIndex, Tool, Unit

path = client.game_data.unit_asset_path(Unit.MEAD_RANGER_L6)
path = client.game_data.tool_asset_path(Tool.RAM)
```

These return the exact CDN-relative client bundle path from `ItemVersions`,
for example `itemassets/Units/Workshop/Workshop_Unit_Ram/Workshop_Unit_Ram--1573584429307`.
The extensionless bundle path is not an individual PNG URL. Tools whose client
class is `ToolUnitVO` use `Unknown_Unit_Tools` when their own asset is absent;
other unit classes do not use this fallback. Unknown IDs and missing final
assets raise `KeyError`.

The first resolution lazily reads the official client page, discovers its
versioned DLL, and extracts `ItemVersions` without executing JavaScript. It
caches the index in memory and on disk by DLL hash, independently of the items
JSON version. Imports and loading `GameData` do not fetch the asset index.
Later resolutions check the page again at most once a minute and switch to a
new DLL's index when the client updates; while the page cannot be read, the
loaded index is kept. `AssetIndex.load(refresh=True)` checks now and downloads
the index again. With nothing loaded, a network failure raises `NetworkError`
and backs off for five minutes, and malformed metadata or an index in an
unsupported format raises `ValueError`.

For reproducible offline resolution, inject a saved mapping and its DLL hash:

```python
index = AssetIndex(saved_paths, version=saved_dll_hash)
path = client.game_data.unit_asset_path(Unit.MEAD_RANGER_L6, index=index)
```
