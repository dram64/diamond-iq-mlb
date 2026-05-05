# ADR 001 — Single-table DynamoDB design

## Status
Accepted

## Context
The backend stores baseball game data and is expected to grow new
entities (teams, players, leaderboards) over time. Two storage shapes
were considered: per-entity tables (one for `games`, one for `teams`,
etc.) or a single table that holds everything keyed by composite
partition / sort keys.

The known access patterns at this stage are tiny:
- `list_todays_games(date)` — get all games for a date
- `get_game(game_pk, date)` — get one game

Future patterns will likely include:
- `list_team_games(team_id, season)`
- `get_player(player_id)`
- `list_leaders(category, season)`

## Decision
Use a **single DynamoDB table** with composite primary key
`(PK, SK)` and prefix-based partitioning. Current schema:

| Entity | PK | SK |
| --- | --- | --- |
| Game | `GAME#<yyyy-mm-dd>` | `GAME#<game_pk>` |

Future additions can use new prefixes (`TEAM#`, `PLAYER#`, etc.) in
the same table without schema migrations or new infrastructure.

## Consequences

### Positive
- One table to provision, monitor, back up, and pay for. PAY_PER_REQUEST
  + 25 GB free tier easily covers the project.
- Adding new entity types is a code-only change.
- Future GSIs (e.g. for "all games by team") are added incrementally
  without touching existing data.
- Consistent IAM scoping — Lambdas need access to one table ARN, not
  a growing list.

### Negative
- Single-table designs need careful documentation of PK/SK conventions
  (this ADR + [docs/architecture.md](../architecture.md)) so future
  contributors don't put the wrong shape of data in the wrong key
  space.
- DynamoDB scans across all entity types are expensive; we have to
  query specific PK prefixes intentionally. Mitigation: never scan
  in production code.
- Mixing entity types in one table makes per-entity TTL slightly
  awkward — TTL is a single attribute applied table-wide. We address
  this by every item carrying a `ttl` attribute (live games get 7
  days; entities that should persist get no `ttl` attribute and never
  expire).

### Follow-ons
- When a second entity type is introduced, add a section to
  [docs/architecture.md](../architecture.md) describing its PK/SK
  conventions.
- Revisit this ADR if access patterns push read costs above ~$5/month
  consistently — that's the threshold where a second table for hot
  data might pay for itself in operational simplicity.
