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
data.events[Event.NOMAD_INVASION].kingdoms                # EventDef
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

The other tables: `tools`, `effects`, `effect_types`, `currencies`,
`general_abilities`, `general_skills`, `legend_skills`, `raid_bosses`,
`global_effects`, `construction_items`, `loot_boxes`, `loot_box_types`,
`equipment_groups` and `difficulty_types` by their enums; `titles`,
`scaling_camps`, `gems`, `equipment_effects`, `relic_effects`,
`alliance_buffs`, `sceat_skills` and `horses` by plain id, as their rows have no
name to make an enum of. `raw("specialcamps")` returns a table that is not
modeled yet, exactly as the items file has it.

A row's bonuses are its `effects`, typed `EffectValue`s: the effect and the
numbers of its value, one tuple per `#`-separated part.
`empire_core.combat.effect_value_bonuses` turns them into the `Bonus`es the
combat maths reads:

```python
from empire_core.gamedata import ConstructionItem

item = data.construction_items[ConstructionItem.BARRACKS_COST_G1_L1]
[(e.effect_id, e.value) for e in item.effects]
```

`load_game_data()` is explicit on purpose: the items data is a large download.
The one other reader is `Movement.troop_count`, which loads it on first use when
nothing has yet. Both go through `GameData.load`, so a process downloads the
data once per game version: it is kept in memory, cached on disk (safe for
several processes sharing the cache directory), and after a failed download the
CDN is left alone for five minutes. When the CDN is down, a load returns the data
already in memory and raises `NetworkError` only when there is none.
`refresh=True` downloads it again, and the data stays on `client.game_data`.

!!! warning "Shared and read-only"

    Every `GameData.load()` in the process, `client.game_data` and the troop
    counts share one instance. Read from it, never change its tables or rows:
    a change shows up for every other caller.

## Lookups by name

For data newer than the generated enums, look a row up by the key that names it:

```python
toril = data.general("Toril")
client.skills.assign_general(commander_id=3, general_id=toril.general_id)

surge = data.general_ability("PowerSurge", 1)
skill = data.general_skill(toril.general_id, "AspectoftheDragon", 1)
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
no named lookup yet; use `get_horse` by id.

**API:** [`GameData`](../reference/gamedata.md#empire_core.gamedata.data.GameData)
