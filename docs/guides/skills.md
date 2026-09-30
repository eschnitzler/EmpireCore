---
description: Generals, their abilities and skills, and the player's legend and sceat skills.
---

# Skills and generals

`client.skills` covers the generals you own, which you assign to commanders,
and the player's own skill trees.

## Generals

```python
generals = client.skills.get_generals()
for general in generals.generals:
    print(general.general_id, general.star_level, general.ability_ids)
```

Give a commander a general, or take it away with `general_id=-1`, then choose
the general's abilities as `(slot_id, ability_id)` pairs:

```python
client.skills.assign_general(commander_id=3, general_id=101)
client.skills.set_abilities(101, [(1, 12), (2, 15)])
```

`unlock_skill`, `reset_skills` and `add_xp` change a general's skill tree the
same way. General, ability and skill ids differ between client releases, so
look them up by name:

```python
data = client.load_game_data()
toril = data.general("Toril")
client.skills.assign_general(commander_id=3, general_id=toril.general_id)
```

See [Lookups by name](game-data.md) for the rest.

## Player skills

```python
skills = client.skills.get_skills()
print(skills.legend_skill_ids, skills.total_points, skills.reset_count)
```

The server sends the skill list again after every change. To follow it, register
a callback; it runs for the reply to `get_skills()` too:

```python
client.skills.on_skill_list(lambda s: print("skills now", s.sceat_skill_ids))
```

Remove it with `remove_skill_list_callback`.

**API:** [`SkillsService`](../reference/commanders.md#empire_core.commanders.service.SkillsService)
