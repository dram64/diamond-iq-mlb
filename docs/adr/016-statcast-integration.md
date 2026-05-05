# ADR 016 — Statcast / Baseball Savant integration

## Status

Accepted (implemented April 2026, Phase 7).

A separate ADR rather than a Phase 6 amendment because Phase 7
introduces a new external **data domain** — Statcast / Baseball
Savant CSV leaderboards — distinct from the MLB Stats API the rest
of the project consumes. ADR 012 covers the MLB Stats API player
data architecture; this ADR covers what's adjacent to it from a
different upstream.

## Context

User wanted Statcast metrics on the Compare Players page:

  - **Core hitter:** avg/max exit velocity, barrel %, hard-hit %,
    sweet spot %, sprint speed, xBA, xSLG, xwOBA
  - **Core pitcher:** avg fastball velocity, fastball spin rate,
    whiff %, chase whiff %, xERA, xBA against
  - **Advanced:** bat speed (2024+), pull / center / oppo splits

These metrics are not in the MLB Stats API (`statsapi.mlb.com`) the
rest of the project consumes. They live on Baseball Savant
(`baseballsavant.mlb.com`), which is owned by MLB but published as a
separate data product.

Step 0 investigation surfaced two viable upstream patterns and three
storage options. This ADR captures the decisions and the reasoning.

## Decisions

### 1. Direct CSV scraping of Baseball Savant leaderboard endpoints

**Chosen over `pybaseball`.** The published `?csv=true` endpoints on
`/leaderboard/*` are first-class CSV downloads — these power the
download buttons in the Savant UI. Hitting them programmatically is
what they exist for. Same posture as the existing `mlb_client.py`
integration with `statsapi.mlb.com`.

`pybaseball` would have pulled in `pandas`, `numpy`, `pyarrow`, and
`lxml` — bloating the Lambda zip ~10× from ~50 KB to ~40 MB. That
push would have forced us into a Lambda Layer, adding a deploy
artifact we don't have today. The `pybaseball` library is largely a
wrapper over the same endpoints we hit directly, so the dependency
adds zero functional value at this scale.

Stdlib-only client at `functions/shared/savant_client.py`
(`urllib.request` + `csv.DictReader`) mirrors the `mlb_client.py`
pattern exactly. ~150 LOC, zero net new dependencies.

User-Agent header: `diamond-iq/0.1 (+https://github.com/dram64/diamond-iq)`,
matching the existing MLB Stats API client. Rate-limit probing
during Step 0 showed no throttling on 10 sequential requests; we
don't pace these because the daily-aggregate ingest only fires 5
HTTP requests total per day.

### 2. Single-row-per-player storage at `STATCAST#<season>/STATCAST#<personId>`

**Chosen over multi-block sub-partitions** (Option B in Step 0).

Trade-off: a single row means one `GetItem` per player on the API
side. A sub-partition design would have allowed independent refresh
of each block (hitter custom, hitter EV, bat tracking, batted ball,
pitcher) but at the cost of 5× read amplification for the
ubiquitous "give me everything for this player" lookup that drives
the Compare page.

The hitter side merges two CSVs (`/leaderboard/custom?type=batter`
and `/leaderboard/statcast`) into a single `hitting` block at ingest
time — this is fine because both CSVs are downloaded in the same
Lambda invocation, so the merge is naturally atomic.

Schema:

```
PK = STATCAST#<season>          SK = STATCAST#<personId>
{
  person_id: int,
  season: int,
  display_name: str | null,
  hitting: {                                       // null when player has no hitter data
    xba, xslg, xwoba: str | null,                  // upstream string-formatted ".290"
    avg_hit_speed, max_hit_speed: Decimal | null,  // mph
    ev95_percent, barrel_percent: Decimal | null,  // hard-hit %, barrel %
    sweet_spot_percent, sprint_speed: Decimal | null,
    barrel_per_pa_percent, max_distance,
    avg_distance, avg_hr_distance: Decimal | null,
  } | null,
  pitching: {                                      // null when player has no pitcher data
    xera, fastball_avg_speed, fastball_avg_spin: Decimal | null,
    whiff_percent, chase_whiff_percent: Decimal | null,
    xba_against: str | null,                       // upstream-formatted
  } | null,
  bat_tracking: {                                  // null pre-2024 / below qualifier
    avg_bat_speed, swing_length, hard_swing_rate: Decimal | null,
    squared_up_per_swing, blast_per_swing: Decimal | null,
  } | null,
  batted_ball: {                                   // null below qualifier
    pull_rate, straight_rate, oppo_rate: Decimal | null,
    gb_rate, fb_rate, ld_rate: Decimal | null,
  } | null,
}
```

Rate stats stored as upstream strings (`.290`) preserve display
formatting verbatim so the frontend renders them without re-parsing.
Numeric stats stored as `Decimal` (DynamoDB rejects native Python
floats — Decimal is the supported type).

Storage volume: ~1.5 KB per row × ~250 qualified players per season
= **~400 KB total partition size**. Well under any limit; storage
cost is negligible.

### 3. Single Lambda + daily cron at 09:30 UTC

**Chosen over Step Functions fan-out.** The whole ingest is 5 HTTP
calls + parse + ~250 PutItems. End-to-end measured ~8.7 s on the
first production run. Step Functions adds operational surface
(state machine, console UI, $0.025/execution) for no benefit at
this scale.

Cadence: daily 09:30 UTC, after `ingest-standings` (09:15) and
`ingest-team-stats` (09:20). Statcast publishes after games settle,
typically T+1 morning. Daily is the natural cadence; doubleheaders
and suspended games don't change the math.

Memory: 256 MB. Timeout: 60 s (~7× headroom over the measured 8.7 s).

### 4. Per-CSV failure isolation, not per-row

If one of the 5 leaderboard endpoints 5xx's after the
exponential-backoff retries (`1s/2s/4s`), the Lambda logs a warning
and proceeds with the other four. A hitter row still merges
correctly with bat-tracking missing — `bat_tracking` becomes `null`
in the row.

Importantly, an **empty** CSV (e.g. `custom_pitcher` returning zero
rows because no pitchers cleared the qualifier yet) is **not**
treated as a failure. We tracked this distinction in the Lambda's
`_safe_fetch` return tuple (`(rows, errored)`) so the `ok` summary
flag only flips false on actual SavantAPIError, not on legitimate
empty results.

This matters because in early-season slices (April), pitchers
qualifying for `/leaderboard/custom?type=pitcher` is a very small
set. If we treated empty == failure, the Lambda's CloudWatch
`ok=false` count would be perpetually noisy.

### 5. Defer per-pitch breakdowns to Phase 7b

User-confirmed scope cut. Per-pitch arsenal (slider movement,
fastball horizontal break, etc.) requires either HTML scraping the
embedded JSON in player pages (~3 MB per page) or per-pitcher calls
to `statcast_search/csv` (heavy). Step 0 didn't locate a bulk-CSV
pitch-arsenal endpoint.

Deferred to Phase 7b. Endpoint hunt + architecture decision can
land in a follow-up without changing anything we ship now. The
existing `STATCAST#<season>/STATCAST#<personId>` row leaves room
for a `pitch_arsenal` sub-block alongside `hitting/pitching/etc`
without partition-key changes.

### 6. Bat-speed coverage gap — show, don't hide

Statcast's bat-tracking metrics start in 2024. For 2026 season
(current) coverage is broad but not complete (mid-season, ~230
hitters with data). For older seasons that may be queried later,
bat-tracking will be null.

The frontend renders the `Bat tracking` sub-block whenever **at
least one** compared player has bat-tracking data, with a footnote
at the bottom of the Statcast section: *"Bat tracking metrics
available from 2024+. Statcast data via Baseball Savant. Players
outside the qualified pool may show no data."*

A row with no bat-tracking data shows an em-dash. **No row is
hidden** — hiding would create per-player layout shifts when
compared players have different coverage profiles.

## Consequences

### Positive

  - **Zero new dependencies.** Stdlib-only ingest. Lambda zip
    increment under 5 KB.
  - **Per-CSV failure isolation.** Bat-tracking endpoint going down
    doesn't kill the entire daily ingest. ~250 hitter rows still
    merge with the other four CSVs.
  - **Sub-second API reads.** Single `GetItem` per player on
    `/api/players/{id}` and `/api/players/compare`. No fan-out.
  - **Fits in 60 s Lambda comfortably.** Real-world first run was
    8.7 s end-to-end with all 5 CSVs succeeding.
  - **Frontend bundle delta minimal.** PlayerComparePage chunk
    grew from 12.88 KB to 18.40 KB (~+5.5 KB raw, ~+1.3 KB gzip).
  - **Mobile responsive** via the same auto-fit grid the parent
    Compare panel uses. Stacks below the breakpoint without
    custom CSS.

### Negative

  - **Manual schema-drift watch.** Baseball Savant's column names
    change occasionally over years (e.g. `barrels_per_pa_percent`
    was `brls_pa` historically). Defensive: `_str_or_none` and
    `_num_or_none` quietly drop unknown columns; the tests assert
    we don't crash on unknown columns. Future schema breaks will
    surface as null fields, not exceptions — visible in the
    frontend as em-dashes.
  - **License/ToS posture is not 100% guaranteed.** The CSV
    endpoints are public download paths, but baseballsavant.mlb.com
    has no formal API contract. If MLB ever locks these down, we'd
    need a new strategy. Same risk as our existing statsapi.mlb.com
    integration — covered by the same posture documentation.
  - **Per-pitch breakdowns deferred.** Users asking specifically
    for "slider horizontal break" or "fastball spin axis" will see
    only fastball-aggregate data until Phase 7b lands.

### Out of scope (deliberate)

  - Per-game Statcast events. We ingest only season aggregates.
  - Statcast for the team comparison page. Phase 7c if ever asked.
  - Historical season backfill. Only ingests current season; older
    seasons stay null.
  - S3 cache layer in front of Baseball Savant. The Savant
    endpoints respond in ~250-500 ms; we don't need an extra cache
    tier at ingest cadence.

## Future polish

  - **Phase 7b — per-pitch arsenal.** Once we locate the right
    bulk endpoint (or commit to per-pitcher `statcast_search/csv`),
    add `pitch_arsenal` sub-block with per-pitch-type breakdown
    (velocity, spin, movement, whiff%).
  - **Phase 7c — team Statcast.** Aggregate hitter rows by team_id
    on the API side (or pre-compute at ingest). Surface on
    /compare-teams.
  - **Daily-stats hint enrichment for the recap prompt.** Already
    surfaced as Phase 6.1 future polish; a Statcast-aware version
    would let the Bedrock recap cite specific exit velocities and
    barrel calls. Pending Phase 6.2 quota resolution.
