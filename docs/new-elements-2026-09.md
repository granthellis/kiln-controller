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
- **Start-time recommender**: `sensor.kiln_recommended_start` gives the start that finishes at
  `input_datetime.kiln_cheap_window_end` (16:00) minus a buffer.
  - Duration is the learned mean from `sensor.kiln_profile_durations`, or the seed above.
  - Buffer: 60 min before any run of that profile, 45 min after 1–2 runs, then
    max(30, max − mean + 15) min.
  - It aims to finish as late in the window as possible because firing power rises with temperature. The
    candle is ~0.3–0.5 kW; the climb and top are 3–4.75 kW.
  - `script.kiln_apply_recommended_start` copies it into `input_datetime.kiln_autostart_time` and turns
    autostart on.
  - Right now: cone 6 FAST → **07:37**, finishing ~15:15 (n = 1).
  - Times are Australia/Sydney local clock. DST starts 4 Oct and the window stays 11:00–16:00 local.

## Possible follow-ups

- `kw_elements = 4.3` in `config.py` under-reads the controller's own cost estimate. The new set draws
  ~4.75 kW at 231 V, so set it to 4.8 at a convenient restart.
- Throttle (50% below a 300 °C setpoint) costs ~15 min on a FAST climb. It's there for the candle, so
  leave it unless the time matters.
- HA's `Kiln refresh rate during run` automation logs a "While condition … looped 5000 times" warning
  (2 s × 5000 ≈ 2.8 h) during long firings. Worth checking whether the 2 s refresh stops there. The
  20 s REST poll carries on either way.
- v2 recommender: shift or flag using Solcast `forecast_tomorrow` and Amber price forecasts.
