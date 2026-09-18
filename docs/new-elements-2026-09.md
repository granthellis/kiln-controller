# New elements (Sep 2026): PID check, top-rate profiles, firing stats

New elements went in on 16 Sep 2026: 11.24 Ω, 21.3 A at 240 V (the old set retired at
15.58 Ω / ~15.5 A). The first loaded firing was cone 6 on 18 Sep, about 75% full, on the new
`cone 6 - Tony Hansen drop soak FAST` profile, autostarted from Home Assistant at 06:00.

Raw 5-second controller log: [`data/firings/2026-09-18-cone6-fast.csv.gz`](../data/firings/2026-09-18-cone6-fast.csv.gz)
(`/api/status` including `pidstats`). Mains current and voltage for the same period are in VictoriaMetrics
(`sensor.kiln_energy_*`).

## Result of the 18 Sep firing

| | Original profile | FAST, measured |
|---|---|---|
| Total (RUNNING → IDLE) | 9.93 h scheduled | **7.62 h** (06:00 → 13:37) |
| 121 → 1138 °C | 5.12 h at 199 °C/h | **2.77 h** at top rate |
| Energy | – | 18.9 kWh |
| Time above 1000 °C | – | 2.9 h |

### PID verdict: pass, gains unchanged

`kp 12.48 / ki 16.08 / kd 275` (Z-N tune, 20 Jun 2026) plus the integral clamp (a84b1ce).

| Phase | Criterion | Measured | |
|---|---|---|---|
| Candle 60 °C/h + 121 hold | ±3 °C | ramp MAE 1.0 °C; one +3.6/−4.0 excursion in the first 15 min (full-power seek from 23 °C at 50% throttle); hold ±0.5 °C | pass |
| Top-rate climb | catch-up, output 1 | output 1 from 300 °C setpoint; 50% throttle below that | n/a |
| Arrival at 1138 from full power | overshoot ≤5 °C, ±3 °C within 10 min | **no overshoot** (max +1.1); inside ±3 °C 4 min after target reached | pass |
| 1138 hold | ±3 °C, no sawtooth | −2.2 … +2.1 °C once settled; 2–3 min dither from kd on quantised temperature, harmless | pass |
| 57 °C/h ramp to 1192 | MAE ≤2 °C | MAE 0.9 °C, −2.3 … +2.6 | pass |
| 1192 hold | ±3 °C | −1.5 … +2.5 | pass |
| Drop 1192 → 1138 (~540 °C/h) | undershoot ≤5 °C | kiln cools ~450 °C/h, so it lags +5 °C on the way down; undershoot −3.2 °C | pass |

The integral saturated at the clamp (100) during the approach to 1138. That is expected: the error sat
just inside the 5 °C window for a few minutes. The clamp is what prevents the July-style sawtooth.
No gain change is needed. Re-check if the elements drop below ~92% health.

### Loaded top-rate curve (75% full, ~231–234 V)

| Band | °C/h |
|---|---|
| 121 → 300 | ~360–500 (throttled to 50% below a 300 °C setpoint) |
| 300 → 500 | 640–860 |
| 500 → 700 | 415–500 |
| 700 → 900 | 310–365 |
| 900 → 1000 | 250–280 |
| 1000 → 1100 | 200–240 |
| 1100 → 1133 | ~180 |

Time from the start of the climb (121 °C): 300 °C 0.46 h · 600 0.93 h · 900 1.76 h · **982 2.06 h** ·
1100 2.59 h · **1133 2.77 h**. Hold power: 1138 °C just after arrival 3.2 kW, 1138 °C after the peak 2.4 kW,
1192 °C 3.0 kW, out of ~4.75 kW available at 231 V. So cone 10's 57 °C/h to 1260 has plenty of headroom
while the elements are new.

A single-C heat-balance fit (`rate = (V²/R − k·ΔT)/C`) fits poorly, with 27 °C/h RMS. That's because the
bricks and ware are still soaking up heat during the climb, so the effective heat capacity isn't constant.
Use the empirical table above to estimate climb times. Refit it after each top-rate firing: the rate at
~1000 °C is a second, load-dependent sign of element wear.

Most of the saving is below ~900 °C, as predicted: near the top, the old 199 °C/h was already close to
flat out.

## Profiles (on the Pi, in `storage/profiles/`, and in the HA selector)

Originals are unchanged. The new entries are:

| Profile | Change | Estimated loaded time (was) |
|---|---|---|
| `cone 6 - Tony Hansen drop soak FAST` | 121 → 1138 in 1 h (top rate via catch-up); tail identical | **7.62 h measured** (9.93) |
| `cone 10 - Tony Hansen drop soak FAST` | 121 → 1153 top rate; 1153 hold, 57 °C/h to 1260, holds and drop identical | ~8.8 h (10.88) |
| `cone 04 - drop soak FAST` | 121 → 982 top rate; rest identical | ~6.7 h (8.12) |
| `cone 07 - standard bisque QUICK` | 120 → 600 at 250 °C/h (was 170); 600 → 860 at 170, 860 → 960 at 60 + 30 min hold unchanged | ~7.2 h (8.05) |

The bisque doesn't get top rate: water smoking and burnout (400–900 °C) are what fast bisques get wrong.
`cone 07 - thick bisque` is untouched. If a FAST glaze shows pinholing, cap 900 → top at 150 °C/h.

## Home Assistant

Everything is in [`homeassistant/kiln-stats/`](../homeassistant/kiln-stats/). The template block lives in
`configuration.yaml` under `template:`, and the automation and script are in storage mode.

- **Counters**: `counter.kiln_firings_<cone>_{lifetime,elementset}` for cone 07/06/05/04/5/6/7/10/other,
  plus `…_lifetime_total` and `…_elementset_total`.
  - Lifetime is backfilled from the VictoriaMetrics history (25 Jul onwards, classified by peak target):
    cone 10 ×2, cone 6 ×4 (including 18 Sep), cone 04 ×1, cone 07 ×4.
  - Not counted: 25 Jul (peak target 1167) and 11 Sep (1145), which don't match a profile. Anything
    before 25 Jul isn't in VictoriaMetrics.
  - The element-set counters start with 18 Sep's cone 6.
- **`automation.kiln_run_tracker`** records profile, start, kWh start and peaks at RUNNING. At RUNNING → IDLE:
  - A run is **completed** if peak temp ≥ peak target − 10 °C.
  - The cone comes from the profile name. dry/test/wear-in profiles are never counted.
  - It increments both counter sets, stores the run's element R, accumulates hot hours (time > 1000 °C
    while running), and fires `kiln_firing_completed` (profile, cone, completed, duration_h, kwh, peaks,
    r_ohm, r_samples).
  - It adds a logbook line, and sends a phone notification if health drops below 92%.
- **Element health**: `sensor.kiln_element_resistance_run` averages R = V/I over samples where current is
  ≥ 90% of full-on and PF ≥ 95.
  - 18 Sep gave **11.243 Ω** from 1254 samples, with p10–p90 of 11.22–11.25. That's within 0.1% of the
    empty-kiln wear-in (11.23 Ω).
  - `input_number.kiln_element_r_baseline` is set to 11.243 Ω; `sensor.kiln_element_health` =
    baseline / last R.
  - Status: ≥92% normal; 85–92% slowing (top of cone 10 may lag); <85% plan replacement. The old set
    was retired at ~72%.
  - Also tracked: `sensor.kiln_element_current_at_240v`, `sensor.kiln_element_energy` (kWh since the set
    went in, including the wear-in) and `input_number.kiln_element_hot_hours` (5.79 h including the
    wear-in).
  - Old-set reference: 15.21 Ω (25 Jul) → 15.58 Ω (11 Sep), about +2.4% over ~12 firings, with the steps
    after the cone 10 firings.
- **Start-time recommender (solar-matched)**: `sensor.kiln_recommended_start`.
  - For each candidate start (15-min steps), it slides the profile's 15-min kiln demand curve across the
    Solcast p50 forecast for the day chosen in `input_select.kiln_firing_day` (Today, Tomorrow, In 2–6 days).
    Solcast covers 7 days; the day 3–7 sensors (`sensor.solcast_pv_forecast_forecast_day_3` … `_7`) were
    disabled by default and are now enabled. Beyond about 2 days the p10 (cloudy) share spreads out a lot,
    so treat those as a rough guide.
  - Today: no start before now (rounded up to 15 min). If the deadline can no longer be met it falls back
    to the best start that finishes by 20:00 and sets `deadline_met: false`; after that it reports
    `too late today`.
  - Active firing: with Today selected and the kiln RUNNING, there is no search. The sensor shows `firing`,
    using the running profile (`input_text.kiln_run_profile`) and its real start. The demand curve is the
    meter's measured 15-min slots so far, followed by the rest of the profile's curve, so the estimated
    finish and solar share update as the firing goes. The Today chart adds a "Measured so far" line
    (`chart_measured`, including the current partial slot up to now).
  - It scores each start by kiln kWh covered by `solar − house base load`
    (`input_number.kiln_house_base_load`, 0.8 kW, the daytime median of house minus kiln).
  - It picks the best start that still finishes by `input_datetime.kiln_cheap_window_end` (16:00) minus
    the buffer, taking the earliest start on near-ties.
  - Attributes: solar share at p50 and p10 (cloudy), kiln kWh, the no-deadline optimum (what the
    deadline costs), and chart series.
  - Demand curves: learned from the meter by `sensor.kiln_demand_trace_current` (kW per 15 min from run
    start), stored per profile in `sensor.kiln_demand_traces` on each completed firing. Until a profile
    has been fired, it uses a seed curve: measured 18 Sep for cone 6 FAST, and simulated with
    [`tools/kiln_sim.py`](../tools/kiln_sim.py) for the rest (`demand-traces-seed.json`).
  - Buffer: 60 min before any run of that profile, 45 min after 1–2 runs, then max(30, max − mean + 15)
    min (durations in `sensor.kiln_profile_durations`).
  - `script.kiln_apply_recommended_start` copies it into the autostart time and arms autostart, but only
    when the recommended start (`start_ts`) is within the next 24 h. `automation.kiln_autostart` fires at the
    next occurrence of the clock time, so a plan for day 3+ has to be applied the day before. Otherwise it
    leaves autostart alone and posts a notification. Note the autostart automation switches the kiln off and
    on if it is already on, so don't leave it armed for a time that falls inside a firing.
  - **Kiln dashboard** (`/dashboard-kiln`, apexcharts-card via HACS, config in
    `dashboard-kiln.json`): the firing day 05:00–20:00 with solar p50 (area), solar p10 (dashed) and
    kiln + house demand at the recommended start (one conditional chart per selector option, since
    apexcharts-card's span can't be templated; Today also shows a "now" line); plus the recommendation,
    elements and counters.
  - For Sat 19 Sep (Solcast clipped at 5 kW from 10:30 to 14:30):

    | Profile | Start → finish | Solar share p50 / p10 | No deadline |
    |---|---|---|---|
    | cone 6 FAST | 07:30 → 15:15 | 94% / 55% | same |
    | cone 10 FAST | 06:15 → 15:00 | 88% / 47% | 07:15 → 16:00, 93% |
    | cone 04 FAST | 08:00 → 15:00 | 94% / 65% | same |
    | cone 07 QUICK | 07:45 → 15:00 | 97% / 70% | 08:30 → 15:45, 100% |

  - Battery isn't modelled: the uncovered kWh (candle, cloud) come from battery or grid.
  - Times are Australia/Sydney local clock. DST starts 4 Oct; Solcast periods are indexed by absolute
    time, so the DST day is handled.

### Firing cost (energy + element wear)

Each run gets a cost made of energy plus element wear.

- **Energy**: `sensor.kiln_run_energy_cost` charges every tick of the kiln's kWh counter at the marginal rate
  for that moment. The kiln's kW is taken from grid import first, then battery discharge, then solar.
  - Grid is priced at the Amber import price (`sensor.home_general_price`, the same price the Energy dashboard uses).
  - Battery is priced at the weighted cost of what's stored (`input_number.battery_charge_cost`).
  - Solar is priced at the feed-in it would have earned (`sensor.home_feed_in_price`), floored at 0: a
    negative feed-in is usually curtailed, so solar never counts as a credit.
  - Attributes give kWh and $ per source. The sensor resets at run start, and deltas are taken against the
    last counter reading it saw, so kWh used while the meter was unavailable are still charged.
  - When the meter reads 0 W between element pulses, that tick's kWh is split as if the kiln drew 1 kW.
- **Wear**: hot hours for the run (>1000 °C while running) × `input_number.kiln_element_set_price` ($500) ÷
  `input_number.kiln_element_life_hot_hours` (500 h), which works out to $1.00 per hot hour.
  - The 500 h life comes from the old set. Its resistance rose 2.4% (15.21 → 15.58 Ω) over ~30–33 running
    hot hours (6 Aug – 11 Sep, VictoriaMetrics). At that rate, reaching the ~72% power at which it was
    replaced takes 480–540 h.
  - It's a first estimate. `sensor.kiln_element_value_used` measures the same thing from resistance
    (R_last / R_baseline against `input_number.kiln_element_retire_health`, 72%). Once a few percent of
    life is used, its `implied_life_hot_h` attribute says what to set the life helper to.
  - Bisque (< 1000 °C) costs about $0 in wear under this model.
- `sensor.kiln_run_cost` shows energy + wear for the current run as it goes (or the last run, once finished).
- At run end, `kiln_run_tracker` adds `energy_cost`, `wear_cost`, `total_cost`, `hot_h` and the per-source
  kWh/$ to `kiln_firing_completed`. It also adds the cost to the logbook line and sends a phone notification.
- **Ledger**: `sensor.kiln_firing_costs` (state = lifetime $, `state_class: total`). Its attributes hold
  lifetime and element-set energy/wear totals, `last_run`, the 20 most recent runs, and per-profile
  averages for completed runs.
  - Fire `kiln_cost_elementset_reset` when the elements are replaced.
  - `kiln_cost_backfill` takes the event fields for runs before the meter existed. I costed them from
    recorder history with [`tools/kiln_cost_backfill.py`](../tools/kiln_cost_backfill.py), and
    `kiln_cost_adjust` seeded the part of 19 Sep's firing that ran before the meter was deployed.

| Run | kWh | grid / battery / solar kWh | Energy | Hot h | Wear | Total |
|---|---|---|---|---|---|---|
| 16–17 Sep wear-in (empty) | 21.8 | 14.4 / 0.7 / 6.7 | $1.60 | 2.83 | $2.83 | $4.43 |
| 18 Sep cone 6 FAST | 18.9 | 7.9 / 0.4 / 10.6 | $0.40 | 2.89 | $2.89 | $3.29 |

On a solar-matched day, wear is most of a glaze firing's cost. So the hot hours the FAST profiles save are
worth more than the energy they save.

## Possible follow-ups

- The controller's cost estimate (`kw_elements`, `kwh_rate`, `sensor.kiln_cost`) isn't meaningful on a
  dynamic tariff with solar and battery, so ignore it. `sensor.kiln_run_cost` replaces it.
- Add the expected cost of a planned firing to the recommender (Amber price forecast × uncovered kWh, plus
  wear from the profile's learned hot hours).
- Throttle (50% below a 300 °C setpoint) costs ~15 min on a FAST climb. It's there for the candle, so
  leave it unless the time matters.
- HA's `Kiln refresh rate during run` automation logs a "While condition … looped 5000 times" warning
  (2 s × 5000 ≈ 2.8 h) during long firings. Worth checking whether the 2 s refresh stops there. The
  20 s REST poll carries on either way.
- v2 recommender: shift or flag using Solcast `forecast_tomorrow` and Amber price forecasts.
