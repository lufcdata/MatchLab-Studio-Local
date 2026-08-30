# MATCHLAB — MASTER CHATGPT HANDOVER
## Authoritative status: 30 August 2026
## Repository: `lufcdata/MatchLab-Studio-Local`

This document is the authoritative continuation note for future ChatGPT sessions working on MatchLab. It records the architecture, Golden rules, successful workflows, signed-off UI state, metric-source responsibilities, validated fixes, GitHub workflow, known pitfalls, and the exact current development status.

---

# 1. FIRST INSTRUCTION TO THE NEXT CHATGPT

Before changing anything:

1. Inspect the current GitHub `main` branch.
2. Read this handover in full.
3. Inspect the current versions of:
   - `backend/golden_metrics.py`
   - `backend/main.py`
   - `backend/runtime.py`
   - `backend/server.py`
   - `backend/fotmob_diagnostic.py`
   - `frontend/src/App.tsx`
   - `frontend/src/polish.css`
   - `frontend/src/ui-enhancements.ts`
   - `Start MatchLab Studio.command`
4. Do not assume a commit is working merely because it exists. User verification is the final proof.
5. Preserve the signed-off UI and all existing working metric definitions.

The repository is the code source of truth. The user's latest successful visual/functionality test is the operational source of truth.

---

# 2. CRITICAL CURRENT STATUS

## Last fully user-verified working baseline

Commit:

`61da778` — **Make three new metrics native to production backend**

At this state the user explicitly confirmed the application worked after Fetch Origin → Pull Origin → full MatchLab relaunch.

This state included the restored/working core UI and the successful three-metric addition:

- Passes in Opposition Half
- Passes in Own Half
- Clearances Off Line

The two half-pass metrics were validated against Nottingham Forest 0–1 Leeds using native SofaScore lineup data:

- Jaka Bijol: Opposition Half `11/19`; Own Half `33/36`; Clearances Off Line `0`
- Ethan Ampadu: Opposition Half `20/27`; Own Half `21/24`; Clearances Off Line `0`

These values are important regression checks.

## Current remote `main`

At the time this handover was written, remote `main` is:

`c456bf6` — **Robustly extract FotMob physical performance metrics**

This is newer than the last fully user-verified baseline.

Recent physical/xG commits on top of the verified baseline include:

- `76a3ea9` — Extract FotMob physical performance metrics
- `e52ca4a` — Add physical metrics and expose xG on Player Stats
- `16d26c4` — Promote FotMob physical metrics through linked imports
- `329ad10` — Keep runtime FotMob promotion in sync with physical metrics
- `344369d` — Capture FotMob physical stats across full player payload
- `fb0c2a3` — Guarantee Player xG row alongside promoted physical metrics
- `c456bf6` — Robustly extract FotMob physical performance metrics

IMPORTANT: after an earlier version of this work, the user's test showed:

- xG was visible in Metric Leaders but NOT Player Stats.
- Distance covered (km), Number of sprints and Sprinting (km) were NOT visible on Match Stats, Player Stats or Leaders.

The later commits `344369d`, `fb0c2a3`, and `c456bf6` were intended to address those failures, but they have NOT yet been user-verified at the point of this handover.

Do not describe those physical metrics as solved until they are actually tested in the running app.

---

# 3. GOLDEN / SAFETY RULES

These rules are integral to MatchLab and must be obeyed.

## Metric rules

- ONE METRIC → ONE AUTHORITATIVE DEFINITION → ALL RELEVANT SURFACES.
- Do not casually rewrite existing metric definitions.
- Do not replace a MatchLab metric with a familiar provider definition merely because it looks more standard.
- Do not add fixture-specific +1/-1 corrections or hard-coded score-fitting hacks.
- Do not silently allow an old/legacy definition to override a Golden definition.
- Do not remove existing metrics without explicit user approval.
- Additive changes are preferred.
- A metric being present in code is not sufficient: verify catalogue → data → API → Player/Match/Leaders → UI.

## UI rules

- The current visual design is signed off and should be preserved.
- Do not mix backend/metric-definition changes with unrelated visual redesign.
- Do not casually alter spacing, typography, image treatments, cards, bars, selectors, headers or footers while fixing data.
- The MatchLab UI Design System extracted for another project is a separate task/reference and must not change MatchLab backend logic.

## Data-provider rules

- SofaScore is the PRIMARY MatchLab source.
- FotMob is SUPPLEMENTARY only for validated fields unavailable or unsuitable from SofaScore.
- Do not make FotMob replace SofaScore globally.
- Linked imports must preserve/reapply the stored FotMob supplement when SofaScore is refreshed.
- Native SofaScore data must be preferred when a validated native field exists.

---

# 4. ARCHITECTURE / RUNTIME

MatchLab is self-contained and launched locally by:

`Start MatchLab Studio.command`

The launcher:

- creates/uses the backend virtual environment;
- installs required dependencies when necessary;
- starts the backend with `uvicorn runtime:app`;
- starts the Vite frontend;
- proxies frontend `/api` to the selected backend port;
- kills only old MatchLab-owned local listeners;
- finds free backend/frontend ports;
- checks `/api/health` before opening the browser;
- preserves team-logo assets separately from replaceable player imagery.

This means **`runtime.py` is part of the real production launch path**. Do not inspect `main.py` alone and assume that is the entire live backend.

Important backend roles:

- `golden_metrics.py`: authoritative metric catalogue, canonical labels, key mapping, Player formatting/calculated metric behaviour.
- `main.py`: core FastAPI endpoints, SofaScore import, Match/Player/Leaders API surfaces, production loader.
- `server.py`: linked SofaScore + FotMob import and supplementary promotion/healing routes.
- `runtime.py`: live app entry point and runtime self-healing/promotion compatibility layer.
- `fotmob_diagnostic.py`: FotMob page extraction, key normalization, supplementary player-stat discovery.

Frontend roles:

- `App.tsx`: three-page app and API data flow.
- `polish.css`: signed-off visual overrides.
- `ui-enhancements.ts`: selection/ranking/reorder/date enhancements and UI compatibility logic.

---

# 5. REQUIRED GITHUB DESKTOP WORKFLOW

This has caused repeated false negatives and must be followed exactly.

When ChatGPT pushes a commit directly to remote GitHub:

1. User opens GitHub Desktop.
2. Click **Fetch Origin**.
3. If the remote is ahead, the button changes to **Pull Origin** and shows the incoming count.
4. Click **Pull Origin**.
5. Open **History** and verify the expected commit is at the top.
6. Do NOT assume Fetch alone pulled the code.
7. Fully quit MatchLab and relaunch after backend/runtime changes.

A key debugging episode proved this workflow:

- Remote GitHub was on `61da778`.
- Local GitHub Desktop still showed `756237f` after a fetch.
- A subsequent fetch exposed **Pull Origin — 1 ↓**.
- Pulling then showed `61da778` in local History.
- After full MatchLab relaunch, the missing three metrics worked.

Therefore: before diagnosing code, compare **remote `main` SHA vs local History SHA**.

## Do not disturb local files

The user's GitHub Desktop has shown roughly **1.4k local Changes**. Do not instruct the user to Discard All, Reset, force checkout, clean the repository, or otherwise destroy those files unless the user explicitly agrees and a backup has been made.

Fetch/Pull has successfully worked while preserving those local changes.

---

# 6. GOLDEN CHECKPOINT BRANCHES

Confirmed checkpoint branches include:

- `golden-checkpoint-2026-08-24-working-fotmob`
- `golden-moment-2026-08-25-everything-working`

These are important historical safety branches.

However, later successful UI and metric work exists after those branches. For functional regression diagnosis, `61da778` is especially important because the user explicitly verified the then-current complete app after pulling it.

Never force-move or delete Golden branches casually.

---

# 7. CURRENT METRIC CATALOGUE / SOURCE RESPONSIBILITIES

The Golden metric map currently contains the following metric families. Existing definitions must be preserved unless specifically being investigated.

## Core / SofaScore-backed metrics

- Goals
- xG
- Possession
- Touches
- Shots
- Shots On-Target
- Shots Outside Box
- Shots Inside The Box
- Big Chances
- Big Chances Created
- Big Chances Missed
- Chances Created
- Successful Passes
- Total Passes
- Passes in Opposition Half
- Passes in Own Half
- Successful Final Third Passes
- Pass Accuracy
- Ball Carries
- Progressive Carries
- Progressive Carrying Distance (m)
- Accurate Long Passes
- Final Third Entries
- Accurate Crosses
- Ground Duels Won
- Aerial Duels Won
- Duels Won
- Ball Recoveries
- Successful Take-Ons
- Tackles Won
- Interceptions
- Clearances
- Fouls
- Fouled
- Possession Lost
- Corners
- Saves
- Assists
- Penalties Won
- Saves From Inside Box
- High Claims
- Red Cards
- Defensive Actions

## Validated FotMob supplementary metrics already successfully used

- Opposition Box Touches
- Passes Into Final Third
- Line-Breaking Passes
- Headed Clearances
- Clearances Off Line

Note: Opposition Box Touches has evolved through the project; native/direct data should be used where established, while the linked FotMob supplement remains part of compatibility for validated matches. Do not regress the currently working behaviour.

## New physical FotMob metrics — CURRENTLY IN DEVELOPMENT / NOT USER-VERIFIED

- Distance covered (km)
- Number of sprints
- Sprinting (km)

The latest extraction code attempts to normalize FotMob key variants and distance units. Treat these as pending until a real linked match successfully exposes them on all required surfaces.

---

# 8. HALF-PASS METRIC PIPELINE — SOLVED AND IMPORTANT

The two metrics:

- Passes in Opposition Half
- Passes in Own Half

must use native SofaScore lineup statistics:

- `accurateOppositionHalfPasses`
- `totalOppositionHalfPasses`
- `accurateOwnHalfPasses`
- `totalOwnHalfPasses`

Display them as successful/attempted, e.g. `11/19`, not just the successful numerator.

The key lesson was that adding labels to the catalogue was not enough. Older locally stored match JSON could lack these native lineup fields. The successful fix put refresh/healing into the actual production backend path so stored lineups can refresh from SofaScore and persist the new native fields.

Regression validation match:

SofaScore event: `16363238`
Nottingham Forest 0–1 Leeds, 22 August 2026.

Use Bijol/Ampadu figures above as exact checks.

---

# 9. LINKED FOTMOB PIPELINE

The frontend can load a SofaScore source plus an optional FotMob source through the linked import endpoint.

Expected process:

1. SofaScore event is imported/refreshed.
2. Existing stored FotMob supplement is preserved when appropriate.
3. FotMob match reference/URL is parsed.
4. `fotmob_diagnostic.py` extracts only approved target fields.
5. Player names are normalized for cross-provider matching.
6. Validated FotMob values are promoted into the canonical SofaScore lineup player statistics consumed by MatchLab APIs.
7. The supplement plus validation metadata is persisted with the local match JSON.
8. Runtime/server healing re-promotes stored supplementary values for older matches.
9. Match Stats can aggregate Player values for full-match metrics when no direct match-stat row exists.
10. Player Stats reads canonical Player rows.
11. Metric Leaders ranks from the same underlying canonical values.

Do not create separate frontend-only fake metrics.

---

# 10. PHYSICAL METRICS — CURRENT INVESTIGATION

Requested FotMob metrics:

- Distance covered (km)
- Number of sprints
- Sprinting (km)

Latest code work tries to handle differing FotMob physical-stat key spellings/shapes via normalized aliases in `fotmob_diagnostic.py`.

Distance-type physical values must be normalized to km before MatchLab display/storage where the source value is in metres. Do not divide blindly if FotMob has already supplied km; verify the payload shape/value semantics.

The intended canonical promoted keys are:

- `distanceCoveredKm`
- `numberOfSprints`
- `sprintingKm`

The Golden catalogue, runtime promotion map and linked-import promotion layer were updated to recognize these.

But again: current user-facing success has NOT been proven after the latest `c456bf6` work.

First task for the next chat should be to verify whether the user has pulled `c456bf6`, relaunched MatchLab and tested a linked SofaScore + FotMob match. If still missing, inspect the actual `/audit/fotmob/...`, stored `fotmob.players[].stats`, `/canonical/metrics`, Player endpoint, Match endpoint and Leaders endpoint in that order.

---

# 11. xG PLAYER STATS — CURRENT INVESTIGATION

xG already existed as a MatchLab metric and in Metric Leaders. It must NOT be duplicated.

The user requested that the existing xG also appear on Player Stats.

At the last user test before the latest corrective commits:

- xG appeared in Metric Leaders.
- xG did NOT appear on the Player page.

Later commits attempted to make xG a required Player row / explicitly guarantee it for participating players, including legitimate `0.00` values when no xG was recorded.

This requires user verification after pulling the latest current `main`.

Do not add a second `Player xG` metric.

---

# 12. SIGNED-OFF UI STATE

The UI has undergone extensive iterative user review and is considered signed off apart from explicitly requested future tweaks.

Brand/header text was changed from MatchLab LOCAL STUDIO to:

`lufcdata.lab`
`football data studio`

## Match Page

Current intended layout:

- Maximum visible stats: 22
- Selector button: **Select 22**
- Title: `31.2px`
- Subtitle/meta: `19px`
- Stat names: `17.8px`
- Stat numbers: `18.8px`
- Stat container minimum height: `42.4px`
- Gap: `6px`
- Progress bar thickness: `4.5px`
- Home/away number columns centred
- Match club crests were enlarged by 10%
- Possession values include `%`
- Full-match uppercase wording was replaced by competition text, e.g. Premier League

The Match stat list had earlier hidden unwanted default metrics such as Possession, Shots Inside Box, Shots Outside Box, Successful Final Third Passes and Final Third Entries from particular leaderboard/default contexts; inspect current frontend before altering these rules.

## Player Page

- Player title/name: approximately `32.5px` via signed-off override
- Subtitle/meta: approximately `22.5px`
- Stat names: `18px`
- Stat numbers: `19px`
- Row minimum height: `42.4px`
- Gap: `6px`
- Progress bar: `4.5px`
- Ranking text: `13px`
- Player portrait enlarged by 12%
- Minutes Played is locked but its green outline was removed to match neutral row styling
- Subtitle uses opponent + competition/full-match context + match date rather than team name
- Player stat bars are measured against the match leader for that metric; percentage metrics use 100 as denominator
- Auto Select selects first 18 Player stats
- Manual stat reordering remains available
- Rank Order works in tandem with manual ordering
- Rank Order must hide/omit zero-value stats so they do not obscure positive metrics
- Every metric >0 must remain available under Rank Order; this was specifically fixed after Goals=1 was incorrectly excluded
- Event icons appear between stat name/value without moving columns:
  - Goal: ⚽ repeated by goal count
  - Assist: 🅰️ repeated by assist count
  - Red Card: 🟥 repeated by red-card count

## Leaders Page

- Title approximately `32.5px`
- Subtitle approximately `22px`
- Stat/player-name text: `18px`
- Stat numbers: `19px`
- Row minimum height: `42.4px`
- Gap: `6px`
- Progress bar: `4.5px`
- Ranking text: `13px`
- Team names removed from each row
- Two club crests displayed together at top, no white circular backgrounds
- Crest size approximately `82.8px`; gap approximately `6px`
- Header spacing and table placement were matched to user-supplied reference images
- Subtitle replaces `Top 20 Metric Leaders` with the match date where the current enhancement logic applies
- Bars are relative to the metric leader; percentage metrics use the percentage scale

## Player imagery

Old player imagery was intentionally removed and replaced with the user's new Leeds Players set. Do not restore legacy player photos. Club crests/logos are separate assets and must not be removed when replacing player images.

---

# 13. UI FEATURES THAT WERE SUCCESSFULLY FIXED

These are worth protecting because regressions occurred during earlier development:

- 22-stat Match layout and Select 22 control.
- Player Auto Select first 18.
- Player drag/manual reordering.
- Rank Order with zero-value hiding.
- Positive metrics must never be hidden simply because the rank-order window is full.
- Player rank badges.
- Goal/assist/red-card icons.
- Player/Leaders match date meta text.
- Club crest/portrait sizing and spacing.
- No recurring heatmap audit panel in the normal UI.
- Opposition Box Touches / Passes Into Final Third / Line-Breaking Passes / Headed Clearances restored across Match/Player/Leaders.
- Possession percentage suffix restored.
- Native half-pass metrics restored.

---

# 14. IMPORTANT DEBUGGING LESSONS

## Do not blame the backend until GitHub sync is proven

A repeated issue was that ChatGPT had pushed a valid remote commit but GitHub Desktop had only fetched, not pulled it. Always inspect local History.

## Catalogue presence is not end-to-end success

A metric can be present in `golden_metrics.py` and `/canonical/metrics` yet still fail because its data was never promoted into stored lineup stats.

Trace in this order:

1. Source payload contains field.
2. Extractor captures field.
3. Linked import stores field.
4. Promotion maps provider label → canonical stats key.
5. Stored match JSON contains promoted field.
6. `player_metric_value()` resolves field.
7. Player endpoint returns row.
8. Match full-match fallback aggregates rows where intended.
9. Leaders endpoint ranks it.
10. Frontend catalogue/selection displays it.

## Old stored JSON matters

Refreshing code alone does not update old match payloads. Self-healing/refetch logic may be necessary, but it must be narrowly scoped and must preserve validated supplements.

## Runtime matters

The launcher runs `uvicorn runtime:app`. A fix only in `main.py` may be modified or bypassed by runtime/server wrappers. Inspect the complete live stack.

---

# 15. WHAT NOT TO DO

- Do not rebuild the app from scratch.
- Do not revert to a visually older version just to solve one metric.
- Do not overwrite the signed-off UI with generic football dashboard styling.
- Do not replace native SofaScore half-pass values with FotMob versions.
- Do not hard-code Bijol/Ampadu validation values into production code.
- Do not add duplicate xG definitions.
- Do not restore the old heatmap audit window in normal use.
- Do not discard the user's large set of local GitHub Desktop changes.
- Do not tell the user to Push after ChatGPT has already pushed directly to remote; the user normally needs Fetch → Pull.
- Do not claim success until the user sees the metrics/values in the running app.

---

# 16. RECOMMENDED NEXT STEPS

1. Verify remote `main` is still `c456bf6` or inspect any newer commits made after this handover.
2. Have the user Fetch Origin → Pull Origin and verify local History SHA.
3. Fully quit and relaunch MatchLab.
4. Load a known match with both SofaScore and FotMob sources.
5. Verify:
   - xG on Player Stats
   - Distance covered (km) on Match/Player/Leaders
   - Number of sprints on Match/Player/Leaders
   - Sprinting (km) on Match/Player/Leaders
6. If missing, use the diagnostic sequence in section 14; do not change UI.
7. Once those are genuinely verified, create a new Golden checkpoint branch/commit representing the new fully working state.

---

# 17. SUCCESS CRITERIA FOR ANY NEW METRIC

A new metric is not complete until all applicable points are true:

- source field validated;
- canonical metric definition exists once;
- provider-to-canonical key is explicit;
- existing stored matches heal safely if required;
- Player row displays correct format;
- Match total/aggregation is correct where appropriate;
- Leaders ranks correctly;
- zero/default behaviour is intentional;
- selector toggles work;
- Rank Order does not suppress positive values;
- page bars use the correct denominator;
- full relaunch tested;
- user confirms the result visually and numerically.

Only then should the feature be called Golden/solved.

---

# 18. SUMMARY FOR THE NEXT CHATGPT

MatchLab is in a strong state and has a signed-off UI, a self-contained local launch workflow, a Golden metric catalogue, SofaScore as primary provider and FotMob as a carefully controlled supplement. The major historical failures came from source fields existing without being promoted into the exact production path, and from local GitHub Desktop lagging behind remote `main`.

Preserve the existing working system. Inspect before changing. Make narrow changes. Keep provider roles explicit. Verify remote/local Git synchronization. Test all relevant surfaces. Never equate a pushed commit with a successful feature until the user confirms it in the running MatchLab application.
