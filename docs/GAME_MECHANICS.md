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

