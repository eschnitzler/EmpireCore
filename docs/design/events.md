# Events & Callbacks

EmpireCore is **not** an asyncio event-bus library. Reacting to the game is
done through two synchronous, thread-based mechanisms:

1. **State callbacks** — high-level, semantic events derived from parsed state.
2. **Connection subscriptions** — low-level, per-command packet feeds.

Both run on background threads, so a handler may make blocking calls (e.g.
send a request and wait for its response) without stalling the receive loop.

## 1. State Callbacks

Registered on `client.state`. These are the events most bots want:

```python
def on_attack(movement):
    print(f"Incoming attack {movement.MID} from {movement.source_player_name}")

client.state.on_incoming_attack(on_attack)
client.state.on_movement_arrived(lambda movement_id: ...)
client.state.on_movement_recalled(lambda movement_id: ...)
```

* `on_incoming_attack` fires once per newly seen hostile attack (not on every
  refresh, and not for your own outgoing attacks).
* Callbacks are dispatched on a thread pool that is created lazily and survives
  disconnect/reconnect, so registered handlers keep working after a re-login.
* Unregister with `remove_incoming_attack_callback` /
  `remove_movement_arrived_callback` / `remove_movement_recalled_callback`.

## 2. Connection Subscriptions

For raw packet streams, subscribe by command id. Alliance chat has a
convenience wrapper:

```python
# Convenience: alliance chat packets
def on_chat_packet(packet):
    ...
client.subscribe_alliance_chat(on_chat_packet)
client.unsubscribe_alliance_chat(on_chat_packet)

# Or subscribe to any command directly
client.connection.subscribe("acm", on_chat_packet)
```

Service-level typed callbacks are also available where a service parses the
packet for you:

```python
def on_message(msg):   # AllianceChatMessageResponse
    print(f"[{msg.player_name}] {msg.decoded_text}")
client.alliance.on_chat_message(on_message)
```

Unlike waiters (one-shot request/response), subscribers receive **every**
matching packet and are never consumed.

## Disconnects

`Connection.on_disconnect` fires on an *unexpected* connection loss (not on a
clean `client.close()`), which you can use as a signal to re-login:

```python
client.connection.on_disconnect = lambda: print("dropped — reconnecting…")
```

## Request/Response (not an event)

A one-off "wait for the reply to this command" is not modelled as an event —
use the blocking request path, which returns the parsed response or raises a
typed error:

```python
resp = client.request(GetPlayerInfoRequest(PID=123), GetPlayerInfoResponse)
```
