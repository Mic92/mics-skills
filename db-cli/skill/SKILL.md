---
name: db-cli
description: Search Deutsche Bahn train connections. Use for train routes, schedules, and travel times in Germany.
---

Station names are fuzzy-matched.

```bash
db-cli "Berlin Hbf" "München Hbf"                  # depart now
db-cli -d "2026-04-10T14:30" Frankfurt Hamburg     # ISO departure
db-cli -d "in 30 minutes" Hamburg Frankfurt        # relative
db-cli -a "by 18:00" Köln Stuttgart                # arrive by (rolls to tomorrow if past)
db-cli -t Berlin München                           # Deutschlandticket only (no ICE/IC/EC)
db-cli -r 5 Berlin München                         # show 5 results (default 3)
```

Output: per-journey departure → arrival, duration, transfer count, per-leg train type and platforms. Ends with a pre-filled bahn.de booking URL.
