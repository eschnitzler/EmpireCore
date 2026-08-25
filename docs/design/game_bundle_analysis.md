# Game Bundle Analysis

**Source:** `Game.bundle.307655b0ef7378beb51b.js` (Empire HTML5 client), plus
`dll/ggs.dll.baad44188cfd15e3936c.js` for the shared protocol key constants.
**Date:** 2026-08-24
**Where they come from:** `https://empire-html5.goodgamestudios.com/default/index.html`
lists the current bundle hashes; they change on every client release.

The client uses SmartFoxServer (SFS) with a mix of XML (handshake) and
JSON-over-string (extended protocol `%xt%`). Command IDs live in `ClientConstSF`
and payload key names in `CommKeys`.

## 1. Command IDs

Extracted from `ClientConstSF`.

| Category | Constant | Command | Description |
|---|---|---|---|
| Auth | `C2S_LOGIN` | `lli` | Login |
| Auth | `C2S_VERSION_CHECK` | `vck` | Pre-login version check |
| Attack | `C2S_CREATE_ARMY_ATTACK_MOVEMENT` | `cra` | Send attack |
| Attack | `C2S_GET_ATTACK_INFO` | `gai` | Attack pre-calculation |
| Attack | `C2S_GET_ATTACK_CASTLE_INFOS` | `aci` | Target defense info |
| Commanders | `C2S_GET_LORDS_INFO` | `gli` | Commander + baron list |
| Commanders | `C2S_RENAME_LORD_EVENT` | `arl` | Rename a commander |
| Generals | `C2S_GET_GENERALS_INFO` | `gie` | General list |
| Generals | `C2S_GENERAL_ASSIGN_LORD` | `gla` | Assign a general to a commander |
| Generals | `C2S_GENERALS_HUB_STATUS` | `gcs` | Generals hub status |
| Generals | `C2S_GENERALS_SET_ABILITIES` | `gaae` | Set general abilities |
| Player | `C2S_GET_DETAILPLAYERINFO` | `gdi` | Player profile |
| Player | `C2S_SEARCH_PLAYER` | `wsp` | Search player by name |
| Castle | `C2S_RENAME_CASTLE` | `arc` | Rename castle |

To extract more:

```bash
grep -oE 'C2S_[A-Z_]+\s*=\s*"[a-z]+"' Game.bundle.js | sort -u
```

## 2. Terminology: commander, baron, general

Three distinct things share the internal name "lord":

- **Commander** — `CommanderVO extends LordVO`. Returned by `gli` under key `C`
  (`CommKeys.COMMANDERS = "C"`). This is what a player picks when sending an
  attack, and what `LID` refers to on movement commands. The UI names them via
  the loca key `commander_index` ("Commander 1", "Commander 2", ...).
- **Castellan** — `BaronVO extends LordVO`, `isBaron` in the client. Also returned
  by `gli`, under key `B`. The UI calls it a castellan
  (`CastleEquipmentDialog.CASTELLAN`, `isBaron ? "castellan" : "general"`).
- **General** — a separate, newer system (`gie`, `gla`, `gcs`, `gaae`). A general
  is *assigned to* a commander; the two are not interchangeable.

EmpireCore names the Python API after the commander, and keeps the server's
own key and command names (`gli`, `LID`, `ID`) on the wire.

## 3. `gli` — commander and castellan list

`CastleLordData.parse_GLI` reads:

```json
{"B": [ ...castellans... ], "C": [ ...commanders... ]}
```

Both entry kinds parse through `LordVO.parseLord`:

| Key | Meaning |
|---|---|
| `ID` | Commander/castellan ID |
| `E` | Raw effects (list) |
| `AE` | Area effects (list) |
| `W` | Wins |
| `D` | Defeats |
| `SPR` | Win spree |
| `EQ` | Equipment entries; `entry[1]` is the slot type (helmet/armor/weapon/artifact/skin/hero) |
| `AIE` / `TAE` | Temporary/alien effect block, whichever is present |

Commanders are sorted, then given `playerIndex = position + 1` for display.

## 4. `cra` — send attack

`C2SCreateArmyAttackMovementVO(srcPos, tgtPos, armyData, waitTime, horses, bpc,
attackType, av, lp, lordId, fc, kingdomId, ptt, sd, isCollector, collectorBooster,
toolsSupportWodIds, yardWaveSlotList, autoSkipCooldownType)`

| Key | Meaning |
|---|---|
| `SX`, `SY` | Source absolute map coordinates |
| `TX`, `TY` | Target absolute map coordinates |
| `A` | Wave list (see below) |
| `KID` | Source kingdom ID |
| `LID` | Selected commander ID, `0` for none (note: `cds` uses `-14` instead) |
| `WT` | Wait time |
| `HBW` | Horse type, forced to `-1` when the feather flag is set |
| `BPC` | Boost with coins |
| `ATT` | `CombatConst.ATTACK_TYPE_ATTACK` or `ATTACK_TYPE_CONQUER` |
| `AV` | Bool flag (0/1) |
| `LP` | Int |
| `FC` | Bool flag; the attack dialog always passes `false` |
| `PTT` | Feathers (0/1) |
| `SD` | Slowdown |
| `ICA` | Collector attack (0/1) |
| `BKS` | Collector booster |
| `AST` | Support tool WOD IDs |
| `CD` | Hardcoded `99` |
| `RW` | Yard wave slot list (`yardWaveContainer.getSlotList(true)`) |
| `ASCT` | Auto-skip cooldown type |

`C2SCreateArmyAttackMovementAdvisorVO` extends this with advisor fields when the
player has advisor attacks left.

### The `A` army payload

`CastleAttackArmyVO.getArmyData()` returns one entry per wave, skipping any wave
whose unit total is zero (`isWaveComplete`). Each entry is:

```json
{"L": {"T": [[wodId, amount]], "U": [[wodId, amount]]},
 "M": {"T": [], "U": []},
 "R": {"T": [], "U": []}}
```

`L`/`M`/`R` are the left, middle and right flank; `T` is tools and `U` is units.
Slot lists come from `CastleFightItemContainer.getSlotList`.

Wave count is `CombatConst.getMaxWaveCountWithBonus(userLevel, areaType, bonus)`,
where the bonus is the `ADDITIONAL_WAVE` legend skill.

## 5. Fill Waves

The attack dialog's "Fill waves" button (`dialog_attack_autofill_fillWaves_button`)
runs entirely on the client. `AttackDialogAutoFill.autoFillSelectedWaves` calls, per
selected wave:

```
new StrongestDefenceCounterWaveStrategy().fillWave(
    attackInfo, options, wave,
    FightScreenHelper.getAttackerEffectVO(wave, selectedLord, isLegendaryFight, attackInfo),
    FightScreenHelper.getDefenderEffectVO(attackInfo))
```

`AFillWaveStrategy.fillWave` fills each enabled flank in turn — tools first, then
soldiers, then `checkFlank` — from a filtered copy of the unit inventory, and
writes the inventory back at the end. Options are `fillLeftFlank`,
`fillRightFlank`, `fillMiddleFlank` plus the unit/tool filters. The yard wave goes
through `fillYardContainer` with the `FLANK_YARD` defender effects.

Reproducing it needs unit and tool stats, which the client gets from its
`items.xml`-derived config (`ITEM_XML_LOADER` → `CastleModel.xmlPropertyData`,
built with `@goodgamestudios/itemsxml2json`). That blob's URL is injected through
the loader parameters, not hardcoded in any bundle.

## 6. Reverse-engineering recipe

1. **Find the VO** — search `function C2S...VO` for the class definition; the
   constructor body lists every JSON key it emits.
2. **Map arguments** — minified parameter names are positional, so read the
   `this.XX = <arg>` assignments in order.
3. **Find usage** — search `new ...C2S...VO(` for a call site to learn what each
   argument actually is.
4. **Resolve key constants** — `CommKeys.FOO` values live in `ggs.dll.js`
   (`grep -o 'FOO="[^"]*"' ggs.dll.js`).
