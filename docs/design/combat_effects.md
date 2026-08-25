# Combat Effects Reference

**Purpose:** everything that can change the outcome — or the composition — of an
attack in Goodgame Empire, catalogued for the attack auto-fill port.

**Sources.** Three artefacts, all from the live client release:

| Short name | File | What it is |
|---|---|---|
| BUNDLE | `Game.bundle.<hash>.js` | the Empire HTML5 client |
| DLL | `dll/ggs.dll.<hash>.js` | shared constants: `CombatConst`, `TravelConst`, `EffectConst`, `CommKeys` |
| ITEMS | `items.json` | the game-data tables, ~233 top-level keys |

Every claim below names the client symbol or the ITEMS table it came from.
Claims that are not directly readable from those files are marked
**(inferred)**, and where nothing could be established the entry says so rather
than guessing.

## 0. Scope caveat — read this first

**Everything in sections 1, 5 and 6 is the client's *preview* computation.** The
server resolves the actual battle, and the server code is not in these files.
The client builds preview value objects (`AttackerFlankEffectVO`,
`DefenderFlankEffectVO`) to display expected strength and to drive auto-fill; it
never simulates the fight. Where the client has three implementations of the
same quantity — `FightScreenHelper`, `AttackDialogHelper.calculateToolsInfo`,
`CastleFightDialog.calculateToolsInfo` — they do not agree, and which one
matches the server cannot be determined from these files.

For the auto-fill port this is mostly fine: the goal is to reproduce *which
units and tools the client would place*, and that decision is made entirely
client-side by the code documented here. It matters only if you try to predict
the battle result.

Two more scope notes:

- The client distinguishes three things all internally called "lord":
  **commander** (`CommanderVO`), **castellan** (`BaronVO`, `isBaron`), and
  **general** (`GeneralVO`, assigned *to* a commander). See
  `docs/design/game_bundle_analysis.md` §2.
- Flank constants are `ClientConstCastle.FLANK_LEFT` = 0, `FLANK_MIDDLE` = 1,
  `FLANK_RIGHT` = 2, `FLANK_YARD` = 3. "Front" and "middle" are the same flank;
  the effect types use both words.

---

## 1. What decides a wave

### 1.1 Number of waves

Two independent additions on top of a level-driven base.

**Base** — `CombatConst.getMaxWaveCount(userLevel, isConquerAttack)` (DLL
@2444371):

```
n = 1
for i = len(WAVE_UNLOCK_LEVEL)-1 down to 0:
    if userLevel >= WAVE_UNLOCK_LEVEL[i]: n = i+1; break
if isConquerAttack: n += CONQUERATTACK_ADDITIONAL_WAVES
```

with `CombatConst.WAVE_UNLOCK_LEVEL = [0, 13, 26, 51]` (DLL @2441005) and
`CombatConst.CONQUERATTACK_ADDITIONAL_WAVES = 2` (DLL @2447724). So 1 wave below
level 13, 2 from 13, 3 from 26, 4 from 51; +2 for a conquer attack.
`CombatConst.isConquerAttack(attackType)` returns true for
`ATTACK_TYPE_CAPITAL_CONQUER`, `ATTACK_TYPE_OUTPOST_CONQUER`,
`ATTACK_TYPE_VILLAGE_CONQUER`, `ATTACK_TYPE_KINGTOWER_CONQUER`.

**Legend-skill wave** — `CastleAttackArmyVO.init` (BUNDLE @6436915) adds
`CastleLegendSkillEffectsEnum.ADDITIONAL_WAVE` (id 22, ITEMS `legendskills`
`effectType` = `additionalWave`) through
`CombatConst.getMaxWaveCountWithBonus(userLevel, isConquer, legendBonus)`, but
only when **all** of these hold:

- `CastleModel.userData.isLegend`
- `attackerLevel >= PlayerConst.LEVEL_CAP`
- the target is a non-NPC player (`!PlayerHelper.isNPCPlayer(ownerInfo.playerID)`)
  **or** an `AAlienInvasionMapobjectVO`

**Equipment / general waves and support-tool waves** —
`AttackDialogWaveHandler.initWaves` (BUNDLE @11855241):

```
lordWaves = int(CastleEffectsHelper.getTotalEffectValue(
                selectedLord.getUniqueBoni(false, EFFECT_TYPE_ADDITIONAL_WAVE,
                                          targetArea.areaType, strategy, true)).strength)
lordWaves += attackInfoVO.supportItemContainer
               .getTotalBonusByToolEffect(ToolEffectType.ADDITIONAL_WAVE)
```

then waves are added or removed until the dialog's count matches.
`strategy = LordEffectHelper.getFilterStrategyAttackOrDefence(targetArea.ownerInfo.playerID, true)`.

The support-tool term is easy to miss: **support tools grant attack waves.**
`ToolEffectType.ADDITIONAL_WAVE` (BUNDLE @1212883, constructed as
`new ToolEffectType(0, "additionalWaves", icon, true)`) is bound to effect type
156 by `EffectTypeEnum.EFFECT_TYPE_ADDITIONAL_WAVE.mapToolEffectType(...)`
(BUNDLE @887665). `CastleFightItemContainer.getTotalBonusByToolEffect` (BUNDLE
@2481148) sums `getBonusByEffect(e)` over the container, multiplying by
`slot.getAmount()` for offensive tools and **not** multiplying for
`isDefensive` tools.

Effect type 156 (`additionalWaves`) has shipped data in ITEMS `equipments` /
`equipment_effects` (7 rows), `generalSkills` (11 refs), `constructionItems`
(7 refs), `buildings.areaSpecificEffects` (3 refs), `units` (4 refs, i.e. the
support tools above) and `relicEffects` (1 row).

### 1.2 Per-flank unit capacity

`AttackDialogWaveHandler.updateMaxUnitCount` (BUNDLE @11856140) sets the
`maxItems` of each flank's unit container. The whole block is skipped when
`controller.selectedLord` is falsy.

```
strategy = LordEffectHelper.getFilterStrategyAttackOrDefence(targetArea.ownerInfo.playerID, true)

left.maxItems   = CombatConst.getAmountSoldiers(0, targetOwnerLevel, flankBonus, 0)
middle.maxItems = CombatConst.getAmountSoldiers(1, targetOwnerLevel, 0, frontBonus)
right.maxItems  = same as left
```

`CombatConst` (DLL @2442387), verbatim:

```
getMaxAttackers(level)          = level <= 69 ? min(260, 5*level + 8) : 320
getAmountSoldiersFlank(l, b)            = int(ceil(0.2 * getMaxAttackers(l) * (1 + b/100)))
getAmountSoldiersFlankWithoutBonus(l)   = int(ceil(0.2 * getMaxAttackers(l)))
getAmountSoldiersMiddle(l, b)           = int(ceil((getMaxAttackers(l)
                                            - 2*getAmountSoldiersFlankWithoutBonus(l))
                                            * (1 + b/100)))
getAmountSoldiers(which, l, flankB, midB) = which==1 ? getAmountSoldiersMiddle(l, midB)
                                                     : getAmountSoldiersFlank(l, flankB)
```

**The level argument is the *target owner's* level, not the attacker's.**

The two bonus terms come from `CastleEffectsHelper` (BUNDLE @562371, @562795):

```
getUnitsOnTheFlankBonusForAreaType(lord, area, isLegendaryFight, strategy) =
    int(getAccumulatedEquipmentBonusByEffectTypeForArea(
          lord, EFFECT_TYPE_ATTACK_UNIT_AMOUNT_FLANK /*28*/, area.areaType, true, strategy).strength)
  + int(isLegendaryFight ? legendSkillData.getTotalValueOfLegendSkillEffect(
          CastleLegendSkillEffectsEnum.ADDITIONAL_UNIT_AMOUNT_ON_FLANK) : 0)

getUnitsOnTheFrontBonusForAreaType(...) = same with EFFECT_TYPE_ATTACK_UNIT_AMOUNT_FRONT /*34*/
                                          and ADDITIONAL_UNIT_AMOUNT_ON_FRONT
```

`isLegendaryFight` is `AttackDialogHelper.isLegendaryFight`, a boolean the
dialog supplies. Note the source: `getAccumulatedEquipmentBonusByEffectTypeForArea`
reads **lord equipment only** (§3.1) — not research, titles, alliance buffs or
any other account-wide source.

### 1.3 Courtyard (reinforcement / yard) wave capacity

`AttackDialogWaveHandler.initWaves` (BUNDLE @11855241):

```
yardWaveContainer.maxItems = CombatConst.getMaxUnitsInReinforcementWave(
    CastleModel.userData.level,
    targetArea.isUnderConquerControl ? targetArea.minimumOwnerLevel : targetOwnerLevel,
    CastleEffectsHelper.getUnitsOnTheYardWaveBonusForAreaType(lord, targetArea, strategy),
    CastleEffectsHelper.getUnitsOnTheYardWaveBoostForAreaType(lord, targetArea, strategy))
```

`CombatConst.getMaxUnitsInReinforcementWave(myLevel, targetLevel, bonus, boost)`
(DLL @2443526):

```
int(round((20*sqrt(myLevel) + 50 + 20*targetLevel + bonus) * boost))
```

`bonus` is effect type 179 (`attackUnitAmountReinforcementBonus`, nominal);
`boost` is effect type 180 (`attackUnitAmountReinforcementBoost`) passed through
`EffectConst.boostToModifier` (DLL @2537352):

```
boostToModifier(pct) = max((BASE_BOOST_PERCENTAGE + pct) * TO_MULTIPLIER_FACTOR, 0)
                     = max((100 + pct) * 0.01, 0)
```

so a boost of 0 yields the multiplier 1.0. (`EffectConst.BASE_BOOST_PERCENTAGE = 100`,
`TO_MULTIPLIER_FACTOR = 0.01`, `DEFAULT_MODIFIER = 1` — DLL @2539546.)

### 1.4 Per-flank tool capacity

**This is not an effect type.** The catalog gap that said "no effect type
governs siege-tool capacity" is correct; the quantity is a level step function
plus one legend skill.

`CastleAttackWaveVO`'s constructor (BUNDLE ~@11520700):

```
n = 0
if target.ownerInfo
   and ((hasOtherPlayerInfo and not PlayerHelper.isNPCPlayer(playerID))
        or PlayerHelper.isNpcPvpPlayer(playerID))
   and targetLevel >= PlayerConst.LEVEL_CAP
   and CastleModel.userData.userLevel >= PlayerConst.LEVEL_CAP:
    n += legendSkillData.getTotalValueOfLegendSkillEffect(
             CastleLegendSkillEffectsEnum.ADDITIONAL_ATTACK_TOOL_AMOUNT_FLANK)   // id 21

maxTools = int(CombatConst.getTotalAmountToolsFlank(level, n))
```

`CombatConst.getTotalAmountTools(which, level, n)` (DLL @2443296), verbatim:

```
which == 1 (middle):  level<11 ? 10 : level<37 ? 20 : level<50 ? 30 : level<69 ? 40 : 50
otherwise  (flank):   level<37 ? 10 : level<50 ? 20 : level<69 ? 30 : int(ceil(40 + n))
```

so the legend bonus reaches the formula **only on flanks and only above level
69**. ITEMS `legendskills` carries 5 rows with
`effectType = additionalAttackToolAmountFlank` (skillIDs 206–210,
`skillTreeID` 0, tier 5, `effectValue` 2 each, `totalEffectValue` 2…10),
i.e. +2 per level to +10.

### 1.5 Slot counts and slot unlocking

Containers are built from `CombatConst.ITEMS_*` / `LEVELS_*` arrays. Examples
read verbatim from the DLL: `ITEMS_MIDDLEWALL_TOOLS = [1,1,1]` with
`LEVELS_MIDDLEWALL_TOOLS = [0,11,37]` (@2438660); `ITEMS_LEFTWALL_TOOLS = [2,2]`
with `LEVELS_LEFTWALL_TOOLS = [0,37]` (@2437956). The `ITEMS_*` value is the
`slotType` the slot accepts; the `LEVELS_*` value is the level at which that
slot unlocks.

`CastleFightItemVO.isUnlocked` (BUNDLE @1510053):

```
unlockLevel >= 0 ? unlockLevel >= itemLevel
                 : legendSkillData.isSkillActive(legendSkillData.getSkillByID(unlockSkillID))
```

`CastleFightItemContainer.freeItems` (BUNDLE @2479106) is `maxItems - sumOfItems`,
and every fill loop gates on `slot.isFree() && slot.isUnlocked()`.

### 1.6 Attacker melee / range multipliers

There are **two different multipliers** in the client and they are not the same
formula. Do not unify them.

**(a) The auto-fill / fight-screen multiplier** —
`FightScreenHelper.getAttackerFlankEffectVO(attackInfo, lord, isLegendaryFight, flank, attackInfoVO)`
(BUNDLE @2327140). Verbatim structure:

```
meleeMult = 1, rangeMult = 1
wallRed = gateRed = moatRed = defRangeRed = 0

if lord:
    wallRed  += equip(EFFECT_TYPE_WALL_REDUCTION /*19*/, target.areaType).strength / 100
    gateRed  += equip(EFFECT_TYPE_GATE_REDUCTION /*20*/, ...).strength / 100
    moatRed  += equip(EFFECT_TYPE_MOAT_REDUCTION /*21*/, ...).strength / 100
    meleeMult += CastleEffectsHelper.getFullAttackBonusForLordByFlankAndAreaType(lord, areaType, flank, true)
    rangeMult += ...(same, isMelee=false)

if isLegendaryFight:
    wallRed  += legend WALL_REDUCTION  / 100
    gateRed  += legend GATE_REDUCTION  / 100
    moatRed  += legend MOAT_REDUCTION  / 100
    meleeMult += legend ATTACK_MELEE_BONUS / 100
    rangeMult += legend ATTACK_RANGE_BONUS / 100

tools = flank's own tool container items, CONCATENATED with attackInfoVO.supportItemContainer.items
for each tool:
    wallRed     += tool.wallBonus     * tool.inventoryAmount
    gateRed     += tool.gateBonus     * tool.inventoryAmount
    moatRed     += tool.moatBonus     * tool.inventoryAmount
    defRangeRed += tool.defRangeBonus * tool.inventoryAmount
    rangeMult   += tool.offRangeBonus * tool.inventoryAmount
    meleeMult   += tool.offMeleeBonus * tool.inventoryAmount
    ab = tool.getBonusByEffect(ToolEffectType.ATTACK_BONUS)
    rangeMult += ab * tool.inventoryAmount
    meleeMult += ab * tool.inventoryAmount

return new AttackerFlankEffectVO(meleeMult, rangeMult, wallRed, gateRed, moatRed, defRangeRed)
```

Two consequences worth stating plainly: **support tools contribute to every
flank**, and the constructor is given only six arguments, so
`_defenderMeleeReduction` starts at 0 on this path (see §5.4).

`CastleEffectsHelper.getFullAttackBonusForLordByFlankAndAreaType(lord, areaType, flank, isMelee, strategy)`
(BUNDLE @564608) is, verbatim:

```
( equip(EFFECT_TYPE_ATTACK_BONUS /*36*/).strength
+ equip(isMelee ? EFFECT_TYPE_MELEE_BONUS /*9*/ : EFFECT_TYPE_RANGE_BONUS /*10*/).strength
+ equip(isMelee ? EFFECT_TYPE_OFFENSIVE_MELEE_BONUS /*23*/
                : EFFECT_TYPE_OFFENSIVE_RANGE_BONUS /*24*/).strength ) / 100
```

Note what is **absent**: the `flank` argument is accepted and never used, and
types 33 / 53 / 54 (yard / front / flank attack boosts) do **not** appear.

**(b) The displayed army-strength aggregation** —
`CastleFightItemContainer.getAttackMeleeValue` / `getAttackRangeValue`
(BUNDLE @2472400–2475750). Per soldier stack:

```
g = lordVO.getEffectValue(EFFECT_TYPE_ATTACK_BONUS_UNIT /*148*/, areaType, spaceID, wodId, strategy)
C = 1 + ( equip 36
        + equip (23 melee | 24 range)
        + (isYard  ? equip 33 : 0)
        + (isFlank ? equip 54 : 0)
        + (isFront ? equip 53 : 0) ) / 100
m = legend/100: (ATTACK_MELEE_BONUS id 4 | ATTACK_RANGE_BONUS id 7)
              + ATTACK_BONUS id 43
              + (isYard ? ATTACK_YARD_BONUS id 15 : 0)
total += (buffedAttack + g) * amount * (C + m)
```

So path (b) includes 33/53/54 and the legend terms, and path (a) includes
9/10 and the tool terms. **A porter that merges them gets one of the two paths
wrong.** Auto-fill uses path (a).

### 1.7 A unit's own attack value

`SoldierUnitVO.buffedMeleeAttack` (BUNDLE @1519216) and `buffedRangeAttack`
(@1519510):

```
buffedMeleeAttack = _meleeAttack > 0
    ? _meleeAttack + int(CastleModel.globalEffectData.getBonusByEffectType(
          EFFECT_TYPE_ATTACK_BONUS_UNIT /*148*/, -1, -1, this.wodId))
    : 0
```

`_meleeAttack` / `_rangeAttack` are the raw ITEMS `units` columns `meleeAttack`
/ `rangeAttack` (`parseXmlNode` @1511500).

`GlobalEffectData.getBonusByEffectType` (BUNDLE @15672456) iterates **only**
`specialEventData.getActiveEventByEventId(EventConst.EVENTTYPE_GLOBAL_EFFECTS).globalEffectData`.
Research, buildings, alliance, VIP and subscription therefore do **not** feed
`buffedMeleeAttack` / `buffedRangeAttack`, even though ITEMS `researches`,
`subscriptionsBuffs`, `sceatSkills`, `constructionItems` and
`officersSchoolEffects` all contain type-148 rows. Their handling is not in the
client; calling them server-side is **(inferred)**.

The only rows the getter can see today are ITEMS `globalEffects` rows carrying
effect 273, format `"273&<wodId>+<strength>#<wodId>+<strength>"`:

| globalEffectID | name | value |
|---|---|---|
| 5 | attackBoostSpeermanBowman | `602+13#608+13` |
| 6 | attackBoostMaceCrossbowman | `603+20#607+20` |
| 7 | attackBoostValkyrieMeleeValkyrieRange | `22+35#23+35` |
| 8 | attackBoostMasterSwordsmanMasterArcher | `781+45#782+45` |
| 9 | attackBoostEliteRankrewardMeleeEliteRankrewardRange | `9+60#10+60` |

There is **no** `buffedMeleeDefence` / `buffedRangeDefence`. Grepping
`buffed[A-Za-z]*` in the bundle yields only `buffedMeleeAttack` (×11),
`buffedRangeAttack` (×11) and `buffedBonus` (×4). Defence uses the raw
`meleeDefence` / `rangeDefence` columns.

### 1.8 The stack score auto-fill actually ranks

`AttackerFlankEffectVO.getSoldierStackAttackValue(unitVO, count)` (BUNDLE
@4955179), verbatim:

```
i = unitType == UNIT_TYPE_SOLDIER_MELEE ? int(buffedMeleeAttack * _attackerMeleeBonus)
  : unitType == UNIT_TYPE_SOLDIER_RANGE ? int(buffedRangeAttack * _attackerRangeBonus)
  : 0
return i * min(count, unitVO.inventoryAmount)
```

The call site passes `count = container.freeItems`
(`pickSoldierStack` @11700100). **This scores a stack, not a unit:** a
high-attack unit you own 3 of loses to a mediocre unit you own 200 of, and the
winner changes as the flank fills up.

`unitType` is a **string**: `ClientConstCastle.UNIT_TYPE_SOLDIER_MELEE =
"soldierMelee"`, `UNIT_TYPE_SOLDIER_RANGE = "soldierRange"` (BUNDLE
@149818–150528). `SoldierUnitVO.unitType` is derived from the ITEMS `units`
column `role` (`"melee"` / `"ranged"`).

### 1.9 Melee-vs-range choice, and the unit-candidacy gates

`StrongestDefenceCounterRatioConsideredFlankStrategy.pickSoldierStack` (BUNDLE
@11699042). A unit is a candidate only if it passes **all** of:

| Gate | Source |
|---|---|
| `isOffensive \|\| isAllround` | `BasicUnitVO` @2342309; `isAllround` = ITEMS `units` column `hybrid`; `isOffensive` = `fightType == FIGHTTYPE_OFF (0)` |
| `healingCostC1 == 0` or filter `c1` on | ITEMS `units.healingCostC1` |
| `healingCostC2 == 0` or filter `c2` on | ITEMS `units.healingCostC2` |
| `meadSupply == 0` or filter `mead` on | ITEMS `units.meadSupply` |
| `beefSupply == 0` or filter `beef` on | ITEMS `units.beefSupply` |
| melee unit → filter `melee` on; range unit → filter `range` on | `AutoFillOptions.UNIT_FILTER_*` |

`AutoFillOptions` (BUNDLE @3081127) defines
`UNIT_FILTER_MELEE = "melee"`, `UNIT_FILTER_RANGE = "range"`,
`UNIT_FILTER_C1 = "c1"`, `UNIT_FILTER_C2 = "c2"`, `UNIT_FILTER_MEAD = "mead"`,
`UNIT_FILTER_BEEF = "beef"`. `AttackDialogAutoFill.autoFillSelectedWaves`
(@11688652) calls `updateOptions()` (@11690900), which rewrites **only**
`fillLeftFlank` / `fillMiddleFlank` / `fillRightFlank` — every unit and tool
filter carries over from prior dialog state. A headless caller must set them
explicitly.

The melee/range decision, verbatim:

```
g = defenderVO ? defenderVO.getMeleeDefenceValue(0, attackerVO.defenderRangeReduction) : 0
C = defenderVO ? defenderVO.getRangeDefenceValue(attackerVO.defenderRangeReduction, 0) : 0
_ = 1; m = 1
if g + C > 0: _ = g/(g+C);  m = C/(g+C)
...
chosen = (bestMeleeScore * m >= bestRangeScore * _) ? bestMeleeWodId : bestRangeWodId
```

Two things to carry over exactly: only `defenderRangeReduction` is ever passed
(`defenderMeleeReduction` is never read here, even though tool placement has
been accumulating it), and the scores are **cross-weighted** — the melee
candidate is weighted by the *range* defence share and vice versa. Candidate
scans use strict `>`, so ties go to whichever unit the inventory iteration
reaches first.

### 1.10 The yard wave is scored differently

`AttackDialogAutoFill.autoFillYardWave` (BUNDLE @11689452) calls
`fillYardContainer` with **no attacker effect VO**; `AFillWaveStrategy.fillYardContainer`
(@11695934) passes `null`, and `pickSoldierStack` then does `t || (t = new AttackerFlankEffectVO())`.
The default constructor is `(e=1, t=1, i=0, n=0, o=0, a=0)` (BUNDLE @4955179),
so the courtyard wave is filled on **raw `buffedMeleeAttack` / `buffedRangeAttack`
with multipliers of exactly 1.0** and all reductions 0 — a different scoring
basis from the three flanks.

### 1.11 Defender quantities the fill reads

See §6 for the full defender side. The three the fill consumes are
`defenderWallBonus`, `defenderGateBonus`, `defenderMoatBonus` from
`FightScreenHelper.getDefenceBonuses`, and the four unit-strength sums plus two
bonus multipliers from `getDefendingUnitStrength`.

---

## 2. The effect type table

`EffectTypeEnum` is constructed as (BUNDLE, `function EffectTypeEnum(t,i,n,s)`):

```
_id              = t
_valueClass      = i || EffectValueSimple
_simpleValueTextID = n || GenericTextIds.VALUE_PERCENTAGE_ADD
_isMalusType     = s || false
```

so an entry with only an id is a percentage-valued scalar. Parsing
`EffectTypeEnum.__initialize_static_members` yields exactly **246 members**
(not 248 — the catalog's count was wrong), and the highest ability id actually
constructed is **1042**, not 1046.

ITEMS `effecttypes` has **239 rows** (`effectTypeID` / `sortCategory` /
`sortGroup` / `name`); `sortCategory` and `sortGroup` are UI grouping only.
ITEMS `effects` has 824 rows mapping a concrete effect instance to an
`effectTypeID` and a `capID`. The wire field name for an effect type id is
`CommKeys.EFFECT_TYPE_ID`.

**Id-space diffs** (both directions verified by set difference):

| | ids |
|---|---|
| In ITEMS `effecttypes`, not in the client enum (8) | 55 `lootBonusPvP`, 57 `enableBuildings`, 87 `unlockSkinIDs`, 153 `featureLoyaltyGift`, 155 `BGCollectorBoost`, 157 `burningChanceBonus`, 158 `tonicBoost`, 188 `CraftingQueueProductionBoost` |
| In the client enum, no `effecttypes` row (15) | −1 (sentinel), 61, 64, 1004, 1006, 1008, 1009, 1017, 1024, 1031, 1032, 1036, 1037, 1041, 1042 |
| In neither, i.e. holes in the 0…218 id space (8) | 62, 63, 65, 66, 67, 68, 159, 171 |

Note 62–68 *do* appear as `capID`s in `effectCaps` — that is a separate id space,
unrelated to these holes.

Where the two names differ, **treat the numeric id as authoritative**; which
side is stale is not established. The known mismatches are all abilities:
1010, 1011, 1012, 1029, 1040 (see §2.2).

### 2.1 Combat-relevant effect types

"Combat-relevant" here means: read by a combat or fill formula, or classified by
the client's own `CastleEffectsHelper.isAttackEffect` (BUNDLE @570005) /
`isDefenseEffect` (@568815). Those two classifiers are **UI classification only**
— no combat math reads them.

The classifiers additionally list these types, not tabulated below because no
combat or fill formula reads them: 3 `perceptionBonus`, 4 `fireBrigadeBoost`,
5 `occupationTimeReduction`, 17 `stealthBonus`, 18 `fireBoost`,
22 `magicFindBonus`, 25 `smashChance`, 27 `cooldownReduction`,
131 `nomadTabletBoost`, 133 `samuraiTokenBoost`.

#### Attacker strength and wall/gate/moat reductions

| id | client `EffectTypeEnum` member | items `effecttypes` name | value class | value text id | `effects` rows | capIDs used |
|---|---|---|---|---|---|---|
| 36 | `EFFECT_TYPE_ATTACK_BONUS` | `attackBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 25 | 99, 1011, 2007, 2117 |
| 23 | `EFFECT_TYPE_OFFENSIVE_MELEE_BONUS` | `offensiveMeleeBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 30 | 23, 43, 86, 99, 1001, … (14) |
| 24 | `EFFECT_TYPE_OFFENSIVE_RANGE_BONUS` | `offensiveRangeBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 33 | 24, 44, 86, 99, 1002, … (14) |
| 53 | `EFFECT_TYPE_ATTACK_BOOST_FRONT` | `AttackBoostFront` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 10 | 81, 99, 1012, 2007, 2117 |
| 54 | `EFFECT_TYPE_ATTACK_BOOST_FLANK` | `AttackBoostFlank` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 10 | 82, 99, 1013, 2007, 2117 |
| 33 | `EFFECT_TYPE_ATTACK_BOOST_YARD` | `attackBoostYard` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 29 | 57, 86, 99, 1009, 1106, … (13) |
| 9 | `EFFECT_TYPE_MELEE_BONUS` | `meleeBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 11 | 9, 99, 2103, 11005, 11103, 11203, 11306, 11407 |
| 10 | `EFFECT_TYPE_RANGE_BONUS` | `rangeBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 12 | 10, 99, 2108, 11006, 11104, 11204, 11307, 11408 |
| 19 | `EFFECT_TYPE_WALL_REDUCTION` | `wallReduction` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 25 | 19, 99, 1003, 1101, 1201, … (12) |
| 20 | `EFFECT_TYPE_GATE_REDUCTION` | `gateReduction` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 23 | 20, 99, 1004, 1102, 1202, … (12) |
| 21 | `EFFECT_TYPE_MOAT_REDUCTION` | `moatReduction` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 18 | 21, 99, 1005, 1108, 1209, … (12) |
| 148 | `EFFECT_TYPE_ATTACK_BONUS_UNIT` | `attackBonusUnit` | EffectValueMap | VALUE_PERCENTAGE_ADD *(default)* | 22 | 99 |
| 149 | `EFFECT_TYPE_SPEED_BOOST_UNIT` | `speedBoostUnit` | EffectValueMap | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |

#### Attacker capacity (slots, waves, loot)

| id | client `EffectTypeEnum` member | items `effecttypes` name | value class | value text id | `effects` rows | capIDs used |
|---|---|---|---|---|---|---|
| 28 | `EFFECT_TYPE_ATTACK_UNIT_AMOUNT_FLANK` | `attackUnitAmountFlank` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 29 | 45, 99, 1008, 1105, 1205, … (12) |
| 34 | `EFFECT_TYPE_ATTACK_UNIT_AMOUNT_FRONT` | `attackUnitAmountFront` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 24 | 46, 99, 1010, 1107, 1207, … (12) |
| 156 | `EFFECT_TYPE_ADDITIONAL_WAVE` | `additionalWaves` | EffectValueSimple *(default)* | VALUE_NOMINAL_ADD | 8 | 99 |
| 179 | `EFFECT_TYPE_ATTACK_UNIT_AMOUNT_REINFORCEMENT_BONUS` | `attackUnitAmountReinforcementBonus` | EffectValueSimple *(default)* | VALUE_NOMINAL_ADD | 2 | 99, 11413 |
| 180 | `EFFECT_TYPE_ATTACK_UNIT_AMOUNT_REINFORCEMENT_BOOST` | `attackUnitAmountReinforcementBoost` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 33 |
| 51 | `EFFECT_TYPE_ATTACK_SUPPORT_UNITS` | `AttackSupportUnits` | EquippableEffectValueSupportUnits | VALUE_NOMINAL_ADD | 9 | 99 |
| 37 | `EFFECT_TYPE_LOOT_CAPACITY` | `lootCapacity` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 4 | 99 |
| 114 | `EFFECT_TYPE_LOOT_CAPACITY_BOOST` | `lootCapacityBoost` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |

#### Defender strength

| id | client `EffectTypeEnum` member | items `effecttypes` name | value class | value text id | `effects` rows | capIDs used |
|---|---|---|---|---|---|---|
| 31 | `EFFECT_TYPE_DEFENSE_BONUS` | `defenseBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 15 | 99, 2104, 2109, 2113, 11009, … (9) |
| 6 | `EFFECT_TYPE_WALL_BONUS` | `wallBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 13 | 6, 99, 2100, 11002, 11101, 11201, 11304, 11405 |
| 7 | `EFFECT_TYPE_GATE_BONUS` | `gateBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 13 | 7, 99, 2105, 11003, 11102, 11202, 11305, 11406 |
| 8 | `EFFECT_TYPE_MOAT_BONUS` | `moatBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 10 | 8, 99, 2110, 11004, 11107, 11208, 11303, 11404 |
| 9 | `EFFECT_TYPE_MELEE_BONUS` | `meleeBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 11 | 9, 99, 2103, 11005, 11103, 11203, 11306, 11407 |
| 10 | `EFFECT_TYPE_RANGE_BONUS` | `rangeBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 12 | 10, 99, 2108, 11006, 11104, 11204, 11307, 11408 |
| 32 | `EFFECT_TYPE_DEFENSE_BOOST_YARD` | `defenseBoostYard` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 13 | 88, 99, 2112, 11008, 11106, 11206, 11309, 11410 |
| 49 | `EFFECT_TYPE_DEFENSE_BOOST_FRONT` | `DefenseBoostFront` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 4 | 79, 99, 2101, 11010 |
| 50 | `EFFECT_TYPE_DEFENSE_BOOST_FLANK` | `DefenseBoostFlank` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 4 | 80, 99, 2106, 11011 |
| 11 | `EFFECT_TYPE_NPC_DEFENSE_BONUS` | `npcDefenseBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 11 |

#### Defender capacity

| id | client `EffectTypeEnum` member | items `effecttypes` name | value class | value text id | `effects` rows | capIDs used |
|---|---|---|---|---|---|---|
| 12 | `EFFECT_TYPE_DEFENSE_UNIT_AMOUNT_WALL` | `defenseUnitAmountWall` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 11 | 87, 99, 2111, 11007, 11105, 11308 |
| 46 | `EFFECT_TYPE_DEFENSE_UNIT_AMOUNT_WALL_P_V_P` | `defenseUnitAmountWallPVP` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 3 | 99, 11205, 11409 |
| 47 | `EFFECT_TYPE_DEFENSE_SUPPORT_UNITS` | `DefenseSupportUnits` | EquippableEffectValueSupportUnits | VALUE_NOMINAL_ADD | 4 | 99 |
| 181 | `EFFECT_TYPE_DEFENSE_UNIT_AMOUNT_YARD_BONUS` | `defenseUnitAmountYardBonus` | EffectValueSimple *(default)* | VALUE_NOMINAL_ADD | 4 | 89, 99, 11414 |
| 182 | `EFFECT_TYPE_DEFENSE_UNIT_AMOUNT_YARD_BOOST` | `defenseUnitAmountYardBoost` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 2 | 32, 34 |
| 183 | `EFFECT_TYPE_ALLIANCE_DEFENSE_UNIT_AMOUNT_YARD_BONUS` | `allianceDefenseUnitAmountYardBonus` | EffectValueSimple *(default)* | VALUE_NOMINAL_ADD | 2 | 56, 99 |
| 184 | `EFFECT_TYPE_ALLIANCE_DEFENSE_UNIT_AMOUNT_YARD_BOOST` | `allianceDefenseUnitAmountYardBoost` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 32 |
| 194 | `EFFECT_TYPE_UNIT_WALL_ABSOLUTE_AMOUNT` | `unitWallAbsoluteAmount` | EffectValueSimple *(default)* | VALUE_NOMINAL_ADD | 1 | 99 |

#### Maluses an attacker applies to defender strength

| id | client `EffectTypeEnum` member | items `effecttypes` name | value class | value text id | `effects` rows | capIDs used |
|---|---|---|---|---|---|---|
| 215 | `EFFECT_TYPE_MELEE_DEFENSE_MALUS` | `meleeDefenseMalus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_SUBTRACT , isMalusType | 1 | 99 |
| 216 | `EFFECT_TYPE_MELEE_DEFENSE_MALUS_YARD` | `meleeDefenseMalusYard` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_SUBTRACT , isMalusType | 1 | 99 |
| 217 | `EFFECT_TYPE_RANGE_DEFENSE_MALUS` | `rangeDefenseMalus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_SUBTRACT , isMalusType | 1 | 99 |
| 218 | `EFFECT_TYPE_RANGE_DEFENSE_MALUS_YARD` | `rangeDefenseMalusYard` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_SUBTRACT , isMalusType | 1 | 99 |

#### March timing and cost

| id | client `EffectTypeEnum` member | items `effecttypes` name | value class | value text id | `effects` rows | capIDs used |
|---|---|---|---|---|---|---|
| 15 | `EFFECT_TYPE_SPEED_BONUS` | `speedBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 12 | 15, 99, 1006, 2003, 2120 |
| 44 | `EFFECT_TYPE_SPEED_BONUS_PVP` | `speedBonusPVP` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 2 | 99 |
| 38 | `EFFECT_TYPE_RETURN_TRAVEL_BOOST` | `returnTravelBoost` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 7 | 99, 2010, 2119 |
| 45 | `EFFECT_TYPE_RETURN_TRAVEL_BOOST_PVP` | `returnTravelBoostPVP` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |
| 39 | `EFFECT_TYPE_SUPPORT_SPEED_BONUS` | `supportSpeedBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 2 | 99 |
| 40 | `EFFECT_TYPE_STATIONING_SPEED_BONUS` | `stationingSpeedBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |
| 1 | `EFFECT_TYPE_CONQUER_SPEED_BONUS` | `conquerSpeedBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 1 |
| 26 | `EFFECT_TYPE_TRAVEL_COST_REDUCTION` | `travelCostReduction` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 4 | 26 |
| 41 | `EFFECT_TYPE_STATIONING_TRAVEL_COST_REDUCTION` | `stationingTravelCostReduction` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |
| 42 | `EFFECT_TYPE_SUPPORT_TRAVEL_COST_REDUCTION` | `supportTravelCostReduction` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |
| 43 | `EFFECT_TYPE_TRAVEL_COST_REDUCTION_PVP` | `travelCostReductionPVP` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 26 |
| 102 | `EFFECT_TYPE_UNIT_SPEED_BONUS` | `unitSpeedBoost` | EffectValueUnitSpeedBoost | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |
| 103 | `EFFECT_TYPE_TRAVEL_KINGDOM_TROOP_TIME_BOOST` | `travelKingdomTroopTimeBoost` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |

#### Loot, fame, honour

| id | client `EffectTypeEnum` member | items `effecttypes` name | value class | value text id | `effects` rows | capIDs used |
|---|---|---|---|---|---|---|
| 16 | `EFFECT_TYPE_LOOT_BONUS` | `lootBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 11 | 16, 99, 1007, 2004, 2118 |
| 55 | `— not in enum` | `lootBonusPvP` | — | — | 1 | 99 |
| 64 | `EFFECT_TYPE_ROYAL_LOOT_BONUS_ALLIANCE_CITY_COINS` | `— no row` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 0 | — (no `effects` row) |
| 75 | `EFFECT_TYPE_COIN_LOOT_BOOST` | `coinLootBoost` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 5 | 99, 1109 |
| 150 | `EFFECT_TYPE_LOOT_VALUE_BOOST_UNIT` | `lootValueBoostUnit` | EffectValueMap | VALUE_PERCENTAGE_ADD *(default)* | 5 | 99 |
| 154 | `EFFECT_TYPE_FAME_BOOST_UNIT` | `fameBoostUnit` | EffectValueMap | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |
| 13 | `EFFECT_TYPE_FAME_OFFENSE_BONUS` | `fameOffenseBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 6 | 13, 1211, 1711 |
| 0 | `EFFECT_TYPE_FAME_DEFENSE_BONUS` | `fameDefenseBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 5 | 0, 11210, 11412 |
| 14 | `EFFECT_TYPE_HONOR_BONUS` | `honorBonus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 2 | 14 |
| 168 | `EFFECT_TYPE_CURRENCY_LOOT_BOOST` | `currencyLootBoost` | EffectValueCurrencyBoost | VALUE_PERCENTAGE_ADD *(default)* | 10 | 99 |
| 2 | `EFFECT_TYPE_LOOT_REDUCTION` | `lootReduction` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 5 | 2, 2107, 11001 |
| 37 | `EFFECT_TYPE_LOOT_CAPACITY` | `lootCapacity` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 4 | 99 |

#### Courtyard kills and alliance-raid boss

| id | client `EffectTypeEnum` member | items `effecttypes` name | value class | value text id | `effects` rows | capIDs used |
|---|---|---|---|---|---|---|
| 172 | `EFFECT_TYPE_KILL_ATTACKING_MELEE_TROOPS_YARD` | `killAttackingMeleeTroopsYard` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |
| 173 | `EFFECT_TYPE_KILL_ATTACKING_RANGED_TROOPS_YARD` | `killAttackingRangedTroopsYard` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |
| 174 | `EFFECT_TYPE_KILL_ATTACKING_ANY_TROOPS_YARD` | `killAttackingAnyTroopsYard` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |
| 175 | `EFFECT_TYPE_KILL_DEFENDING_MELEE_TROOPS_YARD` | `killDefendingMeleeTroopsYard` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |
| 176 | `EFFECT_TYPE_KILL_DEFENDING_RANGED_TROOPS_YARD` | `killDefendingRangedTroopsYard` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |
| 177 | `EFFECT_TYPE_KILL_DEFENDING_ANY_TROOPS_YARD` | `killDefendingAnyTroopsYard` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |
| 197 | `EFFECT_TYPE_INFECTION_RATE_BASE_BONUS` | `infectionRateBaseBonus` | EffectValueSimple *(default)* | null , isMalusType | 1 | 99 |
| 198 | `EFFECT_TYPE_INFECTION_RATE_MELEE_BONUS` | `infectionRateMeleeBonus` | EffectValueSimple *(default)* | null , isMalusType | 1 | 99 |
| 199 | `EFFECT_TYPE_INFECTION_RATE_RANGE_BONUS` | `infectionRateRangeBonus` | EffectValueSimple *(default)* | null , isMalusType | 1 | 99 |
| 200 | `EFFECT_TYPE_INFECTION_RATE_WALL_BONUS` | `infectionRateWallBonus` | EffectValueSimple *(default)* | null , isMalusType | 1 | 99 |
| 201 | `EFFECT_TYPE_INFECTION_RATE_COURTYARD_BONUS` | `infectionRateCourtyardBonus` | EffectValueSimple *(default)* | null , isMalusType | 1 | 99 |
| 202 | `EFFECT_TYPE_INFECTION_RATE_BASE_MALUS` | `infectionRateBaseMalus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_SUBTRACT | 1 | 99 |
| 203 | `EFFECT_TYPE_INFECTION_RATE_MELEE_MALUS` | `infectionRateMeleeMalus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_SUBTRACT | 1 | 99 |
| 204 | `EFFECT_TYPE_INFECTION_RATE_RANGE_MALUS` | `infectionRateRangeMalus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_SUBTRACT | 1 | 99 |
| 205 | `EFFECT_TYPE_INFECTION_RATE_WALL_MALUS` | `infectionRateWallMalus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_SUBTRACT | 1 | 99 |
| 206 | `EFFECT_TYPE_INFECTION_RATE_COURTYARD_MALUS` | `infectionRateCourtyardMalus` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_SUBTRACT | 1 | 99 |
| 207 | `EFFECT_TYPE_RAID_BOSS_WALL_REGENERATION` | `raidBossWallRegeneration` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |
| 208 | `EFFECT_TYPE_RESERVE_UNIT_KILL` | `reserveUnitKill` | EffectValueSpawnReserveUnit | VALUE_PERCENTAGE_ADD *(default)* | 2 | 99 |
| 209 | `EFFECT_TYPE_RAID_BOSS_WALL_REGENERATION_DELAY_LEFT` | `raidBossWallRegenerationDelayLeft` | EffectValueSimple *(default)* | VALUE_NOMINAL_ADD | 2 | 99 |
| 210 | `EFFECT_TYPE_RAID_BOSS_WALL_REGENERATION_DELAY_FRONT` | `raidBossWallRegenerationDelayFront` | EffectValueSimple *(default)* | VALUE_NOMINAL_ADD | 2 | 99 |
| 211 | `EFFECT_TYPE_RAID_BOSS_WALL_REGENERATION_DELAY_RIGHT` | `raidBossWallRegenerationDelayRight` | EffectValueSimple *(default)* | VALUE_NOMINAL_ADD | 2 | 99 |
| 212 | `EFFECT_TYPE_RAID_BOSS_WALL_REGENERATION_DELAY_ALL` | `raidBossWallRegenerationDelayAll` | EffectValueSimple *(default)* | VALUE_NOMINAL_ADD | 2 | 99 |
| 213 | `EFFECT_TYPE_SPAWN_RESERVE_UNIT` | `spawnReserveUnit` | EffectValueSpawnReserveUnit | VALUE_PERCENTAGE_ADD *(default)* | 2 | 99 |
| 214 | `EFFECT_TYPE_MUTATE_RESERVE_UNIT` | `mutateReserveUnit` | EffectValueMutateReserveUnit | VALUE_PERCENTAGE_ADD *(default)* | 2 | 99 |

#### Other combat-adjacent

| id | client `EffectTypeEnum` member | items `effecttypes` name | value class | value text id | `effects` rows | capIDs used |
|---|---|---|---|---|---|---|
| 82 | `EFFECT_TYPE_MORALE_BOOST` | `moraleBoost` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |
| 118 | `EFFECT_TYPE_STRONGER_PEASANT` | `strongerPeasant` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |
| 58 | `EFFECT_TYPE_SURVIVAL_BOOST` | `SurvivalBoost` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 1 | 99 |
| 35 | `EFFECT_TYPE_HIDEOUT_CAPACITY` | `hideoutCapacity` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 2 | 99 |
| 105 | `EFFECT_TYPE_FAME_BOOST` | `fameBoost` | EffectValueSimple *(default)* | VALUE_PERCENTAGE_ADD *(default)* | 4 | 99, 1212, 1501 |

### 2.2 Ability effect types (1001–1042)

Constructed by the enum and named by `effecttypes`, but **no client-side combat
consumer exists** for any of them: they appear only in the enum block, the icon
tables, `ToolUnitVO.createEffectMapping` and
`AllianceRaidHighlightedEffectTooltip.getPlaceholders`. Their magnitudes live in
ITEMS `generalAbilityEffects` (165 rows, `effects` field, e.g.
`"21026&759+1#760+1"` — a `#`-separated per-`wodID` list), and their triggers in
ITEMS `generalAbilities` (87 rows: `abilityID`, `abilityGroupID`, `level`,
`abilityTriggerID`, `triggerPerWave`, `abilityAttackEffectID`,
`abilityDefenseEffectID`, `affectsEnemyArmy`) and ITEMS
`generalAbilityTriggers` (4 rows; id 1 = `preCombat`, id 2 = `everyXWaves`).

`GeneralVO.getPassiveSkills` explicitly filters ability skills out with
`!e.isAbilitySkill`, and `LordVO.getUniqueBoni` excludes them. That ability
resolution therefore happens server-side is **(inferred)** — no client
application site was found.

| id | client `EffectTypeEnum` member | items `effecttypes` name | `generalAbilityEffects` rows |
|---|---|---|---|
| 1001 | `EFFECT_TYPE_ABILITY_POWER_SURGE` | `PowerSurge` | 6 |
| 1002 | `EFFECT_TYPE_ABILITY_RISE_TO_THE_TASK` | `RisetotheTask` | 6 |
| 1003 | `EFFECT_TYPE_ABILITY_GIANT_SLAYER` | `GiantSlayer` | 6 |
| 1004 | `EFFECT_TYPE_ABILITY_AURA_OF_PROTECTION` | `— no row` | 0 |
| 1005 | `EFFECT_TYPE_ABILITY_INTIMIDATE` | `Intimidate` | 6 |
| 1006 | `EFFECT_TYPE_ABILITY_STRENGTH_IN_NUMBERS` | `— no row` | 0 |
| 1007 | `EFFECT_TYPE_ABILITY_HORDEBREAKER` | `Hordebreaker` | 6 |
| 1008 | `EFFECT_TYPE_ABILITY_OUTNUMBERED_NOT_OUTMATCHED` | `— no row` | 0 |
| 1009 | `EFFECT_TYPE_ABILITY_STAND_BEHIND_ME` | `— no row` | 0 |
| 1010 | `EFFECT_TYPE_ABILITY_LIVE_TO_FIGHT_ANOTHER` | `EndlessPractice` | 6 |
| 1011 | `EFFECT_TYPE_ABILITY_STRATEGICAL_RETREAT` | `WayoftheSword` | 6 |
| 1012 | `EFFECT_TYPE_ABILITY_REINFORCEMENTS` | `IronWill` | 6 |
| 1013 | `EFFECT_TYPE_ABILITY_SABOTAGE` | `Sabotage` | 6 |
| 1014 | `EFFECT_TYPE_ABILITY_HEART_OF_A_WARRIOR` | `HeartofaWarrior` | 6 |
| 1015 | `EFFECT_TYPE_ABILITY_TOWERING_SHIELD` | `ToweringShield` | 6 |
| 1016 | `EFFECT_TYPE_ABILITY_WALL_AMOUNT` | `WallAmount` | 3 |
| 1017 | `EFFECT_TYPE_ABILITY_NO_SOLDIER_LEFT_BEHIND` | `— no row` | 0 |
| 1018 | `EFFECT_TYPE_ABILITY_HEROIC_DEFENSE` | `HeroicDefense` | 3 |
| 1019 | `EFFECT_TYPE_ABILITY_MIND_CLARITY_EVEN_WAVE` | `MindClarityEvenWave` | 3 |
| 1020 | `EFFECT_TYPE_ABILITY_ASPECT_OF_THE_DRAGON` | `AspectoftheDragon` | 6 |
| 1021 | `EFFECT_TYPE_ABILITY_AYALA_FALCON` | `Ayala(Falcon)` | 6 |
| 1022 | `EFFECT_TYPE_ABILITY_AMBUSH` | `Ambush` | 6 |
| 1023 | `EFFECT_TYPE_ABILITY_LONGBOWS` | `Longbows` | 6 |
| 1024 | `EFFECT_TYPE_ABILITY_VOLLEY` | `— no row` | 0 |
| 1025 | `EFFECT_TYPE_ABILITY_REINFORCED_ARROWS` | `ReinforcedArrows` | 6 |
| 1026 | `EFFECT_TYPE_ABILITY_PLUNDER` | `Plunder` | 6 |
| 1027 | `EFFECT_TYPE_ABILITY_YOUR_CUT` | `YourCut` | 6 |
| 1028 | `EFFECT_TYPE_ABILITY_HIDDEN_TREASURES` | `HiddenTreasures` | 6 |
| 1029 | `EFFECT_TYPE_ABILITY_GOLD_RUSH` | `TheWayofPerfection` | 6 |
| 1030 | `EFFECT_TYPE_ABILITY_VENGENCE` | `Vengence` | 6 |
| 1031 | `EFFECT_TYPE_ABILITY_CANNON_BARRAGE` | `— no row` | 0 |
| 1032 | `EFFECT_TYPE_ABILITY_DRAGONBREATH` | `— no row` | 0 |
| 1033 | `EFFECT_TYPE_ABILITY_WINGS_WHIRLWIND` | `WingsWhirlwind` | 6 |
| 1034 | `EFFECT_TYPE_ABILITY_TAILWHIP` | `Tailwhip` | 6 |
| 1035 | `EFFECT_TYPE_ABILITY_DRAGONSCALE_ARMOR` | `DragonscaleArmor` | 6 |
| 1036 | `EFFECT_TYPE_ABILITY_DRAGON_CLAW_BLADES` | `— no row` | 0 |
| 1037 | `EFFECT_TYPE_ABILITY_TASTY_SNACK` | `— no row` | 0 |
| 1038 | `EFFECT_TYPE_ABILITY_EXHALTED` | `Exhalted` | 6 |
| 1039 | `EFFECT_TYPE_ABILITY_LASTING_WOUNDS` | `LastingWounds` | 6 |
| 1040 | `EFFECT_TYPE_ABILITY_RANGE_REDUCTION` | `MindClarityOddWave` | 3 |
| 1041 | `EFFECT_TYPE_ABILITY_POISON_ARROWS` | `— no row` | 0 |
| 1042 | `EFFECT_TYPE_ABILITY_VENGENCE_BOOST_YARD_DEF` | `— no row` | 0 |

---

## 3. Bonus sources

### 3.1 The two accumulators

Everything routes through one of two functions, and the difference matters more
than any individual source.

**`CastleEffectsHelper.getAccumulatedEquipmentBonusByEffectTypeForArea(lord, effectType, areaType, useGeneral=true, strategy=null)`**
— reads **lord equipment only**, via `LordVO.getUniqueBoni`. This is what
essentially every combat formula calls.

**`CastleEffectsHelper.getAccumulatedEffectValueForType(effectType, lord, conditionVO, extraSources=null)`**
(BUNDLE @559850) — fuses the lord's boni with every account-wide source. Its
source chain, in order:

```
lord.getUniqueBoni(...)                                   (capped)
userData.getGlobalConstructionItemEffectsByType(...)      (capped)
CastleTitleSystemHelper.returnTitleEffectsByType(...)     (uncapped)
researchData.getResearchEffectsByType(...)                (uncapped)
globalEffectData.getGlobalEffectsByType(...)              (uncapped)
subscriptionData.getSubscriptionEffectsByType(...)        (uncapped)
legendSkillData.getSceatSkillEffectsByType(...)           (uncapped)
userData.playerCrest.getEffectsByType(...)                (uncapped)
allianceData.myAllianceVO.getTotalAllianceBuffEffectsByType(...) (uncapped)
+ caller-supplied extraSources, routed by source.ignoreCap
```

**All six call sites of this function in the bundle are non-combat**
(`BasicUnitVO.calcCostWithFameReductionAndPremium` ×2,
`CastleRefineryToolsmithRecipeScrollItemVO.changeCurrentRecipe`,
`CastleCraftingData.checkForLearnedRecipes`). The account-wide uncapped chain is
therefore **not** reached by any combat formula through this entry point.
Individual account-wide sources reach combat only through their own direct
accessors — e.g. `researchData.getResearchEffectValue` for honour,
`globalEffectData.getBonusByEffectType` for effect 148,
`allianceBuffData` for the temporary power boosts.

### 3.2 Lord-attached sources (`LordVO.getUniqueBoni`, BUNDLE @3177610)

| Source | Runtime symbol | ITEMS table with the values |
|---|---|---|
| Equipment | `CastleEquipmentSlotVO.equipmentVO.boni` | `equipments` (1575 rows, 1409 carry `effects`) |
| Equipment magnitude rolls | — | `equipment_effects` (338), `equipment_effectstrengths` (409), `equipment_rarenesses` (10, `secondaryAttributes`), `equipment_slots` (6, per-slot `bonus`) |
| Alien equipment string | — | `equipments.AlienHeroEffectString` (38 rows) |
| Set bonuses | `LordVO.setCounts`, `equipData.equipmentXml.getEquipmentSet` | `equipment_sets` (678 rows, all carry `effects`) |
| Gems | `CastleGemVO.boni`, `GemBonusVO.triggerChance` | `gems` (501 rows, all carry `effects` + `triggerChance`) |
| Alien gems | `AlienLordEquipmentVO.alienGems[].boni` | as `gems` |
| Relics | `RelicEquipmentVO.relicInfoVO.relicBoni` | `relicEffects` (285), `relicEffectLists`, `relicBluePrints` (38), `relicEffectPowerRatings` (7), `relicPowerDistributions` (100) |
| Relic enchantment | `XmlRelicEnchanterVO._relicNormalEffectBoost` | `relicEnchanters` (50 rows, `relicNormalEffectBoost`) |
| Raw server-pushed lord effects | `LordVO._rawLordEffects` (`gli` key `E`) | — (delivered on the wire, §7) |
| Area-scoped raw effects | `LordVO._areaEffects` (`gli` key `AE`) | — |
| Assigned general, passive skills | `GeneralVO.getPassiveEffects()`, only when `getUniqueBoni(includeGeneral=true)` | `generalSkills` (2196 rows, all carry `effects`) |
| General abilities | `generalAbilities` — **excluded** from `getUniqueBoni` | `generalAbilities`, `generalAbilityEffects`, `generalAbilityTriggers` |
| Temporary equipment | same path as permanent while unexpired | `equipments` |

Combat effect types actually present in each, joined `effects` → `effects` table
→ `effectTypeID` (counts are effect references, not rows):

- `equipments.effects`: 31×594, 12×304, 19×216, 36×216, 24×192, 28×179, 23×172, 20×148, 15×133, 21×104, 6×85, 7×81, 16×73, 44×68, 9×67, 13×64, 10×62, 8×55, 33×57, 148×15, 34×13, 32×8, 0×32, 14×25, 75×19, 46×1, 55×2, 168×1, 179×1, 181×3
- `equipments.AlienHeroEffectString`: 36×39, 31×18, 12×3, 15×3, 28×3, 34×3, 6, 7, 13, 19, 20, 46
- `equipment_sets.effects`: 24×65, 23×61, 33×46, 28×39, 9×34, 19×32, 10×25, 15×23, 20×21, 6×15, 21×14, 12×14, 46×8, 32×7, 13×6, 34×6, 16×6, 8×5, 148×6, 53×2, 54×3, 50×2, 197–200
- `gems.effects`: 33×128, 28×76, 13×55, 20×49, 32×49, 19×46, 23×44, 24×42, 12×31, 34×31, 15×30, 6×23, 21×18, 31×18, 16×18, 7×16, 36×14, 37×13, 38×13, 0×12, 8/9/10×9, 47×10, 51×10, 53/54×8, 49/50×5, 203–206, 209–212
- `generalSkills.effects`: 53×264, 49×252, 54×240, 50×240, 34×156, 179×144, 181×132, 28×132, 33×120, 32×108, 12×106, **156×11**, plus 178 `unlockAbility` ×291
- `relicEffects.effectID`: 19×17, 20×17, 33×17, 23×16, 24×16, 28×16, 21×12, 148×11, 6×11, 7×11, 8/9/10×9, 31×9, 32×9, 34×8, 12×6, 168×8, 150×5, 46×3, 156×1, 179×1, 181×1, 149×1

### 3.3 Non-lord sources

| Source | Runtime symbol | ITEMS table | Combat types it carries |
|---|---|---|---|
| Buildings and construction items on the area | `ABasicBuildingVO.getBonusVOsByType`; `parseEffects` / `parseAreaSpecificEffects` @2206764–2207514 | `buildings` — **no `effects` column at all**; the payload is `areaSpecificEffects` on 720 of 3962 rows | 181×80, 32×48, 183×46, 12×33, 33×33, 23×24, 24×24, 53×20, 54×20, 51×10, 28×5, 34×5, 19×4, 20×4, **156×3**, 182×1 |
| Construction items (decorations) | `CastleUserData.getGlobalConstructionItemEffectsByType` | `constructionItems` (2125 rows, 1204 carry `effects`) | 28×158, 33×140, 34×92, 194×89, 24×86, 49×70, 50×70, 23×68, 181×34, 179×29, 32×28, 9×16, 10×17, 36×16, **156×7**, 15, 16, 31, 180, 182 |
| Titles | `CastleTitleSystemHelper.returnTitleEffectsByType` | `titles` (57 rows, 49 carry `effects`, 50 carry `titleEffectID`) | 13×5, 14×4, 75×3, 15×2, 33×2, 36×2, 82×1, 28×1, 34×1, 16×1 |
| Research | `CastleResearchData.getResearchEffectsByType` / `getResearchEffectValue` | `researches` (1040 rows, 1037 carry `effects`) | 14×10, 40×10, 16×5, 103×5, 114×5, 102×1, 118×1 — mostly non-combat |
| Global / event effects | `GlobalEffectData.getGlobalEffectsByType`, `.getBonusByEffectType` | `globalEffects` (19 rows) | 148×5, 154×6, 15×2, 33×1 |
| Subscriptions | `SubscriptionData.getSubscriptionEffectsByType` | `subscriptionsBuffs` (94 rows) | 75×9, 13×8, 0×4, 38×4, 39×4, 14×3, 36×1 |
| Sceat (second legend tree) | `CastleLegendSkillData.getSceatSkillEffectsByType` | `sceatSkills` (333 rows) | **none** — only types 57, 79, 90, 169 |
| Classic legend skills | `CastleLegendSkillData.getTotalValueOfLegendSkillEffect` — **flat ints, entirely outside the BonusVO/cap pipeline** | `legendskills` (353 rows; `effectType` is a *string*, not an effect-type id) | see §3.4 |
| Player crest | `PremiumCrestSymbolVO.getEffectsByType` (@12910537); parsed by `CastleCrestSymbolData.parseXML` @12904050 | `crestsymbols` (82 rows, 44 carry `effects`) | 13×7 only (plus 22, 80, 92, 93, 164, 165) |
| Alliance crest layout | `AllianceCrestLayoutVO.parseEffects` @12861413; read back via `AllianceInfoVO.getLayoutEffectsByType` @3068007 | `allianceCoatLayouts` (19 rows, 11 carry `effects`) | 33×3, 28×1, 34×1 (plus 86, 161) |
| Alliance buffs | `AllianceInfoVO.getTotalAllianceBuffEffectsByType`; `allianceBuffData.getAllianceBuffVoBySeriesIDAndLevel(...).getBonusVOsByType()` | `alliancebuffs` (261 rows, 213 carry `effects`) | 36×23, 44×21, 114×21, 31×6, 39×32, 13×1 |
| Alliance temporary power boosts | `AllianceConst.TYPE_TEMP_ATTACK_POWER_BOOST` (type 36) / `TYPE_TEMP_DEFENSE_POWER_BOOST` (type 31) — applied **outside** `getUniqueBoni` as a separate multiplier | — | 36 / 31 |
| Alliance Battleground tower buffs | `ABGAllianceTowerEffectVO` (a `RawLordEffectBonusVO`) | `allianceTowerEffects` (5 rows) → effect types **6, 7, 9, 10, 32**; every row `effectBasePrice`=100, `effectMaxLevel`=60, `effectStartValue`=1, `effectIncrease`=2, i.e. value = 1 + 2·(level−1), max 119 | 6, 7, 9, 10, 32 |
| Officers school ("training program") | `OfficersSchoolData.getBonusByEffectType` — **defined but never called anywhere in the client** | `officersSchoolEffects` (5 rows, all effect type **148**) | 148 |
| Private villages | raw lord effects | `privateVillages` (135 rows) | **none** — 92/93/80 only, economy |
| VIP | `CastleVIPData.currentActiveVIPLevel.attackSpeedBonus`; `VIPLevelInfoVO.parseXML` @9024900 | `viplevels` (10 rows: `attackSpeedBoost`, `attackFameBoost`, `magicFindBoost`, …) | march speed — see §3.5 |
| Horse / travel booster | `HorseTravelboosterVO.parseXmlNode` @13618344 | `horses` (33 rows: `unitBoost`, `marketBoost`, `spyBoost`, `isInstantSpyHorse`) | march speed |
| Return-speed booster | `boostData.returnSpeedBoosterVO.returnSpeedForCurrentLevel` | `levelBoosters` (73 rows, `boosterType` = `BoosterConst.RETURNING_SPEED`, `boostPercentage`) | return march |
| Alliance monument | `_monumentBonus` on `CastleAttackInfoVO` (`aci`) | `monuments` (19 rows, `level` → `fameBoost`) | fame |
| Kingstower | `_kingstowerBonus` on `CastleAttackInfoVO` (`aci` key `KTB`) | — | attack boost, server-resolved |
| Per-battle title / morale boost | `BattleParticipantVO.highestFameTitleBonus`, `.moralBoost` (`BattleLogVO` PI-array @15238300: `i[7]`=kingstower, `i[9]`=highestFameTitle, `i[11]`=moralBoost) | — | server-resolved scalars |
| NPC lord effects | `DefaultLordVO.getUniqueBoni` | `lords` (92 rows, 81 carry `effects`) | 9×68, 10×68, 6×56, 7×50, 23×13, 24×13, 19×11, 8×11, 32×11, 20×7, 28×1, 34×1 |
| Auto-scaling event NPC lord | difficulty-scaled | `eventAutoScalingLordEffects` (528 rows) | defender: 6, 7, 8, 9, 10, 12, 31, 32 (44 rows each); **attacker: 19, 20, 21, 23, 24, 33, 53, 54 (22 rows each)** |
| Raid-boss stage effects | `AllianceRaidbossStageVO` @13059700 | `raidBossStages` (397 rows, six effect columns) | §6.5 |

**Verified negative:** `sceatSkills` carries no combat effect type. `privateVillages`
carries no combat effect type. ITEMS `horses`, `viplevels`, `levelBoosters`,
`monuments`, `isles`, `tmapnodes`, `daimyoCastles`, `daimyoTownships`,
`emptyAreas`, `villages`, `nomadCamps`, `samuraiCamps`, `factioninvasioncamps`,
`allianceInvasionCamps`, `allianceBattleGroundDungeons`, `dungeons`,
`specialcamps`, `bossdungeons`, `eventAutoScalings`, `eventAutoScalingCamps` and
`toolCategories` contain **no effect-id references at all** — their combat data
is in scalar columns (§6).

**Known-broken:** `CastleUserData.getGlobalConstructionItemEffectsByType`
(@1264890) returns `[]` unconditionally. Whether that is a live bug or dead code
is **not established**, so the runtime contribution of *global*
construction-item effects is unknown. (Area-scoped construction items still
arrive via the building path.)

### 3.4 Legend skills

`CastleLegendSkillData.getTotalValueOfLegendSkillEffect(enumMember)` returns a
flat integer and bypasses the `BonusVO` / cap pipeline entirely.
`CastleLegendSkillEffectsEnum` members are keyed by a **string** name matching
the ITEMS `legendskills` column `effectType`. The combat-relevant members, with
their enum ids:

| id | member | string | Where it enters combat |
|---|---|---|---|
| 4 | `ATTACK_MELEE_BONUS` | `attackMeleeBonus` | attacker melee mult, paths (a) and (b) |
| 7 | `ATTACK_RANGE_BONUS` | `attackRangeBonus` | attacker range mult, paths (a) and (b) |
| 15 | `ATTACK_YARD_BONUS` | `attackYardBonus` | path (b), yard only |
| 16 | `TRAVEL_ATTACK_BOOST` | — | `calculateTravelTime` |
| 21 | `ADDITIONAL_ATTACK_TOOL_AMOUNT_FLANK` | `additionalAttackToolAmountFlank` | flank tool capacity (§1.4) |
| 22 | `ADDITIONAL_WAVE` | `additionalWave` | wave count (§1.1) |
| 24 | `GATE_BONUS` | `gateBonus` | defender gate (§6) |
| 27 | `DEFENSE_MELEE_BONUS` | `defenseMeleeBonus` | defender melee mult |
| 30 | `DEFENSE_RANGE_BONUS` | `defenseRangeBonus` | defender range mult |
| 35 | `WALL_BONUS` | `wallBonus` | defender wall |
| 36 | `DEFENSE_YARD_BONUS` | `defenseYardBonus` | **no consumer found** |
| 42 | `MOAT_BONUS` | `moatBonus` | defender moat |
| 43 | `ATTACK_BONUS` | `attackBonus` | path (b) |
| — | `WALL_REDUCTION` / `GATE_REDUCTION` / `MOAT_REDUCTION` | — | attacker reductions, gated on `isLegendaryFight` |
| — | `ADDITIONAL_UNIT_AMOUNT_ON_FLANK` / `_ON_FRONT` / `_ON_WALL` | — | slot counts |

`ClientConstLegendSkills.GROUP_ABSOLUTE_SKILLS` (@2194094) lists
`ADDITIONAL_WAVE`, `ADDITIONAL_ATTACK_TOOL_AMOUNT_FLANK`, `LOOT_CAPACITY_BONUS`,
`SPY_AMOUNT_BONUS` as absolute (not percentage) values.

### 3.5 March timing

Distinct from unit speed. `CastleAttackInfoVO.calculateTravelTime` (BUNDLE
@3633500–3634300) assembles, in order:

1. `TravelConst.TRAVEL_BOOST_TUTORIAL` when `lordID < 0`
2. `CastleModel.boostData.returnSpeedBoosterVO.returnSpeedForCurrentLevel / 100`
3. `u = getActionTravelTimeBonusForAreaType(...)`, then
   `TreasureMapsConst.CRUSADE_MAP_IDS.indexOf(targetArea.mapID) < 0 && (u += vipData.currentActiveVIPLevel.attackSpeedBonus)`
4. `isLegend && (p += legendSkillData.getTotalValueOfLegendSkillEffect(TRAVEL_ATTACK_BOOST)/100)`
5. `TravelConst.calculateLowLevelBoost(userData.userLevel, SpecialServerHelper.isOnSpecialServer)`
   — DLL @2642822: `isSpecial || level >= MAX_LEVEL_FOR_LOW_LEVEL_TRAVEL_BOOST ? 0
   : (100*max(0, -0.1667*level + 4.167) | 0) / 100`

all handed to `TravelConst.getTravelTimeWithHorse` together with
`getLowestTravelSpeed` and the horse boost. The horse term inside that function
(DLL @2641674) is `1 + i/100/TravelConst.HORSE_BOOST_FIELDS * s`.

**Correction to the catalog:** "VIP levels — nothing on the combat path" is
**wrong**. Item 3 above adds the VIP attack-speed bonus to every non-crusade
attack. The value is ITEMS `viplevels.attackSpeedBoost`, parsed to
`attackSpeedBonus` at @9025095. (`attackFameBoost` → `attackFameBonus` has no
client consumer; that it applies server-side is **(inferred)**.)

`CastleFightScreenVO.getActionTravelTimeBonusForAreaType` (BUNDLE @3619278)
always pushes `EFFECT_TYPE_SPEED_BONUS` (15) and then, by target action type:

| Action type | Extra effect type |
|---|---|
| `DUNGEONATTACK`, `OUTPOSTATTACK`, `ATTACK`, `COLLECTOR_ATTACK` | 44 `speedBonusPVP` |
| `SENDTROUPS` | 40 `stationingSpeedBonus` |
| `SUPPORTDEFENSE` | 39 `supportSpeedBonus` |
| `CONQUER`, `ISLAND_ATTACK` | 1 `conquerSpeedBonus` |

The strategy is `LordEffectHelper.STRATEGY_ATTACK_PVE` for NPC (non-NpcPvp)
targets, else `STRATEGY_ATTACK`. **Live oddity, reported as found:** the
`legendSkillData.getTotalValueOfLegendSkillEffect(...)` results and the final
`globalEffectData.getBonusByEffectType(EFFECT_TYPE_SPEED_BONUS, ...)` call in
that same body are computed and then **discarded** — only the equipment sum is
returned.

Unit travel speed is a separate layer: `BasicUnitVO.unitSpeed` (@2341860) is the
raw `units` column plus research effect 102, and
`CastleFightItemContainer.getLowestTravelSpeed` (@2478458) takes the minimum of
`ceil(unitSpeed * (100 + lordEffect149) / 100)` over the container, skipping
`UNIT_CATEGORY_TOOLS` when `excludeTools`. Effect 149 reaches this from lord
equipment only (3 references in the whole bundle: enum, icon, this call).

### 3.6 Morality

`CombatConst.getMoralBonus(e)` (DLL @2444163), verbatim:

```
e >= 0 ? 2 - 1/(1 + abs(e)/250)
       : 1/(1 + abs(e)/250)
```

A multiplier bounded on (0, 2) with 250 as the half-scale. Inputs are
`AEffectBuildingVO._morality` from the ITEMS `buildings` column `Moral`
(@342400) and ITEMS `titles` rows carrying effect type 82 `moraleBoost`.

Note the distinction: **effect type 82 feeds the morality *value*; `getMoralBonus`
converts that value into a *multiplier*.** All client call sites of
`getMoralBonus` are display (`ResourcePanelToolTipMorale` @10254963,
`CastleResourcePanel_Season` @6549401, `CastleSeasonInventoryOverviewDialog`
@12563066), each branching to `FactionConst.getMoraleModifier(...)` when
`activeKingdomID == FactionConst.KINGDOM_ID`. **That the server applies this as
an attack multiplier is (inferred)** — no client fight-strength site reads it.
The corroborating evidence is the battle log's per-participant `moralBoost`
field (@15238300).

---

## 4. Accumulation and caps

### 4.1 The clamp

`CastleEffectsHelper.getTotalEffectValue(boni, ignoreCap = false)` (BUNDLE
@561285), verbatim:

```
if boni.length == 0: return null
map = new Map()
for each bonus b in boni:
    if not b: continue
    r = b.capID
    if not map.get(r): map.set(r, new b.effect.effectType.type.valueClass)
    i = map.get(r)
    i.add(b.effectValue, ignoreCap ? null : [b.maxValueStrength])
result = new boni[0].effect.effectType.type.valueClass
for each v in map.values(): result.add(v, null)      // <- second add, maxValues = null
return result
```

Two stages, and they behave differently:

1. **Within a capID bucket**, each bonus is added with the bucket's ceiling
   applied.
2. **Across buckets**, the per-bucket totals are added with `maxValues = null`
   — **no clamp at all**.

So the cap is per `capID`, never a global ceiling on the effect *type*. One
effect type can carry several caps (relic, PvE, PvP, newPVP, deco, construction
item …), and each is clamped independently before the sums are added together.

`BonusVO.maxValueStrength` resolves as
`effectsData.getEffectCap(capID).maxTotalBonus`.

`EffectValueSimple.add(other, maxValues)` applies a `Math.min` ceiling only —
**there is no floor**. `EffectValueMap.add` **ignores `maxValues` entirely**, so
map-valued types (148, 149, 150, 154) are never capped by this path — consistent
with their all being `capID` 99.

### 4.2 Escapes from the clamp

| Escape | Symbol | Effect |
|---|---|---|
| `capID` 99 | ITEMS `effectCaps` row 99 has **no `maxTotalBonus` key** | uncapped |
| `EquipmentBonusVO.overridesBonusCap` | short-circuits `maxValueStrength` to `Number.MAX_VALUE` | that bonus escapes every cap |
| `ignoreCap = true` | `getTotalEffectValue` second parameter; `EffectsHandlerVO` / `SimpleEffectSource` `ignoreCap` | no clamp applied |
| Missing `maxTotalBonus` | `EffectCapVO.parseXml`: `int(e.maxTotalBonus) \|\| Number.MAX_VALUE` | uncapped — **and an explicit `maxTotalBonus="0"` would also become uncapped.** No shipped row has 0, so this is a latent-behaviour note, not an observed case. |
| `GemBonusVO.triggerChance` | proc-chance gems are kept as separate, unmerged entries | not merged into a bucket |
| Legend skills | `getTotalValueOfLegendSkillEffect` returns a plain int | outside the pipeline entirely |

A third clamp point exists **before** capID grouping: `LordVO.mergeBoni` /
`mergeBoniWithSameEffectID` merges equipment bonuses sharing an `effectID` and
applies the cap there too.

`CastleEffectsData._effectCaps` contains **no capID −1 entry**, so
`getEffectCap(-1).maxTotalBonus` would throw in the base `BonusVO` getter.
`EquipmentBonusVO` short-circuits, so the equipment path never reaches it, but
whether some other path constructs a plain `BonusVO` with capID −1 is **not
established**.

### 4.3 The filter applied before any of this

Every collection inside `getUniqueBoni` is filtered by `LordVO.checkConditions`
and, per bonus, `BonusVO.matchesConditions`. The condition object is
`CastleEffectConditionVO(areaType, spaceId, wodId, otherPlayer)`. The strategy
is chosen by `LordEffectHelper.getFilterStrategyAttackOrDefence` /
`getFilterStrategyByMovementVO`:

| Strategy | What it excludes |
|---|---|
| `FULL_ACTIVE` | nothing (UI listing) |
| `FULL_PASSIVE` | nothing; `isGroupActive` always false (greyed display) |
| `ATTACK` | stationing/support travel effects, yard-defence boost, and category 7 |
| `ATTACK_PVE` | same list as `ATTACK`, but flips the PvP/PvE flag rule |
| `DEFENCE_PVE` | only the PvP wall-unit-slot effect, and category 7 |
| `DEFENCE_PVP` | no explicit type exclusions; category 7 |
| `STATION` | support and PvP travel effects |
| `SUPPORT` | stationing and PvP travel/return effects |

**Every combat strategy except `FULL_ACTIVE` / `FULL_PASSIVE` drops effects
whose `effectCategory == 7` (economy).**

### 4.4 The cap table

Numeric `maxTotalBonus` values joined from ITEMS `effects` (`effectID` →
`effectTypeID`, `capID`) to ITEMS `effectCaps`, restricted to the combat effect
types of §2.1.

| capID | `maxTotalBonus` | combat effect types pooled under it | `effects` rows carrying it |
|---|---|---|---|
| 0 | **50** | 0 `fameDefenseBonus` | `fameDefenseBonus`, `fameDefenseBonusBaron`, `fameDefenseMalusBaron` |
| 1 | **80** | 1 `conquerSpeedBonus` | `conquerSpeedBonus` |
| 2 | **70** | 2 `lootReduction` | `lootReduction`, `lootReductionBaron`, `lootIncreaseBaron` |
| 6 | **120** | 6 `wallBonus` | `wallBonus`, `wallBonusBaron`, `wallMalusBaron` |
| 7 | **120** | 7 `gateBonus` | `gateBonus`, `gateBonusBaron`, `gateMalusBaron` |
| 8 | **80** | 8 `moatBonus` | `moatBonus`, `moatBonusBaron`, `moatMalusBaron` |
| 9 | **90** | 9 `meleeBonus` | `meleeBonus`, `meleeBonusPVP` |
| 10 | **90** | 10 `rangeBonus` | `rangeBonus`, `rangeBonusPVP` |
| 11 | **50** | 11 `npcDefenseBonus` | `npcDefenseBonus` |
| 13 | **200** | 13 `fameOffenseBonus` | `fameOffenseBonus`, `fameOffenseBonusGeneral`, `fameMalusGeneral` … (4 rows) |
| 14 | **150** | 14 `honorBonus` | `honorBonus`, `honorBonusGeneral` |
| 15 | **80** | 15 `speedBonus` | `speedBonus`, `speedBonusConquerBaron`, `speedBonusConquerGeneral` … (6 rows) |
| 16 | **80** | 16 `lootBonus` | `lootBonus`, `lootBonusPVE`, `lootDecreaseGeneral` … (4 rows) |
| 19 | **120** | 19 `wallReduction` | `wallReduction`, `wallReductionConquerBaron`, `wallReductionConquerGeneral` … (9 rows) |
| 20 | **120** | 20 `gateReduction` | `gateReduction`, `gateReductionPVP`, `gateReductionPVE` … (7 rows) |
| 21 | **80** | 21 `moatReduction` | `moatReduction`, `moatReductionPVP`, `moatIncreasePVP` … (4 rows) |
| 23 | **90** | 23 `offensiveMeleeBonus` | `offensiveMeleeBonus`, `offensiveMeleeBonusConquerBaron`, `offensiveMeleeBonusConquerGeneral` … (9 rows) |
| 24 | **90** | 24 `offensiveRangeBonus` | `offensiveRangeBonus`, `offensiveRangeBonusConquerBaron`, `offensiveRangeBonusConquerGeneral` … (12 rows) |
| 26 | **95** | 26 `travelCostReduction`; 43 `travelCostReductionPVP` | `travelCostReduction`, `travelCostReductionPVE`, `travelCostIncreaseGeneral` … (5 rows) |
| 32 | **30** | 182 `defenseUnitAmountYardBoost`; 184 `allianceDefenseUnitAmountYardBoost` | `defenseUnitAmountYardBoost`, `allianceDefenseUnitAmountYardBoost` |
| 33 | **30** | 180 `attackUnitAmountReinforcementBoost` | `attackUnitAmountReinforcementBoost` |
| 34 | **12** | 182 `defenseUnitAmountYardBoost` | `defenseUnitAmountYardMinorBoost` |
| 43 | **200** | 23 `offensiveMeleeBonus` | `offensiveMeleeBonusTCICapped` |
| 44 | **200** | 24 `offensiveRangeBonus` | `offensiveRangeBonusTCICapped` |
| 45 | **120** | 28 `attackUnitAmountFlank` | `attackUnitAmountFlankCapped` |
| 46 | **120** | 34 `attackUnitAmountFront` | `AttackUnitAmountFrontCapped` |
| 56 | **150000** | 183 `allianceDefenseUnitAmountYardBonus` | `allianceDefenseUnitAmountYardBonusCapped` |
| 57 | **60** | 33 `attackBoostYard` | `AttackBoostYardCapped` |
| 79 | **30** | 49 `DefenseBoostFront` | `DefenseBoostFrontCapped` |
| 80 | **30** | 50 `DefenseBoostFlank` | `DefenseBoostFlankCapped` |
| 81 | **100** | 53 `AttackBoostFront` | `AttackBoostFrontCapped` |
| 82 | **100** | 54 `AttackBoostFlank` | `AttackBoostFlankCapped` |
| 86 | **120** | 23 `offensiveMeleeBonus`; 24 `offensiveRangeBonus`; 33 `attackBoostYard` | `offensiveMeleeBonusDecoCapped`, `offensiveRangeBonusDecoCapped`, `AttackBoostYardDecoCapped` |
| 87 | **160** | 12 `defenseUnitAmountWall` | `defenseUnitAmountWallCapped` |
| 88 | **130** | 32 `defenseBoostYard` | `defenseBoostYardCapped` |
| 89 | **175000** | 181 `defenseUnitAmountYardBonus` | `defenseUnitAmountYardBonusCapped` |
| 99 | **uncapped** (key absent) | 82 types — every core combat type when the `effects` row is a base (non-relic, non-newPVP, non-deco) row: 6, 7, 8, 9, 10, 12, 15, 16, 19, 20, 21, 23, 24, 28, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 44, 45, 46, 47, 49, 50, 51, 53, 54, 55, 58, 75, 82, 102, 103, 105, 114, 118, 148, 149, 150, 154, 156, 168, 172, 173, 174, 175, 176, 177, 179, 181, 183, 194, 197, 198, 199, 200, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218 | 257 rows |
| 1001 | **140** | 23 `offensiveMeleeBonus` | `relicOffensiveMeleeBonus` |
| 1002 | **140** | 24 `offensiveRangeBonus` | `relicOffensiveRangeBonus` |
| 1003 | **160** | 19 `wallReduction` | `relicWallReduction` |
| 1004 | **160** | 20 `gateReduction` | `relicGateReduction` |
| 1005 | **120** | 21 `moatReduction` | `relicMoatReduction` |
| 1006 | **100** | 15 `speedBonus` | `relicSpeedBonus` |
| 1007 | **50** | 16 `lootBonus` | `relicLootBonus` |
| 1008 | **50** | 28 `attackUnitAmountFlank` | `relicAttackUnitAmountFlank` |
| 1009 | **100** | 33 `attackBoostYard` | `relicAttackBoostYard` |
| 1010 | **50** | 34 `attackUnitAmountFront` | `relicAttackUnitAmountFront` |
| 1011 | **20** | 36 `attackBonus` | `relicAttackBonus` |
| 1012 | **20** | 53 `AttackBoostFront` | `relicAttackBoostFront` |
| 1013 | **20** | 54 `AttackBoostFlank` | `relicAttackBoostFlank` |
| 1101 | **60** | 19 `wallReduction` | `relicWallReductionPVE` |
| 1102 | **60** | 20 `gateReduction` | `relicGateReductionPVE` |
| 1103 | **50** | 23 `offensiveMeleeBonus` | `relicOffensiveMeleeBonusPVE` |
| 1104 | **50** | 24 `offensiveRangeBonus` | `relicOffensiveRangeBonusPVE` |
| 1105 | **40** | 28 `attackUnitAmountFlank` | `relicAttackUnitAmountFlankPVE` |
| 1106 | **60** | 33 `attackBoostYard` | `relicAttackBoostYardPVE` |
| 1107 | **40** | 34 `attackUnitAmountFront` | `relicAttackUnitAmountFrontPVE` |
| 1108 | **30** | 21 `moatReduction` | `relicMoatReductionPVE` |
| 1109 | **50** | 75 `coinLootBoost` | `relicCoinLootBoostPVE` |
| 1201 | **60** | 19 `wallReduction` | `relicWallReductionCapAPVP` |
| 1202 | **60** | 20 `gateReduction` | `relicGateReductionCapAPVP` |
| 1203 | **50** | 23 `offensiveMeleeBonus` | `relicOffensiveMeleeBonusPVP` |
| 1204 | **50** | 24 `offensiveRangeBonus` | `relicOffensiveRangeBonusPVP` |
| 1205 | **40** | 28 `attackUnitAmountFlank` | `relicAttackUnitAmountFlankPVP` |
| 1206 | **60** | 33 `attackBoostYard` | `relicAttackBoostYardCapAPVP` |
| 1207 | **40** | 34 `attackUnitAmountFront` | `relicAttackUnitAmountFrontPVP` |
| 1209 | **30** | 21 `moatReduction` | `relicMoatReductionPVP` |
| 1211 | **30** | 13 `fameOffenseBonus` | `relicFameOffenseBonusPVP` |
| 1212 | **50** | 105 `fameBoost` | `relicFameOffenseBonusAlien` |
| 1301 | **60** | 19 `wallReduction` | `relicWallReductionNomad` |
| 1302 | **60** | 20 `gateReduction` | `relicGateReductionNomad` |
| 1303 | **50** | 23 `offensiveMeleeBonus` | `relicOffensiveMeleeBonusNomad` |
| 1304 | **50** | 24 `offensiveRangeBonus` | `relicOffensiveRangeBonusNomad` |
| 1305 | **40** | 28 `attackUnitAmountFlank` | `relicAttackUnitAmountFlankNomad` |
| 1306 | **60** | 33 `attackBoostYard` | `relicAttackBoostYardNomad` |
| 1307 | **40** | 34 `attackUnitAmountFront` | `relicAttackUnitAmountFrontNomad` |
| 1308 | **30** | 21 `moatReduction` | `relicMoatReductionNomad` |
| 1401 | **60** | 19 `wallReduction` | `relicWallReductionSamurai` |
| 1402 | **60** | 20 `gateReduction` | `relicGateReductionSamurai` |
| 1403 | **50** | 23 `offensiveMeleeBonus` | `relicOffensiveMeleeBonusSamurai` |
| 1404 | **50** | 24 `offensiveRangeBonus` | `relicOffensiveRangeBonusSamurai` |
| 1405 | **40** | 28 `attackUnitAmountFlank` | `relicAttackUnitAmountFlankSamurai` |
| 1406 | **60** | 33 `attackBoostYard` | `relicAttackBoostYardSamurai` |
| 1407 | **40** | 34 `attackUnitAmountFront` | `relicAttackUnitAmountFrontSamurai` |
| 1408 | **30** | 21 `moatReduction` | `relicMoatReductionSamurai` |
| 1501 | **120** | 105 `fameBoost` | `relicFameOffenseBonusAlien` |
| 1502 | **60** | 19 `wallReduction` | `relicWallReductionAlien` |
| 1503 | **60** | 20 `gateReduction` | `relicGateReductionAlien` |
| 1504 | **30** | 21 `moatReduction` | `relicMoatReductionAlien` |
| 1505 | **50** | 23 `offensiveMeleeBonus` | `relicOffensiveMeleeBonusAlien` |
| 1506 | **50** | 24 `offensiveRangeBonus` | `relicOffensiveRangeBonusAlien` |
| 1507 | **40** | 28 `attackUnitAmountFlank` | `relicAttackUnitAmountFlankAlien` |
| 1508 | **60** | 33 `attackBoostYard` | `relicAttackBoostYardAlien` |
| 1509 | **40** | 34 `attackUnitAmountFront` | `relicAttackUnitAmountFrontAlien` |
| 1601 | **60** | 19 `wallReduction` | `relicWallReductionBerimond` |
| 1602 | **60** | 20 `gateReduction` | `relicGateReductionBerimond` |
| 1603 | **50** | 23 `offensiveMeleeBonus` | `relicOffensiveMeleeBonusBerimond` |
| 1604 | **50** | 24 `offensiveRangeBonus` | `relicOffensiveRangeBonusBerimond` |
| 1605 | **40** | 28 `attackUnitAmountFlank` | `relicAttackUnitAmountFlankBerimond` |
| 1606 | **60** | 33 `attackBoostYard` | `relicAttackBoostYardBerimond` |
| 1607 | **40** | 34 `attackUnitAmountFront` | `relicAttackUnitAmountFrontBerimond` |
| 1608 | **30** | 21 `moatReduction` | `relicMoatReductionBerimond` |
| 1702 | **30** | 21 `moatReduction` | `relicMoatReductionPVP` |
| 1703 | **60** | 19 `wallReduction` | `relicWallReductionCapBPVP` |
| 1704 | **60** | 20 `gateReduction` | `relicGateReductionCapBPVP` |
| 1705 | **60** | 33 `attackBoostYard` | `relicAttackBoostYardCapBPVP` |
| 1706 | **40** | 28 `attackUnitAmountFlank` | `relicAttackUnitAmountFlankPVP` |
| 1707 | **40** | 34 `attackUnitAmountFront` | `relicAttackUnitAmountFrontPVP` |
| 1708 | **50** | 23 `offensiveMeleeBonus` | `relicOffensiveMeleeBonusPVP` |
| 1709 | **50** | 24 `offensiveRangeBonus` | `relicOffensiveRangeBonusPVP` |
| 1711 | **30** | 13 `fameOffenseBonus` | `relicFameOffenseBonusPVP` |
| 2000 | **360** | 23 `offensiveMeleeBonus`; 24 `offensiveRangeBonus` | `newPVPOffensiveMeleeBonus`, `newPVPOffensiveRangeBonus` |
| 2001 | **420** | 19 `wallReduction`; 20 `gateReduction` | `newPVPWallReduction`, `newPVPGateReduction` |
| 2002 | **270** | 21 `moatReduction` | `newPVPMoatReduction` |
| 2003 | **100** | 15 `speedBonus` | `newPVPSpeedBonus` |
| 2004 | **150** | 16 `lootBonus` | `newPVPLootBonus` |
| 2005 | **195** | 28 `attackUnitAmountFlank`; 34 `attackUnitAmountFront` | `newPVPAttackUnitAmountFlank`, `newPVPAttackUnitAmountFront` |
| 2006 | **330** | 33 `attackBoostYard` | `newPVPAttackBoostYard` |
| 2007 | **30** | 36 `attackBonus`; 53 `AttackBoostFront`; 54 `AttackBoostFlank` | `newPVPAttackBonus`, `newPVPAttackBoostFront`, `newPVPAttackBoostFlank` |
| 2010 | **38** | 38 `returnTravelBoost` | `newPVPReturnTravelBoost` |
| 2100 | **420** | 6 `wallBonus` | `newDefenseWallBonusPVP` |
| 2101 | **28** | 49 `DefenseBoostFront` | `newDefenseBoostFrontPVP` |
| 2103 | **324** | 9 `meleeBonus` | `newDefenseMeleeBonusPVP` |
| 2104 | **34** | 31 `defenseBonus` | `newDefenseBonusMainCastlePVP` |
| 2105 | **420** | 7 `gateBonus` | `newDefenseGateBonusPVP` |
| 2106 | **28** | 50 `DefenseBoostFlank` | `newDefenseBoostFlankPVP` |
| 2107 | **68** | 2 `lootReduction` | `newLootReductionPVP` |
| 2108 | **324** | 10 `rangeBonus` | `newDefenseRangeBonusPVP` |
| 2109 | **34** | 31 `defenseBonus` | `newDefenseBonusNotMainCastlePVP` |
| 2110 | **270** | 8 `moatBonus` | `newDefenseMoatBonusPVP` |
| 2111 | **176** | 12 `defenseUnitAmountWall` | `newDefenseUnitAmountWallPVP` |
| 2112 | **298** | 32 `defenseBoostYard` | `newDefenseBoostYardPVP` |
| 2113 | **38** | 31 `defenseBonus` | `newDefenseBonusPVP` |
| 2115 | **420** | 19 `wallReduction`; 20 `gateReduction` | `ARELootNomadWallReduction`, `ARELootSamuraiWallReduction`, `ARELootBerimondWallReduction` … (8 rows) |
| 2116 | **270** | 21 `moatReduction` | `ARELootNomadMoatReduction`, `ARELootSamuraiMoatReduction`, `ARELootBerimondMoatReduction` … (4 rows) |
| 2117 | **30** | 36 `attackBonus`; 53 `AttackBoostFront`; 54 `AttackBoostFlank` | `ARELootNomadAttackBonus`, `ARELootSamuraiAttackBonus`, `ARELootBerimondAttackBonus` … (12 rows) |
| 2118 | **150** | 16 `lootBonus` | `ARELootNomadLootBonus`, `ARELootSamuraiLootBonus`, `ARELootBerimondLootBonus` … (4 rows) |
| 2119 | **38** | 38 `returnTravelBoost` | `ARELootReturnTravelBoost` |
| 2120 | **150** | 15 `speedBonus` | `ARELootSpeedBonus` |
| 2121 | **360** | 23 `offensiveMeleeBonus`; 24 `offensiveRangeBonus` | `ARELootNomadOffensiveMeleeBonus`, `ARELootSamuraiOffensiveMeleeBonus`, `ARELootBerimondOffensiveMeleeBonus` … (8 rows) |
| 2122 | **330** | 33 `attackBoostYard` | `ARELootNomadAttackBoostYard`, `ARELootSamuraiAttackBoostYard`, `ARELootBerimondAttackBoostYard` … (4 rows) |
| 2123 | **195** | 28 `attackUnitAmountFlank`; 34 `attackUnitAmountFront` | `ARELootNomadAttackUnitAmountFlank`, `ARELootSamuraiAttackUnitAmountFlank`, `ARELootBerimondAttackUnitAmountFlank` … (8 rows) |
| 11001 | **50** | 2 `lootReduction` | `relicLootReduction` |
| 11002 | **160** | 6 `wallBonus` | `relicWallBonus` |
| 11003 | **160** | 7 `gateBonus` | `relicGateBonus` |
| 11004 | **120** | 8 `moatBonus` | `relicMoatBonus` |
| 11005 | **140** | 9 `meleeBonus` | `relicMeleeBonus` |
| 11006 | **140** | 10 `rangeBonus` | `relicRangeBonus` |
| 11007 | **50** | 12 `defenseUnitAmountWall` | `relicDefenseUnitAmountWall` |
| 11008 | **100** | 32 `defenseBoostYard` | `relicDefenseBoostYard` |
| 11009 | **20** | 31 `defenseBonus` | `relicDefenseBonus` |
| 11010 | **20** | 49 `DefenseBoostFront` | `relicDefenseBoostFront` |
| 11011 | **20** | 50 `DefenseBoostFlank` | `relicDefenseBoostFlank` |
| 11101 | **60** | 6 `wallBonus` | `relicWallBonusCapAPvE` |
| 11102 | **60** | 7 `gateBonus` | `relicGateBonusCapAPvE` |
| 11103 | **50** | 9 `meleeBonus` | `relicMeleeBonusPvE` |
| 11104 | **50** | 10 `rangeBonus` | `relicRangeBonusPvE` |
| 11105 | **40** | 12 `defenseUnitAmountWall` | `relicDefenseUnitAmountWallPvE` |
| 11106 | **60** | 32 `defenseBoostYard` | `relicDefenseBoostYardPvE` |
| 11107 | **30** | 8 `moatBonus` | `relicMoatBonusPvE` |
| 11201 | **60** | 6 `wallBonus` | `relicWallBonusCapAPvP` |
| 11202 | **60** | 7 `gateBonus` | `relicGateBonusCapAPvP` |
| 11203 | **50** | 9 `meleeBonus` | `relicMeleeBonusPVP` |
| 11204 | **50** | 10 `rangeBonus` | `relicRangeBonusPVP` |
| 11205 | **40** | 46 `defenseUnitAmountWallPVP` | `relicDefenseUnitAmountWallPVP` |
| 11206 | **60** | 32 `defenseBoostYard` | `relicDefenseBoostYardPvP` |
| 11208 | **30** | 8 `moatBonus` | `relicMoatBonusPvP` |
| 11210 | **30** | 0 `fameDefenseBonus` | `relicFameDefenseBonusPVP` |
| 11301 | **25** | 31 `defenseBonus` | `relicDefenseBonusMainCastleCapA` |
| 11302 | **25** | 31 `defenseBonus` | `relicDefenseBonusNotMainCastleCapA` |
| 11303 | **30** | 8 `moatBonus` | `relicMoatBonusPvE` |
| 11304 | **60** | 6 `wallBonus` | `relicWallBonusCapBPvE` |
| 11305 | **60** | 7 `gateBonus` | `relicGateBonusCapBPvE` |
| 11306 | **50** | 9 `meleeBonus` | `relicMeleeBonusPvE` |
| 11307 | **50** | 10 `rangeBonus` | `relicRangeBonusPvE` |
| 11308 | **40** | 12 `defenseUnitAmountWall` | `relicDefenseUnitAmountWallPvE` |
| 11309 | **60** | 32 `defenseBoostYard` | `relicDefenseBoostYardPvE` |
| 11401 | **25** | 31 `defenseBonus` | `relicDefenseBonusMainCastleCapB` |
| 11402 | **25** | 31 `defenseBonus` | `relicDefenseBonusNotMainCastleCapB` |
| 11404 | **30** | 8 `moatBonus` | `relicMoatBonusPvP` |
| 11405 | **60** | 6 `wallBonus` | `relicWallBonusCapBPvP` |
| 11406 | **60** | 7 `gateBonus` | `relicGateBonusCapBPvP` |
| 11407 | **50** | 9 `meleeBonus` | `relicMeleeBonusPVP` |
| 11408 | **50** | 10 `rangeBonus` | `relicRangeBonusPVP` |
| 11409 | **40** | 46 `defenseUnitAmountWallPVP` | `relicDefenseUnitAmountWallPVP` |
| 11410 | **60** | 32 `defenseBoostYard` | `relicDefenseBoostYardPvP` |
| 11412 | **30** | 0 `fameDefenseBonus` | `relicFameDefenseBonusPVP` |
| 11413 | **3000** | 179 `attackUnitAmountReinforcementBonus` | `attackUnitAmountReinforcementBonus` |
| 11414 | **3000** | 181 `defenseUnitAmountYardBonus` | `defenseUnitAmountYardBonus` |

### 4.5 Unresolved cap semantics

- **Mixed-sign buckets are order-sensitive.** The clamp is `Math.min` only, so a
  bucket holding both a bonus and a malus depends on iteration order, which
  depends on runtime source ordering (equipment slot order, `mergeBoni` output).
  The arithmetic is verified; the ordering is **not established**.
- `EffectValueMap.strength` returns the **first** map value, not the value for
  the requested `wodId`. Verified in the client (@3766203). Every shipped
  type-148 global effect uses equal per-`wodId` strengths, so it is currently
  unobservable — treat it as a divergence risk.
- Per-`add` semantics of the non-simple value classes (`EffectValueMindClarity`,
  `EffectValueAyalaFalcon`, `EffectValueLongbows`, `EffectValueHiddenTreasures`,
  `EffectValueDragonscaleArmor`, `EffectValueSpawnReserveUnit`,
  `EffectValueMutateReserveUnit`, `EffectValueTools`, `EffectValueIdList`,
  `EffectValueWodID`, `EffectValueUnitSpeedBoost`, `EffectValueCurrencyBoost`)
  were not enumerated. All their effect types carry capID 99, so cap semantics
  are moot, but whether each `add()` honours `maxValues` is unverified for all
  but `EffectValueSimple` and `EffectValueMap`.
- The DLL defines `CommKeys.IGNORE_CAP = "ignoreCap"` and
  `CommKeys.EXCLUDE_EFFECT = "excludedMali"`, but **no** row in ITEMS `effects`
  carries either field. Which table uses them is **not established**.
- Whether the server applies the same cap and merge semantics is **not
  established**. The capped/uncapped split described in §3.1 is a client-side
  arrangement.

---

## 5. Tool effects

### 5.1 Encoding

A tool is a `ToolUnitVO` parsed from an ITEMS `units` row. It carries bonuses in
two forms.

**Scalar columns**, parsed as `0.01 * parseInt(...)` in
`ToolUnitVO.parseXmlNode` (BUNDLE @873404 ff) — so a column value of `40` means
`0.40`:

| Column | `ToolUnitVO` field | Used as |
|---|---|---|
| `wallBonus` | `.wallBonus` | attacker wall **reduction** / defender wall protection |
| `gateBonus` | `.gateBonus` | attacker gate reduction / defender gate protection |
| `moatBonus` | `.moatBonus` | attacker moat reduction / defender moat protection |
| `defMeleeBonus` | `.defMeleeBonus` | defender melee defence |
| `defRangeBonus` | `.defRangeBonus` | defender ranged defence |
| `offMeleeBonus` | `.offMeleeBonus` | attacker melee multiplier |
| `offRangeBonus` | `.offRangeBonus` | attacker range multiplier |

Whether a value reads as a bonus or a reduction is decided by which side holds
the tool, not by its sign; `ToolUnitVO.isPositiveEffect` carries the sign
semantics for display.

**Effect rows**, via `ToolUnitVO.getBonusByEffect(toolEffectType)` →
`getEffectValue`. ITEMS `units` has an `effects` column on 146 of 999 rows,
resolving to effect types 33×40, 32×40, 208×12, 172–177×10 each, 12×10, 31×10,
36×4, **156×4**, 168×7, 209–212×6 each, 215×3, 217×3, 202×3.

`ToolUnitVO.createEffectMapping` (BUNDLE @887665) binds `EffectTypeEnum` members
to `ToolEffectType` members, which is what makes a numeric effect type reachable
through `getBonusByEffect`. `ToolEffectType`'s first constructor argument is **0
for roughly 30 members and is not a usable id**; the discriminator is the string
name (e.g. `"attackBonus"`, `"additionalWaves"`).

| `ToolEffectType` | string | `EffectTypeEnum` id | Meaning |
|---|---|---|---|
| `WALL_BONUS` | — | — | scalar column path (sortOrder 2) |
| `GATE_BONUS` | — | — | sortOrder 1 |
| `MOAT_BONUS` | — | — | sortOrder 5 |
| `DEF_MELEE_BONUS` | — | — | sortOrder 3 |
| `DEF_RANGE_BONUS` | — | — | sortOrder 4 |
| `OFF_MELEE_BONUS` | — | — | sortOrder 7 |
| `OFF_RANGE_BONUS` | — | — | sortOrder 9 |
| `ATTACK_BONUS` | `attackBonus` | **36** (ITEMS `effects` row 48) | adds to **both** melee and range multipliers |
| `DEFENSE_BONUS` | — | **31** | adds to **both** defender melee and range multipliers |
| `ADDITIONAL_WAVE` | `additionalWaves` | **156** | grants attack waves (§1.1) |
| `ATTACK_BOOST_YARD` | `attackBoostYard` | 33 | |
| `KILL_*_TROOPS_YARD` | — | 172–177 | no client math |

Slot eligibility: `ToolUnitVO.isToolForSlotType(slotType)` (@876177) scans the
`slotTypes` column against `ToolUnitVO.SLOTTYPE_*` (0, 1, 2, 4, 5, 6, 10) and
the container's `CombatConst.ITEMS_*` layout. **`slotType` 9 appears on 485 of
527 tools, has no named constant anywhere in BUNDLE or DLL, and is referenced by
no `ITEMS_*` array.** Calling it an inventory/shop pseudo-slot is **(inferred)**,
not verified.

ITEMS `toolCategories` (5 rows) is **not** UI-only on the fill path — see §5.2.

### 5.2 Gates on placing a tool

`AReduceDefenseBonusStrategy.pickToolByStrategy` (BUNDLE @2895880) accepts a
tool only if all hold:

```
tool.attackType == ClientConstCastle.ATTACK_TOOL ("Attack")   // ITEMS units column `typ`
AttackHelper.canUseToolForAttackOnTarget(area, tool, spaceID)
this.getRelevantToolBonus(tool) > 0
tool.inventoryAmount > 0
```

`AttackHelper.canUseToolForAttackOnTarget` (@1086773):

```
a = tool.canBeUsedToAttackNPC or area.hasOtherPlayerInfo
      or instanceOfClass(area, "AAlienInvasionMapobjectVO")
s = tool.isAllowedByAttackTarget(spaceId, area.areaType)
if a and s:
    r = cast tool to EventtoolUnitVO
    if not (r and r.usedForEvent.length > 0 and r.inventoryAmount == 0): return true
    for u in r.usedForEvent: if specialEventData.isEventActive(u): return true
return false
```

Backing ITEMS `units` columns: `canBeUsedToAttackNPC`, `allowedToAttack`,
`clientUsageEventID` (→ `EventtoolUnitVO.usedForEvent`, parsed @13623158),
`amountPerWave`. `isAllowedByAttackTarget` → `checkIfTargetIsInArray`
(@2342771): an empty list allows all, and `BasicUnitVO.ALL_ALLOWED` (= −1) is a
wildcard on either `spaceId` or `areaType`.

**`spaceID` is derived, not passed through.** `DefenderEffectVO`'s constructor
(@7663495): `_spaceID = area.mapID > 0 ? area.mapID : area.kingdomID`. Compute
it the same way or every kingdom- or event-restricted tool is misjudged.

**Inventory filtering happens earlier.** `AFillWaveStrategy.createFilteredInventory`
(@~11696700) builds the inventory the strategies see:

```
t && "" != r.toolCategory && !t.isToolFilterActive(r.toolCategory) || i.addUnitReference(r)
```

i.e. a tool is dropped when its non-empty `units.toolCategory` has its
`AutoFillOptions` filter off. Filters:
`TOOL_FILTER_BASIC = "basic"`, `TOOL_FILTER_PREMIUM = "premium"`,
`TOOL_FILTER_ELITE = "elite"`, `TOOL_FILTER_EVENT = "event"`,
`TOOL_FILTER_COMBO = "combo"`. An empty `toolCategory` always passes.

**`amountPerWave` is a hard cap, not display metadata:**

```
D = tool.amountPerWave > 0 ? tool.amountPerWave - wave.getSumOfToolsByTool(tool)
                           : container.freeItems
I = int(min(tool.inventoryAmount, freeItemsArg, D))
```

`CastleAttackWaveVO.getSumOfToolsByTool` (@11523879) sums that tool across **all
three** flank tool containers of the wave.

### 5.3 Which tool gets picked

Selection rule, verbatim (`pickToolByStrategy` @2895880):

```
b = ceil(p / getRelevantToolBonus(tool) * 100 / 100)     // p = residual defender bonus
if b <= I:  if b < _ or _ == -1: C = tool.wodId; _ = b   // smallest count that fully cancels
else:       v = getRelevantToolBonus(tool) * I
            if v > E: m = tool.wodId; f = I; E = v       // else largest achievable reduction
return C != -1 ? inventory.deductUnit(C, _) : (m != -1 ? inventory.deductUnit(m, f) : null)
```

Note `* 100 / 100` is a no-op — it does **not** round to whole percent.

The five strategies live in a **LIFO pool with a destructive pop**.
`AFillFlankStrategy.fillToolStrategyPool` (@6475119) pushes in the order
`[Moat, Range, Melee, Gate, Wall]`, and `fillFlankWithTools` (@6474007) reads
`pool[pool.length - 1]`. **Effective priority is therefore Wall > Gate > Melee >
Range > Moat**, and a strategy that returns null is **popped for the rest of
that flank**. The pool is recreated per flank
(`AFillWaveStrategy.fillWave` @11696290 calls `fillToolStrategyPool()` before
each of left / right / middle).

| Strategy | `getRelevantToolBonus(tool)` | `getRelevantDefenderBonus(attacker, defender)` | Extra gate |
|---|---|---|---|
| `ReduceWallBonusStrategy` @11704291 | `tool.wallBonus` | `defenderWallBonus − attackerWallReduction` | — |
| `ReduceGateBonusStrategy` @11700900 | `tool.gateBonus` | `defenderGateBonus − attackerGateReduction` | inert off-middle (§5.5) |
| `ReduceMeleeBonusStrategy` @11702826 | `tool.defMeleeBonus + getConditionedEffectBonus(tool, EFFECT_TYPE_MELEE_DEFENSE_MALUS /*215*/)` | `defenderMeleeBonus − attackerDefenderMeleeReduction` | returns null unless `defender.hasMeleeDefenders` |
| `ReduceRangeBonusStrategy` @11701958 | `tool.defRangeBonus + getConditionedEffectBonus(tool, EFFECT_TYPE_RANGE_DEFENSE_MALUS /*217*/)` | `defenderRangeBonus − attackerDefenderRangeReduction` | returns null unless `defender.hasRangeDefenders` |
| `ReduceMoatBonusStrategy` @11701363 | `tool.moatBonus` | `defenderMoatBonus − attackerMoatReduction` | reached last |

The three wall/gate/moat strategies read **no effect types at all** — only the
plain scalar columns. Only the melee/range pair consults effects 215/217.

`hasMeleeDefenders` / `hasRangeDefenders` (`DefenderFlankEffectVO` @7664833) test
the strength sums that `getDefendingUnitStrength` filled from spy data. **These
are runtime inputs from the spy report, not from any effect table**, and they
decide whether two of the five strategies survive their first attempt.

`AReduceDefenseBonusStrategy.getConditionedEffectBonus` (@2895560):

```
if bonus.effect.effectType.type == t and EffectConditionHelper.isEffectApplicable(bonus.effect, this._area):
    i += 0.01 * bonus.strength
```

`this._area` is set at the top of `pickToolByStrategy` to the defender area.
`EffectConditionHelper.isEffectApplicable` gates on `effect.isForAreaType(area.areaType)`
and, when `effect.raidBossIDs` is non-empty, on the **currently active**
alliance raid-boss event. So the same tool contributes a different melee/range
reduction depending on the target's area type and on live event state.

### 5.4 The feedback loop

`AttackerFlankEffectVO.updateEffectsWithNewTool(tool, area)` (BUNDLE @4955179,
tail) is applied **incrementally during the fill**, not only in the drag-and-drop
preview. `fillFlankWithTools` calls `t && t.updateEffectsWithNewTool(d, a)` after
every placement:

```
_attackerWallReduction += tool.wallBonus * tool.inventoryAmount
_attackerGateReduction += tool.gateBonus * tool.inventoryAmount
_attackerMoatReduction += tool.moatBonus * tool.inventoryAmount
i = tool.defRangeBonus;  n = tool.defMeleeBonus
for bonus in tool.effects:
    if EffectConditionHelper.isEffectApplicable(bonus.effect, area):
        if type == 217: i += 0.01 * bonus.strength
        if type == 215: n += 0.01 * bonus.strength
_defenderRangeReduction += i * tool.inventoryAmount
_defenderMeleeReduction += n * tool.inventoryAmount
```

Each placement therefore shrinks the next strategy's residual `p`, and can push
it to ≤ 0, popping that strategy. Note this path uses the **area-gated** form of
215/217, whereas `ToolUnitVO.getBonusByEffect` → `getEffectValue` uses
`CastleEffectConditionVO.NULL_CONDITION` and bypasses the gate. The divergence
is currently inert because only ungated effect 48 matters for normal flank math,
but it is real.

`_defenderMeleeReduction` accumulates here and is read **only** by
`ReduceMeleeBonusStrategy.getRelevantDefenderBonus` — never by `pickSoldierStack`
(§1.9), and `getAttackerFlankEffectVO` never populates it in the first place
(six constructor arguments, §1.6).

### 5.5 Slot mechanics and the post-condition

`AFillFlankStrategy.fillFlankWithTools` (@6474007):

```
if slot and slot.isFree() and slot.isUnlocked() and inventory.getToolCount() > 0 and container.freeItems > 0:
    ...
    if tool and tool.isToolForSlotType(slot.slotType):
        if container.getTotalAmountOfUntit(tool) > 0:
            slot = container.getAllSlotsWithUnit(tool)[0]
            slot.unitVO.inventoryAmount += tool.inventoryAmount     // stack into existing slot
        else:
            slot.unitVO = tool
        attackerVO && attackerVO.updateEffectsWithNewTool(tool, area)
    else:
        this._toolStrategyPool.pop()                                // wrong slot type -> pop the STRATEGY
```

Two behaviours worth stating: a picked tool that does not fit the current slot
type pops the **strategy**, not the slot; and a tool already present in the flank
merges into its existing slot rather than consuming a new one.

**Gate strategy is inert on the side flanks.** `FightScreenHelper.getDefenceBonuses`
ends `return t != ClientConstCastle.FLANK_MIDDLE && (n = 0), [i, n, o]` — the
gate term is zeroed off-middle (the moat term is **not**). So on left and right,
`ReduceGateBonusStrategy` sees `p <= 0` on its very first attempt and is popped,
which changes the pool state for every later strategy on that flank.

**A flank's tools can be undone.** `AFillFlankStrategy.checkFlank` (@6474893):

```
if unitContainer.sumOfItems == 0:
    for slot in toolContainer.items:
        if not slot.isFree(): inventory.addUnit(slot.unitVO.wodId, slot.getAmount()); slot.unitVO = null
    return false
return true
```

i.e. if zero soldiers landed on a flank, its tools are returned to inventory.

### 5.6 Support tools

Auto-fill has **no fill path** for the support container.
`AttackDialogAutoFill.autoFillSelectedWaves` handles the three flanks and the
yard; `onAutoFillClearClicked` does handle
`AttackDialogWaveHandlerSupportToolWaveInfoItemFoldOut.CONST_WAVE_NAME` via
`clearContainer(attackInfoVO.supportItemContainer)`, but there is no matching
fill branch. Whatever is already in the support container still:

- adds to every flank's attacker multipliers and reductions (§1.6), and
- grants attack waves (§1.1).

### 5.7 What actually reaches the wire

`CastleAttackData.sendAttack` (@14755979):

```
if attackInfoVO.isAttackComplete():
    send C2SCreateArmyAttackMovementVO(sourcePos, targetPos, army.getArmyData(), waitTime, ...,
                                       toolsSupportWodIds, yardWaveContainer.getSlotList(true))
```

- `isAttackComplete()` = `army.isAnyWaveComplete()`; `CastleAttackWaveVO.isWaveComplete`
  (@11523247) = `getSumOfUnits() > 0` — **tools do not count**.
- `CastleAttackArmyVO.getArmyData` (@6439828) **drops any wave with zero
  soldiers**, so wave indices in the `cra` payload do not match wave indices in
  the dialog.
- Flank waves serialize `getSlotList()` → `_items`; the yard serializes
  `getSlotList(true)` → `_serverItems`. `CastleFightItemContainer.addItemstoList`
  (@2469016) runs `addItemstoList(true, true)` then `addItemstoList(false)`, so
  `_serverItems` is natural slot order while `_items` is unlocked slots first
  followed by a second, distinct set of locked-slot VOs that the fill never
  touches.

---

## 6. The defender side

### 6.1 Assembly

`FightScreenHelper.getDefenderFlankEffectVO(attackInfo, flank)` (BUNDLE
@2323398):

```
i = getDefendingUnitStrength(attackInfo, flank)   // 6 values
n = getDefenceBonuses(attackInfo, flank)          // 3 values
return new DefenderFlankEffectVO(i[0], i[1], i[2], i[3], i[4], i[5], n[0], n[1], n[2])
```

`DefenderFlankEffectVO`'s constructor (@7664833) maps them, in order:

| # | Field | Default |
|---|---|---|
| 1 | `_meleeDefenceUnitsMeleeStrength` | 0 |
| 2 | `_meleeDefenceUnitsRangeStrength` | 0 |
| 3 | `_defenderMeleeBonus` | 1 |
| 4 | `_rangeDefenceUnitsMeleeStrength` | 0 |
| 5 | `_rangeDefenceUnitsRangeStrength` | 0 |
| 6 | `_defenderRangeBonus` | 1 |
| 7 | `_defenderWallBonus` | 1 |
| 8 | `_defenderGateBonus` | 1 |
| 9 | `_defenderMoatBonus` | 1 |

Final values (@7666856):

```
getMeleeDefenceValue(e, t) = _meleeDefenceUnitsMeleeStrength * (_defenderMeleeBonus - e)
                           + _rangeDefenceUnitsMeleeStrength * (_defenderRangeBonus - t)
getRangeDefenceValue(e, t) = _rangeDefenceUnitsRangeStrength * (_defenderRangeBonus - e)
                           + _meleeDefenceUnitsRangeStrength * (_defenderMeleeBonus - t)
```

### 6.2 Unit strengths and defence multipliers

`FightScreenHelper.getDefendingUnitStrength(attackInfo, flank)` (@2323634),
verbatim structure. Units come from
`spyInfo.itemsLeft` / `itemsMiddle` / `itemsRight` / `itemsKeep` by flank
(`FLANK_YARD` and the default branch both use `itemsKeep`), **always
concatenated with `spyInfo.itemsSupport`**.

```
i = n = o = u = 0;  d = 1 (melee mult);  h = 1 (range mult)

for each SoldierUnitVO f:
    if f.role == ROLE_MELEE: i += f.meleeDefence * f.inventoryAmount
                             n += f.rangeDefence * f.inventoryAmount
    else:                    o += f.meleeDefence * f.inventoryAmount
                             u += f.rangeDefence * f.inventoryAmount

for each ToolUnitVO E:
    d += E.defMeleeBonus                            // NOT multiplied by inventoryAmount
    h += E.defRangeBonus
    O = E.getBonusByEffect(ToolEffectType.DEFENSE_BONUS)   // effect type 31
    d += O;  h += O

if spyInfo.defendingLord:
    d += getFullDefenseBonusForLordByFlankAndAreaType(lord, areaType, flank, true)
    h += ...(isMelee = false)

for each skill id in spyInfo.defenderSkills:
    DEFENSE_MELEE_BONUS (27) -> d += totalEffectValue/100
    DEFENSE_RANGE_BONUS (30) -> h += totalEffectValue/100

return [i, n, d, o, u, h]
```

**Defender tool bonuses are not multiplied by `inventoryAmount`** — unlike the
attacker's, which are.

`CastleEffectsHelper.getFullDefenseBonusForLordByFlankAndAreaType(lord, areaType, flank, isMelee)`
(@565250), verbatim:

```
o  = equip(EFFECT_TYPE_DEFENSE_BONUS /*31*/).strength
o += equip(isMelee ? EFFECT_TYPE_MELEE_BONUS /*9*/ : EFFECT_TYPE_RANGE_BONUS /*10*/).strength
if flank == FLANK_MIDDLE:               o += equip(EFFECT_TYPE_DEFENSE_BOOST_FRONT /*49*/).strength
if flank == FLANK_LEFT or FLANK_RIGHT:  o += equip(EFFECT_TYPE_DEFENSE_BOOST_FLANK /*50*/).strength
if flank == FLANK_MIDDLE:               o += equip(EFFECT_TYPE_DEFENSE_BOOST_YARD /*32*/).rawValues[0]
return o / 100
```

Two oddities, **reported as found, not rationalised**: type 32 (yard defence
boost) is applied on `FLANK_MIDDLE` rather than `FLANK_YARD`, and it reads
`.rawValues[0]` instead of `.strength` unlike every other term in the function.

### 6.3 Wall / gate / moat

`FightScreenHelper.getDefenceBonuses(attackInfo, flank)` (@2325271):

```
i = max(attackInfo.baseWallBonus, targetArea.baseWallBonus) / 100
n = max(attackInfo.baseGateBonus, targetArea.baseGateBonus) / 100
o = max(attackInfo.baseMoatBonus, targetArea.baseMoatBonus) / 100

for each ToolUnitVO d in (flank container + itemsSupport):
    i += d.wallBonus;  n += d.gateBonus;  o += d.moatBonus     // not × inventoryAmount

if spyInfo.defendingLord C:
    i += equip(C, EFFECT_TYPE_WALL_BONUS /*6*/, targetArea.areaType).strength / 100
    n += equip(C, EFFECT_TYPE_GATE_BONUS /*7*/, ...).strength / 100
    o += equip(C, EFFECT_TYPE_MOAT_BONUS /*8*/, ...).strength / 100

for each skill in spyInfo.defenderSkills:
    WALL_BONUS (35) -> i += totalEffectValue/100
    GATE_BONUS (24) -> n += totalEffectValue/100
    MOAT_BONUS (42) -> o += totalEffectValue/100

return flank != FLANK_MIDDLE ? [i, 0, o] : [i, n, o]
```

There is **no `FLANK_YARD` case** in the flank switch — the default branch
(`itemsKeep`) covers it, and the gate term is zeroed for it too.

Base values come from the map-object VO:

| VO | Fields |
|---|---|
| `InteractiveMapobjectVO` | `baseWallBonus`, `baseGateBonus`, `baseMoatBonus` (player castles, generic areas) |
| `FactionCampMapobjectVO` | `baseWallBonus` |
| `DungeonMapobjectVO` | `baseWallBonus`, `baseGateBonus` |
| `FactionInvasionCampMapObjectVO` | `baseWallBonus` |
| `ResourceIsleMapobjectVO`, `DungeonIsleMapobjectVO` | base wall bonus |
| `CastleTreasureHuntFightscreenVO` | base wall/gate bonus |
| `DummyMapobjectVO` | wall/gate/moat |
| NomadCamp, SamuraiCamp, AlienInvasion, AllianceInvasionCamp, Daimyo, Wolfking | **from the server comm array**, not client tables |

`AttackDialogHelper.calculateToolsInfo` subtracts the attacker's reductions from
these at the level cap, and gates the lord's defence flanks differently from
`FightScreenHelper`. Which matches the server is **not established** (§0).

Alliance-tower fights override wall/gate/moat via
`CastleDefenceDialog.calculateToolsInfo` and the tower's own data (§6.6).

### 6.4 NPC camp and dungeon tables

None of these carry effect ids — they are **scalar defence columns**. Verified
column presence across all rows (not first-row sampling):

| ITEMS table | rows | Defence columns present |
|---|---|---|
| `nomadCamps` | 90 | `wallBonus`, `gateBonus`, `defStrength`, `defenceUnits`, `defenceTools`, `dungeonPToolStacks`, `dungeonNPToolStacks`, `lordID`, `guards`, `unitWallCount` — **no `moatBonus`** |
| `samuraiCamps` | 90 | identical set — no `moatBonus` |
| `factioninvasioncamps` | 154 | identical set — no `moatBonus` |
| `allianceInvasionCamps` | 26 | identical set + `generatedRagePerDefense` (16) — no `moatBonus` |
| `allianceBattleGroundDungeons` | 40 | identical set — no `moatBonus` |
| `dungeons` | 1769 | `lordID` (1555), `unitsL/M/R` (~1500 each), `unitsK` (991), `toolL/M/R` (~1400 each) — **no wall/gate/moat columns** |
| `specialcamps` | 91 | `defStrength`, `dungeonPTools`, `randomizedDefence` on **1 row only**; the other 90 carry no defence data |
| `bossdungeons` | 3 | only `attackStrength` — **no defence, wall/gate/moat or composition data at all** |
| `eventAutoScalings` | 44 | `wallReductionBoost`, `gateReductionBoost`, `moatReductionBoost`, `guardsReductionBoost`, `npcDefenseScoreMultiplier`, `defaultDefenseUnits`, `default{Wall,Gate,Moat,Range,Melee}DefenseTools`, `default{Attack…}Tools`, `wavesPerTool`, `minDefStrength`, `toolPlayerLevel` |
| `eventAutoScalingCamps` | 1078 | `maxTroopCapacityDefense`, `randomFactorDefense`, `normal/premiumDiffDefStrengthBoostMin/Max{Defense,Attack}`, `lordID`, `unitCapacity`, `flank/frontToolsPerWave(Min/Max)` — **no `wallBonus`/`gateBonus`** |
| `tmapnodes` | 499 | `wallBonus` (290), `gateBonus` (290), `defStrength`/`defenceUnits`/`defenceTools`/`unitWallCount`/`randomizedDefence` (176) |
| `isles` | 14 | `wallBonus`, `gateBonus`, **`moatBonus`**, `wallLevel`, `gateLevel`, `moatLevel`, `guards` — all 14 rows |
| `daimyoCastles` | 30 | `wallBonus`, `gateBonus`, `guards`, `unitWallCount` — no `moatBonus` |
| `daimyoTownships` | 30 | `wallBonus`, `gateBonus`, **`moatBonus`**, `unitWallCount`, `unitCapacity` |
| `emptyAreas` | 24 | `unitWallCount`, `lordID`, `wallWodId`, `gateWodId`, `defStrength`, `defenceUnits`, `defenceTools`, `guards`, `peasants` |
| `villages` | 3 | `wallWodId`, `gateWodId`, `moatWodId`, `unitWallCount`, `peasants`, `guards` |
| `allianceTowers` | 5 | `wallWodId`, `gateWodId`, `moatWodId`, `unitWallCount`, `peasants`, `guards`, `lordID`, `unitCapacity`, plus `areaSpecificEffects` → effect type **181** on all 5 rows |
| `lords` | 92 | `lordID`; 81 rows carry `effects` (NPC lord bonuses, §3.3) |

**Base defender capacity** is not an effect type either. ITEMS `buildings`
columns `unitWallCount` (14 rows) and `unitSize` (20 rows) are the flat base that
the percentage effects multiply: `AEffectBuildingVO.parseXmlNode` (@342478) does
`_unitCapacity = int(getIntAttribute("unitSize", t))` and
`_unitWallCount = int(getIntAttribute("unitWallCount", t))`, with
`_morality` from `Moral`. Displayed as "unitCapacity" by
`GuardTowerVO.createInfoPanelItems` (@5723262).

The `dungeons` composition string format (`unitsM` = `"603+2#606+2#607+4"`,
`toolM` = `"637+1#626+1"`) is **(inferred)** as `wodID+count` with `#`
separating stacks. Grepping the bundle for `unitsL` / `toolM` finds **no
client-side parser** — the table appears to be server-only data, so the format
is not verified.

### 6.5 Alliance raid boss

Base parameters, ITEMS `raidBossLevels` (60 rows): `raidBossLevelID`,
`raidBossID`, `level`, `wallRegenerationTime`, `courtyardReserveUnits`,
`courtyardMeleePercent`, `courtyardSize`, `minPointsForBossRewards`,
`lootBoxTombolaID`, `rewardIDs`. Read by `AllianceRaidbossLevelVO` (@13055800);
DLL `CommKeys` at @2713337 / @2713403 / @2713520.

Effect delivery, ITEMS `raidBossStages` (397 rows), parsed by
`AllianceRaidbossStageVO` (@13059700). Six effect columns, joined to effect types:

| Column | rows | effect types |
|---|---|---|
| `defenderBattleEffects` | 397 | 49×397, 50×397, 6×377, 7×377, 32×362 |
| `attackerBattleEffects` | 155 | 24×88, 23×67 (delivered as maluses) |
| `defenderStageEffects` | 337 | 207×317, 214×40 |
| `defenderWallRegenerationEffects` | 257 | 213×357 |
| `attackerPostBattleEffects` | 120 | 197×120, 198×120, 199×228, 200×66, 201×66 |
| `defenderPostBattleEffects` | 157 | 214×471 |

Rows also carry `leftWallUnits` / `frontWallUnits` / `rightWallUnits` (e.g.
`"506+500#505+400"`), `wallPointFactor`, `courtyardPointFactor` and
`HighlightEffectIcon`. The VO declares an `_attackerStageEffects` list with **no
matching ITEMS column** in this dataset.

None of the raid-boss effect types (172–177, 197–214) has client-side battle
math; they appear only in the enum block, the icon tables,
`ToolUnitVO.createEffectMapping` and `AllianceRaidHighlightedEffectTooltip`.
Server-side resolution is **(inferred)**.

### 6.6 Alliance Battleground towers

ITEMS `allianceTowerEffects` (5 rows) → effect types **6 `wallBonus`,
7 `gateBonus`, 9 `meleeBonus`, 10 `rangeBonus`, 32 `defenseBoostYard`**
(the catalog's "141–144, none 148-typed" was short by one row and never resolved
the types). Every row: `effectBasePrice` 100, `effectMaxLevel` 60,
`effectStartValue` 1, `effectIncrease` 2 — so **value = 1 + 2·(level − 1)**,
maximum 119 at level 60.

Companions: `allianceTowerEffectsActivations` (6 rows:
`allianceTowerEffectsActivationID`, `remainingTime` 21600/18000/…, `cost`
5000/10000/…) sets activation duration and price;
`allianceBattleGroundSettings.allianceTowerEffectIDs` (3 of 15 rows) selects
which are live per preset, alongside `defenceTowerLossMalus`,
`defenceTowerLossMalusMax`, `malusCurrencyID`; `allianceTowers` (5 rows) carries
`areaSpecificEffects` → type 181.

`ABGAllianceTowerEffectVO.currentBonusVO` is built as a `RawLordEffectBonusVO`
(the same class as `_rawLordEffects`), but **the site that folds it into a fight
was not found**.

### 6.7 Defender-side effect types with no client consumer

Reported so a porter does not go looking: 181, 182, 183, 184 and 194 appear only
in the enum definition, in `isDefenseEffect`, and in building info panels
(`KeepBuildingVO`, `StrongholdBuildingVO`, `GuardpostBuildingVO`,
`MaintentBuildingVO`, `FactionUnittentBuildingVO`). **No formula reads them** —
defender courtyard capacity is never computed client-side. They do have shipped
data (`buildings.areaSpecificEffects`, `allianceTowers`, `constructionItems`,
`generalSkills`), so they are real; server-side application is **(inferred)**.

Same status for 47 `DefenseSupportUnits` and 51 `AttackSupportUnits`: their only
references are the two classifiers, `RelicEquipmentUpgradeInfoComponent.getValueTextVO`
(a tooltip) and the gem colour table.

Also read only by classification switches or text composers, never by a combat
formula: 11 `npcDefenseBonus`, 82 `moraleBoost`, 78 `auxiliaryCapacityBoost`,
83 `enemyFameBoost`, 84 `enemyLootBoost`, 73 `spyCountBoost`, 25 `smashChance`.

Alliance `TYPE_TEMP_DEFENSE_POWER_BOOST` and `TYPE_KHAN_DEFENSE_BOOST` exist in
`CastleEffectsHelper.getNameTextId` but have **no wiring into
`getDefendingUnitStrength` / `getDefenceBonuses`**.

---

## 7. Protocol sources

Which server command a bot reads each source from. Command ids are
`ClientConstSF` constants; payload keys are `CommKeys`.

`gbd` (`S2C_GET_BASIC_DATA`, BUNDLE @14413000–14417500) is the login mega-payload
and carries the initial snapshot of most of these as sub-keys:
`gli rei vip bie gatp skl sei gai boi ain gls nec gpi kpi gxp vli uap uar ufa uht dcl gcl esl …`.
A bot gets most values without extra round-trips.

| Bonus source | Command | Payload / parse site |
|---|---|---|
| Commander + castellan equipment, gems, relics, sets, raw effects | `gli` | `LordVO.parseLord` @3172607: `ID E AE W D SPR EQ AIE`/`TAE VIS N GID`. `E`/`AE` entry = `[effectID, valueArray, extra]` → `parseRawEffects` @3175262. `EQ` entry array: 0 id, 1 slotTypeId, 2 lordTypeId, 3 rareID, 4 graphic, 5 boni, 6 uniqueID, 7 setID, 8 enchantLvl, 9 durationSec, 10 gemID, 11 equipmentTypeID (3 = RELIC) / alienString, 12 relic `[type, cat, might, gem]`. `boni` entry = `[effectID, value or valueArray]` |
| Generals (star level, unlocked skills, selected abilities) | `gie` | `GeneralsData.parse_GIE` @13014149: `{G:[{GID,XP,ST,IN,LU,SIDS,GASAIDS,LEVEL,OLD_XP,WINS,DEFEATS}]}` |
| Assign general to a lord | `gla` | response re-delivers the whole `gli` list |
| Set a general's abilities | `gaae` | C2S only (`GASAIDS`) |
| Generals hub status | `gcs` | `{CHR:[{CID,…}]}` — **not** a combat-bonus carrier |
| Which global effects are currently boosted | `bie` | `GlobalEffectData.parse_GIE` @15673466: `{GE:[globalEffectID]}` (`S2C_GLOBAL_EFFECT_BOOSTER_INFO_EVENT`) |
| Legend skills + sceat skills | `skl` | `CastleLegendSkillData.parse_SKL`: `SID[] SIDS[] SP RS RC SSA[{ID,RS}]`. Also pushed via `ego` (`i.skl` branch) |
| Research | `rei` | `CastleResearchData.parse_REI` @15315245: `BR[] ARID ARRT` |
| Unequipped equipment (swap candidates) | `gei` | `CastleEquipmentData.parse_GEI` @15677703: `{I:[equipArray]}` |
| **Attack pre-calculation** | `aci` | `CastleAttackData.parse_ACI` @14752091 → `CastleAttackInfoVO.fillFromParamObject` @3629428: `gaa.AI` (target area, incl. `baseWallBonus`/`baseGateBonus`/`baseMoatBonus`), `gui.I`, `gui.SHI`, `SCID`, `KID`, **`KTB`** (kingstower bonus), **`MB`** (monument bonus), `S`, `AS`, `abe`/`B`, `LS`, an embedded `gli`, `HAWL` |
| Attack counter (**not** a pre-calculation) | `gai` | `AttackCounterVO.parseParamObject` @7599970: `AC ACTH ACGR` — carries no combat bonuses. Two `CommKeys.ATTACK_COUNT` definitions exist in the DLL (`"AAC"` and `"AC"`); which one `AttackCounterVO` binds is **not established** — tolerate both |
| Own unit + stronghold inventory | `gui` | `{I, SHI}` (also embedded in `aci`) |
| VIP level | `vip` | `CastleVIPData.parse_VIP` @5531044: `VP VRL UPG VRS` → `attackSpeedBonus` |
| Boosters, premium account, horse | `boi` | `CastlePremiumBoostData.parse_BOI` @1871375: `BO[{ID,…}] PT SU[] ST[] bfs` |
| Subscriptions | `sie` | `SubscriptionData.parseSIE`: `{SP:[activePackage]}` |
| Officers school, active effect | `gatp` | `OfficersSchoolData.parse_GATP` @15741084: `{S, E, RS}` |
| Officers school, offer list | `gtp` | `{TP[], AT{TE,D}, PC, RCSC, RCHC, CT}` — per-entry field names inside `TP[]` **not dumped** |
| Alliance info incl. buff list, landmarks | `ain` | `parseAllianceInfo(e.A)` → `fillFromParamObject`: `AID N M ML MP ABL[] ADL AMI STO …` |
| Alliance buff levels | `abl` | `AllianceInfoVO.parseABL`: `{ABL:[{BT,L,CD}]}` → `getAllianceBuffVoBySeriesIDAndLevel(seriesId, level)` |
| Alliance tower buffs | `tbi` | `allianceBattlegroundData.parseTBI`; per-effect fields inside `TE[]` beyond `TEID` **not dumped** |
| Alliance tower positions | `tie` / `tpi` | `{TOWERS:[area]}` — targets, not bonus values |
| Player crest | `gem` | `S2C_GET_EMBLEM`; fields `IS SPT S1 SC1 S2 SC2 BGT BGC1 BGC2` → `playerCrest.getEffectsByType` |
| Titles | `uar` / `uht` / `ufa` / `apt` | `CastleTitleData.parseUAR`: `SFX PFX`; `uht` `{RS}`; `apt` `{TI}` |
| Global / event effects | `sei` | `C2S/S2C_SPECIAL_EVENT_INFO` → `globalEffectData.getGlobalEffectsByType` |
| Construction items | `nec` + `gca` `CI` | `S2C_GET_NEXT_EXPIRING_CONSTRUCTION_ITEM_EVENT`; the `CI` block arrives with the area |
| Buildings / castle layout | `jaa` | `AreaDataUpdater.parseJAA` @14571795: `gca csl grc gpa gab`; `gca` → `scl`, `CI` |
| Alliance crest layout | *(via `ain`)* | `AllianceInfoVO.getLayoutEffectsByType` @3068007 |

### 7.1 Sources with no protocol read path

- **Building combat effects — no dedicated command.** Buildings arrive with the
  area (`jaa` → `gca`); their effects are derived **client-side from static
  ITEMS columns**, not from the wire: `ABasicBuildingVO` stores
  `_effectsString` = `getStringAttribute("effects")` and `_areaEffectsString` =
  `getStringAttribute("areaSpecificEffects")`, and `parseEffects` /
  `parseAreaSpecificEffects` (@2206813–2207514) split on `,` then `&`, resolve
  via `CastleModel.effectsData.getEffectByID` and build `BonusVO`s. (ITEMS
  `buildings` has **no `effects` column at all** — only `areaSpecificEffects`.)
- **Officers school delivery.** `CommKeys.EFFECT_SOURCE_TRAINING = "TG"` maps to
  `EffectSourceEnum.BUILDING`, which suggests delivery via the lord's `E`/`AE`
  raw-effect payload — but no `TG`-tagged payload was ever observed. **No known
  source yet.**
- **`eventAutoScalingLordEffects` / `eventAutoScalingHoLSkills` injection.** The
  tables and the VO caches (`_eventAutoScalingDifficultyEffectVOsByDifficultyID`)
  exist; **no client-side path from them into a lord's bonus list was found.**
- **`ABGAllianceTowerEffectVO` consumption site.** **No known source yet.**
- **Alliance temporary power boosts** reach the client through `ain`/`abl`, but
  their application site in the fight math was not found (§6.7).
- **Morality.** Fed by `buildings.Moral` and title effect 82; converted by
  `CombatConst.getMoralBonus`; per-battle value arrives in the battle log
  (`moralBoost`). No pre-attack command exposing the resolved multiplier was
  found.
- **`ego`** (`S2C_EDITOR_GLOBAL_OBJECT`) pushes `skl` updates outside a `skl`
  request; its `ClientConstSF` constant string was not read, so its command id
  is **unconfirmed**.

---

## 8. Open questions

Stated plainly; none of these are resolved by the three files.

**Server vs client**

1. Whether the server applies the same cap and merge semantics as
   `getTotalEffectValue`. The capped/uncapped split in §3.1 is a client-side
   arrangement and could not be cross-checked.
2. Which of the three client implementations of the defender-facing numbers
   (`FightScreenHelper`, `AttackDialogHelper.calculateToolsInfo`,
   `CastleFightDialog.calculateToolsInfo`) matches the server.
3. Whether the server applies `CombatConst.getMoralBonus` as an attack
   multiplier. No client fight-strength site reads it.
4. Whether the server uses the same `+1` base multiplier, the same
   `inventoryAmount`-vs-`getAmount()` stacking, and the same
   ATTACK_BONUS-to-both-melee-and-range doubling for tools.
5. Whether `EffectValueMap.strength` returning the **first** map value (rather
   than the requested `wodId`'s) matches server behaviour. Unobservable today.

**Unresolved client behaviour**

6. Deterministic ordering inside a mixed-sign cap bucket (§4.5).
7. Whether any code path constructs a plain `BonusVO` with `capID` −1, which
   would throw in `maxValueStrength` (§4.2).
8. Whether `CastleUserData.getGlobalConstructionItemEffectsByType` returning `[]`
   unconditionally is a live bug or dead code (§3.3).
9. `CastleEffectConditionVO`'s constructor is `(areaType, spaceId, wodId,
   otherPlayer)`, but `getGlobalEffectValue` / `getSubscriptionEffectValue` /
   `getResearchEffectValue` construct it as `(i, n, t)` with locals whose
   defaults imply a different intent. Whether this is an argument-order bug or
   minifier naming is **not established**.
10. Why lord effect type 32 is applied on `FLANK_MIDDLE` rather than
    `FLANK_YARD`, and why it reads `.rawValues[0]` (§6.2).
11. Whether a separate code path supplies defender **melee** reduction for
    raid-boss attacks. `getAttackerFlankEffectVO` never populates
    `_defenderMeleeReduction`; harmless today because no `typ=Attack` tool in
    ITEMS carries `defMeleeBonus` and effects 489/491 are raid-boss-3 gated.
12. The meaning of `slotType` 9 — present on 485 of 527 tools, no constant, no
    `ITEMS_*` reference (§5.1).
13. The meaning of ITEMS `equipment_slots.bonus` (armor 100, weapon 90, …). Its
    consumer was not traced; "slot-relative bonus scaling" is **(inferred)**.
14. What ITEMS `levelBoosters.boosterType` values 19 (51 rows) and 11 (22 rows)
    target. **(inferred)** as production / collect boosters, not verified.
15. `ToolEffectType`'s numeric constructor argument is 0 for ~30 members, so it
    is not a usable id; `ToolUnitVO.getBonusByEffect`'s lookup logic was not
    dumped.

**Data with no located consumer**

16. Where general **ability** skills are applied. `GeneralVO.getPassiveSkills`
    filters them out; no client application site exists (§2.2).
17. What each ability effect type 1001–1042 numerically does. The magnitudes are
    in `generalAbilityEffects`, but their semantics are not readable client-side.
18. Ability name mismatches between enum and ITEMS, unresolvable as to which side
    is stale: 1010 (`LIVE_TO_FIGHT_ANOTHER` vs `EndlessPractice`), 1011
    (`STRATEGICAL_RETREAT` vs `WayoftheSword`), 1012 (`REINFORCEMENTS` vs
    `IronWill`), 1029 (`GOLD_RUSH` vs `TheWayofPerfection`), 1040
    (`RANGE_REDUCTION` vs `MindClarityOddWave`). **Use the numeric id.**
19. Where the eight items-only effect types (55, 57, 87, 153, 155, 157, 158, 188)
    are handled. Only their **absence** from the client enum was verified;
    calling them server-side is **(inferred)**.
20. The source of a boss dungeon's defence. `bossdungeons` carries none (§6.4).
21. The server's moat source for `nomadCamps` / `samuraiCamps` /
    `factioninvasioncamps` / `allianceInvasionCamps` /
    `allianceBattleGroundDungeons` — all have `wallBonus` and `gateBonus` but no
    `moatBonus` column, while the corresponding map-object VOs accept a
    `baseMoatBonus` from the server comm array.
22. `eventAutoScalingCamps` has no `wallBonus`/`gateBonus` columns; those reach
    the client only as comm-array indices (`e[9]`/`e[10]`/`e[11]`). The
    server-side derivation from `eventAutoScalingLordEffects`
    `difficultyScalingWallBonus`/`GateBonus` `minValue..maxValue` is
    **(inferred)**.
23. Most `specialcamps` rows (90 of 91) carry no defence data at all.
24. The `dungeons` composition string format is **(inferred)** — no client
    parser exists (§6.4).
25. `raidBossStages`' VO declares `_attackerStageEffects` with no matching ITEMS
    column (§6.5).
26. Legend skill `DEFENSE_YARD_BONUS` (id 36) and effect types 182 / 184 appear
    in no defender strength or bonus path.
27. ITEMS `titles.titleEffectID` appears **0 times** in the bundle and once in
    the DLL. Its use is **not established**.
28. VIP `attackFameBonus` has three references, none a fame formula. Server-side
    application is **(inferred)**.
29. Values of `TravelConst.CAPITAL_CONQUER_SPEED`, `METROPOL_CONQUER_SPEED`,
    `BARON_SPEED`, `TRAVEL_BOOST_TUTORIAL` were not dumped.
30. `CastleSpyArmyInfoVO.parseArmyInfo`'s four `aci` arguments (`S`, `AS`,
    `abe`/`B`, `LS`) were identified by position; their internal field layout —
    the defender's actual unit and tool composition — was **not expanded**. This
    is the largest remaining protocol gap for the auto-fill port, since
    `hasMeleeDefenders` / `hasRangeDefenders` and all four unit-strength sums
    come from it.
