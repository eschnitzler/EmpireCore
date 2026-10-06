---
description: Alliance chat, help requests, members, applications, ranks and the treasury.
---

# Alliance

`client.alliance` covers your own alliance and looks up others.

## Chat

```python
client.alliance.send_chat("Hello alliance!")   # special characters are encoded for you

for entry in client.alliance.get_chat_log():
    print(f"{entry.player_name}: {entry.decoded_text}")
```

State keeps the chat history from the login data on, with every message the
server sends after it, oldest first, so reading it costs no request:

```python
for entry in client.state.get_alliance_chat():
    print(entry.sent_at, entry.player_name, entry.decoded_text)
```

Subscribe to new messages with a typed callback, and detach it again with
`client.alliance.on_chat_message.remove(on_message)`:

```python
def on_message(msg):                  # an AllianceChatMessageResponse
    print(f"[{msg.player_name}] {msg.decoded_text}")

client.alliance.on_chat_message(on_message)
```

!!! warning "Chat callbacks run on the receive thread"

    Unlike the [state callbacks](movements.md), chat callbacks are called on
    the thread that reads the socket. Keep them short: a call that waits for a
    reply raises `ReceiveThreadError` there. Hand real work to another thread.

## Help requests

`client.alliance.help_requests` is the alliance help list. The login data fills
it and the server's pushes keep it current, so reading it costs no request.

```python
client.alliance.help_all()            # help every request on the list
```

To pick requests yourself, skip the ones the client skips: those you already
helped, your own, and finished ones. A request is finished once its progress
reaches its help type's `maxHelpersCount` in the items data's
`alliancehelprequests` table (3 for most types, 5 for healing and 20 for loop
recruiting in items version 786.03):

```python
max_helpers = {1: 3, 2: 5, 3: 3, 4: 3, 5: 20, 6: 3}
player = client.state.get_local_player()
my_id = player.id if player else None

for request in client.alliance.help_requests:
    finished = request.progress >= max_helpers.get(request.help_type, 0)
    if not (request.already_confirmed or finished or request.player_id == my_id):
        client.alliance.help_member(request)
```

`on_help_update(callback)` calls you after each change to the list. Ask for
help yourself with `request_build_help`, `request_repair_help`,
`request_recruit_help` and `request_heal_help`.

## Members and other alliances

```python
members = client.alliance.get_local_members()
online = client.alliance.get_local_online_members()

for result in client.alliance.search_alliances("PACT"):
    info = client.alliance.get_alliance_info(result.alliance_id)
```

`get_members(alliance_id)` and `get_online_members(alliance_id)` do the same
for any alliance, and `client.alliance.local_alliance_id` is your own alliance's
id, or `None` outside one. Outside an alliance the two `get_local_*` calls raise
`NotInAllianceError` without sending anything, so "no alliance" is never
mistaken for an alliance without members. `search_alliances` returns an empty
list when nothing matches.

A member's protection times count from when the reply was read (`received_at`,
in `time.monotonic()` seconds): `revenge_protection_end` and
`beginner_protection_end` stay fixed, and
`remaining_revenge_protection_seconds()` counts down; `has_bird` and
`has_beginner_protection` turn False once the time runs out. To store or show
an end, `revenge_protection_end_utc()` and `beginner_protection_end_utc()` give
it as a UTC `datetime` (or `None`), counted from the wall-clock time stamped at
the same read (`received_at_wall`), so they do not move between calls. A player
from `client.player.get_player_info` has the same on its `owner`.

`client.state.get_own_alliance()` is your alliance's details as the login data
and the replies since left them (a chat message marks its sender online), or
`None` outside one, without a request.

## Applications, ranks and the treasury

```python
from empire_core.alliance import AllianceDonation, AllianceRank

for application in client.alliance.get_applications().applications:
    client.alliance.answer_application(application.player_id, accept=True)

client.alliance.set_rank(player_id, AllianceRank.SERGEANT)
client.alliance.donate(castle_id, AllianceDonation(wood=1000))
```

Also on the service: `invite`, `kick_member`, `leave`, `change_diplomacy`,
`refuse_diplomacy`, `set_auto_war` and `send_newsletter`.

All of these, and `get_chronicle`, are about your own
alliance, which the client only offers inside one. Outside an alliance they raise
`NotInAllianceError` without sending anything, and so does a server answer of
`ALLI_NOT_FOUND` (your alliance id was stale). `set_rank` returns `None` for
`NO_CHANGE`, the rank the member already has; `kick_member`, `set_rank` and
`refuse_diplomacy` otherwise return the alliance the reply carries.
`get_subscriber_count` is sent outside an alliance too, as the client sends it.

## Map bookmarks

`get_bookmarks` lists your own bookmarks and your alliance's. Your own are a
friend or an enemy; the alliance ones (free attack, defend, attack order) need
the right to manage bookmarks. A name is 1 to 30 characters
(`BOOKMARK_NAME_MAX_LENGTH`) and goes out as typed.

```python
from empire_core.alliance import BookmarkType

added = client.alliance.add_bookmark(640, 655, "Farm", BookmarkType.PLAYER_FRIEND)
client.alliance.change_bookmark(640, 655, "Barn", BookmarkType.PLAYER_FRIEND)
client.alliance.delete_bookmark(added)
```

`add_bookmark` and `change_bookmark` return the bookmark the reply carries and
raise `CommandError` when the server refuses, such as `BOOKMARK_ALREADY_ADDED`,
`BOOKMARK_MAX_ENTRYS` (50 own) or `NO_SELF_TARGET`; the alliance list of 20
has `ALLIANCE_BOOKMARK_MAX_ENTRYS`.
`change_bookmark` changes only your own bookmarks, as the client does.
`delete_bookmark` deletes an own bookmark by its position and an alliance one
by its id, and returns False when the server refuses. An alliance attack order
takes `attack_in_seconds` (an hour to just under a day) and `attacker_ids`.
Adding or deleting an alliance bookmark outside an alliance raises
`NotInAllianceError` without sending anything.

## Runnable example

```python title="examples/alliance_chat.py"
--8<-- "examples/alliance_chat.py"
```

**API:** [`AllianceService`](../reference/alliance.md#empire_core.alliance.service.AllianceService)
