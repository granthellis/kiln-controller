import json, numpy as np
from sim import sim, profiles, meas
f=json.load(open('simfit.json'))
opts=json.load(open('select_update2.json'))['options']
out={}
for p in opts:
    if p not in profiles: print('missing',p); continue
    if p=='cone 6 - Tony Hansen drop soak FAST':
        sl=meas
    else:
        sl,_=sim(profiles[p],f['a'],f['n'],f['C'])
    out[p]=[round(float(x),1) for x in sl]
    print(f"{p:42s} {len(sl)/4:5.2f} h {sum(sl)/4:5.1f} kWh  peak-2h kWh {max(sum(sl[i:i+8])/4 for i in range(len(sl))):.1f}")
json.dump(out,open('demand_traces.json','w'))
