"""Candle and peak holds set per firing (docs/candle-and-peak-holds.md).

D-numbers refer to the decisions table in that document.
"""
import glob
import json
import os

import pytest

import config
from holds import (HoldError, find_peak_hold, keep_markers, phase_at,
                       split_candle)
from lib.oven import Profile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# cone 6 FAST as stored before the migration: candle 25->121 over 96 min,
# hold 60 min, then the firing (peak hold 1195 C for 20 min, drop soak).
CONE6_FAST = [[0, 25], [5760, 121], [9360, 121], [12960, 1138],
              [14760, 1138], [18180, 1195], [19380, 1195], [19740, 1138],
              [21540, 1138]]
# its body: the same firing, starting at the candle temperature
CONE6_BODY = [[0, 121], [3600, 1138], [5400, 1138], [8820, 1195],
              [10020, 1195], [10380, 1138], [12180, 1138]]
# fast glaze: no candle, ends at its peak (no flat top)
BRTF6 = [[0, 25], [12000, 1083], [16500, 1222]]

RAMP_S = round((121 - 25) / 170 * 3600)   # 2033 s: 25->121 C at 170 C/h


def profile(data, candle=False, **kw):
    obj = {'name': 't', 'data': data}
    if candle:
        obj['candle'] = True
    return Profile(json.dumps(obj), **kw)


def unchanged_up_to(old, new, runtime):
    """True if the target curve up to and including `runtime` is identical
    (D7): a live change may add a point at `runtime`, never move the past."""
    before = Profile(json.dumps({'name': 'old', 'data': old}))
    after = Profile(json.dumps({'name': 'new', 'data': new}))
    times = list(range(0, int(runtime), 30)) + [runtime]
    return all(before.get_target_temperature(t) == after.get_target_temperature(t)
               for t in times)


# ── composition (D2, D3, D6) ──

def test_candle_is_prepended_with_default_hold():
    p = profile(CONE6_BODY, candle=True)
    end = RAMP_S + 3600
    assert p.data[:3] == [[0, config.candle_start_temp], [RAMP_S, 121], [end, 121]]
    assert p.data[3:] == [[t + end, x] for t, x in CONE6_BODY[1:]]
    c = p.holds['candle']
    assert (c['temp'], c['hold_min'], c['start_s'], c['end_s']) == (121, 60, RAMP_S, end)


def test_candle_ramp_takes_about_half_an_hour_to_120():
    p = profile([[0, 120], [3600, 1000]], candle=True)
    assert 30 * 60 <= p.holds['candle']['start_s'] <= 35 * 60


def test_candle_hold_is_set_per_firing():
    p = profile(CONE6_BODY, candle=True, candle_min=180)
    assert p.holds['candle']['end_s'] == RAMP_S + 180 * 60
    assert p.get_duration() == RAMP_S + 180 * 60 + CONE6_BODY[-1][0]


def test_candle_hold_zero_ramps_straight_into_the_firing():
    p = profile(CONE6_BODY, candle=True, candle_min=0)
    assert p.data[:3] == [[0, config.candle_start_temp], [RAMP_S, 121],
                          [RAMP_S + 3600, 1138]]
    assert len({t for t, _ in p.data}) == len(p.data)   # no zero-length segment


def test_schedule_without_marker_runs_unchanged():
    p = profile(CONE6_FAST, candle_min=180)
    assert p.data == CONE6_FAST
    assert p.holds['candle'] is None


@pytest.mark.parametrize('kw', [{'candle_min': -1},
                                {'candle_min': config.candle_hold_max_min + 1},
                                {'peak_extra_min': -5},
                                {'peak_extra_min': config.peak_extra_max_min + 1}])
def test_out_of_range_hold_is_refused(kw):
    with pytest.raises(HoldError):
        profile(CONE6_BODY, candle=True, **kw)


def test_candle_body_must_start_at_time_zero():
    with pytest.raises(HoldError):
        profile([[60, 121], [3600, 1000]], candle=True)


def test_empty_schedule_still_loads():
    assert profile([]).holds == {'candle': None, 'peak': None}


# ── peak hold (D5) ──

def test_peak_hold_is_the_first_flat_segment_at_the_top():
    assert find_peak_hold(CONE6_FAST) == (5, 6)


def test_peak_touched_without_a_hold():
    assert find_peak_hold(BRTF6) == (2, 2)


def test_peak_extra_extends_the_top_hold_and_shifts_the_rest():
    p = profile(CONE6_FAST, peak_extra_min=30)
    assert p.data[:6] == CONE6_FAST[:6]
    assert p.data[6:] == [[t + 1800, x] for t, x in CONE6_FAST[6:]]
    pk = p.holds['peak']
    assert (pk['temp'], pk['default_min'], pk['hold_min'], pk['extra_min']) == (1195, 20, 50, 30)
    assert (pk['start_s'], pk['end_s']) == (18180, 19380 + 1800)


def test_peak_extra_inserts_a_hold_where_the_schedule_has_none():
    p = profile(BRTF6, peak_extra_min=15)
    assert p.data == BRTF6 + [[16500 + 900, 1222]]
    assert p.holds['peak']['default_min'] == 0


def test_peak_and_candle_compose_together():
    p = profile(CONE6_BODY, candle=True, candle_min=120, peak_extra_min=10)
    end = RAMP_S + 7200
    assert p.holds['peak']['start_s'] == end + 8820
    assert p.holds['peak']['end_s'] == end + 10020 + 600


# ── phase (D9) ──

def test_phase_follows_the_composed_run():
    p = profile(CONE6_BODY, candle=True)
    h, end = p.holds, RAMP_S + 3600
    assert phase_at(h, 0) == 'candle'
    assert phase_at(h, end - 1) == 'candle'
    assert phase_at(h, end) == 'firing'
    assert phase_at(h, end + 9000) == 'peak_hold'
    assert phase_at(h, end + 10020) == 'after_peak'


def test_phase_without_candle_starts_firing():
    assert phase_at(profile(CONE6_FAST).holds, 0) == 'firing'


# ── live changes (D7) ──

def test_extend_candle_during_its_hold_moves_only_the_future():
    p = profile(CONE6_BODY, candle=True)
    old, runtime = [list(x) for x in p.data], RAMP_S + 3000
    before = p.get_target_temperature(runtime)
    p.extend_hold('candle', 60, runtime)
    assert unchanged_up_to(old, p.data, runtime)
    assert p.get_target_temperature(runtime) == before
    assert p.holds['candle']['hold_min'] == 120
    assert p.get_duration() == old[-1][0] + 3600


def test_extend_candle_while_still_ramping():
    p = profile(CONE6_BODY, candle=True)
    p.extend_hold('candle', 30, 600)
    assert p.holds['candle']['hold_min'] == 90


def test_extend_candle_after_it_ended_is_refused():
    p = profile(CONE6_BODY, candle=True)
    with pytest.raises(HoldError):
        p.extend_hold('candle', 30, RAMP_S + 3600)


def test_extend_candle_on_a_schedule_without_one_is_refused():
    with pytest.raises(HoldError):
        profile(CONE6_FAST).extend_hold('candle', 30, 0)


@pytest.mark.parametrize('add', [0, -10])
def test_extend_needs_a_positive_amount(add):
    with pytest.raises(HoldError):
        profile(CONE6_BODY, candle=True).extend_hold('candle', add, 0)


def test_candle_extension_is_capped():
    p = profile(CONE6_BODY, candle=True, candle_min=config.candle_hold_max_min - 10)
    with pytest.raises(HoldError):
        p.extend_hold('candle', 30, 0)


def test_end_candle_now_starts_the_firing_at_the_current_runtime():
    p = profile(CONE6_BODY, candle=True, candle_min=180)
    old, runtime = [list(x) for x in p.data], RAMP_S + 1800
    p.end_candle(runtime)
    assert unchanged_up_to(old, p.data, runtime)
    assert p.holds['candle']['end_s'] == runtime
    assert p.get_target_temperature(runtime) == 121
    assert p.get_target_slope(runtime + 1) > 0
    assert phase_at(p.holds, runtime) == 'firing'


def test_end_candle_while_ramping_drops_the_hold():
    p = profile(CONE6_BODY, candle=True)
    p.end_candle(600)
    assert p.holds['candle']['hold_min'] == 0
    assert p.holds['candle']['end_s'] == RAMP_S


def test_end_candle_after_it_ended_is_refused():
    with pytest.raises(HoldError):
        profile(CONE6_BODY, candle=True).end_candle(RAMP_S + 3600)


def test_extend_peak_during_the_peak_hold():
    p = profile(CONE6_FAST)
    old, runtime = [list(x) for x in p.data], 18900
    p.extend_hold('peak', 15, runtime)
    assert unchanged_up_to(old, p.data, runtime)
    assert p.get_target_temperature(runtime) == 1195
    assert p.holds['peak']['extra_min'] == 15


def test_extend_peak_before_reaching_it():
    p = profile(CONE6_FAST)
    p.extend_hold('peak', 30, 1000)
    assert p.holds['peak']['hold_min'] == 50


def test_extend_peak_after_it_is_refused():
    with pytest.raises(HoldError):
        profile(CONE6_FAST).extend_hold('peak', 15, 19380)


def test_peak_extension_is_capped_in_total():
    p = profile(CONE6_FAST, peak_extra_min=config.peak_extra_max_min - 10)
    with pytest.raises(HoldError):
        p.extend_hold('peak', 15, 0)


def test_unknown_hold_is_refused():
    with pytest.raises(HoldError):
        profile(CONE6_FAST).extend_hold('bisque', 15, 0)


# ── restart (D8) ──

def test_restart_rebuilds_the_same_curve_after_live_changes():
    p = profile(CONE6_BODY, candle=True, candle_min=90)
    p.extend_hold('candle', 45, 1000)
    p.end_candle(RAMP_S + 4000)
    p.extend_hold('peak', 25, RAMP_S + 5000)
    h = p.holds
    again = profile(CONE6_BODY, candle=True, candle_min=h['candle']['hold_min'],
                    peak_extra_min=h['peak']['extra_min'])
    assert again.data == p.data


def test_seek_on_a_warm_kiln_lands_on_the_candle_ramp():
    p = profile(CONE6_BODY, candle=True)
    t = p.find_next_time_from_temperature(60)
    assert 0 < t < RAMP_S
    assert p.get_target_temperature(t) == pytest.approx(60)


# ── migration (D2, D4) and the web-UI save (D10) ──

def test_split_candle_extracts_the_body():
    obj, old_candle_s = split_candle({'name': 'x', 'type': 'profile', 'data': CONE6_FAST})
    assert obj == {'name': 'x', 'type': 'profile', 'data': CONE6_BODY, 'candle': True}
    assert old_candle_s == 9360


def test_migrated_schedule_fires_the_same_after_the_candle():
    obj, old_candle_s = split_candle({'name': 'x', 'data': CONE6_FAST})
    p = profile(obj['data'], candle=True)
    new_end = p.holds['candle']['end_s']
    assert [[t - new_end, x] for t, x in p.data if t >= new_end] == \
           [[t - old_candle_s, x] for t, x in CONE6_FAST if t >= old_candle_s]


@pytest.mark.parametrize('data', [
    [[0, 25], [3600, 120], [14400, 120]],                     # 4hr dry: candle only
    BRTF6,                                                    # no candle
    [[0, 25], [4200, 121], [19740, 1083], [27240, 1222]],     # ramp, no hold
    [[0, 20], [3600, 120], [15480, 1110], [19680, 1110]],     # SiC: no hold at 120
    [[0, 65], [600, 200], [2088, 250], [5688, 250]],          # hold at 250, not a candle
])
def test_split_candle_leaves_other_schedules_alone(data):
    assert split_candle({'name': 'x', 'data': data}) == (None, 0)


def test_split_candle_is_idempotent():
    obj, _ = split_candle({'name': 'x', 'data': CONE6_FAST})
    assert split_candle(obj) == (None, 0)


def test_every_stored_schedule_still_loads_after_migration():
    for path in glob.glob(os.path.join(ROOT, 'storage', 'profiles', '*.json')):
        with open(path) as f:
            obj = json.load(f)
        migrated, _ = split_candle(obj)
        obj = migrated or obj
        if not obj['data']:
            continue
        p = Profile(json.dumps(obj), candle_min=180, peak_extra_min=30)
        times = [t for t, _ in p.data]
        assert times == sorted(times) and len(set(times)) == len(times), path


def test_editor_save_keeps_the_candle_marker():
    incoming = {'type': 'profile', 'name': 'x', 'data': CONE6_BODY}
    existing = {'type': 'profile', 'name': 'x', 'data': CONE6_BODY, 'candle': True}
    assert keep_markers(incoming, existing)['candle'] is True
    assert 'candle' not in keep_markers(incoming, None)
