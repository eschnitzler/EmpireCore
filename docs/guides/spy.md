---
description: Spy missions planned for risk, sabotage, and reading spy reports.
---

# Spy

`client.spy` sends spies the way the game's spy dialog does: it asks what the
target's guards and your free spies are, plans the mission at the lowest risk
your spy pool allows, sends it, and waits for the report.

## Spy a target

```python
from empire_core import Kingdom, SpyOutcome, SpyType

castle = client.castle.get_all()[0]

result = client.spy.execute_instant_spy(
    castle.castle_id,
    target_x=700,
    target_y=710,
    target_kingdom=Kingdom.GREEN,
    risk_tolerance=20,          # skip the target rather than spy it above 20% risk
    spy_type=SpyType.MILITARY,  # or SpyType.ECO for resources
)

if result.success:
    print(result.report)
    print(result.army)          # the defenders by position
elif result.outcome is SpyOutcome.RISK_OVER_BUDGET:
    print("too well guarded")
else:
    print(result.outcome, result.step, result.error)
```

`risk_tolerance` does not make the mission riskier; missions always run at the
lowest risk the pool allows, and the ceiling only decides whether to send at
all. A lower `accuracy` (50 to 100) needs fewer spies for the same risk but
returns a less complete report.

The call blocks until the spies arrive plus 10 seconds for the report, or
`max_wait` if that is shorter, so do not call it from a state callback. With
no spy at home it returns at once; `wait_for_spies` keeps asking for up to that
many seconds while spies are on their way home.

Nothing is paid unless you ask: by default the spies travel without a horse.
`feathers=True` uses the instant spy horse, paid with feathers, and
`horse_booster_id` a horse of your own.

### How a mission ends

`SpyResult.outcome` is a `SpyOutcome`:

| Outcome | Meaning |
|---|---|
| `SUCCESS` | The report was read; `report` and `army` hold it. |
| `SENT` | The mission was sent and its report not waited for (sabotage). |
| `NO_SPIES_AVAILABLE` | No spy was free, after polling for returning spies. |
| `RISK_OVER_BUDGET` | Even the whole pool stays above `risk_tolerance`, so nothing was sent. |
| `COMMAND_FAILED` | A request failed; `error` holds why and `step` which one. |
| `TIMEOUT` | No report for this mission arrived before the deadline. |

`step` is a `SpyStep`, the command the mission was at when it ended: `ssi`
(the spy screen), `csm` (sending), `sne` (the report's mail) or `bsd` (reading
it).

## Sabotage

```python
result = client.spy.send_sabotage(castle.castle_id, 700, 710, damage=10)
```

Sabotage spies travel at a ninth of a spy's speed, so the report is not
waited for: the outcome is `SENT` with the server's reply in `result.mission`.

## Lower-level calls

- `get_screen_info(target_x, target_y)`: what a mission would face, the
  target's guards, your free spies and its map row.
- `send_spy_mission(...)`: send one mission exactly as given, without planning
  or waiting.
- `auto_spy(target_x, target_y)`: spy at once with the auto-spy subscription.
- `spies_in_use()`: spies on your own spy movements, as state tracks them.

## Reports

Any spy report in the mailbox can be read by its message id:

```python
report = client.spy.get_report(message_id)  # None when the server has none
client.spy.forward_report(message_id, [player_id])
```

**API:** [`SpyService`](../reference/spy.md#empire_core.spy.service.SpyService),
[`SpyResult`](../reference/spy.md#empire_core.spy.service.SpyResult)
