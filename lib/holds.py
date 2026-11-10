"""Candle and peak holds, set per firing (docs/candle-and-peak-holds.md).

Pure functions - no hardware or config imports - so the composition rules can
be tested off the Pi. lib/oven.py's Profile wraps them.

A schedule marked ``"candle": true`` stores only its *body*: the firing,
starting at ``[0, T]`` where T is the candle temperature. At run time the
candle is prepended: ``[0, start_temp]`` -> ramp at ``rate`` C/h to T -> hold.

The peak hold is not marked: it is the first flat segment at the schedule's
maximum temperature (zero-length if the schedule only touches its peak).
Extra peak minutes lengthen it and shift everything after it.
"""

PHASES = ('candle', 'firing', 'peak_hold', 'after_peak')

# migration: what a built-in candle looks like in a pre-2026-11-11 schedule
_AMBIENT_MAX = 40
_CANDLE_TEMP_RANGE = (90, 130)


class HoldError(ValueError):
    """A hold setting or live change that the controller refuses."""


def find_peak_hold(data):
    """(first, last) index of the peak hold in ``data``.

    first = the first point at the maximum temperature; last = the end of the
    flat segment that starts there (== first if the schedule only touches it).
    """
    top = max(x for _, x in data)
    first = next(i for i, (_, x) in enumerate(data) if x == top)
    last = first
    while last + 1 < len(data) and data[last + 1][1] == top:
        last += 1
    return first, last


def _extend_peak(data, extra_s):
    """``data`` with the peak hold lengthened by ``extra_s``, plus peak info."""
    first, last = find_peak_hold(data)
    t_start, top = data[first]
    t_end = data[last][0]
    default_s = t_end - t_start
    if extra_s > 0:
        out = [list(p) for p in data[:last]]
        if last == first:
            out.append(list(data[first]))
        out.append([t_end + extra_s, top])
        out += [[t + extra_s, x] for t, x in data[last + 1:]]
    else:
        out = [list(p) for p in data]
    peak = {'temp': top, 'default_s': default_s, 'extra_s': extra_s,
            'start_s': t_start, 'end_s': t_end + extra_s}
    return out, peak


def compose(body, candle, candle_hold_s, peak_extra_s, start_temp, rate):
    """Compose the run curve.

    Returns ``(data, holds)``; ``holds`` is ``{'candle': ..., 'peak': ...}``
    with times in seconds of the composed run (None where not applicable).
    """
    if len(body) < 2:
        return [list(p) for p in body], {'candle': None, 'peak': None}

    data, peak = _extend_peak(body, peak_extra_s)
    if not candle:
        return data, {'candle': None, 'peak': peak}

    temp = data[0][1]
    ramp_s = round(max(temp - start_temp, 0) / rate * 3600)
    end_s = ramp_s + candle_hold_s
    prefix = [[0, start_temp]] if ramp_s > 0 else []
    prefix.append([ramp_s, temp])
    if candle_hold_s > 0:
        prefix.append([end_s, temp])
    data = prefix + [[t + end_s, x] for t, x in data[1:]]
    peak = dict(peak, start_s=peak['start_s'] + end_s, end_s=peak['end_s'] + end_s)
    cand = {'temp': temp, 'rate': rate, 'hold_s': candle_hold_s,
            'start_s': ramp_s, 'end_s': end_s}
    return data, {'candle': cand, 'peak': peak}


def report(holds):
    """``holds`` in minutes for /api/status, the state file and HA."""
    out = {'candle': None, 'peak': None}
    c, p = holds['candle'], holds['peak']
    if c:
        out['candle'] = {'temp': c['temp'], 'rate': c['rate'],
                         'hold_min': round(c['hold_s'] / 60, 3),
                         'start_s': c['start_s'], 'end_s': c['end_s']}
    if p:
        out['peak'] = {'temp': p['temp'],
                       'default_min': round(p['default_s'] / 60, 3),
                       'extra_min': round(p['extra_s'] / 60, 3),
                       'hold_min': round((p['default_s'] + p['extra_s']) / 60, 3),
                       'start_s': p['start_s'], 'end_s': p['end_s']}
    return out


def phase_at(holds, runtime):
    """Which part of the run ``runtime`` (s) falls in."""
    c, p = holds.get('candle'), holds.get('peak')
    if c and runtime < c['end_s']:
        return 'candle'
    if p and runtime >= p['end_s']:
        return 'after_peak'
    if p and runtime >= p['start_s'] and p['end_s'] > p['start_s']:
        return 'peak_hold'
    return 'firing'


def split_candle(obj):
    """Migrate a schedule with a built-in candle to body + marker.

    A built-in candle is: start at ambient (<= 40 C), ramp to 90-130 C, hold
    there, then more schedule. Returns ``(new_obj, old_candle_s)``, or
    ``(None, 0)`` when the schedule is left alone (already migrated, no
    candle, a ramp without a hold, or a candle-only drying schedule).
    """
    if obj.get('candle'):
        return None, 0
    data = sorted(obj.get('data') or [])
    if len(data) < 4:
        return None, 0
    (_, t0), (t1, temp), (t2, temp2) = data[0], data[1], data[2]
    lo, hi = _CANDLE_TEMP_RANGE
    if not (t0 <= _AMBIENT_MAX and lo <= temp <= hi and temp2 == temp and t2 > t1):
        return None, 0
    body = [[0, temp]] + [[t - t2, x] for t, x in data[3:]]
    new = dict(obj, data=body, candle=True)
    return new, t2


def keep_markers(incoming, existing):
    """The web-UI editor saves only {type, data, name}; keep the existing
    file's candle marker when it overwrites a schedule (D10)."""
    out = dict(incoming)
    if existing and existing.get('candle') and 'candle' not in out:
        out['candle'] = True
    return out
