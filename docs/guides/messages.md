---
description: The mailbox, reading, sending, archiving and deleting mail.
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
and every push after it. Remove it with `remove_new_messages_callback`.

Spy reports arrive as mail too; [`client.spy.get_report`](spy.md#reports)
reads one by its message id.

**API:** [`MessagesService`](../reference/messages.md#empire_core.messages.service.MessagesService)
