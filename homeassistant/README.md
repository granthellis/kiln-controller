# Kiln Controller — Home Assistant integration

A proper custom integration for [kiln-controller](https://github.com/jbruce12000/kiln-controller),
replacing the old `rest:` sensors and `rest` switch in `configuration.yaml`.

It exposes a single **Kiln Controller** device with:

| Entity | Type | Notes |
|--------|------|-------|
| Temperature | sensor | °C/°F follows the kiln's `temp_scale` |
| Target temperature | sensor | live setpoint |
| State | sensor | `IDLE` / `RUNNING` |
| Profile | sensor | name of the active profile |
| Cost | sensor | monetary, uses the kiln's currency symbol |
| kWh rate | sensor | current (peak/off-peak) rate |
| Heat | sensor | element duty (0–1) |
| Runtime / Total time | sensor | duration |
| **Time remaining** | sensor | duration, plus an `hh_mm` attribute (e.g. `1:45`) |
| **Projected finish** | sensor | timestamp, shown in your local time |
| **Projected target** | sensor | state = live target; `forecast` attribute = full projected target curve |
| **Run** | switch | runs the selected profile / stops the kiln |
| **Profile** | select | synced list of stored kiln profiles |
| **Start at** | number | minutes into the profile to begin (for restarts) |

## Requirements

This integration relies on two endpoints added to kiln-controller:

- `GET /api/status` now also returns `temp_scale`, and while running `start_time`,
  `time_remaining`, and `profile_data`.
- `GET /api/profiles` returns the list of stored profiles.

Run a kiln-controller build that includes these (this repo's current version).

## Install

1. Copy `custom_components/kiln_controller/` into your Home Assistant
   `config/custom_components/` directory (or install via HACS as a custom repo).
2. Restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Kiln Controller**.
4. Enter the kiln-controller **host** (e.g. `192.168.1.124`) and **port** (`8081`).

The update interval defaults to 10 s and can be changed via the integration's
**Configure** (options) dialog.

## Starting a firing

1. Set **Profile** (select) to the schedule you want.
2. Optionally set **Start at** (number) to skip into the profile (minutes).
3. Turn the **Run** switch on. Turn it off to stop.

## Migrating from the YAML setup

Remove the old `rest:` sensor block and the `switch: - platform: rest` block from
`configuration.yaml`, along with the `input_select.kiln_switch_schedule` and
`input_number.kiln_switch_start_at` helpers — the **Profile** select and **Start at**
number replace them.

Entity IDs change (e.g. `sensor.kiln_temp` → `sensor.kiln_controller_temperature`).
Update any dashboards or automations that referenced the old IDs.

## Charting the projected target curve

The **Projected target** sensor carries a `forecast` attribute — a list of
`{datetime, temperature}` points spanning the whole run — so you can plot the
planned target line against the actual temperature. Example with
[apexcharts-card](https://github.com/RomRider/apexcharts-card):

```yaml
type: custom:apexcharts-card
graph_span: 12h
header:
  show: true
  title: Kiln firing
series:
  - entity: sensor.kiln_controller_temperature
    name: Actual
  - entity: sensor.kiln_controller_projected_target
    name: Projected target
    data_generator: |
      return (entity.attributes.forecast || []).map(p => {
        return [new Date(p.datetime).getTime(), p.temperature];
      });
```
