---
description: Look up generals, skills, currencies, units and more by the key that names them.
---

# Lookups by name

Game-data ids (generals, skills, currencies, effects, units and tools) change
from one client release to the next, so look them up by the key that names
them rather than hard-coding ids.

```python
data = client.load_game_data()

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

`load_game_data()` is explicit on purpose: the items data is a large download,
and nothing else in the library fetches it behind your back. It is cached on
disk per game version, so later calls are cheap. `refresh=True` downloads it
again, and the data stays on `client.game_data`.

## Misses and ambiguous keys

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

## Full rows for generated ids

With the [generated id enums](game-data-ids.md), `record` returns the row for
a member, and `records` a list of rows in order:

```python
from empire_core.gamedata import Building, General, Research, Unit

data.record(Unit.MEAD_RANGER_L6)                  # UnitStats
data.record(General.TORIL)                        # GeneralDef
data.record(Research.RECRUITMENT_SPEED_G41_L1)    # the items row, as a dict
data.records([Unit.MEAD_RANGER_L6, Building.KEEP_L1])
```

Where `GameData` models the table, `record` returns the model: `UnitStats`,
`ToolStats`, `EffectDef`, `EffectTypeDef`, `CurrencyDef`, `GeneralDef`,
`GeneralAbilityDef`, `GeneralSkillDef`, `LegendSkillDef`, `RaidBossDef`,
`GlobalEffectDef` or `ConstructionItemDef`. A wall, gate or moat `Building`
gives its `FortificationDef`. Other buildings, researches, events, loot boxes,
equipment groups and difficulty types give the items row as a dict, and an id
the data lacks gives `None`.

**API:** [`GameData`](../reference/gamedata.md#empire_core.gamedata.data.GameData)
