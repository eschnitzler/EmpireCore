---
description: The mailbox, reading, sending, archiving and deleting mail, and battle reports.
---

# Messages

`client.messages.mailbox` is the mailbox as the login data and the server's
`sne` pushes left it, in the order the messages first arrived. Reading it costs no request; reading a
message's body does.

```python
for message in client.messages.mailbox:
    if message.subject is not None and not message.is_read:
        body = client.messages.read(message.message_id).decoded_body
        print(message.sender_name, message.subject, body)
        client.messages.mark_read(message.message_id)
```

`mark_read` marks the mailbox's own copy read too, as the game client does.

## Send, archive and delete

```python
client.messages.send_message("SomePlayer", "Hello", "Want to trade?")

client.messages.archive(message_id)            # the archive holds 20
client.messages.delete(message_id)
read = [m.message_id for m in client.messages.mailbox if m.is_read]
client.messages.delete_many(read)
```

`send_message` raises `ValueError` for what the game client would not send: an
empty receiver, a subject over 20 characters, or a text over 1300 characters or
with fewer than 3 that are not whitespace.

## New mail

```python
client.messages.on_new_messages(lambda event: print("new mail", event))
```

The callback runs after the mailbox is updated, for the login data's section
and every push after it. Remove it with `client.messages.on_new_messages.remove(callback)`.

Spy reports arrive as mail too; [`client.spy.get_report`](spy.md#reports)
reads one by its message id.

## Battle reports

Every attack on or by you leaves a battle log in the mailbox. `is_battle_log`
finds them, and `battle_log_header()` reads what the header says without a
request: the area type, the attack type, how it ended and whose area it was.

```python
from empire_core.enums import LogResult

for message in client.messages.mailbox:
    header = message.battle_log_header()
    if header is not None and header.result is LogResult.DEFENDER_FAILED:
        report = client.messages.get_battle_report(message.message_id, detail="full")
        short = report.short
        for player in short.losers:
            print(player.player_id, player.lost_units, player.loot)
```

`detail` picks how much is read:

| `detail` | Requests | What it adds |
| --- | --- | --- |
| `"short"` (default) | `bls` | Who fought and won, the loot, the area, the commander and castellan |
| `"middle"` | `bls`, then `blm` | Each wave's soldiers and tools per flank, the courtyard, support tools |
| `"full"` | `bls`, then `blm` and `bld` | Every unit and tool type per flank and wave |

Lost amounts come as 0 or negative numbers, as the server sends them. The unit
lists keep the server's order; the game client sorts them by its unit order.

A log the server no longer has raises `MessageUnavailableError` (error 66 or
225), as for mail.

Forward one to other players, e.g. your alliance's other members, as the game client offers:

```python
me = client.state.local_player.id
members = [m.player_id for m in client.alliance.get_local_members() if m.player_id != me]
client.messages.forward_battle_report(message_id, members)
```

**API:** [`MessagesService`](../reference/messages.md#empire_core.messages.service.MessagesService)
