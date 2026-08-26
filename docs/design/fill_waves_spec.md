# Fill-Waves Implementation Spec

**Purpose:** enough detail to write the three pieces of attack auto-fill the
port still lacks, in Python, without opening the client again.

1. Tool filling — the five strategies, slot matching, `checkFlank`, and the
   feedback into the attacker effects.
2. The yard / final-assault wave — its capacity and the `RW` payload field.
3. Buffed unit attack values — effect type 148.

**Sources**, same three artefacts as `docs/design/combat_effects.md`:

| Short name | File | What it is |
|---|---|---|
| BUNDLE | `Game.bundle.<hash>.js` | the Empire HTML5 client |
| DLL | `dll/ggs.dll.<hash>.js` | `CombatConst`, `ClientConst*`, `EffectConst` |
| ITEMS | `items.json` | the game-data tables |

Every formula names the client symbol or ITEMS table it came from. `@N` is a
character offset into the named file. Claims that cannot be read from those
files are marked **(inferred)**; where nothing could be established the entry
says so rather than guessing.

**Scope caveat.** All of this is the *client's* arrangement. The server resolves
the real battle and its code is not in these files. The goal is to reproduce
which units and tools the client would place, which is decided entirely
client-side.

**Two helpers assumed present.** `int(x)` is the client's truncation
(`ggs.dll.js` @2249491) — `math.trunc`, toward zero, **not** floor. JS
`Math.round` is `floor(x + 0.5)`, half **up**, which is not Python's `round`.

---

## 1. Tool filling

Already in the port and treated here as verified input: wave and flank capacity
(`combat/capacity.py`), attacker melee/range multipliers and wall/gate/moat
reductions before any tool is placed (`combat/effects.py`,
`FightScreenHelper.getAttackerFlankEffectVO`), the defender-side
`DefenderFlankEffects`, and effect resolution with caps and conditions
(`combat/bonuses.py`). This section covers only what happens once filling
starts.

### 1.1 The strategy pool

`AFillFlankStrategy.prototype.fillToolStrategyPool` (BUNDLE @6475247), verbatim:

```js
this._toolStrategyPool=[],
this._toolStrategyPool.push(new ReduceMoatBonusStrategy),
this._toolStrategyPool.push(new ReduceRangeBonusStrategy),
this._toolStrategyPool.push(new ReduceMeleeBonusStrategy),
this._toolStrategyPool.push(new ReduceGateBonusStrategy),
this._toolStrategyPool.push(new ReduceWallBonusStrategy)
```

Picks always read `pool[pool.length-1]` and `pool.pop()` on failure, so the
effective priority is **wall → gate → melee → range → moat**.

`AFillWaveStrategy.fillWave` (BUNDLE @11696519) calls `fillToolStrategyPool()`
again before each of left, right and middle. **The pool resets per flank**;
exhaustion never leaks across flanks. The port's
`default_tool_strategies()` list must be rebuilt per flank, not shared.

### 1.2 The five strategies

Each subclass supplies two methods; only range and melee override
`pickToolByStrategy`, and only to add a precondition.

| Strategy | BUNDLE | `getRelevantToolBonus(tool)` | `getRelevantDefenderBonus(att, def)` | Precondition |
|---|---|---|---|---|
| `ReduceWallBonusStrategy` | @11703928 | `tool.wallBonus` | `def.defenderWallBonus - att.attackerWallReduction` | — |
| `ReduceGateBonusStrategy` | @11701000 | `tool.gateBonus` | `def.defenderGateBonus - att.attackerGateReduction` | — |
| `ReduceMeleeBonusStrategy` | @11703067 | `tool.defMeleeBonus + getConditionedEffectBonus(tool, 215)` | `def.defenderMeleeBonus - att.defenderMeleeReduction` | `def.hasMeleeDefenders` |
| `ReduceRangeBonusStrategy` | @11702198 | `tool.defRangeBonus + getConditionedEffectBonus(tool, 217)` | `def.defenderRangeBonus - att.defenderRangeReduction` | `def.hasRangeDefenders` |
| `ReduceMoatBonusStrategy` | @11701595 | `tool.moatBonus` | `def.defenderMoatBonus - att.attackerMoatReduction` | — |

The range and melee overrides are `return i.hasRangeDefenders ? super(...) :
null` and `return i.hasMeleeDefenders ? super(...) : null`, where `i` is the
defender effects. The getters are

```
hasMeleeDefenders = _meleeDefenceUnitsMeleeStrength != 0 || _meleeDefenceUnitsRangeStrength != 0
hasRangeDefenders = _rangeDefenceUnitsMeleeStrength != 0 || _rangeDefenceUnitsRangeStrength != 0
```

already modelled as `DefenderFlankEffects.has_melee_defenders` /
`.has_range_defenders`.

**The melee and range strategies are live in this ITEMS snapshot.** No
`typ=="Attack"` row carries `defMeleeBonus`, but six do carry the effect rows
that feed the conditioned term — see §1.9. The port's strategy table now adds it
(`combat/tools.py:170` and `:177`, `malus_effect_type` plus
`conditioned_effect_bonus`), so
a strategy that reads the scalar column alone would silently score those six at
zero.

### 1.3 `getConditionedEffectBonus`

`AReduceDefenseBonusStrategy.prototype.getConditionedEffectBonus`
(BUNDLE @2895560), verbatim:

```js
function(e,t){if(!e||!e.effects)return 0;
for(var i=0,n=0,o=e.effects;n<o.length;n++){var a=o[n];
a&&a.effect&&a.effect.effectType&&(a.effect.effectType.type==t
&&EffectConditionHelper.isEffectApplicable(a.effect,this._area)&&(i+=.01*a.strength))}
return i}
```

`t` is an **EffectTypeEnum id** (215 or 217), not an ITEMS `effects` row id.
`this._area` is assigned at the top of `pickToolByStrategy` from its sixth
argument, the defender area.

`EffectConditionHelper.isEffectApplicable(effect, area)`:

```
if not effect: return False
if area and not effect.isForAreaType(area.areaType): return False
if len(effect.raidBossIDs) > 0:
    ev = AllianceRaidbossEventEventVO.getActiveEventVO()
    if not ev or not ev.raidBossServerDataVO: return False
    if not effect.isForRaidBoss(ev.raidBossServerDataVO.raidBossID): return False
return True
```

`isForAreaType(x)` is `len(areaTypes) == 0 or x in areaTypes`, from ITEMS
`effects.areaTypeID` (comma list). `raidBossIDs` comes from
`effects.raidBossID`.

This is the **only** path on which a tool effect's conditions are honoured.
`ToolUnitVO.getBonusByEffect` ignores them entirely (it passes
`NULL_CONDITION` = `(-1,-1,-1,None)` and every guard is a `> -1` test), which
is documented in `combat_effects.md` §5.1 and is not changed here.

### 1.4 Candidate eligibility

`AReduceDefenseBonusStrategy.prototype.pickToolByStrategy` (BUNDLE @2895880),
verbatim:

```js
function(e,t,i,o,r,l,c,d){this._area=l;var p=this.getRelevantDefenderBonus(e,t);
if(p<=0)return null;
for(var h,g=i.getTools(),C=-1,_=-1,m=-1,f=-1,E=0,O=0;O<g.length;O++){
var y=n.castAs(g[O],"ToolUnitVO");
if(y&&y.attackType==s.ClientConstCastle.ATTACK_TOOL
&&u.AttackHelper.canUseToolForAttackOnTarget(l,y,r)
&&this.getRelevantToolBonus(y)>0&&y.inventoryAmount>0){
var b=Math.ceil(p/this.getRelevantToolBonus(y)*100/100),
D=y.amountPerWave>0?y.amountPerWave-d.getSumOfToolsByTool(y):c.freeItems,
I=a.int(Math.min(y.inventoryAmount,o,D));
if(b<=I)(b<_||-1==_)&&(C=a.int(y.wodId),_=b);
else{var v=this.getRelevantToolBonus(y)*I;v>E&&(m=a.int(y.wodId),f=I,E=v)}}}
return-1!=C?h=i.deductUnit(C,_):-1!=m&&(h=i.deductUnit(m,f)),h}
```

Argument mapping from the caller: `e` = attacker flank effects, `t` = defender
flank effects, `i` = filtered inventory, `o` = `container.freeItems`, `r` =
defender space id, `l` = defender area, `c` = container, `d` = the wave VO.

**Early guard.** `p <= 0` returns `null` *before* the candidate loop, so no
deduction happens. This is why the gate strategy is harmless on the side
flanks — see §1.7.

**Filter.** A candidate must satisfy all five:

1. `castAs(x, "ToolUnitVO")` is non-null.
2. `attackType == ClientConstCastle.ATTACK_TOOL`, which is the **string**
   `"Attack"` (`DEFENSE_TOOL` is `"Defence"`), from ITEMS `units.typ`.
3. `AttackHelper.canUseToolForAttackOnTarget(defenderArea, tool, spaceId)`.
4. `getRelevantToolBonus(tool) > 0`.
5. `tool.inventoryAmount > 0`.

There is **no slot-type filtering here**. Slot matching happens afterwards in
`fillFlankWithTools`, which is what makes the discard quirk in §1.7 possible.

### 1.5 `canUseToolForAttackOnTarget`

`AttackHelper.canUseToolForAttackOnTarget` (BUNDLE @1086773):

```
def can_use(area, tool, space_id):
    a = tool.canBeUsedToAttackNPC or area.hasOtherPlayerInfo \
        or isinstance(area, AAlienInvasionMapobjectVO)
    s = tool.isAllowedByAttackTarget(space_id, area.areaType)
    if a and s:
        r = castAs(tool, "EventtoolUnitVO")
        if not (r and len(r.usedForEvent) > 0 and r.inventoryAmount == 0):
            return True
        for u in r.usedForEvent:
            if CastleModel.specialEventData.isEventActive(u): return True
    return False
```

```
def is_allowed_by_attack_target(space_id, area_type, allowed):   # _allowedToAttack
    if len(allowed) < 1: return True                 # empty list = allowed everywhere
    for space, atype in allowed:
        if (space == space_id or space == -1) and (atype == -1 or atype == area_type):
            return True
    return False
```

`-1` is `BasicUnitVO.ALL_ALLOWED`.

Data facts a port needs:

- `canBeUsedToAttackNPC` parses as `1 == parseInt(getValueOrDefault(..., "1"))`,
  so **absent means true**. It is present on exactly 50 of the 353 attack tools
  and every one of those 50 has the value `"0"` — in practice a pure opt-out
  flag. The port's `ToolStats.can_attack_npc` defaults to `False`
  (`gamedata/models.py:141`), which inverts this; fix the default or the gate
  rejects almost every tool.
- `allowedToAttack` is `"spaceId+areaType#spaceId+areaType#..."`, parsed by
  `BasicUnitVO.parseSpaceIdAreaTypeValues`: split `#`, drop a leading empty
  entry, split `+`, `parseInt` both. Present on 185 attack tools. In this
  snapshot no pair contains `-1`, no value has a leading `#`, and every pair has
  the two-field shape — so the sentinel and empty-entry branches are untested by
  the data. Most common values: `0+43` ×66, `0+29` ×41, `0+27#0+35` ×26.
- The `EventtoolUnitVO` branch is unreachable from `pickToolByStrategy`: it
  needs `inventoryAmount == 0`, which filter (5) already excludes. **Not
  established:** which ITEMS `units` column feeds `usedForEvent`. Candidates
  present on unit rows are `eventIDs`, `usageEventID` and `clientUsageEventID`
  (135 rows). This blocks other callers of `canUseToolForAttackOnTarget`, not
  this one.

### 1.6 Required count, usable count, and selection

**Required count `b`** — how many of this tool cancel the whole remaining
defence:

```
b = Math.ceil(p / getRelevantToolBonus(y) * 100 / 100)
```

The `*100/100` is **inside** the `ceil` and left-associative, so this reduces to
`ceil(p / bonus)` up to float noise. Do not "fix" it to
`ceil(p*100/bonus)/100`. Both `p` and `bonus` are already fractional (ITEMS
integer percents scaled by `.01` at parse time).

**Usable count `I`**:

```
D = (y.amountPerWave - waveVO.getSumOfToolsByTool(y)) if y.amountPerWave > 0 else container.freeItems
I = int(min(y.inventoryAmount, container.freeItems, D))
```

  It is a ternary, not `&&`/`||`: a budget that is exactly spent gives `D == 0`
  and the tool becomes unusable, rather than falling back to `freeItems`.

- `ToolUnitVO.amountPerWave` getter is `return this.isOffenseSupportTool ? 1 :
  this._amountPerWave`, and `_amountPerWave` defaults to `-1` (unlimited).
  `isOffenseSupportTool` is `"10" in slotTypes`. The port's `ToolStats`
  defaults `amount_per_wave` to `0`, which the `> 0` branch treats the same as
  `-1`; that is accidentally correct but should be `-1` for clarity.
- `CastleAttackWaveVO.getSumOfToolsByTool(e)` sums
  `container.getAmountOfToolInContainer(e)` over
  `[middleWall_tools, leftWall_tools, rightWall_tools]`, and
  `getAmountOfToolInContainer` sums `items[i].unitVO.inventoryAmount` where
  `items[i].unitVO.type == e.type`.

  **Two different keys.** The per-wave budget is keyed by the ITEMS `type`
  **string** (e.g. `"SceatAttGateDefRange"`), so all upgrade levels of one tool
  share one budget and it is shared across all three flanks of the wave.
  Placement and merging (`getTotalAmountOfUntit`, `getAllSlotsWithUnit`) are
  keyed by **wodId**. The port has neither: `combat/tools.py` scopes
  `amount_per_wave` to a single flank and never consults the sibling
  containers.

  Wrinkle the client does not smooth over: within one `type` group the per-row
  `amountPerWave` values differ. 23 attack-tool type strings span several
  wodIds and 10 of those groups carry `amountPerWave` — e.g. `SceatAttWallMelee`
  wodIds 267-276 are 20,21,21,22,22,23,23,24,24,25, and `SceatSuppAttWaves`
  401/402/403 are `1` while 567 has no column at all. The **ceiling** comes from
  the candidate being evaluated; the **consumed** sum spans every wodId sharing
  its type. So mixing tiers gives a different cap depending on which tier is
  picked first.
- `container.freeItems = _maxItems - sumOfItems`, where `sumOfItems` sums
  `getAmount()` over slots. It is remaining **amount** capacity, not a count of
  free slots — the name misleads.

**Selection.** Two registers, both scanned in `inv.getTools()` order:

```
if b <= I:                                  # exact cover
    if b < best_b or best_b == -1: exact_wod, best_b = int(y.wodId), b
else:                                       # partial
    v = getRelevantToolBonus(y) * I
    if v > best_v: partial_wod, partial_amt, best_v = int(y.wodId), I, v
```

Return: exact cover if any (`deductUnit(exact_wod, best_b)`), else partial
(`deductUnit(partial_wod, partial_amt)`), else `undefined` — `var h` is never
assigned, so the caller sees a falsy value and pops the strategy.

**An exact cover always beats any partial, regardless of value.** Both
comparisons are strict (`b < best_b`, `v > best_v`), so the **first** candidate
in iteration order wins a tie.

**Not established:** the iteration order of `AUnitInventory.getTools()`. It
walks `this.units`, whose concrete type varies by inventory class, in insertion
order. Since ties go to the first candidate, this decides the outcome whenever
two tools score equal. The port should pick a deterministic order — ascending
wodId is the suggestion — and document it as a possible divergence.

**Deduction happens inside the pick.**
`UnitInventoryDictionary.deductUnit(wodId, t)`:

```
if not _inventoryItems.get(wodId) or t <= 0: return None
n = int(_inventoryItems.get(wodId).inventoryAmount); t = int(min(t, n))
i = createVObyWOD(wodId, TYPE_UNIT); i.inventoryAmount = t
changeUnitAmount(wodId, min(0, -t))          # == -t; removed from inventory NOW
return i
```

The filtered inventory holds **references** to the player's real unit objects
(`createFilteredInventory` uses `addUnitReference`), and
`AFillWaveStrategy.applyInventoryChanges` copies the surviving amounts back.
The port defers deduction until after the slot-type check
(`combat/tools.py`, `fill_flank_with_tools`), which is the correct-looking
choice but is not what the client does — see §1.7.

### 1.7 The slot loop

`AFillFlankStrategy.prototype.fillFlankWithTools` (BUNDLE @6474036), verbatim:

```js
function(e,t,i,n,o,a,s){for(var r=0,l=e.items;r<l.length;r++){var c=l[r];
if(void 0!==c&&(c&&c.isFree()&&c.isUnlocked()&&n.getToolCount()>0&&e.freeItems>0)){
for(var u=!1;!u&&this._toolStrategyPool.length>0;){
var d=this._toolStrategyPool[this._toolStrategyPool.length-1]
        .pickToolByStrategy(t,i,n,e.freeItems,o,a,e,s);
d&&d.isToolForSlotType(c.slotType)?
(e.getTotalAmountOfUntit(d)>0?(c=e.getAllSlotsWithUnit(d)[0]).unitVO.inventoryAmount+=d.inventoryAmount
:c.unitVO=d,t&&t.updateEffectsWithNewTool(d,a),u=!0)
:(this._toolStrategyPool.pop(),u=!1)}
if(!u)break}}return!0}
```

Parameters, from `fillWave`: `e` = the flank's tool container, `t` = attacker
flank effects, `i` = defender flank effects, `n` = filtered inventory, `o` =
`attackInfo.spaceID`, `a` = `attackInfo.defenderArea`, `s` = the wave VO. The
inner call reorders them.

`inv.getToolCount()` is the total tool **count** (sum of `inventoryAmount`), not
a count of distinct tools.

Four behaviours a port must reproduce deliberately:

**(a) Pop, not skip — an already-deducted stack is discarded.** When the pick
returns a real tool whose `slotTypes` do not contain this slot's `slotType`,
`deductUnit` has already removed the stack from the shared-reference inventory,
`d` is dropped on the floor, and the strategy is popped permanently for this
flank. `applyInventoryChanges` then writes the reduced amount back, so the loss
persists into the remaining flanks.

  Reachable in practice on left/right (slot type 2) only via
  `ReduceRangeBonusStrategy`: the eleven `SceatAttGateDefRange` tools (wodIds
  245-255) are `slotTypes "1,9"` with `defRangeBonus > 0`, so they can be
  selected against a non-zero `defenderRangeBonus` and then fail the slot match.

  It is **not** reachable via `ReduceGateBonusStrategy`.
  `FightScreenHelper.getDefenceBonuses` ends
  `return t!=ClientConstCastle.FLANK_MIDDLE&&(n=0),[i,n,o]` (BUNDLE @2326975)
  where `n` is the gate component, and that value becomes
  `DefenderFlankEffectVO._defenderGateBonus` (8th ctor argument). So
  `defenderGateBonus` is structurally 0 on left, right and yard; the gate
  strategy hits `p <= 0` and returns `null` before deducting anything. Gate
  tools only ever matter on the middle container.

  **Not established** whether the discard is intended. It is reproducible from
  the code as written. The port must decide explicitly: reproduce it, or return
  the stack to the inventory before popping, and log which.

**(b) A merge abandons the slot that triggered it.** On the merge branch `c` is
reassigned to `getAllSlotsWithUnit(d)[0]`. `c` is a local copy of `l[r]`, so the
container is unchanged: the free slot that triggered the pick stays **empty**
and the for-loop advances past it, never revisiting it. There is no
`TravelConst.MAX_TOOLS_PER_SLOT` check on this path (that cap exists only in the
manual `AdvancedTroopSelectionToolStrategy`).

**(c) Pool exhaustion aborts the whole flank.** `if(!u) break`. The only way `u`
stays false after the while is `pool.length == 0`, so once every strategy has
been popped, all remaining slots stay empty even if capacity and inventory
remain.

**(d) The slot gate is re-evaluated per slot** and merely skips: an occupied
slot, a locked slot, an empty inventory or `freeItems == 0` continues the loop
rather than aborting it.

### 1.8 Slot matching

`ToolUnitVO.prototype.isToolForSlotType` (BUNDLE @876187):

```js
function(e){if(this.slotTypes!=null)for(n of this.slotTypes)if(n!==undefined&&n==e)return true;return false}
```

`slotTypes` is `getValueOrDefault("slotTypes", node, "", true).split(",")` — an
array of **strings**. `slot.slotType` is an int. The comparison is JS loose
`==`, so `"1" == 1` is true. **A Python port must int-cast both sides**; a
strict compare never matches. The port's `ToolStats.slot_types` already parses
to ints (`gamedata/models.py:193`), which is the right call.

Contrast `isOffenseSupportTool` / `isDefenceSupportTool`, which use
`slotTypes.indexOf(CONST.toString())` — a strict string match. Reproduce both
as written.

Slot-type constants (`ToolUnitVO`): `SOLDIER` 0, `TOOL_WALL` 1, `TOOL_GATE` 2,
`TOOL_MOAT` 4, `TOOL_KEEP` 5, `TOOL_SUPPORT_DEFENSE` 6,
`TOOL_SUPPORT_OFFENSE` 10. No constant exists for 3, 7, 8 or 9.

Wave tool containers (`CombatConst`, DLL):

```
ITEMS_MIDDLEWALL_TOOLS = [1,1,1]   LEVELS_MIDDLEWALL_TOOLS = [0,11,37]   @2438479 / @2438660
ITEMS_LEFTWALL_TOOLS   = [2,2]     LEVELS_LEFTWALL_TOOLS   = [0,37]      @2437785 / @2437956
ITEMS_RIGHTWALL_TOOLS  = [2,2]     LEVELS_RIGHTWALL_TOOLS  = [0,37]      @2439699
```

**Middle slots are slot type 1 and flank slots are slot type 2.** The constant
names mislead — `TOOL_WALL` = 1 is the middle slot.

Attack-tool `slotTypes` distribution (353 rows with `typ=="Attack"`):
`"1,2,9"` ×224, `"9,10"` ×44, `"1,9"` ×43, `"10"` ×42. Slot type 9 is used by
no `CombatConst.ITEMS_*` container; its meaning is **not established** and is
irrelevant here. Consequence: `"1,9"` tools (all gate tools, plus the eleven
`SceatAttGateDefRange` range tools) fit the middle only; `"1,2,9"` fits both;
`"10"` / `"9,10"` support tools fit neither wave tool container.

Slot construction, `CastleFightItemContainer` ctor:

```
for i in range(len(itemTypes)):
    v = CastleFightItemVO(); v.slotType = int(itemTypes[i])
    v.itemLevel = int(itemLevels[i]); v.unlockLevel = unlockLevel
    _serverItems.push(v)
    if v.isUnlocked(): _items.push(v)
# second pass pushes the locked ones
```

so `_items` is **all unlocked slots in declaration order, then all locked
slots**. `isUnlocked()` is `unlockLevel >= 0 ? unlockLevel >= itemLevel :
legendSkillData.isSkillActive(...)`. `isFree()` is `unitVO is None`.
`getWodId()` is `int(unitVO.wodId) if unitVO else -1`; `getAmount()` is
`int(unitVO.inventoryAmount) if unitVO else 0`.

`addItemstoList` is called twice from the ctor and each pass allocates **fresh**
`CastleFightItemVO` objects; only the first writes `_serverItems`. So for a
container with any locked slot the locked entry in `_items` is a different
object from the `_serverItems` entry. No observable divergence today, because a
locked slot can never be filled.

Merge helpers, both keyed on **wodId**:

```
getTotalAmountOfUntit(e) = sum(t.getAmount() for t in _items if t.getWodId() == e.wodId)
getAllSlotsWithUnit(e)   = [o for o in items if o is not None and o.getWodId() == e.wodId]
```

`_maxItems` is `CombatConst.getTotalAmountToolsFlank(level, legendBonus)` for
left/right and `getTotalAmountToolsMiddle(level)` for middle, already ported in
`combat/capacity.py`.

### 1.9 The feedback into the attacker effects

`AttackerFlankEffectVO.prototype.updateEffectsWithNewTool` (BUNDLE @4957221),
verbatim shape:

```
def update_effects_with_new_tool(self, e, t=None):     # e = placed stack, t = defenderArea
    self._attackerWallReduction += e.wallBonus * e.inventoryAmount
    self._attackerGateReduction += e.gateBonus * e.inventoryAmount
    self._attackerMoatReduction += e.moatBonus * e.inventoryAmount
    i = e.defRangeBonus
    n = e.defMeleeBonus
    for l in (e.effects or []):
        if l and l.effect and l.effect.effectType \
           and EffectConditionHelper.isEffectApplicable(l.effect, t):
            c = l.effect.effectType.type
            if   c == 217: i += .01 * l.strength      # RANGE_DEFENSE_MALUS
            elif c == 215: n += .01 * l.strength      # MELEE_DEFENSE_MALUS
    self._defenderRangeReduction += i * e.inventoryAmount
    self._defenderMeleeReduction += n * e.inventoryAmount
```

**This is the loop invariant.** Without it `getRelevantDefenderBonus` never
shrinks and the loop re-picks the same tool forever.

The ctor is `AttackerFlankEffectVO(e=1, t=1, i=0, n=0, o=0, a=0)` →
`(_attackerMeleeBonus, _attackerRangeBonus, _attackerWallReduction,
_attackerGateReduction, _attackerMoatReduction, _defenderRangeReduction)`.
`_defenderMeleeReduction` takes no ctor argument, starts at 0 and is only ever
grown here.

The port's `AttackerFlankEffects.apply_tool` (`combat/effects.py:48`) covers the
five scalar columns but **not** the 215/217 terms — so a tool picked *because* of
its conditioned bonus (the pick side now reads it) contributes nothing back to
the reductions, and the loop can re-pick it. The field it needs
(`defender_melee_reduction`) already exists at `combat/effects.py:43`; only the
two effect terms are missing. `apply_tool` also needs the area type, which
`conditioned_effect_bonus` already threads through the pick side.

Only the `_YARD` siblings differ: 216 and 218 are **not** consulted by either
this function or `getConditionedEffectBonus`.

### 1.10 `checkFlank`

`AFillFlankStrategy.prototype.checkFlank` (BUNDLE @6474922), verbatim:

```js
function(e,t,i){if(0==t.sumOfItems){for(var n=0,o=e.items;n<o.length;n++){var a=o[n];
void 0!==a&&(a.isFree()||(i.addUnit(a.unitVO.wodId,a.getAmount()),a.unitVO=null))}
return!1}return!0}
```

`e` = tool container, `t` = unit container, `i` = the filtered inventory.
`fillWave` calls it immediately after `fillFlankWithSoldiers` for each flank: a
flank that ended with no soldiers has its tools **refunded** to the inventory
and cleared. Net tool consumption for the wave must be computed after this step.
Already ported as `check_flank` (`combat/tools.py`).

### 1.11 Order of operations

Per flank, from `AFillWaveStrategy.fillWave` (BUNDLE @11696519 — left, then
right, then middle):

0. `fillToolStrategyPool()` → `[Moat, Range, Melee, Gate, Wall]`. Picks read the
   tail; priority is wall → gate → melee → range → moat.
1. `for c of container.items` — iterate slots in `_items` order (unlocked first,
   then locked).
2. Slot gate: `c is not None and c.isFree() and c.isUnlocked() and
   inv.getToolCount() > 0 and container.freeItems > 0`. Fails → skip this slot,
   continue.
3. `u = False; while not u and pool:`
   a. `d = pool[-1].pickToolByStrategy(attEff, defEff, inv, container.freeItems,
      spaceId, area, container, waveVO)` — this **deducts** on success.
   b. If `d` and `d.isToolForSlotType(c.slotType)`:
      - if `container.getTotalAmountOfUntit(d) > 0`: merge into
        `getAllSlotsWithUnit(d)[0]`, adding `d.inventoryAmount`; the current
        free slot is abandoned;
      - else `c.unitVO = d` (the setter also resets `outline = OUTLINE_NONE`);
      - `attEff.updateEffectsWithNewTool(d, area)`;
      - `u = True`, advance to the next slot.
   c. Else: `pool.pop()`, retry the **same** slot with the next strategy. The pop
      is permanent for this flank. If `d` was non-null, the deducted stack is
      lost.
4. `if not u: break` — pool empty, abandon the slot loop entirely.
5. `return True`, always.
6. Later, same flank, after `fillFlankWithSoldiers`:
   `checkFlank(toolContainer, unitContainer, inv)`.

Then the next flank, starting again at step 0 with a fresh pool.

### 1.12 ITEMS columns and payload fields

ITEMS `units`, rows with `typ == "Attack"` (353):

| Column | Parse | Note |
|---|---|---|
| `wodID` | int | placement / merge key |
| `type` | string | `amountPerWave` accounting key |
| `typ` | string | `"Attack"` / `"Defence"`; filter (2) |
| `slotTypes` | `split(",")` → strings | loose `==` against int slot type |
| `amountPerWave` | `parseInt(..., "-1")` | absent = unlimited |
| `canBeUsedToAttackNPC` | `1 == parseInt(..., "1")` | **absent = true** |
| `allowedToAttack` | `"space+area#..."` | empty = allowed everywhere |
| `effects` | `"id&value,id&value"` | id is an ITEMS `effects` row id |
| `toolCategory` | string | the auto-fill category filter |
| `wallBonus` `gateBonus` `moatBonus` `defRangeBonus` `defMeleeBonus` | `.01 * parseInt(..., "0")` | integer percents → fractions |

Column coverage in this snapshot, for tests: `wallBonus` 56 rows, all
`slotTypes "1,2,9"`; `gateBonus` 43 rows, all `"1,9"`; `moatBonus` 21 rows, all
`"1,2,9"`; `defRangeBonus` 51 rows — 40 `"1,2,9"` plus the 11
`SceatAttGateDefRange` (wodIds 245-255) at `"1,9"`; `defMeleeBonus` on 0 attack
tools (43 units overall). `toolCategory` is absent on 101 of the 353, and
`createFilteredInventory` only drops units whose `toolCategory` is non-empty and
filtered off, so those 101 are never filterable by the category checkboxes.
`fightType` is absent on two attack rows — wodId 56 `LightStone` and 57
`HeavyStone` — so `isDefensive` (`fightType == 1`) needs a documented default;
they carry no bonus column, so filter (4) drops them from every strategy.

ITEMS `effects`, the two rows that make the melee/range strategies live:

```
489  meleeDefenseMalus   effectTypeID 215  capID 99  areaTypeID 43  raidBossID 3
491  rangeDefenseMalus   effectTypeID 217  capID 99  areaTypeID 43  raidBossID 3
```

Their carriers, all `typ=="Attack"`, all `slotTypes "1,2,9"` (so they fit both
middle and flank slots), all `allowedToAttack "0+43"`:

```
807 ARELegendaryDragonWeakeningToolMeleeWeak    effects "489&50"   → 0.50
808 ...MeleeMedium                              effects "489&250"  → 2.50
809 ...MeleeStrong                              effects "489&500"  → 5.00
810 ARELegendaryDragonWeakeningToolRangedWeak   effects "491&50"   → 0.50
811 ...RangedMedium                             effects "491&250"  → 2.50
812 ...RangedStrong                             effects "491&500"  → 5.00
```

Every tool-borne effect row carries `capID 99`, and `effectCaps` row 99 has no
`maxTotalBonus`, so nothing on this path is capped.

**Not in ITEMS:** the value class. `effecttypes` has only `effectTypeID`,
`sortCategory`, `sortGroup`, `name`, `combatType` — the port must hardcode the
map/simple split from the bundle. The complete `EffectValueMap` set is
`{148, 149, 150, 154, 188}`; everything on the tool path is `EffectValueSimple`
(`parseFloat`, plain summation).

Wire shape. Tools reach `cra` as the `T` list of each flank object inside `A`:
`{"L": {"T": [[wodId, amount], ...], "U": [...]}, "M": ..., "R": ...}`, one pair
per **slot**. Because the model is per slot, the merge behaviour in §1.7(b)
changes the emitted bytes: a merged pick produces one pair with a larger amount
and leaves the triggering slot empty, not two pairs.

### 1.13 Test cases

No captured tool-fill trace exists in the repo, so none of these can be checked
against a recorded dialog today. They are the scenarios a capture would settle,
and each is decidable from the client code above.

1. **Middle gate fill.** Middle container, `defenderGateBonus = 1.0`,
   `attackerGateReduction = 0`, inventory holds 20 Rams (wodId 611,
   `gateBonus 0.10`, `slotTypes "1,9"`). Wall strategy pops (no wall tools),
   gate picks `b = ceil(1.0/0.10) = 10`, `10 <= I`, exact cover → one slot holds
   `[611, 10]`, and `attackerGateReduction` becomes 1.0. The next slot's gate
   pick sees `p = 0` and pops.
2. **Flank discard.** Left container (`slotType 2`), `defenderRangeBonus > 0`,
   `hasRangeDefenders` true, inventory holds only `SceatAttGateDefRange`
   (wodId 245, `slotTypes "1,9"`). Range strategy returns a stack, the slot
   match fails, the strategy pops — and the deducted stack is **gone** from the
   inventory. Assert the inventory shrank and no slot was filled.
3. **Gate is inert on a flank.** Same setup with rams in inventory and any
   defender: `defenderGateBonus` is 0 on left/right, so the gate strategy
   returns `null` at the `p <= 0` guard and no ram is consumed.
4. **Merge leaves a slot empty.** Middle container, two picks of the same wodId:
   the second merges into the first slot and the second slot stays free, so the
   emitted `T` has one pair, not two.
5. **Pool exhaustion aborts.** A container with three free slots and a defender
   whose every bonus is zero: all five strategies pop on the first slot, `break`
   fires, and slots 2 and 3 stay empty even with capacity and inventory left.
6. **`amountPerWave` is shared across flanks.** `SceatAttGateDefRange`
   (`amountPerWave 5`, keyed by type). Place 5 across the middle; a later flank
   pick of any wodId in that type group sees `D = 5 - 5 = 0`, so `I = 0` and the
   tool cannot be an exact cover. Also check the mixed-tier case: placing
   wodId 567 (no `amountPerWave`) still counts against wodId 403's cap of 1.
7. **`checkFlank` refund.** Fill a flank's tools, leave its unit container
   empty, run `checkFlank`: the tools return to the inventory, the flank's `T`
   is empty, and the wave-level tool consumption is unchanged.
8. **Conditioned effect on and off.** wodId 809 (`489&500`) against
   `defenderArea.areaType == 43` with raid boss 3 active:
   `getRelevantToolBonus = 5.00` and the melee strategy is a real candidate.
   Against any other area type: `isEffectApplicable` is false, the bonus is 0,
   filter (4) drops it, and the strategy pops.
9. **Precedence.** `p = 0.35`, `bonus = 0.10` → `b = 4`. A port that writes
   `ceil(p*100/bonus)/100` gets `3.5`; assert 4.

---

## 2. The yard / final-assault wave

### 2.1 Capacity

`CombatConst.getMaxUnitsInReinforcementWave` (DLL @2443526), verbatim:

```js
CombatConst.getMaxUnitsInReinforcementWave=function(e,t,n,i){
  var a=20*Math.sqrt(e)+50+20*t+n;return 0|Math.round(a*i)}
```

```python
def yard_capacity(my_level, target_level, bonus, boost_modifier):
    a = 20 * math.sqrt(my_level) + 50 + 20 * target_level + bonus
    return to_int32(math.floor(a * boost_modifier + 0.5))
```

`Math.round` is `floor(x + 0.5)` — half **up** — and `0|` is `ToInt32`. There is
no clamp to `>= 0` and no cap; the only floor is inside `boostToModifier`.

**Porting trap, and a live bug.** `combat/capacity.py:144` is
`int(round(base * boost_to_modifier(boost)))`. Python's `round` is banker's
rounding and diverges at exactly `.5`, which is reachable whenever
`boost_modifier != 1.0`. Replace with `math.floor(v + 0.5)`.

Arguments, from `AttackDialogWaveHandler.initWaves` (BUNDLE @11855241):

```js
attackInfoVO.yardWaveContainer.maxItems = CombatConst.getMaxUnitsInReinforcementWave(
    CastleModel.userData.level,
    attackInfoVO.targetArea.isUnderConquerControl
        ? attackInfoVO.targetArea.minimumOwnerLevel
        : attackInfoVO.targetOwnerLevel,
    CastleEffectsHelper.getUnitsOnTheYardWaveBonusForAreaType(selectedLord, targetArea, strategy),
    CastleEffectsHelper.getUnitsOnTheYardWaveBoostForAreaType(selectedLord, targetArea, strategy))
```

**The yard is the only wave capacity that reads the attacker's own level.**
Every flank formula reads the target's. `strategy` is
`LordEffectHelper.getFilterStrategyAttackOrDefence(targetArea.ownerInfo.playerID,
true)` — the same PvP/PvE filter the flank code uses.

### 2.2 The bonus and the boost

`CastleEffectsHelper.getUnitsOnTheYardWaveBonusForAreaType` (BUNDLE @563219):

```python
def yard_bonus(lord, target_area, strategy=None):
    return int(getAccumulatedEquipmentBonusByEffectTypeForArea(
        lord, EFFECT_TYPE_ATTACK_UNIT_AMOUNT_REINFORCEMENT_BONUS,   # 179
        target_area.areaType, True, strategy).strength)
```

Type 179 is `VALUE_NOMINAL_ADD`: **absolute units, not a percentage**. The
literal `true` fourth argument is load-bearing — it turns on the assigned
general's passive skills, which is the only path by which the "+2,400 troop
capacity for final assault" skill reaches this number.

`getUnitsOnTheYardWaveBoostForAreaType` (BUNDLE @563493) is the same call with
type 180, wrapped in `EffectConst.boostToModifier` (DLL):

```js
EffectConst.boostToModifier=function(e){
  var t=(EffectConst.BASE_BOOST_PERCENTAGE+e)*EffectConst.TO_MULTIPLIER_FACTOR;return Math.max(t,0)}
// BASE_BOOST_PERCENTAGE = 100, TO_MULTIPLIER_FACTOR = 0.01
```

Already ported as `boost_to_modifier` (`combat/capacity.py:105`).

Accumulation, `getAccumulatedEquipmentBonusByEffectTypeForArea`
(BUNDLE @561054):

```js
function(e,t,i,n,o){n=n??true;o=o??null;
  var a=CastleEffectsHelper.getTotalEffectValue(e.getUniqueBoni(false,t,i,o,n));
  return a||new t.valueClass}
```

Argument order is `(lord, effectType, areaType, useGeneral=true,
strategy=null)`, forwarded as `getUniqueBoni(mergeFlag, effectType, areaType,
strategy, useGeneral)` — note the reorder.

`LordVO.getUniqueBoni` (BUNDLE @3177610) collects, in order, each filtered by
`checkConditions(effectType, areaType, strategy)`:

1. every equipped item's `boni`, plus `RelicEquipmentVO.relicInfoVO.relicBoni`,
   plus `gemVO.boni` (or a gem's `relicBoni`), plus
   `AlienLordEquipmentVO.alienGems[].boni`;
2. `_rawLordEffects` (`gli` key `E`);
3. `_areaEffects` (`gli` key `AE`);
4. equipment set bonuses whose `neededItemThresholds[v] <= setCounts[setID]`;
5. `assignedGeneralVO.getPassiveEffects()`, when `includeGeneral`.

Not included anywhere: general **abilities**, research, titles, alliance buffs,
subscriptions, construction items, player crest.

Its last statement is `return this.mergeBoni(s, e)`. **`mergeBoni` was not
decompiled**; it de-duplicates and merges the collected `BonusVO`s — bucketing
`GemBonusVO` with `triggerChance != 100` separately, and special-casing
`maxValueStrength == Number.MAX_VALUE` — before `getTotalEffectValue` sees the
list. A port of the 179 total needs it. `checkConditions` also gates on the
strategy object itself via `LordEffectHelper.isEffectTypeIncluded`, which was
likewise **not dumped**.

`getTotalEffectValue(list, ignoreCaps=False)` groups by `bonus.capID`, sums
within a group under that group's cap, then sums across groups **uncapped**.
For the yard:

```
total_179 = (uncapped capID-99 sum) + min(capID-11413 sum, 3000)
total_180 = min(sum, 30)              → boost_modifier tops out at 1.30
```

### 2.3 The container

`CastleAttackInfoVO.fillFromParamObject` (BUNDLE @3632313), verbatim:

```js
this._yardWaveItemContainer=new CastleFightItemContainer([0,0,0,0,0,0,0,0],[0,0,0,0,0,0,0,0],0,1e4)
```

Eight slots, `slotType 0` (unit), `itemLevel 0`, `unlockLevel 0`, initial
`maxItems` 10000, no legend slots. `isUnlocked()` is `0 >= 0` for all eight, so
**the yard has exactly 8 unit slots at every level** — unlike a flank (2) or the
middle (6) — and **no tool slots at all**. The UI agrees: the three final-wave
display classes all set `CONST_MAX_SLOTS = 8`. `maxItems` is then overwritten by
`initWaves`.

```
freeItems     = maxItems - sumOfItems
sumOfItems    = sum(item.getAmount() for item in _items)
isFull        = freeItems <= 0
exceedsLimit  = freeItems < 0
```

### 2.4 Filling it

`AFillWaveStrategy.prototype.fillYardContainer` (BUNDLE @11695962), verbatim:

```js
function(e,t,i,n){var a=this.createFilteredInventory(e.unitInventory,t);
return this.relevantFilteredUnits=this.extractUnitWodIdsFromInventory(a),
this.flankFillStrategy.fillFlankWithSoldiers(i,null,
  n.getDefenderFlankEffects(ClientConstCastle.FLANK_YARD),a,t),
this.applyInventoryChanges(a,e.unitInventory),!0}
```

Five differences from `fillWave`, all load-bearing:

1. **No tools.** `fillWave` calls `fillToolStrategyPool()` + `fillFlankWithTools()`
   per flank; the yard never does. The container has no tool slots and `cra` has
   no yard tool field.
2. **Attacker effects are literally `null`**, so `pickSoldierStack` falls back to
   `new AttackerFlankEffectVO()` = `(1, 1, 0, 0, 0, 0)`. Multipliers are exactly
   1.0 and every reduction is 0.
3. The defender side uses `FLANK_YARD = 3` (`LEFT` 0, `MIDDLE` 1, `RIGHT` 2,
   `YARD` 3, `REINFORCEMENT` 4).
4. **No `checkFlank`.** There are no tools to refund.
5. Both `autoFillYardWave` and `autoFillWave` build a
   `StrongestDefenceCounterWaveStrategy`, whose ctor loads
   `StrongestDefenceCounterRatioConsideredFlankStrategy` — so the yard uses the
   **same** `pickSoldierStack`; only its inputs differ.

The slot loop, `fillFlankWithSoldiers` (BUNDLE @6475148), re-evaluates
`e.freeItems` each iteration (assigning `unitVO` changes `sumOfItems`), so the 8
stacks together can never exceed `maxItems`.

`pickSoldierStack` (BUNDLE @11699527), verbatim tail:
`h=c*m>=u*_?d:p`. In full:

```python
def pick_soldier_stack(container, attacker_fx, defender_fx, inv, options):
    attacker_fx = attacker_fx or AttackerFlankEffects()          # (1,1,0,0,0,0)
    g = defender_fx.melee_defence_value(0, attacker_fx.defender_range_reduction) if defender_fx else 0
    C = defender_fx.range_defence_value(attacker_fx.defender_range_reduction, 0) if defender_fx else 0
    melee_share, range_share = 1, 1
    if g + C > 0:
        melee_share = g / (g + C)
        range_share = C / (g + C)
    ...
    # ties go to melee; melee is weighted by the RANGE-defence share
    chosen = melee_wod if best_melee * range_share >= best_range * melee_share else range_wod
    return inv.deductUnit(chosen, container.freeItems)
```

The cross-weighting is deliberate and easy to invert: the melee candidate is
weighted by `m` (the **range**-defence share) and the range candidate by `_`
(the **melee**-defence share). Candidate scans use strict `>`, so equal scores
keep whichever unit the inventory reached first.

Per-unit score, with yard multipliers of 1.0
(`getSoldierStackAttackValue`, BUNDLE @1519216):

```
melee: int(buffedMeleeAttack) * min(freeItems, inventoryAmount)
range: int(buffedRangeAttack) * min(freeItems, inventoryAmount)
```

No commander equipment, no general, no legend skill and no effect 33/53/54
touches yard **composition**. See §3 for `buffed*Attack`.

### 2.5 The defender side of the yard

`FightScreenHelper.getDefenderFlankEffectVO(vo, flank)` builds one
`DefenderFlankEffectVO` per flank from `getDefendingUnitStrength` and
`getDefenceBonuses`. The yard's unit source is `itemsKeep` (the courtyard
garrison), and `itemsSupport` is concatenated for **every** flank including the
yard.

Spy-report sections are **positional, not named**.
`CastleSpyArmyInfoVO.parseArmyInfo` (BUNDLE @3639368) shifts one array in fixed
order: `[0]` left, `[1]` middle, `[2]` right, `[3]` keep, `[4]` stronghold,
`[5]` support, `[6]` reserve (optional). Index 4 is easy to miss. Already
modelled correctly at `services/spy_army.py:21`.

`getDefenceBonuses` is computed for the yard (it falls through to `default`) but
the yard fill never reads wall/gate/moat, because no tools are placed. Note the
gate zeroing from §1.7(a) applies here too.

With both reductions at 0, the yard's two scores reduce to

```
g = meleeDefUnits_meleeStr * defMeleeBonus + rangeDefUnits_meleeStr * defRangeBonus
C = rangeDefUnits_rangeStr * defRangeBonus + meleeDefUnits_rangeStr * defMeleeBonus
```

### 2.6 The `RW` payload field

`CastleFightItemContainer.prototype.getSlotList` (BUNDLE @2470865):

```js
function(e){e=e??false;var t=[],i=e?this._serverItems:this._items;
for(var n=0;n<i.length;n++){var o=i[n];t.push([o.getWodId(),o.getAmount()])}return t}
```

The three send sites all pass `true`, selecting `_serverItems`. Verbatim tail of
one of them (another appends `e.autoSkipCooldownType` after it):

```js
new C2SCreateArmyAttackMovementVO(..., e.collecterBooster, e.toolsSupportWodIds,
                                  e.yardWaveContainer.getSlotList(true), e.autoSkipCooldownType)
```

and inside the ctor that 18th positional argument becomes field `RW`
(alongside `BKS`, `AST`, `CD = 99`, `ASCT`). Command is `cra`.

**Encoding, exactly:**

```
RW = [[wodId, amount] × 8]     # ALWAYS 8 pairs, one per slot, in slot order
                               # an empty slot is [-1, 0]
```

There is no compaction — unlike the server's echo `AAM.FA.RW`, the request
always carries all eight pairs. For the yard `_serverItems == _items` (all 8
unlock at level 0), so the `true` makes no difference here; keep it anyway,
because the flank containers do differ and share the accessor.

The port emits a compacted list: `fill_yard_wave` (`combat/solver.py:319`)
returns only the filled stacks and defaults `slots=1`. Both need fixing —
`slots` should be 8 and the result padded to 8 pairs with `[-1, 0]`.

The inverse, `fillFromParamArray`: `for t, entry in enumerate(list): wodId =
int(entry.shift()); amount = int(entry.shift()); if wodId != -1:
addToItems(wodId, amount, t)`.

The model already exists at `protocol/models/attack.py:131` as
`yard_wave: list[list[int]] = Field(alias="RW", default_factory=list)`.

### 2.7 Overflow

`maxItems` is a guard, not a truncation. On resize (lord swap, target change,
wave add/remove) `initWaves` does **not** trim:

```js
if (yardWaveContainer.maxItems < yardWaveContainer.sumOfItems)
    for (item of yardWaveContainer.items) if (item.unitVO) item.outline = 1   // OUTLINE_ORANGE
```

On send (BUNDLE @6494749) the check is
`any(wave.exceedsUnitLimit() for wave in army.waves) or
yardWaveContainer.exceedsLimit()`; if true the client shows a blocking
`CastleStandardOkDialog` and sends nothing. A port must validate
`sum(RW amounts) <= maxItems` itself before emitting `cra`. The auto-fill path
can never exceed it, but a manual fill followed by a lord change can.

### 2.8 Display-only paths

Effect type 33 (`attackBoostYard`) and legend skill 15 (`ATTACK_YARD_BONUS`)
change only the strength number the final-wave panel prints and the
`<sum> / <maxItems>` label beside it. They do not enter
`getMaxUnitsInReinforcementWave` and they do not enter `pickSoldierStack`. A
port reproducing yard composition can ignore both.

### 2.9 Order of operations

1. Dialog open, or any wave-count or lord change → `initWaves`. It adds/removes
   `ADDITIONAL_WAVE` waves and calls `updateMaxUnitCount` per flank wave, **then**
   sets `yardWaveContainer.maxItems`. Immediately after, if
   `maxItems < sumOfItems`, every filled slot gets `outline = 1`.
2. Auto-fill → `AttackDialogAutoFill.autoFillYardWave` (BUNDLE @11689452)
   constructs a fresh `StrongestDefenceCounterWaveStrategy` and calls
   `fillYardContainer(attackInfoVO, options, yardWaveContainer,
   FightScreenHelper.getDefenderEffectVO(attackInfoVO))`. The yard is selected
   independently of the three flanks, by wave **name**
   (`AttackDialogWaveHandlerFinalYardWaveInfoItem.CONST_WAVE_NAME`), not by a
   numeric wave index.
3. `fillYardContainer` → `fillFlankWithSoldiers(container, None,
   defenderEffectVO.getDefenderFlankEffects(FLANK_YARD), filteredInventory,
   options)` → 8 slots, each filled by `pickSoldierStack` → `applyInventoryChanges`.
4. Send → `getSlotList(true)` as the 18th ctor argument → field `RW` of `cra`.
5. Pre-send guard → `exceedsLimit()`.

### 2.10 ITEMS tables and payload fields

| Table | Rows that matter |
|---|---|
| `effects` | 700 (type 179, capID 99), 2115 (type 179, capID 11413), 701 (type 180, capID 33) |
| `effectCaps` | 99 → no `maxTotalBonus` (uncapped); 11413 → 3000; 33 → 30 |
| `generalSkills` | 144 rows carrying `effects: "700&<value>"`. One `ReinforcementWave*` group per general, 12 levels, linear: Common +50/level (max 600), Rare +100 (max 1200), Epic +150 (max 1800), Legendary +200 (max 2400). `101024` = `ReinforcementWaveLegendary` level 12 = `700&2400` is the in-game "+2,400 to troop capacity for final assault" |
| `equipments` | exactly one row carries 700 — equipmentID 991, `wearerID 2` (commander), `slotID 5`, `effects "700&750"` |
| `relicEffects` | id 10119, effectID 2115, min 120, max 750 — the only non-multiple-of-50 source of type 179 |
| `constructionItems` | 29 rows with `700&{500…1500}`, one with `701&10` — see §2.12 |

Runtime inputs: `CastleModel.userData.level`,
`targetArea.isUnderConquerControl`, `targetArea.minimumOwnerLevel`,
`attackInfoVO.targetOwnerLevel`, the selected commander's equipment / relics /
gems / sets, `gli` keys `E` and `AE`, and the assigned general's passive
effects. Wire: `cra` request field `RW`, `cra` response `AAM.FA.RW`, and the spy
report's `itemsKeep` + `itemsSupport`.

### 2.11 Test cases

**The four captured capacities.** All four reproduce exactly, and they are
mutually consistent with a single loadout:

```
my_level = 70, bonus = 2872, boost_modifier = 1.0
base(70) = 20*sqrt(70) + 50 = 217.33200530...
  target  1 → floor(217.332 +   20 + 2872 + 0.5) = 3109
  target 13 → floor(217.332 +  260 + 2872 + 0.5) = 3349
  target 45 → floor(217.332 +  900 + 2872 + 0.5) = 3989
  target 70 → floor(217.332 + 1400 + 2872 + 0.5) = 4489
```

They differ by 240, 640, 500 = 20 × (12, 32, 25) — exactly the formula's
`20*targetLevel` spacing, so it is one attacker against four targets 12, 32 and
25 levels apart. At attacker level 70 the fit is **forced** given target levels
in 1..70: target 70 forces `bonus >= 2872` and target 1 forces `bonus <= 2872`.

Two caveats a test must carry:

- **The decomposition of 2872 is (inferred), not established.** 2872 is not a
  multiple of 50, while every ITEMS source of type 179 that reaches
  `getUniqueBoni` is (general skills in 50/100/150/200 steps up to 2400, plus the
  one +750 equipment row). The only non-quantised source is `relicEffects`
  10119 (120…750), so 2400 + 472 is consistent — as is any server-pushed `gli`
  `E`/`AE` value. Not decidable from these files.
- **The fit is not unique across attacker levels.** A brute force over attacker
  level 1..70, boost 0..30, bonus a multiple of 50 and target level 1..120 finds
  52 `(level, bonus)` pairs that also hit all four — e.g. attacker level 20 with
  bonus 2950, or level 48 with bonus 2900. Reproducing a captured number needs
  the **attacker's own level**, which is the one thing the yard formula does
  differently from every flank formula.

Other cases:

1. **Half-up rounding.** `my_level = 1, target_level = 1, bonus = 0,
   boost_modifier = 1.05` → `a = 90`, `a*i = 94.5`. JS gives **95**; Python's
   `round` gives 94. This is exactly the defect at `capacity.py:144`.
2. **`RW` shape.** A yard filled with two stacks emits 8 pairs — the two, then
   six `[-1, 0]`. Assert length 8 and slot order.
3. **Capacity never exceeded by auto-fill.** With `maxItems = 100` and a huge
   inventory, `sum(amounts) == 100` and no stack was truncated after the fact —
   `freeItems` is re-read per slot.
4. **Overflow blocks the send.** `sumOfItems > maxItems` → the pre-send guard
   fires and nothing is emitted; the container is **not** trimmed.
5. **Boost cap.** A type-180 total of 45 clamps to 30 → modifier 1.30, not 1.45.
6. **Cross-group 179.** capID-99 sum 2400 plus capID-11413 sum 3500 → 2400 +
   min(3500, 3000) = 5400; the cross-group sum is uncapped.
7. **Yard tie goes to melee.** Equal melee and range stack scores with equal
   defence shares → the melee wodId is chosen (`>=`).
8. **Eight slots at every level.** `yard_slots(level)` is 8 for level 1 and for
   level 70.

### 2.12 Not established

- Which sources make up the implied 2872 (see above). Settling it needs a live
  `gli` dump for the capturing account; no stored capture exists in the repo.
- `relicEffects` 10119 appears in no `relicEffectLists.relicEffectIDs` and no
  `relicBluePrints.baseRelicEffectIDs` in this snapshot, so whether it is
  currently obtainable is not established.
- 29 `constructionItems` rows grant effect 700 and one grants 701. Per the client
  these **cannot** affect the previewed yard capacity — `getUniqueBoni` reads
  equipment / relics / gems / sets / `gli` `E`-`AE` / general passives only, and
  construction items surface through `getGlobalConstructionItemEffectsByType`,
  reached only by `getAccumulatedEffectValueForType`, whose six call sites are
  all non-combat. Whether the **server** counts decorations for the real capacity
  is not established; if it does, a client-faithful port under-counts.
- Nothing in ITEMS grants type 180 to a `LordVO` (the only 701 row is the
  construction item), so `boost_modifier` is 1.0 in practice today and the
  cap-30 ceiling is theoretical. Whether a live server pushes 180 via `gli`
  `E`/`AE` is not established.
- `CastleModel.userData.level` is assumed to be the account level (cap 70). Not
  checked whether a legendary-level account reports something higher, which
  would change the `20*sqrt(level)` term.
- Whether attack **presets** also populate the yard container, and in what order,
  was not traced. `onAutoFillClearClicked` **does** clear the yard, via the
  wave-name check; `combat_effects.md:1471` already records this.
- Whether the server re-validates the resulting wave the same way.

---

## 3. Buffed unit attack values

### 3.1 The two getters

`SoldierUnitVO.prototype.buffedMeleeAttack` (BUNDLE @1519216), verbatim:

```js
{get:function(){var e=r.int(u.CastleModel.globalEffectData.getBonusByEffectType(
  d.EffectTypeEnum.EFFECT_TYPE_ATTACK_BONUS_UNIT,-1,-1,this.wodId));
  return this._meleeAttack>0?this._meleeAttack+e:0}}
```

`buffedRangeAttack` (@1519571) is identical with `_rangeAttack`. **Same effect
type 148, same arguments.** There is no melee/range split on the effect side;
which getter applies is decided purely by which raw column is non-zero. A wodId
keyed in a 148 map on a unit with both columns non-zero would be buffed on both
(none ship today).

Two details that a paraphrase loses:

- `e` is computed **unconditionally**, then the `> 0` guard is applied to the raw
  column. A unit with `_meleeAttack == 0` returns 0, never `0 + e`. A pure-ranged
  unit never picks up a melee buff even if the map keys it.
- `int()` wraps the **whole** sum returned by `getBonusByEffectType`, not each
  term. Every term is an integer today so this is unobservable, but port it as
  `int(total)`.

This is a **per-unit** flat additive on one unit's stat line, independent of
stack size and of every flank/wave multiplier.

`_meleeAttack` and `_rangeAttack` are ITEMS `units.meleeAttack` /
`.rangeAttack`; already modelled as `UnitStats.melee_attack` / `.range_attack`.

### 3.2 The feeder

`GlobalEffectData.prototype.getBonusByEffectType` (BUNDLE @15672733):

```python
def get_bonus_by_effect_type(self, effect_type, area_type=-1, space_id=-1, wod_id=-1):
    if not self.eventVO: return 0
    total = 0
    a = int(activeArea.areaInfo.areaType if area_type < 0 else area_type)
    l = int(activeArea.spaceId            if space_id  < 0 else space_id)
    for entry in self.eventVO.globalEffectData:     # [GlobalEffectVO[], endTimestampMs, seenFlag]
        if not entry or len(entry) == 0: continue
        if entry[1] < CachedTimer.getCachedTimer(): continue      # expired
        for vo in (entry[0] or []):
            if vo is None: continue
            if not vo.canBeUsed: continue                          # level gate
            if not vo.bonus.matchesConditions(effect_type, a, l, wod_id): continue
            total += vo.bonus.strength
    return total
```

```
eventVO   = specialEventData.getActiveEventByEventId(EventConst.EVENTTYPE_GLOBAL_EFFECTS)  # 610
canBeUsed = userData.userLevel >= vo.minLevel and userData.userLevel <= vo.maxLevel
vo.bonus  = vo.buffedBonus if globalEffectData.isEffectBoosted(vo.globalEffectID) else vo.rawBonus
```

It iterates **only** the event-610 payload. Research, buildings, alliance,
titles, VIP, subscription, sceat skills, crest, construction items and the
officers' school are all unreachable from here, even though several ITEMS tables
carry type-148 rows.

**Porting trap.** Passing `-1` for `areaType`/`spaceId` does **not** mean
"unrestricted" — it resolves to the player's **currently viewed** area, not the
attack target's. So a unit's buffed attack in the client is a function of which
castle the UI is looking at. Unobservable today, because the only 148 rows this
getter can see use ITEMS effect 273, which has no `areaTypeID` and no `spaceIDs`
so both `isFor*` tests always return true. A headless port must pick a
convention: **evaluate against the attack target's `areaType`/`spaceId` and
document the divergence** is the recommendation.

`BonusVO.matchesConditions` (BUNDLE @776608):

```python
def matches_conditions(self, effect_type, area_type=-1, space_id=-1, wod_id=-1, other_player=None):
    if not self.effect: return False
    s = True
    if effect_type and effect_type.id != self.effect.effectType.id:            s = False
    if wod_id > -1 and isinstance(self.effectValue, (EffectValueWodID, EffectValueMap)) \
                   and not self.effectValue.hasWodId(wod_id):                  s = False
    if space_id  > -1 and not self.effect.isForSpaceID(space_id):              s = False
    if area_type > -1 and not self.effect.isForAreaType(area_type):            s = False
    if other_player and not self.effect.checkPlayerRelation(other_player):     s = False
    return s
```

**The wodId is a gate, not a key.** It decides *whether* the bonus counts; the
amount then comes from `.strength` — see §3.4.

### 3.3 The `"273&<wodId>+<strength>"` encoding

The string is ITEMS `globalEffects.effects`, shape `"<effectID>&<valueString>"`.

**273 is an ITEMS `effects` row id, not an effect type id.** Row 273 is
`{"effectID":"273","name":"attackBonusUnit","effectTypeID":"148","capID":"99"}`,
so 273 → type 148 → value class `EffectValueMap`
(`new EffectTypeEnum(148, EffectValueMap)`, BUNDLE @211379), capID 99 =
uncapped.

`GlobalEffectVO.prototype.parseXml` (BUNDLE @15675298) splits on `&`, resolves
the row, builds a `BonusVO`, and — when the value class is `EffectValueMap` —
normalises the `#`/`+` form to a flat comma list and re-parses. That re-parse is
redundant belt-and-braces: `EffectValueMap.parseFromValueString` already handles
`#`.

```python
def parse_from_value_string(s):          # EffectValueMap, BUNDLE @3766254
    t = []
    if "#" in s:
        for part in s.split("#"):
            o = part.split("+")
            t.append(int(o[0]))
            t.append(int(o[1]) if len(o) > 1 else 0)
    else:
        a = s.split(",") if "," in s else (s.split("+") if "+" in s else [s])
        t = [int(x) for x in a]
    return parse_from_value_array(t)     # pairs: {t[i]: t[i+1] or 0}
```

**Danger:** a lone scalar `"195"` parses to `{195: 0}` — a wodId key with
strength 0, **not** a strength of 195. Insertion order is source-string order.

The five 148-typed rows this getter can see, from ITEMS `globalEffects`:

| globalEffectID | name | `effects` | boostValue | keys |
|---|---|---|---|---|
| 5 | `attackBoostSpeermanBowman` | `273&602+13#608+13` | 13 | 602, 608 |
| 6 | `attackBoostMaceCrossbowman` | `273&603+20#607+20` | 20 | 603, 607 |
| 7 | `attackBoostValkyrieMeleeValkyrieRange` | `273&22+35#23+35` | 35 | 22, 23 |
| 8 | `attackBoostMasterSwordsmanMasterArcher` | `273&781+45#782+45` | 45 | 781, 782 |
| 9 | `attackBoostEliteRankrewardMeleeEliteRankrewardRange` | `273&9+60#10+60` | 60 | 9, 10 |

All 19 `globalEffects` rows use exactly one effectID each; the only other
map-typed one is 285 (`fameBoostUnitAlienBC`, type 154). **No `globalEffects`
row uses the area-restricted 148 variants (276-280)**, so area filtering never
bites this path.

**Type coercion.** `minLevel` is a JSON int (`10`) while `maxLevel` is a string
(`'99'`) on all 19 rows. `userLevel >= vo.minLevel and userLevel <= vo.maxLevel`
is fine in JS and raises `TypeError` in Python. Coerce both with `int()`.

### 3.4 The server strength override, and why the first-value defect is invisible

`GlobalEffectEventVO.prototype.parseParamObject` (BUNDLE @13357875):

```python
def parse_param_object(self, t):
    self.seenGlobalEffects = t.SGE
    self.globalEffectData = []
    n = 0
    for c in t.GE:                      # [globalEffectID, remainingSeconds, strengthOverride]
        d, p, h = int(c[0]), c[1], int(c[2])
        g = CachedTimer.getCachedTimer() + p * 1000
        C = globalEffectData.getGlobalEffectVOsByGlobalEffectID(d)
        if h > -1 and C is not None:
            for f in C: f.setEffectStrength(h, f.rawBonus)
        self.globalEffectData.append([C, g, d in self.seenGlobalEffects])
        n = max(n, g)
    self._endTimestamp = n
```

```python
def set_effect_strength(self, value, bonus):
    if isinstance(bonus.effectValue, EffectValueMap):
        i = ",".join(f"{k},{value}" for k in bonus.effectValue.getWodIds())
    else:
        i = str(value)
    bonus.parseFromValueString(bonus.effect, i)
```

**This is the key insight.** The server sends **one scalar strength per
globalEffectID**, and `setEffectStrength` writes that one value onto **every**
wodId in the map. The ITEMS strengths (13/20/35/45/60) are only the fallback used
when the server sends `h == -1`. So a live 148 map is always uniform across its
keys — which is exactly why the next defect is currently unobservable.

The booster path (`addBuffStrengthValue`, event type 612) compounds it:
`setEffectStrength(this.buffedBonus.strength + e, this.buffedBonus)` takes the
first key's value and stamps the result onto all keys. Uniform maps make this
correct; a non-uniform map would be silently flattened.

`EffectValueMap.strength` (BUNDLE @3767400), verbatim:

```js
{get:function(){var e=0;if(null!=this._map)for(var t=0,i=Array.from(this._map.values());t<i.length;t++){
var n=i[t];if(void 0!==n){e=n;break}}return e}}
```

**It returns the first map value, not the requested wodId's.** The correct
per-wodId lookup exists and is simply never called for 148:
`hasWodId(e)`, `getValueforId(e)` (note the lowercase "for"), `getWodIds()`,
`rawValues` (flat `[k0,v0,k1,v1,…]` in insertion order).

`EffectValueMap.add(other, maxValues)` merges per key and **never reads
`maxValues`**, so map types are never clamped by the cap pipeline (consistent
with capID 99 anyway). New keys are appended, so after `a.add(b)` the first key
of the result is still `a`'s first key.

**Two implementations, pick deliberately:**

```python
def map_strength(m):            # client-faithful
    for v in m.values(): return v
    return 0
# wodId is used ONLY as an inclusion gate, never as the key read

m.get(wod_id, 0)                # probably correct — divergence risk, flag it
```

For the global path the two agree, because the server flattens. For the
lord/relic path they do not — see §3.6.

### 3.5 Where 148 does and does not land

There are exactly seven occurrences of `EFFECT_TYPE_ATTACK_BONUS_UNIT` in the
bundle:

| @ | Site | Effect |
|---|---|---|
| 211324 | enum definition, `new EffectTypeEnum(148, EffectValueMap)` | — |
| 228598 | `.simpleEffectIconClass` | cosmetic |
| 571740 | `CastleEffectsHelper.isAttackEffect` | UI tab classifier |
| 1519332 | `SoldierUnitVO.buffedMeleeAttack` | **global path only** |
| 1519626 | `SoldierUnitVO.buffedRangeAttack` | **global path only** |
| 2472547 | `CastleFightItemContainer.getAttackRangeValue` | lord path, **display only** |
| 2474282 | `CastleFightItemContainer.getAttackMeleeValue` | lord path, **display only** |

The split is clean and total:

- **Global event 148** → `buffed*Attack` → the auto-fill stack score and
  everything downstream that reads `buffed*Attack`.
- **Lord-side 148** → **only** the displayed army-strength number. It never
  touches a unit's stat line, never reaches
  `getSoldierStackAttackValue`, and never reaches
  `getFullAttackBonusForLordByFlankAndAreaType`.

Conversely, the global 148 is already baked into `buffedAttack`, so the display
path applies the two as separate additive terms — `(buffedAttack + g)`, where
`buffedAttack` carries the global part and `g` the lord part. They do not double
count.

**Do not add a lord-side 148 term to the fill path.** A commander wearing the
mead-unit relic changes the displayed strength and nothing about which stacks
auto-fill picks.

What auto-fill actually scores (`getSoldierStackAttackValue`, BUNDLE @4955179):

```
i = int(buffedMeleeAttack * _attackerMeleeBonus)   if melee
  = int(buffedRangeAttack * _attackerRangeBonus)   if range
  = 0                                              otherwise
return i * min(count, unitVO.inventoryAmount)
```

The `int()` is applied **before** the multiply by count, so the truncation error
is multiplied by the stack size. Port the parenthesisation exactly. Already
correct at `combat/effects.py:104`.

### 3.6 The lord path, for completeness

`LordVO.getEffectValue(effectType, areaType=-1, spaceId=-1, wodId=-1,
strategy=None)` (BUNDLE @3180760) collects equipment boni (including relic and
gem boni), equipment-set bonuses at reached thresholds, and the assigned
general's passives; then `D = a[0].clone()`, merges the rest with
`D.effectValue.add(...)`, and returns `D.effectValue.strength`. This is a
different, leaner filter than `getUniqueBoni`: `matchesConditions` plus the
PvP/PvE flip, with no capID bucketing.

**Same first-value defect**, and unlike the globals relic maps are **not**
server-flattened — there is no `setEffectStrength` equivalent on the relic path.
So the divergence is live there if the server ever rolls per-key strengths, or
if two relics of different 148 effectIDs merge on one lord.

**(Inferred, strongly):** a reported relic "type 148 `attackBonusUnit` with value
195" is the first wodId **key** of the map, not a strength. `relicEffects` id
20017 → effectID 22012 (`relicAttackBonusUnitMeadAttacker`, type 148) has
`minimumValue 5`, `maximumValue 20` and `effectValueKeys` beginning
`"195,196,197,…"`; ITEMS `units` 195 is a mead melee unit; and 195 is out of
range for **every** 148 relic band (4-12, 20-60, 10-40, 5-20).

**Likely live bug in the port.** `combat/bonuses.py`, `parse_bonus_entries`
(line 87) with `_first_number` (line 74): for the relic triple
`[20017, power, [195, 8, 196, 8, …]]` it takes the first number of the first
nested sequence and stores `Bonus(effect_id=20017, value=195.0)` — the first
wodId read as a strength. When `e[2]` is a plain scalar it instead falls back to
`_first_number(entry[1])`, the `power` roll-quality field, which is also wrong.
For map-valued types the port must parse `entry[2]` as pairs and keep the map.

A relic bonus arrives as the triple `[relicEffectId, power, value]`
(`RelicBonusVO.parseRelicFromValueArray`, BUNDLE @5032758); `power` is roll
quality, **not** strength. Entry points: `RelicEquipmentVO.parseEquipFromArray`
reads index `[5]`, `RelicGemVO.parseServerObject` reads `[4]`.

### 3.7 Defence has no equivalent

Three facts, all confirmed:

1. `getDefence{Melee,Range}Value` read the **raw** ITEMS columns `meleeDefence` /
   `rangeDefence` directly. There is no `buffedMeleeDefence` symbol anywhere in
   the bundle.
2. There is **no map-valued defence effect type**. The complete `EffectValueMap`
   set is `{148, 149, 150, 154, 188}`; every defence-side type
   (175/176/177/181-184/215-218) uses a scalar value class. There is no
   `defenceBonusUnit` analogue to build a per-unit defence buff from, on either
   path.
3. `isAttackEffect` classifies 148/149/150/154 as attack effects; the
   `isDefenceEffect` list contains none of them. UI classification only, but it
   confirms the intent.

**Client inconsistency, verify before mirroring.** The range branch composes the
equipment bonus and the alliance defence boost **multiplicatively**,
`(1+o)*(1+a)`, while the melee branch composes them **additively**, `(o+a)` with
`o` already pre-incremented. These are not the same function. Looks like a
genuine client bug; a port must pick one and document it. `int()` is applied per
stack inside the loop, not to the total.

### 3.8 Order of operations

Per unit, once, at stat-line level:

1. `raw = ITEMS units.meleeAttack` (or `.rangeAttack`).
2. If `raw == 0` → buffed is 0, stop. (The guard is on the raw column; the bonus
   is computed before the guard and discarded.)
3. `e = int(sum of bonus.strength over active event-610 effects)`, each passing:
   not expired, `userLevel` in `[minLevel, maxLevel]`, effect type 148, map
   contains this wodId, area/space gates.
4. `buffed = raw + e`.

Then, per path:

**A. Auto-fill scoring** — `int(buffed * attackerMelee|RangeBonus)`, then
`× min(count, inventoryAmount)`. No lord-side 148 term.

**B. Displayed army strength** — `(buffed + g) × amount × (C + m)`, where `g` is
the lord 148, `C = 1 + (equip 36 + 23|24 + 33/53/54)/100`, and
`m = (legend 4|7 + 43 + 15)/100`. Display only.

**C. Defence** — raw columns, no buff step exists at all.

Cap ordering is a no-op for 148: `EffectValueMap.add` never reads `maxValues`,
and every 148 `effects` row is capID 99. The ordering that **does** matter is
`EffectValueMap` insertion order, because both `.strength` getters read the first
inserted key.

### 3.9 ITEMS tables and payload fields

| Table | What it supplies |
|---|---|
| `units` | `wodID`, `meleeAttack`, `rangeAttack`, `meleeDefence`, `rangeDefence`, `role`, `hybrid`, `fightType`, `healingCostC1/C2`, `meadSupply`, `beefSupply` |
| `effects` | 824 rows: `effectID`, `name`, `effectTypeID`, `capID`, `areaTypeID`, `spaceIDs`, `isPvPFight`, `isPvEFight`. Resolves 273 → type 148 |
| `globalEffects` | 19 rows: `globalEffectID`, `effects`, `boostValue`, `minLevel`, `maxLevel`, `effectValueKeys` |
| `relicEffects` | 285 rows: `id` (what arrives on the wire), `effectID` (joins to `effects`), `minimumValue`, `maximumValue`, `effectValueKeys` |
| `equipment_sets` | `neededItemThresholds`, `effects` — a lord-side 148 source |
| `effecttypes` | name / sortCategory / sortGroup / combatType **only**; no value class |

Type 148 has **22** rows in `effects`: 273 (unrestricted, the only one used by
`globalEffects`), 276-280 (area-scoped: Nomad 27/35, Samurai 29/37, Alien 21,
Bloodcrows 34, Berimond 30), 485/486 (`isPvPFight`), 759/760, 763/764, 767/768,
771/772 (ARE loot variants), and 22001-22005 + 22012 (relic). All carry capID 99.
Siblings: type 149 one row (22006), type 150 five (22007-22011), type 154 one
(285).

Payload: `bie` at login (`CastleModel.globalEffectData.parse_GIE(n.bie)`,
BUNDLE @14416881) and the `BIE` command, shape

```
{ "SGE": [globalEffectID, ...],
  "GE":  [[globalEffectID, remainingSeconds, strengthOverride], ...] }
```

The `strengthOverride` is the **live** strength; the ITEMS value is only the
fallback when it is `-1`.

The port's `global_unit_attack_bonuses` (`combat/bonuses.py:415`) takes only a
list of effect **ids**, so it can never apply an override — it always uses the
ITEMS value. Change the input to the `GE` triples.

### 3.10 Test cases

1. **Global effect 5, no override.** `GE = [[5, 3600, -1]]`, `userLevel = 40` →
   `{602: 13, 608: 13}`. A unit with wodId 602 and `meleeAttack 200` has
   `buffedMeleeAttack == 213`.
2. **Override wins.** `GE = [[5, 3600, 25]]` → `{602: 25, 608: 25}` and the same
   unit buffs to 225. The ITEMS `boostValue` of 13 must not appear.
3. **Zero column stays zero.** A pure-melee unit keyed by an active map has
   `buffedRangeAttack == 0`, not `0 + e`.
4. **wodId is a gate.** A unit not keyed by any active map is unbuffed even while
   the effect runs.
5. **Level gate, with coercion.** `minLevel` 10 (int) and `maxLevel` `'99'`
   (string): `userLevel = 5` → no buff; `userLevel = 40` → buffed. A port that
   compares without `int()` raises `TypeError`.
6. **Expiry.** `entry[1] < now` → the whole entry is skipped.
7. **Truncation order.** `buffed = 213`, `melee_bonus = 1.37`, stack of 100:
   `int(213 * 1.37) = 291`, then `× 100 = 29100`. A port that truncates after the
   multiply gets 29181.
8. **Two effects on one unit sum.** Two active global effects both keying wodId
   602 → the strengths add (`total += bonus.strength` per VO).
9. **First-value vs per-key.** Build a deliberately non-uniform map
   `{602: 13, 608: 99}` and assert whichever convention the port chose, with the
   divergence logged. The client returns 13 for both keys.
10. **Lord 148 is not in the fill.** A commander with relic 22012 changes nothing
    about which stacks the fill picks.

### 3.11 Not established

- Whether the **server** applies any type-148 bonus to real combat, and from which
  sources. The client reads only event-610 into a unit's stat line, yet ITEMS
  `researches` (11 rows), `officersSchoolEffects` (5 rows, via an `effectID`
  column, singular, not the `effects` string every other table uses) and
  `equipment_sets` (6 rows) all carry type-148 data that nothing in the client
  consumes. `OfficersSchoolData.getBonusByEffectType` is defined and never
  called. Either the server applies them, or they are dead data.
  (`subscriptionsBuffs`, `sceatSkills` and `constructionItems` carry **none** —
  a claim to the contrary elsewhere is wrong.)
- Whether the server also applies the lord-side 148, or whether it is purely a
  display number as it is in the client. This is the practically important open
  question; the client answer is unambiguous, but it says nothing about the
  server.
- **Resolved.** `LordVO.parseRawEffects` reads each entry as
  `[effectID, valueArray, sourceTag]` and passes `n[1]` straight to
  `BonusVO.parseFromValueArray`, so `e[2]` is the **source tag**, not the value.
  The value is `n[1]`, an array, and `EffectValueMap.parseFromValueArray`
  accepts it either flat (`[wodId, value, wodId, value]`, stepping by 2) or as
  nested pairs. Both `EffectValueMap.strength` and `EffectValueWodID.strength`
  then return the first key's **value** — index 1 of the flat form. Ported at
  `combat/bonuses.py`, `Bonus.strength`.
- Which wodIds a relic keyed effect covers. The `relicEffects` rows carry an
  `effectValueKeys` column (e.g. row 20001, effect 22001, keys
  `672,664,686,687,75,76`), but `ClientConstItems.EFFECT_VALUE_KEYS` is defined
  and **never read** in either bundle, so the client does not expand it: the map
  arrives already built from the server. A scalar value with no keys is
  therefore also a legitimate shape, and the port handles both.
- Whether the buffed getters' use of the **currently viewed** area rather than the
  target's is intentional. Harmless with today's data (effect 273 is
  unrestricted); the port must pick a convention regardless.

---

## Port deltas, collected

Checked against `ea42a90`. Two entries an earlier draft carried are already
fixed there and are **not** listed: the range/melee strategies now add the
conditioned 215/217 term (`combat/tools.py:170`, `:177`), and the strategy pool is
rebuilt per flank (`combat/solver.py:285`).

| Where | What |
|---|---|
| `combat/capacity.py:144` | `int(round(...))` → `math.floor(v + 0.5)`; JS `Math.round` is half-up, Python's `round` is banker's |
| `combat/effects.py:48` | `apply_tool` lacks the 215/217 additions, so a tool picked for its conditioned bonus feeds nothing back — asymmetric with the pick side, which now reads it |
| `combat/tools.py` | no `canUseToolForAttackOnTarget` gate (neither `allowedToAttack` nor `canBeUsedToAttackNPC` is consulted) |
| `combat/tools.py:137` | `amount_per_wave` is scoped to one flank and keyed by wodId; the client keys it by the ITEMS `type` string and sums across all three tool containers of the wave |
| `combat/tools.py`, `fill_flank_with_tools` | deduction is deferred until after the slot-type check, so the client's deduct-then-discard cannot occur; slots are a count rather than a list, so merge-abandons-the-slot cannot either. Both are deliberate divergences — decide and log them |
| `gamedata/models.py:141` | `can_attack_npc` defaults to `False`; the client's default is **true** (`1 == parseInt(..., "1")`) |
| `combat/solver.py:324` | `fill_yard_wave` defaults `slots=1` (should be 8) and returns a compacted list (`RW` is always 8 pairs, `[-1, 0]` for empties) |
| `combat/bonuses.py:415` | `global_unit_attack_bonuses` takes effect ids, so it cannot apply the `GE` `strengthOverride`; take the triples |
| ~~`combat/bonuses.py:87`~~ | Fixed: `Bonus` keeps the array it was sent and `Bonus.strength` reads index 1 for the nine keyed effect types |
