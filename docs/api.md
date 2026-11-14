start a run

    curl -d '{"cmd":"run", "profile":"cone-05-long-bisque"}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8081/api

skip the first part of a run
restart the kiln on a specific profile and start at minute 60

    curl -d '{"cmd":"run", "profile":"cone-05-long-bisque","startat":60}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8081/api

start a run with a 3 h candle and 30 min added to the top-temperature hold
(see docs/candle-and-peak-holds.md; candle_min applies to schedules marked
"candle": true, default 60; peak_extra_min defaults to 0, max 120)

    curl -d '{"cmd":"run", "profile":"cone 07 - standard bisque QUICK","candle_min":180,"peak_extra_min":30}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8081/api

`startat` counts minutes into the composed run (candle included).

extend the candle of the running firing by an hour, or end it now

    curl -d '{"cmd":"hold", "which":"candle", "add_min":60}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8081/api
    curl -d '{"cmd":"hold", "which":"candle", "end_now":true}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8081/api

add 15 min to the running firing's top-temperature hold (before or during it)

    curl -d '{"cmd":"hold", "which":"peak", "add_min":15}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8081/api

A refused change returns `{"success": false, "error": "..."}` and changes nothing.
While running, `/api/status` carries `phase` (candle / firing / peak_hold /
after_peak) and `holds` (positions in seconds of the composed run).

preview a composed run, and the per-schedule shapes Home Assistant plans with

    curl "http://0.0.0.0:8081/api/compose?profile=cone%2007%20-%20standard%20bisque%20QUICK&candle_min=180&peak_extra_min=30"
    curl http://0.0.0.0:8081/api/profile_shapes

stop a schedule

    curl -d '{"cmd":"stop"}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8081/api

post a memo

    curl -d '{"cmd":"memo", "memo":"some significant message"}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8081/api

stats for currently running schedule

    curl -X GET http://0.0.0.0:8081/api/stats

pause a run (maintain current temperature until resume)

    curl -d '{"cmd":"pause"}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8081/api

resume a paused run
    
    curl -d '{"cmd":"resume"}' -H "Content-Type: application/json" -X POST http://0.0.0.0:8081/api
