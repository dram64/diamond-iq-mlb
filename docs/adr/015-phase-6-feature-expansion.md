# ADR 015 — Phase 6 feature expansion

## Status

Accepted (implemented April 2026). This is a separate ADR rather than an
amendment to ADR 012 because Phase 6 is a feature-surface expansion of the
dashboard product (homepage, compare, teams, stats) rather than an
evolution of the player-data partition strategy. ADR 012 stays scoped to
"how player data lives in the table"; this one is "what the dashboard
does with it."

## Context

After commit `41fe4fe` declared Diamond IQ feature-complete (Option 5
Phase 5L), eight follow-on requests reopened scope:

1. **Featured Matchup of the Day** on the home page — daily-rotating
   two-player spotlight with a click-through to a deep compare view.
2. **Yesterday's Game Recap rewrite** — analytical / numbers-driven
   instead of narrative prose.
3. **Player comparisons inside the recap** — embedded head-to-head
   sub-blocks instead of long-form text.
4. **Search bar fix** — the navbar had a placeholder `<input>` with no
   handler; needed real typeahead over the player table.
5. **Compare page extension** — N-player support (2-4) with career
   accolades and an AI-written analytical paragraph.
6. **Live tab removal** — drop the dedicated `/live/:gameId` page.
7. **Teams page** — fill in the empty `/teams` route and a per-team
   detail page.
8. **Stats Explorer** — fill in the empty `/stats` route as a
   leaderboards browser.

Constraint: existing infrastructure patterns must hold. New features
must follow the established Lambda-+-cron-+-alarms-+-IAM-+-tests-+-ADR
shape; no new charting libraries, no auth surface, no write paths.
Realistic cost delta target: **+$1-3 / month at portfolio traffic**.

## Decisions

### 1. Two new Lambdas, not three

The plan started with three new Lambdas (awards, search, AI compare).
We collapsed search into the existing `api_players` Lambda — it shares
the same DynamoDB read pattern and partition (PLAYER#GLOBAL), and the
single-Lambda routeKey-dispatch pattern from Phase 5E already handles
multi-route fan-out cleanly. Net result: **2 new Lambdas** (`ingest-
player-awards`, `ai-compare`) plus 5 new API routes on the existing
`api_players` Lambda's two-route-list pattern.

### 2. Awards: hardcoded MLB-tier allowlist

MLB's `/people/{id}/awards` endpoint returns a mix of MLB-tier honors
(MVP, Cy Young, All-Star, Gold Glove, etc.) and lower-tier entries (SAL
Mid-Season All-Star, college conference awards, international leagues).
Filtering to MLB-tier is essential — otherwise Aaron Judge's career
hardware list reads with 80+ entries instead of the meaningful 16.

We hardcode an allowlist of stable upstream id codes:

  - **MVP** — `ALMVP`, `NLMVP`, `MLBMVP`
  - **Cy Young** — `ALCY`, `NLCY`, `MLBCY`
  - **Rookie of the Year** — `ALROY`, `NLROY`
  - **All-Star** — `MLBASG`, `ALAS`, `NLAS`
  - **Gold Glove** — `ALGG`, `NLGG`, `MLBGG`
  - **Silver Slugger** — `ALSS`, `NLSS`, `MLBSS`
  - **World Series ring** — `WSC`

Plus secondary categories (`ASGMVP`, `WSMVP`, `ALCSMVP`, `NLCSMVP`)
recognized but rolled into the `total_awards` count without surface
display. The seven-bucket aggregate is what the Compare card shows.

**Tradeoff:** if MLB ever renames an id code (rare but not impossible),
that category drops to 0 silently until we patch. We accept this; the
alternative — a fuzzy-match heuristic over award `name` strings — has
worse failure modes.

### 3. Featured matchup: deterministic seeded RNG over wOBA top-10

The home-page Featured Matchup must be **stable across reloads** within
a UTC day so a refresh doesn't shuffle the spotlight, and **rotate**
day-over-day so it doesn't get stale. We hash `(date_iso, season)` →
SHA-256 → take the leading 32 bits as a seed, then index into a top-10
wOBA list pulled from `STATS#<season>#hitting`.

**Why STATS not LEADERBOARD:** there's no pre-computed `LEADERBOARD#`
partition in this build (Phase 5D's leaders route reads STATS directly
and sorts on the fly; same shape works here). Top-10 from ~150-200
qualified hitters costs one Query + in-memory sort, well under 100 ms
p99 — no infrastructure addition warranted.

**Cross-team preference:** if the seeded indices land on two players on
the same team, we walk forward through the seed-derived offset table
up to 3 times looking for a different-team second pick. After 3
retries (extreme edge case) we accept the same-team pair anyway. A
stale or off-season partition (< 2 qualified hitters) returns 503
`data_not_yet_available` with the empty-state UI rendering the count.

### 4. Search: in-memory scan over the 779-row PLAYER#GLOBAL partition

The player table has ~779 rows. Substring + prefix matching in memory
is well under 100 ms p99 at this scale. We do **not** introduce
OpenSearch, an ElasticCache layer, or a name-prefix GSI — those add
operational surface (clusters, IAM, alarms, cost) for a corpus that
fits in 60 KB of JSON.

If the table grows beyond ~5,000 rows we'd revisit. Documented in the
search route module docstring so the next maintainer knows the
tipping point.

### 5. Recap rewrite: structured JSON inside `<json>` tags

The new recap prompt requires Claude to emit:

```json
{
  "headline": "lead with the most distinguishing fact",
  "score_summary": "one-sentence final state",
  "top_performers": [{"name", "team", "line", "context?"}],
  "head_to_head": [{"player_a": {...}, "player_b": {...}, "takeaway"}],
  "tidbits": ["short stat-grounded observations"]
}
```

Wrapped in `<json>...</json>` sentinel tags so a regex extraction is
deterministic even if the model leaks an explanation around the JSON
block. The frontend `parseAnalyticalRecap()` falls back to the legacy
narrative paragraph render if the JSON parse fails — pre-Phase-6
content rows in DynamoDB still display correctly during the
transition window.

**Stat-light scope:** Phase 6 ships the structural rewrite without
pulling DAILYSTATS data into the prompt. The model produces
structurally-correct but stat-thin recaps until Phase 6.1 (or never;
the structural change alone is the meaningful product improvement).

### 6. AI Compare: cache-first, model-swappable, route-shared Lambda

`/api/compare-analysis/players` and `/api/compare-analysis/teams`
share one Lambda with route-dispatch. Each request:

  1. Checks the **AIANALYSIS#<kind>#<season>#<sorted-ids>** cache row.
     If present and TTL not expired, returns it (`cache_hit: true`).
  2. Gathers source data — players: PLAYER#GLOBAL + STATS#<season> +
     AWARDS#GLOBAL; teams: TEAMSTATS#<season>.
  3. Builds a stable JSON-shaped prompt body, invokes Bedrock.
  4. Writes the result with a 7-day TTL.

**Model-swappable:** `BEDROCK_MODEL_ID` env var. Phase 6 ships with
**Claude Haiku 3.5** because the test AWS account hit a daily-token
throttle on Haiku 4.5 during the smoke-test gate (the daily-token
quota is non-adjustable; resets at UTC midnight). Swapping to 4.5
later is one Terraform value change.

**Cache key includes season** so a 2027 rerun of the same player pair
regenerates rather than serving a stale 2026 analysis with a 2027
header.

**Failure modes:**
  - 502 `bedrock_unavailable` on `ThrottlingException` /
    `ServiceUnavailableException` / `InternalServerException`
  - 502 `bedrock_empty` if the model returns empty text
  - 404 `player_not_found` / `team_not_found` if any source row missing
  - Cache write failures don't block the response (we log + serve
    uncached; the next user pays the regeneration cost again)

### 7. Cost projection (Phase 6 delta)

| Item | Monthly |
|------|---------|
| `ingest-player-awards` (4 invocations × ~80 s × 512 MB) | ~$0.02 |
| Bedrock Haiku 3.5 calls (~150 unique compares/mo, 7-day cache) | ~$0.50-1.20 |
| `ai-compare` Lambda compute | <$0.10 |
| AIANALYSIS DDB storage + RCU/WCU | <$0.05 |
| 5 new API GW routes (low traffic) | <$0.10 |
| **Phase 6 delta total** | **~$1-1.50/mo** |

Within the user-stated +$1-3 ceiling. New monthly project total:
**~$26/mo**, dominated still by API WAF + CloudFront ($14).

### 8. Live tab removal

The `/live/:gameId` route powered a per-game live experience that
overlapped substantially with the home-page live scoreboard. Removing
it simplifies the navbar to four entries (Today, Compare, Teams, Stat
Explorer) and reclaims the WebSocket-subscription complexity if we
ever rebuild a similar view.

The home-page LiveGameCard tiles **stay** as a non-interactive
scoreboard surface — the data path is unchanged, only the
click-through is removed. WebSocket pipeline (DynamoDB Streams →
stream-processor → connections table) stays intact for future use.

## Consequences

### Positive

  - **Eight new feature surfaces** without introducing OpenSearch, a
    new charting library, or a write surface.
  - **Cache-first AI** — a recruiter clicking through the same
    compare 5 times pays one Bedrock call total.
  - **Model-swappable** Bedrock integration lets us upgrade Haiku 3.5
    → 4.5 (or fall back to 3) without touching code.
  - **Frontend pages all under 9 KB gzip** — lazy-chunked, no impact
    on home-page LCP.
  - **Search latency p99 < 100 ms** at the current 779-row corpus —
    no infrastructure surface added.

### Negative

  - **Daily-token throttle exposure** for Bedrock. The us-east-1
    account-wide daily-token cap is non-adjustable; if we exhaust it
    via traffic plus generate-daily-content, AI Compare returns 502s
    until UTC midnight. Frontend renders a graceful "Generating
    analysis…" → "Try again shortly" path.
  - **Awards staleness** — weekly cron means a fresh post-season
    award announcement could lag up to 7 days. Acceptable for a
    portfolio dashboard.
  - **Recap stat-thinness** in v6 — until DAILYSTATS hint enrichment
    lands, the analytical recap is structurally clean but uses fewer
    specific player-line numbers than the raw data could support.

### Smoke-test record

The Haiku 4.5 smoke test couldn't complete during Phase 6 build
because the AWS account hit the global cross-region daily-token cap
(`Adjustable: false`, resets nightly UTC). We swapped to Haiku 3.5
(separate quota bucket — same daily cap landed there too within the
same UTC day). Production deploy ships with Haiku 3.5 as the
default model; measurement deferred to a Phase 6.0.1 follow-up
re-run. The model-swappable env var means changing this is a one-
line Terraform edit.

## Future polish

  - **Phase 6.1 — DAILYSTATS recap enrichment.** Pull yesterday's
    boxscore stats into the recap prompt builder so the analytical
    cards have specific player lines to cite. Estimated +80 LOC,
    one extra DDB query per recap call.
  - **AIANALYSIS partition GSI.** If we ever want a "browse all AI
    analyses" surface (we don't, today), a GSI on (kind, season)
    avoids a full-table scan.
  - **Bedrock latency p95 SLO alarm.** Haiku is fast (1-3 s typical)
    but a long tail could surface as "Generating analysis…" hanging
    forever. Wire a CloudWatch alarm on `ai-compare` Duration p95 > 8 s
    once we have a baseline measurement.
  - **Search relevance ranking.** Today the typeahead is alphabetical
    after a prefix-vs-substring split. A more mature ranker would
    weight by recent activity (recent boxscore appearance, recent
    AS / MVP votes) — out of scope for Phase 6.

---

## Phase 6.1 Amendment — three real bugs, fixed (Apr 2026)

User feedback after the Phase 6 deploy surfaced three real bugs.
Phase 6.1 fixes Bug 1 and Bug 3 directly and adds a build-time env
config hardening that incidentally surfaced as a blank-page during
the deploy. Bug 2 (team AI analysis) is deferred to Phase 6.2 — see
the AWS Bedrock quota footnote below.

### Bug 1 — Featured matchup reshape (players → teams)

**Symptom:** Phase 6 shipped the home-page Featured Matchup of the
Day as a two-player card. The user feedback was that it should be a
two-**team** card with a click-through to `/compare-teams`, not
`/compare-players`. The framing reads better editorially as
"today's premier cross-league standings duel" and the click-through
is a more natural fit for a casual viewer.

**Heuristic chosen: AL #1 vs NL #1.** Considered four candidates
during the surface-for-approval gate (AL/NL leaders, biggest run
differential, highest-OPS vs lowest-ERA, closest divisional rivals).
AL/NL leaders won because it has the cleanest editorial framing,
naturally rotates as standings shift over the season, guarantees
cross-team without an extra check, and the click-through is
unambiguous.

**Implementation:**

  - `functions/api_players/routes/featured_matchup.py` rewritten.
    Reads `STANDINGS#<season>`, partitions by `league_id` (103=AL,
    104=NL), picks the team with the lowest `league_rank` per
    league. Date-seeded RNG breaks ties when multiple teams share
    rank 1. Enriches each pick with `TEAMSTATS#<season>` for OPS /
    ERA / WHIP highlight stats.
  - 503 `data_not_yet_available` if STANDINGS is empty or one
    league has no entries.
  - Cache header `max-age=3600` (stable per UTC day).
  - Frontend: `FeaturedMatchupSection` rewritten. Two team cards
    side-by-side with logo, league badge, W-L, run differential,
    highlight stats. Click-through to `/compare-teams?ids=<a>,<b>`.
  - Live verified: NYY (AL) vs ATL (NL) — both true standings
    leaders for the slice that ran.

### Bug 3 — Player Compare picker (curated → search-driven)

**Symptom:** Phase 6 left the on-page picker as the original
`MatchupPicker`, which iterates the 4-entry hardcoded
`FEATURED_COMPARISONS` constant. Users without URL knowledge could
only click those four chips. The page itself supported 2-4 players
via the `?ids=` URL param (also Phase 6) but had no UI surface to
add an arbitrary player.

**Implementation:**

  - New `PlayerSearchPicker` component. Three rows:
    1. Selected-player chips with × remove (disabled at `MIN_IDS=2`).
    2. Search input — 200 ms debounce → `/api/players/search` (the
       in-memory scan endpoint already shipped in Phase 6). Dropdown
       of up to 10 hits. Excludes already-selected ids from the
       result list. Disabled when at `MAX_IDS=4`, with a capacity-
       hint placeholder.
    3. "Quick picks" preset row — the original `FEATURED_COMPARISONS`
       chips kept as one-click presets. Replaces the entire id list
       (rather than appending) so the curated workflow stays clean.
  - `PlayerComparePage` integrates the new picker via the existing
    `?ids=` URL state — no schema change, deep links keep working.
  - Selected-chip display reuses the `compare` query response —
    means a freshly added id flashes "Player #<id>" until the next
    fetch resolves (~one render). Pre-fetching metadata in the
    picker would have required a separate per-slot API call;
    accepted the brief flash for code simplicity.
  - Search results are excluded if already selected so users can't
    pick the same player twice.

### Build-time env-config hardening (.env.production)

**Symptom:** The Phase 6.1 deploy shipped a bundle that threw
`Missing required environment variable VITE_API_URL` on first load,
rendering a blank `<div id="root">`. Diagnosis confirmed delivery
was healthy — S3 had the new bundle, CloudFront served it — but the
JS itself ran the boot-time `required()` check from `lib/env.ts`
and threw because `import.meta.env.VITE_API_URL` was `undefined` at
build time.

**Root cause:** The manual deploy procedure ran a bare
`npm run build` without prefixing the env vars. Vite's mode for
`npm run build` defaults to `production`, which loads
`.env.production` + `.env.local` — neither of which existed on
disk. `.env.development` is loaded only in `dev` mode. The CI
deploy workflow (`.github/workflows/frontend-deploy.yml`) sets the
env vars in its job env so it gets this right; manual deploys
bypassed that.

**Fix:** Added `frontend/.env.production` checked into the repo
with the production CloudFront URLs:

```
VITE_API_URL=https://d17hrttnkrygh8.cloudfront.net
VITE_WS_URL=wss://cw8v5hucna.execute-api.us-east-1.amazonaws.com/production
VITE_HIDE_DEMO_BADGES=false
```

A clean-checkout `npm run build` now picks the URLs up
automatically. CI workflow still sets the same values in its job
env (defense in depth — a config drift check would catch a future
divergence). Fixed bundle verified live: `index-PE7CJieW.js`
contains both URLs inlined; live page renders.

**Trade-off:** the production CloudFront URL is now duplicated in
two places (`.env.production` and `frontend-deploy.yml`). If the
API distribution ever moves, both files need updating. README's
deploy walkthrough was already pointing at the right URL; nothing
to update there.

### Bug 2 — Deferred to Phase 6.2 (Bedrock quota blocker)

Bug 2 (team AI analysis section on `TeamComparePage` and
`TeamDetailPage`) was scoped into Phase 6.1 originally but
gated on a Bedrock smoke-test. The smoke-test could not be
completed because the test AWS account hit the **non-adjustable
on-demand inference daily-token cap** for every Anthropic model
tried (Haiku 3, Haiku 3.5, Haiku 4.5 — same throttle across all
three). Confirmed via:

  - `aws service-quotas` API rejected an increase request — the
    relevant daily-token quotas (`L-A2E1E2DD`, `L-B5C049AE`) are
    `Adjustable: false`. Adjustable per-minute quotas already
    default to 5 M TPM (well above what we need).
  - Tried the base Haiku 3 model (no cross-region prefix) as a
    fallback bucket; same throttle.

**The only path forward is a manual AWS Support case** to lift
the on-demand daily-token cap. Filed outside this session;
24-48h approval window. Bug 2 ships in Phase 6.2 once approved.

In the meantime, the `/api/compare-analysis/players` and
`/api/compare-analysis/teams` endpoints (shipped in Phase 6) work
when the daily quota is fresh — so the API surface is ready, just
no frontend integration. The handler + cache + tests are all in
place; the frontend integration is a small UI change once Bedrock
is healthy.

### Test + lint status

  - Backend: 342 / 342 pass (was 341; +6 new featured-matchup
    tests reshape, -5 old player-shape tests).
  - Frontend: 214 / 214 pass (was 213; +1 new search-picker
    integration test).
  - Lint clean. Production build clean.
  - Bundle delta: `PlayerComparePage` 8.60 KB → 12.88 KB (+4 KB
    gross / +1.3 KB gzip) for the search picker. Home bundle
    unchanged at ~327 KB.

### Live verification (post-fix)

  - All five frontend routes return HTTP 200.
  - Live JS bundle (`index-PE7CJieW.js`) has both production URLs
    inlined.
  - `/api/featured-matchup` → NYY (AL) vs ATL (NL) — true standings
    leaders.
  - `/api/players/search?q=ohtani` → Shohei Ohtani — confirms the
    search-picker dropdown will populate correctly.
