# Goodgame Empire - Game Mechanics Reference

Based on: https://goodgameempire.fandom.com/wiki/GoodGame_Empire_Wiki

## 🏰 Core Game Concepts

### Castles
- **Main Castle**: Your starting castle, cannot be lost
- **Outposts**: Additional castles you can conquer (up to 4 initially, more with Glory)
- Each castle has:
  - **Keep**: Central building, determines castle level
  - **Resources**: Wood, Stone, Food (production buildings)
  - **Buildings**: Military, resource production, defensive
  - **Units**: Trained troops for attack/defense
  - **Wall**: Defensive strength

### Resources
1. **Wood** - From Woodcutter
2. **Stone** - From Quarry  
3. **Food** - From Farm
4. **Gold** - Taxed from population
5. **Rubies** - Premium currency

### Buildings
- **Keep**: Castle level (0-70+)
- **Barracks**: Train troops
- **Wall**: Defense strength
- **Castle Yard**: Build decorations
- **Resource Buildings**: Woodcutter, Quarry, Farm
- **Housing**: Cottages for population
- **Defense**: Towers, walls, traps

### Units
- **Unit ID 620**: Militia (basic infantry)
- **Unit Types**:
  - Infantry (swords, spears)
  - Cavalry (mounted units)
  - Ranged (bows, crossbows)
  - Siege (rams, catapults)
  - Special units (various kingdoms)

### Kingdoms
- **Green Kingdom** (KID: 0) - Basic units
- **Ice Kingdom** (KID: 2) - Ice units
- **Sand Kingdom** (KID: 1) - Desert units  
- **Fire Kingdom** (KID: 3) - Lava units

## ⚔️ Combat System

### Attack Types
- **Regular Attack**: Siege enemy castles
- **Plunder**: Raid for resources
- **Scout**: Spy on enemy defenses
- **Reinforce**: Support allies

### Movement Types (TT values)
- `1`: Attack
- `2`: Scout
- `11`: Return
- Transport types (need to document)

### Barbarian Camps
- **Type ID 32**: Barbarian camps
- Safe to attack (don't retaliate)
- Drop loot and resources
- Good for farming/training

### Combat Resolution
- Defender advantage
- Wall strength matters
- Unit counters (infantry > cavalry > ranged > infantry)
- Morale system
- Commander bonuses

## 🎯 Quest System

### Quest Types
- **Daily Quests**: Reset daily
- **Main Quests**: Story progression
- **Side Quests**: Optional objectives
- **Alliance Quests**: Group activities

### Quest Rewards
- Resources
- Rubies
- Items
- XP

## 👥 Alliance System

### Features
- Alliance chat
- Member management
- Diplomacy (war, peace, NAP)
- Alliance fortress
- Shared objectives

### Ranks
- Leader
- Co-leader  
- Officer
- Member

## 📊 Player Progression

### Experience & Levels
- **Level**: Player level (1-70+)
- **XP**: Experience points
- **Legendary Level**: Post-70 progression
- Glory points

### Advancement
- Upgrading Keep increases castle level
- Castle level unlocks new buildings/units
- Glory unlocks special features
- Achievements give bonuses

## 🎲 Game Events

### Event Types
- **Castellan Events**: Special missions
- **Kingdom Events**: Server-wide
- **Seasonal Events**: Limited time
- **Alliance Events**: Group challenges

### Event Rewards
- Special units
- Decorations
- Resources
- Rubies

## �� Economy

### Resource Production
- Base production from buildings
- Modifiers from research/items
- Population affects production
- Storage capacity limits

### Trading
- **Market**: Trade resources
- **Alliance Market**: Trade with members
- Resource exchange rates

### Premium Features
- Rubies for instant completion
- Premium items
- Cosmetic decorations
- Time skips

## 🛡️ Defense

### Defensive Structures
- **Wall**: Main defense
- **Towers**: Shoot at attackers
- **Traps**: Hidden defenses
- **Moat**: Slows attackers

### Defensive Strategy
- Wall strength crucial
- Unit composition matters
- Commander placement
- Keep troops garrisoned

## 📍 Map System

### Map Objects
- **Player Castles**: Type varies
- **Barbarian Camps**: Type 32
- **Robber Barons**: Type varies
- **NPC Castles**: Type varies
- **Resources**: Trees, mines, etc.

### Coordinates
- X, Y grid system
- Kingdom determines map section
- Distance affects travel time

## ⏱️ Time Mechanics

### Building Times
- Varies by building level
- Can be reduced with rubies
- Commander skills reduce time
- Events may have bonuses

### Travel Times
- Based on distance
- Unit speed varies
- Can be calculated: `distance / speed`

### Training Times
- Unit type dependent
- Barracks level affects
- Can queue multiple units

## 🎁 Items & Boosters

### Item Types
- **Instant Build**: Complete construction
- **Resource Packages**: Instant resources
- **Speed Ups**: Reduce timers
- **Boosts**: Increase production/combat

### Commander Items
- Equipment sets
- Skill books
- Special abilities

## 📈 Strategy Tips (from Wiki)

### Early Game
1. Focus on resource production
2. Upgrade Keep steadily
3. Train basic troops
4. Complete quests
5. Join active alliance

### Mid Game
1. Expand to outposts
2. Specialize castles
3. Research technologies
4. Build strong army
5. Participate in events

### Late Game
1. Max out buildings
2. Legendary levels
3. Alliance warfare
4. Event participation
5. Glory advancement

## 🔍 Important for Bot Development

### Key Mechanics to Implement
1. **Resource Management**
   - Track production rates
   - Calculate time to capacity
   - Optimize collection

2. **Building Queue**
   - Track upgrades in progress
   - Calculate completion times
   - Prioritize upgrades

3. **Unit Training**
   - Queue management
   - Resource requirements
   - Training times

4. **Attack System**
   - Target finding (barbarians safe)
   - Unit composition
   - Travel time calculation
   - Wave coordination

5. **Quest Automation**
   - Daily quest completion
   - Reward collection
   - Progress tracking

### Bot-Friendly Activities
- ✅ **Barbarian Farming**: Safe, profitable
- ✅ **Resource Collection**: Essential
- ✅ **Quest Completion**: Rewards
- ✅ **Building Upgrades**: Progression
- ⚠️ **Player Attacks**: Risky, can cause retaliation
- ⚠️ **Alliance Wars**: Requires coordination

### Rate Limiting Considerations
- Login cooldowns (we've observed)
- Action spam detection
- Reasonable delays between actions
- Human-like behavior patterns

## 📚 Resources for Development

### Official Resources
- Wiki: https://goodgameempire.fandom.com/wiki/GoodGame_Empire_Wiki
- Forums: Community discussions
- In-game help

### Useful Wiki Pages
- Units list
- Buildings list
- Research tree
- Event calendar
- Map information

---

**Note**: This is a living document. Update as we discover more through testing and wiki research.


---

## 📚 Additional Wiki Resources

### Secondary Wiki: https://goodgameempirewiki.wordpress.com/

This WordPress-based wiki provides additional detailed information:

#### Key Resources Available
- **Unit Details**: Comprehensive unit stats tables
- **Building Data**: Upgrade costs and requirements
- **Combat Mechanics**: Detailed battle calculations
- **Resource Production**: Production rate formulas
- **Research Tree**: Technology unlocks
- **Commander System**: Skills and equipment
- **Event Guides**: Seasonal and special events

#### Useful Sections to Explore
1. **Units Section**
   - Full unit stats (attack, defense, speed, cost)
   - Training times
   - Unit counters and effectiveness
   - Special abilities by kingdom

2. **Buildings Section**
   - Upgrade costs per level (1-70+)
   - Build time formulas
   - Production rates by level
   - Requirements and prerequisites
   - Space requirements

3. **Combat Section**
   - Battle algorithm details
   - Wall effectiveness
   - Unit counter system
   - Morale mechanics
   - Commander bonuses

4. **Economy Section**
   - Resource production formulas
   - Tax rates and population
   - Market exchange rates
   - Trade routes

5. **Strategy Guides**
   - Optimal build orders
   - Army compositions
   - Farming strategies
   - Defense setups

#### Data Extraction Priorities

**High Priority - Needed for Bot:**
1. ✅ Unit costs (W, S, F) - For training decisions
2. ✅ Unit speeds - For travel time calculations
3. ✅ Building costs by level - For upgrade planning
4. ✅ Production rates - For resource optimization
5. ⏳ Unit stats (attack/defense) - For combat calculator

**Medium Priority - Nice to Have:**
6. Training times - For queue management
7. Build times - For construction planning
8. Commander skills - For advanced optimization
9. Research costs - For tech tree
10. Event schedules - For automation timing

**Low Priority - Future Features:**
11. Decorations and cosmetics
12. Achievement requirements
13. Glory system details
14. Alliance fortress mechanics

#### Web Scraping Strategy

For extracting data from both wikis:

```python
# Pseudo-code for data extraction
import requests
from bs4 import BeautifulSoup

def scrape_unit_data():
    """
    Extract unit data from wiki tables.
    
    Target fields:
    - Unit ID (internal game ID)
    - Name
    - Cost (wood, stone, food)
    - Training time
    - Speed
    - Carrying capacity
    - Attack/Defense values
    """
    # Implementation needed
    pass

def scrape_building_data():
    """
    Extract building upgrade costs.
    
    Target fields:
    - Building type
    - Level (1-70+)
    - Cost (wood, stone, food, gold)
    - Build time
    - Production rate (if applicable)
    """
    # Implementation needed
    pass
```

#### Known Unit IDs (from testing)
- **620**: Militia (infantry, basic unit)
  - Cost: W:10, F:10
  - Training time: ~30 seconds (estimated)
  - Speed: Slow
  - Good for: Early game, farming weak barbarians

#### Known Building Types
From our `dcl` responses, we see:
- **BL**: Building list with IDs and levels
- Buildings tracked by internal ID
- Need to map ID to building type from wiki

#### Map Object Types (from testing)
- **Type 32**: Barbarian camps (safe to attack)
- **Type ?**: Player castles
- **Type ?**: Robber barons
- **Type ?**: NPC castles
- Need comprehensive list from wiki

---

## 🎯 Action Items from Wiki Research

### Immediate (This Week)
1. [ ] Create unit database from wiki data
   - Start with basic units (militia, swordsman, archer)
   - Focus on cost, speed, carry capacity
   - Store as JSON or SQLite

2. [ ] Create building cost tables
   - Focus on resource buildings (woodcutter, quarry, farm)
   - Keep levels 1-20 (most relevant)
   - Include build times

3. [ ] Map object type reference
   - Document all map object types
   - Create enum for easy reference
   - Add to state management

### Short Term (Next 2 Weeks)
4. [ ] Combat calculation data
   - Unit attack/defense values
   - Wall effectiveness formulas
   - Counter system multipliers

5. [ ] Production formulas
   - Base production rates
   - Level multipliers
   - Population effects

6. [ ] Research tree data
   - Technology costs
   - Research times
   - Unlock requirements

### Long Term (Month)
7. [ ] Commander system
   - Skill tree data
   - Equipment stats
   - Bonus calculations

8. [ ] Event mechanics
   - Event types and rewards
   - Participation requirements
   - Optimal strategies

9. [ ] Alliance features
   - Fortress mechanics
   - Shared technologies
   - Diplomatic options

---

## 📝 Data Schema for Extracted Information

### Units Table
```python
{
    "unit_id": 620,
    "name": "Militia",
    "kingdom": "green",  # or 0
    "type": "infantry",
    "cost": {
        "wood": 10,
        "stone": 0,
        "food": 10,
        "gold": 0
    },
    "training_time": 30,  # seconds
    "speed": 5,  # tiles per hour
    "carry_capacity": 50,  # resources
    "attack": 5,
    "defense": 3,
    "health": 100,
    "special_abilities": []
}
```

### Buildings Table
```python
{
    "building_id": 1,
    "name": "Woodcutter",
    "type": "resource",
    "max_level": 70,
    "levels": [
        {
            "level": 1,
            "cost": {"wood": 100, "stone": 50},
            "build_time": 60,  # seconds
            "production": 10  # per hour
        },
        # ... more levels
    ]
}
```

### Map Objects Reference
```python
{
    "type_id": 32,
    "name": "Barbarian Camp",
    "description": "NPC enemy, safe to attack",
    "can_attack": True,
    "retaliates": False,
    "loot": "resources and items",
    "levels": [1, 2, 3, 4, 5, 10, 15, 20, 25, 30]
}
```

---

## 🔗 Combined Wiki Strategy

### Use Fandom Wiki For:
- Quick reference
- General mechanics
- Strategy guides
- Community discussions

### Use WordPress Wiki For:
- Detailed data tables
- Precise statistics
- Formula documentation
- Advanced mechanics

### Cross-Reference:
- Verify data between both sources
- Fill gaps from one wiki with the other
- Note discrepancies (may be from game updates)
- Prefer more recent/updated source

---

**Last Updated**: 2025-11-30
**Sources**: 
- https://goodgameempire.fandom.com/wiki/GoodGame_Empire_Wiki
- https://goodgameempirewiki.wordpress.com/

