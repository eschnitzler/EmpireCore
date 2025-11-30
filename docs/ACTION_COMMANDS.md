# Action Commands Guide

## Overview

EmpireCore now supports sending game actions such as attacks, resource transports, building upgrades, and unit recruitment.

⚠️ **WARNING:** These commands directly interact with the game. Use responsibly and only on accounts you own.

---

## Available Actions

### 1. Send Attack

Launch an attack from your castle to a target area.

```python
await client.send_attack(
    origin_castle_id=16654591,
    target_area_id=16654500,
    units={
        620: 10,  # 10 of unit type 620
        614: 5    # 5 of unit type 614
    },
    kingdom_id=0
)
```

**Parameters:**
- `origin_castle_id` (int): Your attacking castle ID
- `target_area_id` (int): Target area/castle ID
- `units` (Dict[int, int]): Dictionary of unit_id -> count
- `kingdom_id` (int, optional): Kingdom ID (default: 0)

**Returns:** `bool` - True if command sent successfully

**Raises:** `ActionError` if attack fails

---

### 2. Send Transport

Send resources from one castle to another.

```python
await client.send_transport(
    origin_castle_id=16654591,
    target_area_id=16654705,
    wood=1000,
    stone=500,
    food=200
)
```

**Parameters:**
- `origin_castle_id` (int): Your sending castle ID
- `target_area_id` (int): Receiving area/castle ID
- `wood` (int, optional): Amount of wood (default: 0)
- `stone` (int, optional): Amount of stone (default: 0)
- `food` (int, optional): Amount of food (default: 0)

**Returns:** `bool` - True if command sent successfully

**Raises:** `ActionError` if transport fails or no resources specified

---

### 3. Upgrade Building

Build or upgrade a building in your castle.

```python
await client.upgrade_building(
    castle_id=16654591,
    building_id=10,
    building_type=None  # Only needed for new construction
)
```

**Parameters:**
- `castle_id` (int): Your castle ID
- `building_id` (int): Building ID to upgrade
- `building_type` (int, optional): Building type (for new buildings)

**Returns:** `bool` - True if command sent successfully

**Raises:** `ActionError` if upgrade fails

---

### 4. Recruit Units

Train/recruit units in your castle.

```python
await client.recruit_units(
    castle_id=16654591,
    unit_id=620,
    count=10
)
```

**Parameters:**
- `castle_id` (int): Your castle ID
- `unit_id` (int): Unit type ID to recruit
- `count` (int): Number of units to recruit

**Returns:** `bool` - True if command sent successfully

**Raises:** `ActionError` if recruitment fails

---

## Complete Example

```python
import asyncio
from empire_core import EmpireClient
from empire_core.config import EmpireConfig

async def automated_actions():
    config = EmpireConfig(username="player", password="password")
    client = EmpireClient(config)
    
    try:
        # Login
        await client.login()
        await asyncio.sleep(2)
        
        # Get castle info
        await client.get_detailed_castle_info()
        await asyncio.sleep(1)
        
        player = client.state.local_player
        castle_id = list(player.castles.keys())[0]
        
        # Example 1: Send resources to another castle
        await client.send_transport(
            origin_castle_id=castle_id,
            target_area_id=16654705,
            wood=1000,
            stone=500
        )
        print("✅ Transport sent!")
        
        # Example 2: Recruit units
        await client.recruit_units(
            castle_id=castle_id,
            unit_id=620,  # Unit type 620
            count=5
        )
        print("✅ Units recruited!")
        
        # Example 3: Upgrade a building
        await client.upgrade_building(
            castle_id=castle_id,
            building_id=10  # Town Hall
        )
        print("✅ Building upgrade started!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await client.close()

asyncio.run(automated_actions())
```

---

## Error Handling

All action commands raise `ActionError` on failure:

```python
from empire_core.exceptions import ActionError

try:
    await client.send_attack(
        origin_castle_id=123,
        target_area_id=456,
        units={620: 10}
    )
except ActionError as e:
    print(f"Attack failed: {e}")
```

---

## Validation

Actions are validated before sending:

- **send_attack**: Requires at least one unit
- **send_transport**: Requires at least one resource
- **recruit_units**: Requires count > 0

---

## Best Practices

### 1. Check Resources Before Acting

```python
castle = player.castles[castle_id]
if castle.resources.wood >= 1000:
    await client.send_transport(castle_id, target, wood=1000)
```

### 2. Verify Movement Capacity

```python
movements = client.state.movements
if len(movements) < 5:  # Assuming max 5 movements
    await client.send_attack(...)
```

### 3. Add Delays Between Actions

```python
await client.send_transport(...)
await asyncio.sleep(1)
await client.recruit_units(...)
```

### 4. Use Event Handlers for Confirmations

```python
@client.event
async def on_att(event):
    """Confirm attack sent"""
    print(f"Attack confirmed: {event.payload}")
```

---

## Unit IDs Reference

Common unit IDs (may vary by kingdom):
- `620`: Militia
- `614`: Swordsman  
- `611`: Bowman
- `629`: Cavalry

*Check your game data or building IDs for accurate unit types*

---

## Building IDs Reference

Common building IDs:
- `10`: Town Hall
- `614`: Barracks
- `651`: Farm
- `649`: Quarry
- `648`: Sawmill

*Building IDs can be found in castle.buildings list*

---

## Safety Notes

⚠️ **Important:**
- Test on development accounts first
- Actions are **irreversible**
- Validate inputs carefully
- Monitor server responses
- Respect rate limits
- Don't use for cheating or exploits

---

## Troubleshooting

**Action doesn't execute:**
- Check if you have sufficient resources
- Verify castle/area IDs are correct
- Ensure you're logged in
- Check for cooldowns or restrictions

**ActionError raised:**
- Read the error message for details
- Verify your account has permission
- Check if target is valid
- Ensure units/buildings exist

---

## Future Enhancements

Planned features:
- [ ] Response validation (wait for server confirmation)
- [ ] Resource availability checking
- [ ] Distance/travel time calculations
- [ ] Batch action support
- [ ] Action queueing system

---

For more examples, see `test_actions.py` and `examples/` directory.
