# ADR 004 — Two-date ingestion window

## Status
Accepted

## Context
The first version of `ingest_live_games` queried MLB's schedule for a
single date computed as `date.today()` — which inside a Lambda is the
**UTC** date. This produced no live games during a real test window
even though MLB.com clearly showed in-progress games.

Investigation: an MLB game played in Pacific time at 7:00 PM has
`gameDate: "2026-04-25T02:00:00Z"`. The MLB schedule API groups it
under local date `2026-04-24` (their server zone is ET-anchored), but
its UTC date is `2026-04-25`. After UTC midnight crosses, our handler
asked MLB for `?date=2026-04-25` and got tomorrow's slate (all in
`Preview` status), missing the games actually being played right then.

Two possible fixes:
1. Anchor the query to ET (`America/New_York`) since MLB groups by ET.
2. Query both today UTC and yesterday UTC on every invocation and
   merge.

## Decision
Query **both today UTC and yesterday UTC** on every ingest invocation.
Combine the live games from both responses, deduplicate by `gamePk`,
write to DynamoDB.

## Consequences

### Positive
- Correct at every wall-clock time. Late East Coast games, Pacific
  games, Hawaii games, doubleheaders that span UTC midnight — all
  covered. No edge case for any specific timezone.
- No timezone library dependency (`zoneinfo` would work but adds
  reasoning surface).
- Resilient: if one date's MLB query fails (transient 5xx), the other
  date's results are still processed. Only when *both* fail does the
  invocation report `ok=False`.

### Negative
- Two MLB API calls per minute instead of one. ~86k requests/month
  total to MLB Stats API. The API is unauthenticated and has no
  documented rate limit at this volume.
- Lambda duration increases from ~70 ms to ~1.3 s when there are
  live games (12 DynamoDB writes + 2 MLB calls). Memory usage rose
  from 70 MB to 93 MB. Both still well under the configured limits
  (60 s timeout, 512 MB memory).
- The summary log now includes `dates_queried: ["yesterday", "today"]`
  so observability is correct.

### When to revisit
- If MLB introduces a rate limit that bites at ~2 req/min, switch to
  ET-anchored single query.
- If we add international leagues that play across more than 24 hours
  of UTC offset (NPB, KBO), expand to a 3-day window or use league-
  specific timezone anchoring.
