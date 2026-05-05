# Option 5 Design — Player and Pitch-level Data

## Status
Implemented across Phases 5B–5L + 5G. All four "Demo data" badges
on the home page (LeaderCard, HardestHitChart, CompareStrip,
TeamGridCard) replaced with real MLB data from this design's
ingestion + API contracts. Per-phase implementation decisions
captured in the ADR 012 amendment trail.

## Goal

Replace the four "Demo data" badges on the home page (LeaderCard,
HardestHitChart, CompareStrip, TeamGridCard) with real MLB
player-level, team-level, and pitch-event data. The data layer
extends the existing `diamond-iq-games` single-table design rather
than introducing a new table per entity type.

This document is the design contract for sub-phases that follow:
each implementation commit references the schema and access patterns
defined here.

---

## a) MLB Stats API endpoints

The MLB Stats API at `https://statsapi.mlb.com/api/v1` (and `v1.1`
for the live feed) is public, requires no authentication, and has
no formal documented rate limit. Empirically ~100 req/min/IP is
the safe ceiling — exceeding it returns 503s. All samples below
captured live during this design phase against the 2026 season.

### `GET /teams?sportId=1&season={season}`

All 30 teams plus league/division IDs.

```json
{
  "teams": [
    {
      "id": 133,
      "name": "Athletics",
      "season": 2026,
      "venue": { "id": 2529, "name": "Sutter Health Park" },
      "teamCode": "ath",
      "abbreviation": "ATH",
      "...": "..."
    }
  ]
}
```

**Refresh cadence:** once per season at start. Cache indefinitely.
**Volume:** 1 request, 30 teams in response.

### `GET /teams/{id}/roster?season={season}&rosterType=Active`

Active roster for one team. ~25-40 players each.

```json
{
  "roster": [
    {
      "person": {
        "id": 592450,
        "fullName": "Aaron Judge",
        "link": "/api/v1/people/592450"
      },
      "jerseyNumber": "99",
      "position": {
        "code": "9",
        "name": "Outfielder",
        "abbreviation": "RF"
      },
      "status": { "code": "A", "description": "Active" },
      "parentTeamId": 147
    }
  ]
}
```

**Refresh cadence:** daily (rosters churn from IL moves, trades,
call-ups). 30 teams × 1 request = 30 calls/day.

### `GET /people/{id}`

Player metadata.

```json
{
  "people": [
    {
      "id": 592450,
      "fullName": "Aaron Judge",
      "primaryNumber": "99",
      "currentAge": 34,
      "height": "6' 7\"",
      "weight": 282,
      "batSide": { "code": "R", "description": "Right" },
      "pitchHand": { "code": "R", "description": "Right" },
      "primaryPosition": {
        "code": "9",
        "name": "Outfielder",
        "abbreviation": "RF"
      }
    }
  ]
}
```

**Refresh cadence:** weekly. Player metadata is essentially
static within a season. Bulk-fetch on roster ingest using
`?personIds=1,2,3,...`.

### `GET /people/{id}/stats?stats=season&group=hitting&season={season}`

Season totals for one player. Group is `hitting` or `pitching`.

```json
{
  "stats": [
    {
      "type": { "displayName": "season" },
      "group": { "displayName": "hitting" },
      "splits": [
        {
          "season": "2026",
          "stat": {
            "gamesPlayed": 28,
            "atBats": 100,
            "runs": 22,
            "hits": 23,
            "doubles": 3,
            "homeRuns": 10,
            "rbi": 18,
            "baseOnBalls": 21,
            "strikeOuts": 34,
            "stolenBases": 5,
            "avg": ".230",
            "obp": ".369",
            "slg": ".560",
            "ops": ".929",
            "babip": ".232",
            "plateAppearances": 123,
            "totalBases": 56
          },
          "team": { "id": 147, "name": "Yankees" }
        }
      ]
    }
  ]
}
```

Pitching group has `era`, `wins`, `losses`, `saves`, `inningsPitched`,
`strikeOuts`, `walks`, `whip`, `hits`, `earnedRuns`, `homeRuns`,
`battersFaced`.

**Refresh cadence:** after each Final game involving the player.
**Volume estimate:** ~1500 active players, ~150 qualified.

### `GET /stats?stats=season&group=hitting&playerPool=Qualified&season={season}&limit=50`

League-wide leaderboard for qualified hitters or pitchers.

```json
{
  "stats": [
    {
      "splits": [
        {
          "season": "2026",
          "stat": {
            "avg": ".358",
            "obp": ".465",
            "slg": ".755",
            "ops": "1.220",
            "homeRuns": 11,
            "rbi": 22,
            "...": "..."
          },
          "player": { "id": ..., "fullName": "..." },
          "team": { "id": ..., "name": "..." }
        }
      ]
    }
  ]
}
```

**Refresh cadence:** daily (after Final games settle). One call per
group-stat combination is enough; pre-compute the top-50 snapshot
and store ranked rows.

**`playerPool=Qualified`** restricts to players with ≥3.1 PA per
team game (hitting) or ≥1 IP per team game (pitching). Approx 150
qualified hitters, 80 qualified pitchers in a typical season.

**Sort parameters:** the `&sortStat=homeRuns` query param is
supported but the default sort is by the stat name in the query.
Multi-stat sort isn't supported; we'd issue one call per stat we
want to lead by (HR, AVG, RBI, etc.).

### `GET /standings?leagueId=103,104&season={season}`

Division standings + W-L + GB + L10 + streak.

```json
{
  "records": [
    {
      "division": { "id": 201, "name": "American League East" },
      "teamRecords": [
        {
          "team": { "id": 147, "name": "Yankees" },
          "wins": 18,
          "losses": 10,
          "divisionRank": "1",
          "gamesBack": "-",
          "streak": {
            "streakCode": "L1",
            "streakType": "losses",
            "streakNumber": 1
          },
          "records": {
            "splitRecords": [
              { "type": "home", "wins": 8, "losses": 5 },
              { "type": "away", "wins": 10, "losses": 5 },
              { "type": "lastTen", "wins": 6, "losses": 4 }
            ]
          }
        }
      ]
    }
  ]
}
```

**Refresh cadence:** daily. Two leagueIds (103=AL, 104=NL); one
call per league.

### `GET /game/{gamePk}/feed/live` (v1.1)

The live-feed payload contains `liveData.plays.allPlays[]`. Each play
has `playEvents[]`; each event with a hit has `hitData`. Sample from
game 822824 (Final, 70 plays, 45 events with launchSpeed):

```json
{
  "launchSpeed_mph": 109.3,
  "launchAngle_deg": 16.0,
  "totalDistance_ft": 370.0,
  "pitch_type": "Sweeper",
  "result": "Lineout",
  "batter": "Vladimir Guerrero Jr.",
  "inning": 8
}
```

**Refresh cadence:** once per game-final transition (the existing
ingest Lambda already triggers this signal — extend it to also fan
out a hit-extraction job).

**Volume estimate:** ~30-45 events with launchSpeed per game ×
15 games/day = ~600 hit events/day league-wide.

### Endpoints surveyed but deferred

- `/people?personIds=1,2,...` — bulk metadata, useful for the
  on-demand non-qualified fetch path. Implementation Phase 5C.
- `/awards`, `/draft`, `/transactions` — not needed for v1
  scope.
- `/scheduledEvents`, `/seasons`, `/sports` — utility lookups,
  cache once or hit on demand.

---

## b) DynamoDB schema design

Single-table extension of `diamond-iq-games`. Same composite key
shape (`PK`, `SK`), TTL attribute, PAY_PER_REQUEST billing. New
entity types added; existing GAME and CONTENT items unaffected.

### Entity-to-key mapping

| Entity | PK | SK | TTL |
|---|---|---|---|
| Player metadata | `PLAYER#GLOBAL` | `PLAYER#<personId>` | none (static-ish) |
| Roster entry | `ROSTER#<season>#<teamId>` | `ROSTER#<personId>` | 7 days (re-ingested daily) |
| Season stats | `STATS#<season>#<group>` | `STATS#<personId>` | 90 days post-season-end |
| Standings | `STANDINGS#<season>` | `STANDINGS#<teamId>` | 7 days (re-ingested daily) |
| Leaderboard snapshot | `LEADERBOARD#<season>#<group>#<stat>` | `LEADERBOARD#<rank>` | 14 days |
| Hardest-hit hit | `HITS#<date>` | `HIT#<paddedExitVelo>#<gamePk>#<eventIdx>` | 30 days |

Where:
- `<season>` = 4-digit calendar year (e.g., `2026`).
- `<group>` = `hitting` or `pitching`.
- `<stat>` = the lead stat for a leaderboard (e.g., `avg`, `homeRuns`,
  `era`, `whip`).
- `<paddedExitVelo>` = exit velocity as a fixed-width zero-padded
  string (e.g., `109.3` → `"1093"`) so SK descending sort produces
  hardest-hit-first.
- `<eventIdx>` = the event's position in the play (allows multiple
  events from one game).

### GSI design

**`PLAYER#GLOBAL`** uses no GSI — direct GetItem by personId.

**`STATS#<season>#<group>`** gets a sparse GSI:
- GSI name: `by-stat`
- GSI PK: `STATS_LEADER#<season>#<group>#<stat>` (string)
- GSI SK: `<rank>` (number, 1-N)

This GSI lets us query "top N players by stat" without scanning
the whole partition. Each season-stat tuple is its own partition
on the GSI.

But because we already pre-compute leaderboard snapshots into
their own `LEADERBOARD#...` partition (cheaper reads, simpler), we
**won't actually create the by-stat GSI in v1**. The trade-off:
leaderboards are stale by up to 24 hours, which is fine.

If a future feature needs real-time leaderboard recomputation, we'd
add the GSI then.

**`HITS#<date>`** uses no GSI — the SK already encodes exit velocity
for a sortable Query. `Query` with `Limit=10, ScanIndexForward=false`
returns the day's top-10 hardest hits.

### TTL strategy

- **Player metadata:** no TTL. Players don't churn enough to warrant
  expiration; manual cleanup at season transitions.
- **Roster entries:** 7-day TTL. Daily re-ingest re-writes them
  with refreshed TTL; if ingest is paused for >7 days, the roster
  data ages out automatically.
- **Season stats:** 90 days post-season-end (ttl set to
  `season_end_date + 90 days`). Survives off-season for "look up
  last year's stats" queries; replaced when next season begins.
- **Standings:** 7-day TTL.
- **Leaderboards:** 14-day TTL (longer than refresh cadence so a
  bad ingest day doesn't blank the page).
- **Hardest-hit hits:** 30-day TTL. The home page only renders
  today's; other dates can be hit on demand within the window.

---

## c) Access pattern catalog

Every read pattern the frontend consumes, with the DynamoDB query
that satisfies it. None require a Scan.

| Frontend section | Access pattern | Query |
|---|---|---|
| `LeaderCard` (Batting) | Top-5 qualified hitters by AVG | `Query LEADERBOARD#2026#hitting#avg, Limit=5` |
| `LeaderCard` (Pitching) | Top-5 qualified pitchers by ERA | `Query LEADERBOARD#2026#pitching#era, Limit=5` |
| `LeaderCard` (Standings) | One division's standings | `Query STANDINGS#2026, FilterExpression division=:d` |
| `HardestHitChart` | Top-10 hardest-hit balls today | `Query HITS#<date>, ScanIndexForward=false, Limit=10` |
| `CompareStrip` | Two specific players' season stats, side by side | `BatchGetItem on STATS#2026#hitting/SK=STATS#<id>` × 2 |
| `TeamGridCard` | All 8 teams' record + L10 + streak + odds | `Query STANDINGS#2026` (returns 30 items, render only the 8 we want — playoff odds computed locally if not in source) |
| Player detail (future) | One player's metadata + current season | `GetItem PLAYER#GLOBAL/SK=PLAYER#<id>` + `GetItem STATS#2026#hitting/SK=STATS#<id>` |
| Non-qualified player on demand (future) | Single player not in our pre-ingested set | Lambda that hits `/people/{id}/stats` live, returns adapted response, optionally caches in `STATS#...` partition |

### Read-cost back-of-envelope

The home page issues 7 reads on first load:
- 2 `LeaderCard` (batting + pitching) → 2 Query, 5 items each = 10 RCU
- 1 `LeaderCard` (standings) → 1 Query, 5 items = 5 RCU
- 1 `HardestHitChart` → 1 Query, 10 items = 10 RCU
- 1 `CompareStrip` → 2 GetItem = 2 RCU
- 1 `TeamGridCard` → 1 Query, 30 items = 30 RCU
- ~57 RCU per home-page render. Fits comfortably in DynamoDB free
  tier (25 RCU sustained or ~2M reads/month at PAY_PER_REQUEST).

---

## d) Computed stat formulas

For v1 we trust the MLB API for everything it provides directly,
and compute three "advanced" metrics ourselves. The portfolio
pitch is "we know what these mean and can derive them," not "we
beat Fangraphs at sabermetrics."

### Direct from API (`hitting` group)

`avg`, `obp`, `slg`, `ops`, `homeRuns`, `rbi`, `runs`,
`baseOnBalls`, `strikeOuts`, `stolenBases`, `caughtStealing`,
`atBats`, `plateAppearances`, `totalBases`, `babip`, `gamesPlayed`.

### Direct from API (`pitching` group)

`era`, `wins`, `losses`, `saves`, `inningsPitched`, `strikeOuts`,
`baseOnBalls`, `whip`, `hits`, `earnedRuns`, `homeRuns`,
`battersFaced`.

### Computed (v1 trio)

**wOBA** — weighted on-base average. League-average linear weights
needed; cache per season.

```
wOBA = (0.69·BB + 0.72·HBP + 0.89·1B + 1.27·2B + 1.62·3B + 2.10·HR)
       / (AB + BB - IBB + SF + HBP)
```

Primitives required: `baseOnBalls`, `hitByPitch`, `hits` (less
doubles+triples+homers = 1B), `doubles`, `triples`, `homeRuns`,
`atBats`, `intentionalWalks`, `sacFlies`. All present in the API
hitting group response.

**OPS+** — park-and-league-adjusted OPS, indexed to 100.

```
OPS+ = 100 · (OBP / lgOBP + SLG / lgSLG - 1)
```

Primitives: player's `obp` and `slg`, plus league averages
(captured separately each season as a `LEAGUE_CONST#<season>` row).

**FIP** — fielding-independent pitching.

```
FIP = (13·HR + 3·(BB+HBP) - 2·K) / IP + cFIP
```

Primitives: `homeRuns`, `baseOnBalls`, `hitByPitch`, `strikeOuts`,
`inningsPitched`, plus the season's `cFIP` constant
(usually 3.00–3.20; cache as `LEAGUE_CONST#<season>`).

### Deferred (Phase 5C+)

xwOBA (Statcast-derived expected wOBA), BABIP-against, K-BB%,
ZiPS / Steamer projections, park-adjusted SLG, defensive runs
saved.

---

## e) Ingestion strategy

Three Lambdas. Two new (player + leaderboard); one extension to
the existing ingest. Naming follows the project pattern.

### `diamond-iq-ingest-players` (new)

- **Trigger:** EventBridge cron once daily at 14:00 UTC (after
  every prior-day game has gone Final).
- **Behavior:**
  1. `GET /teams?sportId=1&season=$SEASON` → 30 team IDs.
  2. For each team, `GET /teams/{id}/roster?...&rosterType=Active`.
  3. Deduplicate person IDs into a set (some players appear on
     multiple parent-team IDs during call-ups).
  4. Bulk-fetch player metadata via `/people?personIds=1,2,3,...`
     in chunks of 50 (to keep URL length sane).
  5. Write each `PLAYER#GLOBAL/PLAYER#<id>` and
     `ROSTER#<season>#<teamId>/ROSTER#<personId>` row.
- **Volume:** ~30 roster calls + ~30 bulk metadata calls = 60
  requests. Fits well under MLB's effective rate limit.
- **Cost:** 1 invocation/day, ~10s runtime, ~$0/month at portfolio
  scale.

### `diamond-iq-ingest-stats` (new)

- **Trigger:** EventBridge cron once daily at 14:30 UTC (after
  player ingest).
- **Behavior:**
  1. Read all qualified player IDs from the leaderboard endpoints
     (`playerPool=Qualified`, both groups).
  2. For each qualified player, fetch `/people/{id}/stats?...`
     for that group.
  3. Compute wOBA / OPS+ / FIP locally using the league constants
     row.
  4. Write to `STATS#<season>#<group>/STATS#<personId>`.
- **Volume:** ~150 hitters + ~80 pitchers = 230 calls/day.
  Spread over ~3 minutes. Well under rate-limit ceiling.

### `diamond-iq-compute-leaderboards` (new)

- **Trigger:** EventBridge cron once daily at 15:00 UTC (after
  stats ingest).
- **Behavior:**
  1. Read all `STATS#<season>#<group>` rows.
  2. For each lead-stat we render (AVG, HR, RBI, WAR, OPS,
     ERA, K, WHIP, K/9, FIP), sort and write the top-50 snapshot
     into `LEADERBOARD#<season>#<group>#<stat>` rows with rank
     in the SK.
- **Volume:** read 230 rows + write 50 rows × 10 stats = 500
  writes/day. Negligible.

### Extension to `diamond-iq-ingest-live-games` (existing)

- **New behavior:** when a game's status transitions from `live`
  to `final` in this run (i.e., the OldImage was live and the
  NewImage is final), enqueue a hit-extraction job.
- **Job:** call `feed/live` for the gamePk, walk
  `liveData.plays.allPlays[].playEvents[]`, write any event with
  `hitData.launchSpeed > 95.0` to `HITS#<date>/HIT#<padded>...`.
- **Implementation choice:** rather than coupling this into the
  ingest Lambda's hot path, the existing DynamoDB Streams from
  the games table can fire a separate `diamond-iq-extract-hits`
  Lambda that watches for `live → final` transitions specifically.
  Reuses the streaming pipeline pattern from Option 4.

### Standings refresh

Folded into either `ingest-stats` or its own daily cron at 14:45
UTC. Single API call to `/standings?leagueId=103,104`. Trivial.

---

## f) Cost projection

### Current portfolio scale (5-10 daily home-page loads)

| Component | Estimate |
|---|---|
| 3 new Lambdas × 1 daily invocation × ~10-30 s | <$0.10 |
| `extract-hits` Lambda: ~15 invocations/day × ~5s | <$0.05 |
| MLB Stats API egress | $0 (free, public) |
| Additional DynamoDB writes (~600 rows/day, ~2.5K/month) | <$0.10 |
| Additional DynamoDB reads (~57 RCU per page load × 300 loads/month) | <$0.05 |
| Additional CloudWatch Logs (3 small Lambdas × 14d retention) | <$0.20 |
| **Option 5 monthly cost** | **~$0.50** |

### Hypothetical 10× scale (50-100 daily page loads, 1500 active players ingested fully)

A move from "qualified-only" to "all-active-players" multiplies
the player-stats fetch from 230/day to ~1500/day. That brings
two cost drivers into play that don't apply at portfolio scale:

- **MLB Stats API rate limits become real.** 1500 calls in a
  3-minute window is ~8/s — well above MLB's effective ~2/s
  ceiling. Mitigation: spread the fetch across a 30-minute window
  with `time.sleep(2)` between chunks, or batch-pull via
  `?personIds=1,2,...` (already used for metadata; need to verify
  the `/stats` endpoint supports it).
- **DynamoDB write capacity.** 1500 writes/day still fits
  PAY_PER_REQUEST trivially (~$0.01). Reads stay flat unless
  we add a "search players" feature.
- **Lambda concurrency.** Stats ingest takes ~30 min instead
  of ~3 min; well within the 15-min Lambda timeout if we split
  into smaller batched invocations driven by a Step Function or
  SQS chain. Keeps the per-invocation cost flat; total cost
  scales linearly.
- **Hardest-hit volume.** 10× home-page loads doesn't change
  ingest volume; reads scale linearly with no architectural change.

Net 10× monthly cost: **~$3-5** (adds <$5 above baseline).
DynamoDB RCU/WCU at PAY_PER_REQUEST scales without re-architecting;
the only meaningful infrastructure change is splitting the stats
ingest into a multi-step pipeline to spread API requests.

The architecture explicitly avoids any path that doesn't
horizontal-scale cleanly: no Scans, no GSI projections that grow
with the table, no per-player Lambdas (one Lambda iterating a
qualified-player list, not 230 concurrent invocations).

---

## g) Open questions (Phase 5B implementation)

These must be answered before sub-phase B begins; the design above
defers them deliberately.

1. **Playoff odds for `TeamGridCard`.** MLB API doesn't expose a
   playoff probability. Two paths: (a) compute a simple model
   locally (record + remaining schedule), (b) drop the column
   from the rendered card and replace with another standings
   stat. Recommend (b) for v1; revisit if the column is missed.
2. **WAR source.** The MLB API exposes a `war` field on some
   stat groups but not consistently. We may need to substitute a
   different headline metric (`bWAR` is Bbref's; the MLB number
   is a hybrid) or pull from Fangraphs/Bbref directly (added
   ingestion complexity). Check API responses across multiple
   2026 players before committing.
3. **League constants for OPS+ and FIP.** MLB API doesn't expose
   `lgOBP`, `lgSLG`, or `cFIP` directly. Compute from aggregating
   all qualified players' totals each season — simple but adds a
   step to the daily compute pipeline. Or hardcode reasonable
   approximations (~`.320` lgOBP, `~3.10` cFIP) and refresh once
   a month.
4. **"Sample preview" badges that are ALSO present on the daily
   AI sections.** The DemoBadge primitive currently distinguishes
   "demo data" from "AI generated" via the badge's color. After
   Option 5, the demo badges drop from leaderboards/teams and
   only the AI badges remain. Verify the badge component handles
   both states cleanly.
5. **Pitch-level retention beyond hardest-hit.** v1 stores only
   hits with `launchSpeed > 95.0`. If a future feature wants
   "all pitches by pitcher X this season," we'd add a separate
   ingest path and a `PITCHES#<season>#<pitcherId>` partition.
   Defer until a real product need surfaces.
6. **On-demand non-qualified player fetch.** A Lambda backed by
   `GET /people/{id}/stats` for any personId not in our scheduled
   ingest. The cache write-back is straightforward; the harder
   question is rate-limit budgeting if this becomes a frequent
   read. Defer to Phase 5C.
7. **Pitcher leaderboards by relievers.** Qualified pitchers are
   typically starters. If we want a relief-leaderboard, we'd
   need a separate `playerPool=All&filterByMinIP=15`-style query.
   Defer; v1 ships starters-only on the pitching leaderboard.
8. **Stat schema versioning.** The MLB API occasionally adds new
   fields to its `stat` object. Our schema stores a fixed shape;
   new fields are dropped on adapter unless we add them. Plan: log
   a WARNING for unrecognized fields during ingest, and a weekly
   "fields encountered but not adapted" report for visibility.

---

## Summary

- **9 entity types** in 6 PK families, single-table extension of
  `diamond-iq-games`.
- **8 documented access patterns** plus 2 deferred.
- **3 new Lambdas** + 1 extension to existing ingest.
- **3 computed stats** (wOBA, OPS+, FIP) derived from API
  primitives.
- **~$0.50/month** at current portfolio scale; **~$3-5/month** at
  10× scale.
- **8 open questions** documented for Phase 5B.

Implementation begins in Phase 5B against this contract. ADR 012
records the high-level commitments.
