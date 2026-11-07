"""Schedule catch-up and low-temperature PID behaviour (2026-11-08).

The closed-loop tests drive the real PID class and catch-up rule against a
plant fitted to the 2026-11-08 cone 6 firing (08:30-10:06 AEDT, 14->95 C,
0.37 C RMS open-loop fit): one lumped thermal mass, almost no loss, seen by
the thermocouple through a 191 s first-order lag and a 19 s delay, read in
0.25 C steps every 2 s. The same plant with the old rules reproduces that
morning: overshoot to ~39 C (real 37.9), a schedule stall of ~38 min (real
30) and a +-4 C limit cycle on the 1 C/min ramp.
"""
import datetime
import json
import math

import pytest

import config
from lib.oven import PID, Oven, Profile

PMAX_KW = 4.8          # new elements, 231 V
C_KJ_PER_K = 17.743    # element + kiln lumped heat capacity
LOSS_KW_PER_K = 0.003071
TC_LAG_S = 190.8
TC_DELAY_STEPS = 9     # 18.7 s at 2 s steps
AMBIENT = 14.4
DT = 2.0

TODAY = [[0, 25], [5760, 121], [9360, 121], [12960, 1141]]
DRY = [[0, 25], [3600, 120], [21600, 120]]


class Plant:
    def __init__(self, T0=AMBIENT, gain=1.0, lag=1.0, loss=1.0):
        self.T = T0
        self.tc = T0
        self.buf = [T0] * TC_DELAY_STEPS
        self.C = C_KJ_PER_K / gain
        self.k = LOSS_KW_PER_K * loss
        self.ts = TC_LAG_S * lag
        self.delay = max(1, round(TC_DELAY_STEPS * lag))
        self.buf = [T0] * self.delay

    def step(self, duty):
        p = PMAX_KW * min(max(duty, 0.0), 1.0)
        self.T += (p - self.k * (self.T - AMBIENT)) / self.C * DT
        self.buf.append(self.T)
        delayed = self.buf.pop(0)
        self.tc += (delayed - self.tc) / self.ts * DT
        return round(self.tc * 4) / 4   # MAX31855 resolution


def fly(profile_data, plant, old_rules=False, duration=None, monkeypatch=None):
    """Run the oven loop (catch-up -> runtime -> target -> PID) at 2 s steps.
    Returns (schedule lag in minutes, list of (wall s, target, temp))."""
    profile = Profile(json.dumps({'name': 't', 'data': profile_data}))
    pid = PID(ki=config.pid_ki, kd=config.pid_kd, kp=config.pid_kp)
    now = datetime.datetime(2026, 11, 8, 8, 30)
    pid.lastNow = now
    runtime, wall, temp = 0.0, 0.0, plant.tc
    target = profile.get_target_temperature(0)
    trace = []
    duration = duration or profile.get_duration()
    while runtime < profile.get_duration() and wall < duration:
        if old_rules:
            wait = abs(target - temp) > config.pid_control_window
        else:
            wait = Oven.schedule_must_wait(target, temp, profile.get_target_slope(runtime))
        if not wait:
            runtime += DT
            if runtime >= profile.get_duration():
                break
        target = profile.get_target_temperature(runtime)
        now += datetime.timedelta(seconds=DT)
        duty = pid.compute(target, temp, now)
        temp = plant.step(duty)
        wall += DT
        trace.append((wall, target, temp))
    return (wall - runtime) / 60, trace


def rms(trace, after_s):
    errs = [t - s for (w, s, t) in trace if w >= after_s]
    return math.sqrt(sum(e * e for e in errs) / len(errs)), max(abs(e) for e in errs)


@pytest.fixture
def legacy_pid(monkeypatch):
    monkeypatch.setattr(config, 'pid_ki_low', None, raising=False)
    monkeypatch.setattr(config, 'pid_derivative_window', 0, raising=False)


# ---- schedule catch-up --------------------------------------------------

@pytest.mark.parametrize('target,temp,slope,wait', [
    (28.8, 37.9, +0.0167, False),  # ahead on a rising ramp: keep running (2026-11-08)
    (100, 90, +0.0167, True),      # behind on a rising ramp: wait (max heating)
    (1150, 1170, -0.1, True),      # behind on a drop: wait (fall as fast as it can)
    (700, 680, -0.05, False),      # ahead on a slow cool: keep running
    (121, 110, 0.0, True),         # below a hold: wait, hold time counts at temp
    (121, 130, 0.0, False),        # above a hold: keep running
    (100, 104, +0.0167, False),    # inside the window: never wait
    (100, 96, -0.1, False),
])
def test_schedule_waits_only_when_behind(target, temp, slope, wait):
    assert Oven.schedule_must_wait(target, temp, slope) is wait


def test_target_slope():
    p = Profile(json.dumps({'name': 't', 'data': TODAY}))
    assert p.get_target_slope(0) == pytest.approx(96 / 5760)
    assert p.get_target_slope(6000) == 0.0           # hold
    p2 = Profile(json.dumps({'name': 't', 'data': [[0, 1195], [360, 1138], [2160, 1138]]}))
    assert p2.get_target_slope(100) == pytest.approx(-57 / 360)
    assert p2.get_target_slope(5000) == 0.0          # past the end


def test_overshoot_on_slow_ramp_no_longer_stalls_schedule(legacy_pid):
    old_lag, _ = fly(TODAY, Plant(), old_rules=True, duration=5760)
    new_lag, _ = fly(TODAY, Plant(), duration=5760)
    assert old_lag > 20     # reproduces the 2026-11-08 stall
    assert new_lag < 5


# ---- PID -----------------------------------------------------------------

def test_low_temp_ki_switch(monkeypatch):
    monkeypatch.setattr(config, 'pid_ki_low', 48, raising=False)
    monkeypatch.setattr(config, 'pid_low_temp_below', 200, raising=False)
    pid = PID(ki=16, kp=12, kd=275)
    assert pid.ki_for(120) == 48
    assert pid.ki_for(200) == 48
    assert pid.ki_for(201) == 16
    monkeypatch.setattr(config, 'pid_ki_low', None)
    assert pid.ki_for(120) == 16


def test_derivative_ignores_single_quantisation_step(monkeypatch):
    monkeypatch.setattr(config, 'pid_derivative_window', 30, raising=False)
    pid = PID(ki=16, kp=12.48, kd=275)
    now = datetime.datetime(2026, 11, 8, 9, 0)
    pid.lastNow = now
    for i in range(15):
        now += datetime.timedelta(seconds=2)
        pid.compute(100, 100.0, now)
    now += datetime.timedelta(seconds=2)
    pid.compute(100, 100.25, now)
    # raw differencing: 275 * 0.25 / 2 = 34 output units; filtered: a few
    assert abs(pid.pidstats['d']) < 5


def test_derivative_keeps_ramp_feedforward(monkeypatch):
    monkeypatch.setattr(config, 'pid_derivative_window', 30, raising=False)
    pid = PID(ki=16, kp=12.48, kd=275)
    now = datetime.datetime(2026, 11, 8, 9, 0)
    pid.lastNow = now
    sp = 500.0
    for i in range(20):   # 150 C/h ramp, kiln momentarily flat
        now += datetime.timedelta(seconds=2)
        sp += 150 / 3600 * 2
        pid.compute(sp, 500.0, now)
    # same feed-forward the raw error difference gave: kd * dSP/dt
    assert pid.pidstats['d'] == pytest.approx(275 * 150 / 3600, rel=1e-6)


@pytest.mark.parametrize('profile,T0,duration', [(TODAY, 14.4, 9360), (DRY, 21.0, 21600)],
                         ids=['1C-per-min-ramp-and-121-hold', '5hr-dry'])
def test_low_temp_tracking(profile, T0, duration, legacy_pid, monkeypatch):
    _, old = fly(profile, Plant(T0), duration=duration)
    monkeypatch.setattr(config, 'pid_ki_low', 48)
    monkeypatch.setattr(config, 'pid_low_temp_below', 200, raising=False)
    monkeypatch.setattr(config, 'pid_derivative_window', 30)
    lag, new = fly(profile, Plant(T0), duration=duration)
    old_rms, _ = rms(old, 3600)
    new_rms, new_pk = rms(new, 3600)
    assert old_rms > 1.0               # the limit cycle the operator saw
    assert new_rms < 0.5 and new_pk < 3.0
    assert lag < 5


@pytest.mark.parametrize('variant', [dict(gain=1.5), dict(gain=0.6), dict(lag=1.6),
                                     dict(lag=0.6), dict(loss=0.3)],
                         ids=['gain1.5', 'gain0.6', 'lag1.6', 'lag0.6', 'soaked-walls'])
def test_low_temp_tuning_is_robust_to_model_error(variant, monkeypatch):
    """A 120 C hold whose swing grew over 3 h (2026-11-05) is what a marginal
    loop does as the plant drifts; the new tuning must hold with the kiln's
    gain, lag or loss off by a wide margin."""
    monkeypatch.setattr(config, 'pid_ki_low', 48, raising=False)
    monkeypatch.setattr(config, 'pid_low_temp_below', 200, raising=False)
    monkeypatch.setattr(config, 'pid_derivative_window', 30, raising=False)
    _, trace = fly(DRY, Plant(21.0, **variant), duration=21600)
    r, pk = rms(trace, 3600)
    # worst peak is the corner from the 1.6 C/min ramp into the hold
    assert r < 1.0 and pk < 5.0
    # and the hold itself settles: last 3 h within the control window
    _, late_pk = rms(trace, 3600 * 3)
    assert late_pk < 2.0
