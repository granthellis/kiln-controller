"""Cost a kiln run from HA recorder history with the same marginal attribution
as sensor.kiln_run_energy_cost. Prints JSON: kWh/$ per source + hot hours.

usage: cost_backfill.py START_ISO END_ISO
Needs HA_URL / HA_TOKEN in the environment (source nas.env); never printed.
"""

import bisect
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

ENT = {
    "e": "sensor.kiln_energy_energy_a",
    "k": "sensor.kiln_energy_power_a",
    "g": "sensor.elektrobank_14_grid_power",
    "b": "sensor.elektrobank_14_battery_power",
    "imp": "sensor.home_general_price",
    "bat": "input_number.battery_charge_cost",
    "fi": "sensor.home_feed_in_price",
    "st": "sensor.kiln_state",
    "t": "sensor.kiln_temp",
}


def history(start, end):
    q = urllib.parse.urlencode(
        {"filter_entity_id": ",".join(ENT.values()), "end_time": end, "minimal_response": "", "no_attributes": ""}
    )
    url = f"{os.environ['HA_URL']}/api/history/period/{urllib.parse.quote(start)}?{q}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {os.environ['HA_TOKEN']}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        if r.status in (401, 403):
            sys.exit("STOP: auth rejected")
        data = json.load(r)
    out = {}
    for series in data:
        eid = series[0]["entity_id"]
        key = [k for k, v in ENT.items() if v == eid][0]
        ts, vs = [], []
        for s in series:
            t = dt.datetime.fromisoformat(s.get("last_changed") or s["last_updated"]).timestamp()
            ts.append(t)
            vs.append(s["state"])
        out[key] = (ts, vs)
    return out


def at(h, key, t, num=True):
    ts, vs = h[key]
    i = bisect.bisect_right(ts, t) - 1
    if i < 0:
        return 0.0 if num else ""
    v = vs[i]
    if not num:
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main():
    start, end = sys.argv[1], sys.argv[2]
    h = history(start, end)
    acc = dict(kwh=0, grid_kwh=0, grid_cost=0, battery_kwh=0, battery_cost=0, solar_kwh=0, solar_cost=0)
    ets, evs = h["e"]
    last = None
    for t, v in zip(ets, evs):
        try:
            e = float(v)
        except (TypeError, ValueError):
            continue
        if last is not None and at(h, "st", t - 1, num=False) == "RUNNING" and 0 <= e - last < 10:
            de = e - last
            k = at(h, "k", t) / 1000
            kk = k if k > 0.1 else 1.0
            g = max(at(h, "g", t) / 1000, 0)
            b = max(-at(h, "b", t) / 1000, 0)
            fg = min(kk, g) / kk
            fb = min(kk - min(kk, g), b) / kk
            fs = 1 - fg - fb
            acc["kwh"] += de
            acc["grid_kwh"] += de * fg
            acc["grid_cost"] += de * fg * at(h, "imp", t)
            acc["battery_kwh"] += de * fb
            acc["battery_cost"] += de * fb * at(h, "bat", t)
            acc["solar_kwh"] += de * fs
            acc["solar_cost"] += de * fs * max(at(h, "fi", t), 0)
        last = e
    # hot hours: temp > 1000 while RUNNING, stepped over temp samples
    tts, tvs = h["t"]
    hot = 0.0
    for i in range(1, len(tts)):
        try:
            temp = float(tvs[i - 1])
        except (TypeError, ValueError):
            continue
        if temp > 1000 and at(h, "st", tts[i - 1], num=False) == "RUNNING":
            hot += tts[i] - tts[i - 1]
    acc = {k: round(v, 4) for k, v in acc.items()}
    acc["energy_cost"] = round(acc["grid_cost"] + acc["battery_cost"] + acc["solar_cost"], 4)
    acc["hot_h"] = round(hot / 3600, 2)
    acc["counter_first_last"] = [evs[0], evs[-1]] if evs else None
    print(json.dumps(acc))


if __name__ == "__main__":
    main()
