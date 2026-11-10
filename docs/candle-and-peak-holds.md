# Candle and peak holds, set per firing (2026-11-11)

Plan of record for taking the candle and the top-temperature ("peak") hold out of the stored
schedules and making them per-firing settings that can also be changed while the kiln runs.

## Why

Every schedule carried its own candle, written two ways: the standard schedules ramp 25→121 °C at
~1 °C/min (96 min) and hold 60 min; the QUICK ones ramp 30→120 °C in 32 min (~170 °C/h) and hold
60 min. A bisque that needs 3 h of drying, or a densely packed glaze load that needs a longer soak
at the top, meant editing or copying a schedule. The operator wants to:

- choose the candle hold for each firing (default 60 min, ramp ~170 °C/h, about 30 min to 120 °C);
- **extend the candle while it runs** — e.g. moisture still at the exhaust, add an hour — or end
  it early once the exhaust is dry;
- add time to the top hold for a firing, before the start or while firing.

## Decisions

| # | Decision |
|---|----------|
| D1 | The **controller** composes the run: stored schedule + candle + peak hold. Every start path (REST, web-UI websocket, automatic restart) gets the same curve, and `/api/status` `profile_data` already carries it to HA. |
| D2 | A schedule with `"candle": true` stores only the **body**, starting at `[0, T]` where `T` is the candle temperature. Run-time prefix: `[0, candle_start_temp]` → ramp at `candle_rate` (170 °C/h) to `T` → hold `candle_min`. Hold 0 ramps straight into the body. |
| D3 | Schedules without the marker run unchanged (fast glaze, 4hr/5hr dry, tests). |
| D4 | Standard schedules move from the 96-min 1 °C/min ramp to 170 °C/h like QUICK (operator, 2026-11-11). 4hr/5hr dry stay as they are (redundant now; not deleted). |
| D5 | The **peak hold** is detected, not marked: the first flat segment at the schedule's maximum temperature. If the schedule just touches its peak, the hold is 0 min and extra time inserts one. The schedule's own length is the default. |
| D6 | Start parameters: `candle_min` (absolute, default `candle_hold_min_default` = 60, max `candle_hold_max_min` = 1440) and `peak_extra_min` (added to the schedule's own, default 0, max `peak_extra_max_min` = 120). |
| D7 | Live changes recompose only the future. A change that would alter any point at or before the current runtime is refused. Candle: `add_min > 0` while before its end; `end_now` ends it at the current runtime. Peak: `add_min > 0` while before its end, total extra ≤ the max; it can never be cut below the schedule's own hold (underfiring risk). |
| D8 | `startat` stays "minutes into the composed run". Restart state saves the current hold lengths (including live changes) so an automatic restart rebuilds the same curve. |
| D9 | `/api/status` adds `phase` (`candle` / `firing` / `peak_hold` / `after_peak`) and `holds`; `GET /api/profile_shapes` gives HA each schedule's body length and peak position for planning; `GET /api/compose` previews a composed run. |
| D10 | `save_profile` keeps an existing file's `candle` marker when the web-UI editor (which saves only `{type, data, name}`) overwrites it. |

## Controller work (this branch)

- `lib/holds.py` — pure functions: `find_peak_hold`, `compose`, `phase_at`; no hardware imports.
- `lib/oven.py` `Profile(json, candle_min=None, peak_extra_min=None)` composes on construction and
  keeps the body; `extend_hold(which, add_min, runtime)` / `end_candle(runtime)` recompose in place
  (the watcher holds a reference, so the web UI follows). `Oven.adjust_hold` updates `totaltime`.
- `kiln-controller.py` — `run` accepts `candle_min` / `peak_extra_min`; new `hold` command;
  websocket `RUN` accepts the same keys; `GET /api/profile_shapes`, `GET /api/compose`;
  `save_profile` keeps the marker.
- `config.py` — `candle_start_temp = 25`, `candle_rate = 170`, `candle_hold_min_default = 60`,
  `candle_hold_max_min = 1440`, `peak_extra_max_min = 120`.
- `tools/migrate_candle.py` — dry-run by default; converts ramp → hold → more schedules only;
  prints each converted schedule's old candle length (needed to migrate HA's learned data).
- Web UI: candle-hold and peak-extra fields on the start dialog, sent with `RUN`.
- Tests (`Test/test_holds.py`): composition, hold 0, peak detection + insertion, seek on a warm
  kiln, live extend/end continuity (no point at or before runtime moves), refusals, restart
  rebuild, migration round-trip (migrated schedule at hold 60 = original after the candle).

## Home Assistant work (after the controller merges)

- Helpers `input_number.kiln_candle_hold_min` (0–720, step 15) and
  `input_number.kiln_peak_hold_extra_min` (0–120, step 5), created **without** `initial`, set to
  60 / 0. Both reset to 60 / 0 when a firing completes (a leftover value is how the 2026-11-11
  autostart began at minute 32).
- REST switch `body_on` sends `candle_min` and `peak_extra_min`; status sensor exposes `phase` and
  `holds`; a `rest_command` + scripts drive `hold` (candle +30/+60/end now, peak +15/+30).
- Learning stores body-only traces/durations: the tracker records wall-clock phase transitions
  (robust to catch-up pauses) and the candle and the extra peak time are cut out. One-off event
  migrates existing learned + seed traces/durations by each schedule's old candle length.
- Recommender + scenario plan `candle(hold) + body[..peak] + extra × peak-slot kW + rest`, with
  peak positions from `/api/profile_shapes`; both hold helpers are triggers.
- Kiln dashboard: hold fields, Start-at-minute, live phase/remaining, live hold buttons.
- Phone (S23 Ultra) notification 10 min before each hold ends, with
  `+30 / +60 / Proceed` (candle) and `+15 / +30 / Proceed` (peak) actions.

## Rollout (between firings only — never restart the controller mid-firing)

1. Merge #4 (the Pi's uncommitted watchdog fix + schedule edits) so the deploy can't overwrite it.
2. On the Pi: `tools/migrate_candle.py` dry run → review → `--apply`.
3. Pull + restart `kiln-controller` while IDLE; check `/api/compose` for every migrated schedule at
   candle 60 and 180, peak extra 0 and 30.
4. HA changes + learned-data migration in the same window; check config; reload templates.
5. First firing: learned trace starts after the candle; duration excludes candle + extra peak.
