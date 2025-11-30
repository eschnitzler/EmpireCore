# Event System

EmpireCore is fundamentally event-driven. This document outlines the events hierarchy and usage.

## Event Loop Integration
All events are dispatched on the standard Python `asyncio` event loop. Handlers can be synchronous (`def`) or asynchronous (`async def`).

## Event Hierarchy

All events inherit from `EmpireEvent`.

*   `EmpireEvent`
    *   `ConnectionEvent`
        *   `ConnectedEvent`
        *   `DisconnectedEvent`
    *   `GameEvent`
        *   `LoginSuccessEvent`
        *   `MapUpdateEvent`
    *   `PlayerEvent`
        *   `LevelUpEvent`
        *   `ResourceUpdateEvent`
    *   `CombatEvent`
        *   `AttackIncomingEvent`
        *   `AttackFinishedEvent`
        *   `EspionageReportEvent`

## Subscription Model

### Decorator Style (Preferred)
```python
@client.event
async def on_attack_incoming(event: AttackIncomingEvent):
    pass
```

### Explicit Registration
```python
def my_handler(event):
    pass

client.add_listener(AttackIncomingEvent, my_handler)
```

### One-time Listeners
Useful for waiting for a specific response.

```python
# Wait for the next map update
event = await client.wait_for(MapUpdateEvent, timeout=10.0)
```

## Custom Events

Users can define their own events if they build plugins or extensions on top of the library.

```python
class BotStuckEvent(EmpireEvent):
    pass

client.dispatch(BotStuckEvent())
```
