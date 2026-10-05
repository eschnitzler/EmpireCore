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
`remove_chat_message_callback`:

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
id, or `None` outside one.

A member's protection times count from when the reply was read (`received_at`,
in `time.monotonic()` seconds): `revenge_protection_end` and
`beginner_protection_end` stay fixed, and
`remaining_revenge_protection_seconds()` counts down; `has_bird` and
`has_beginner_protection` turn False once the time runs out. A player from
`client.player.get_player_info` has the same on its `owner`.

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
`refuse_diplomacy`, `set_auto_war`, `send_newsletter` and `get_bookmarks`.

## Runnable example

```python title="examples/alliance_chat.py"
--8<-- "examples/alliance_chat.py"
```

**API:** [`AllianceService`](../reference/alliance.md#empire_core.alliance.service.AllianceService)
