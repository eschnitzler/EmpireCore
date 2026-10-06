---
description: Reading and collecting the free daily rewards: the login bonus, the startup bonus, lost and found, the activity chest and the weekly honour reward.
---

# Daily rewards

`client.rewards` reads each free reward the way its dialog does, and collects it
with the request the dialog's button sends. None of these requests costs
anything: they carry only ids, so there is no `spend_rubies` to pass.

The client enables a collect button only when the read says the reward is
there; the library leaves that check to you and to the server. A collect the
server refuses returns False, or raises `CommandError` where the call returns
the reply's data.

## Daily login bonus

From 1200 XP (`LOGIN_BONUS_REQUIRED_XP`) the client reads the login bonus after
every login. Below it the server does not answer at all, so the login bonus calls
raise `LoginBonusUnavailableError` without sending anything, as they do before
the player data has arrived. Today is one day of a seven-day week: pick one of its rewards, and
collect the alliance and VIP bonus where you have one.

```python
from empire_core.rewards import LoginBonusSpecial

bonus = client.rewards.get_login_bonus()
today = bonus.today
if today is not None and today.picked is None:
    bonus = client.rewards.collect_login_bonus(today.rewards[0])

in_alliance = client.alliance.local_alliance_id is not None
if in_alliance and bonus.has_anything_to_collect(in_alliance=True):
    client.rewards.collect_login_bonus_special(LoginBonusSpecial.ALLIANCE)
```

Each reward is a `Collectable`: its `kind` (`CollectableKind.COINS`,
`UNITS`, ...), its `amount`, and the `item` it names, such as the `Unit` of a
units reward or the `Currency` of a minute skip. A pick goes out under
`send_key`, the key the client sends: mostly the one it came under, but a
booster of a type of its own (`B` with a glory or XP booster id, ...) goes
under that type's key, a hero equipment under `RE`, and a currency under its
own key. A units reward sends its unit's id with the pick. A reward under a
key the client has no type for (`HF`, the hidden food some quests grant) is
kept as `CollectableKind.OTHER`; the client drops it and never offers it, so
its pick raises `ValueError` unsent.

The alliance bonus needs an alliance: outside one `collect_login_bonus_special`
raises `NotInAllianceError` without sending. The client offers the VIP bonus
only while VIP is active, which the library does not track, so that one is left
to the server.

## Startup bonus

The beginner rewards of an account's first days:

```python
startup = client.rewards.get_startup_bonus()
if startup.collectable:
    client.rewards.collect_startup_bonus()
```

## Lost and found

Items that found no room in their inventory wait here until they expire:

```python
for item in client.rewards.get_lost_and_found():
    print(item.reward.kind, item.reward.item, round(item.remaining_seconds()))
    client.rewards.collect_lost_and_found(item.item_id)
```

The server refuses an item whose inventory is still full.

## Activity chest

The server pushes the activity chest (`uac`) and nothing asks for it, so
`client.rewards.activity_chest` is None until the first push and only as fresh
as the last one. `on_activity_chest` calls you with each push.

```python
chest = client.rewards.activity_chest
if chest is not None and chest.is_ready():
    next_chest = client.rewards.open_activity_chest()
```

The client opens the chest only once it is ready, so `open_activity_chest`
raises `ValueError` without sending while `activity_chest` is None or not
ready. The server sends no reply to the open; `open_activity_chest` returns the
next chest it pushes instead (a push still naming the opened chest, ready, does
not count), or None when none came within `timeout` (10 seconds by default).

## Weekly honour reward

Last week's honour rank earns a reward to redeem:

```python
honor = client.rewards.get_weekly_honor()
if honor.is_ready:
    after = client.rewards.redeem_weekly_honor()
    print(after.currencies)
```

The client offers it only to a player with honour. The reply's coins and rubies
reach `client.state`.
