# MatchLab Studio Local

Clean local-first MatchLab Studio application.

## Runtime architecture

SofaScore URL -> local importer -> canonical MatchLab metrics -> Matchday Studio UI.

Pages:
- Match Stats
- Player Stats
- Metric Leaders

Periods:
- Full Match
- 1st Half
- 2nd Half

This repository is intentionally separate from legacy Analysis-App / Render frontend experiments.

## Deployment policy

Local runtime is the source of truth. Render is parked and not required to run MatchLab Studio.
