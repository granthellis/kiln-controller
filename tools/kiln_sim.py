"""Heat-balance kiln simulator, fitted to the 18 Sep 2026 cone 6 FAST firing.

Model: C dT/dt = P - a (T - 20)^n. The controller logic mirrors lib/oven.py:
catch-up (full power, schedule clock paused) outside the 5 C window, and a 50%
throttle below a 300 C setpoint. Fitted values are in simfit-2026-09-18.json
(n 1.4, C 30 kJ/K, loss 2.6 kW at 1138 C). It reproduces that firing to
7.65 h / 19.0 kWh (measured 7.62 h / 19.2 kWh), 0.4 kW RMS per 15 min.

Inputs (from the working directory): f18_sensor.kiln_energy_energy_a_value.jsonl
(VictoriaMetrics /api/v1/export of the energy counter for the firing) and
profiles_now.json (GET /api/profiles). Run: uv run --with numpy python kiln_sim.py
"""
import json,bisect
from datetime import datetime
import numpy as np
E=sorted((t/1000,v) for l in open('f18_sensor.kiln_energy_energy_a_value.jsonl') for d in [json.loads(l)] for t,v in zip(d['timestamps'],d['values']))
t0=datetime.fromisoformat('2026-09-18T06:00:01+10:00').timestamp(); t1=datetime.fromisoformat('2026-09-18T13:37:10+10:00').timestamp()
et=[e[0] for e in E]
def eat(t):
    i=max(bisect.bisect_right(et,t)-1,0)
    if i+1<len(E):
        (a,va),(b,vb)=E[i],E[i+1]; return va+(vb-va)*(t-a)/(b-a) if b>a else va
    return E[i][1]
meas=[]; t=t0
while t<t1:
    meas.append((eat(min(t+900,t1))-eat(t))*3600/ (min(t+900,t1)-t)); t+=900
meas=np.array(meas)
profiles={p['name']:p['data'] for p in json.load(open('profiles_now.json')) if p.get('data')}
def sim(data,a,n,C,Pmax=4.75,dt=30.0,window=5,T0=None):
    ts=[x[0] for x in data]; vs=[x[1] for x in data]
    def sp(s):
        if s>=ts[-1]: return None
        i=bisect.bisect_right(ts,s)-1; return vs[i]+(vs[i+1]-vs[i])*(s-ts[i])/(ts[i+1]-ts[i])
    T=vs[0]-2 if T0 is None else T0; s=0; t=0; P=[]
    while True:
        target=sp(s)
        if target is None: break
        L=a*max(T-20,0)**n
        pm=Pmax*(0.5 if target<300 else 1)
        if T<target-window:
            p=pm; s_adv=0
        else:
            nxt=sp(s+dt); rate=((nxt if nxt is not None else target)-target)/dt
            need=L+C*(rate+(target-T)/300)   # track with a 5-min correction
            p=min(max(need,0),pm); s_adv=dt
        T+= (p*1000-L*1000)/C/1000*dt if False else (p-L)*1000*dt/(C*1000)
        s+=s_adv; t+=dt; P.append(p)
        if t>30*3600: break
    P=np.array(P); k=int(900/dt)
    slots=[P[i:i+k].mean() for i in range(0,len(P),k)]
    return np.array(slots), t/3600
if __name__=='__main__':
    d=profiles['cone 6 - Tony Hansen drop soak FAST']
    best=None
    for n in [1.0,1.2,1.4,1.6,1.8,2.0]:
      for C in [18,22,26,30,35,40]:
        for L1138 in [2.4,2.6,2.8,3.0,3.2]:
          a=L1138/(1118**n)
          sl,dur=sim(d,a,n,C)
          m=min(len(sl),len(meas)); err=np.sqrt(np.mean((sl[:m]-meas[:m])**2))+abs(dur-7.62)*0.5
          if best is None or err<best[0]: best=(err,n,C,a,dur,sl)
    err,n,C,a,dur,sl=best
    print('best n',n,'C kJ/K',C,'a',a,'L1138',a*1118**n,'dur',dur,'err',err)
    print('meas',np.round(meas,1).tolist()); print('sim ',np.round(sl,1).tolist())
    print('kWh meas',meas.sum()/4,'sim',sl.sum()/4)
    json.dump({'a':a,'n':n,'C':C},open('simfit.json','w'))
