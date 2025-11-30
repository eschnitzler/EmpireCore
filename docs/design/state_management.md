# State Management

One of the biggest weaknesses of existing bots is their statelessness—they query the server for every small decision. EmpireCore introduces a persistent, reactive state model.

## The `World` Object

The `World` singleton acts as the central database for the library instance.

```python
class World:
    me: Player
    map: GameMap
    alliances: Dict[int, Alliance]
    castles: Dict[int, Castle]
```

## Entity Tracking

To avoid memory bloat and ensure consistency, we use an **Identity Map** pattern.

*   If `AttackEvent` references Castle ID `101`, the library looks up `101` in `World.castles`.
*   If it exists, the existing `Castle` object is updated.
*   If not, a new `Castle` object is created and cached.

This ensures that if you have a reference to `my_castle` in one part of your code, it will automatically reflect updates received from a background packet in another part of the code.

## Reactive Updates

State objects should not just be data containers; they should be observable.

### Observer Pattern
We will use a lightweight implementation of the Observer pattern or C#'s `INotifyPropertyChanged` equivalent.

```python
class Castle:
    def __init__(self):
        self._food = 0
        self._events = EventEmitter()

    @property
    def food(self):
        return self._food

    @food.setter
    def food(self, value):
        old = self._food
        self._food = value
        self._events.emit("change", "food", old, value)
```

### Usage in Logic
This allows users to write logic that reacts to state rather than packets:

```python
# Triggers whenever food changes, regardless of which packet caused it
@castle.on("change")
def check_food(attr, old, new):
    if attr == "food" and new < 1000:
        send_emergency_food()
```

## Data Persistence (Optional)

The State Manager should have hooks to dump/load state from a local SQLite database (like `Dreambot.py` does) to persist knowledge across restarts (e.g., remembering enemy castle locations).
