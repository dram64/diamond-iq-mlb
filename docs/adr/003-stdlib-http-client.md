# ADR 003 — `urllib.request` over `httpx` / `requests`

## Status
Accepted

## Context
The MLB Stats API client lives in `functions/shared/mlb_client.py`.
Three reasonable choices for the HTTP layer:

1. **`requests`** — the de facto Python HTTP library. Sync, ergonomic.
2. **`httpx`** — modern, sync + async, HTTP/2 support.
3. **`urllib.request`** — Python stdlib. No extra dependency.

## Decision
Use **`urllib.request`** (stdlib).

## Consequences

### Positive
- Zero runtime dependencies. The Lambda zip is just our handful of
  Python files. No `pip install` step in the deploy build.
- Smallest possible cold start. Lambda imports only stdlib modules,
  which the runtime has already loaded into bytecode cache.
- One fewer attack surface — a CVE in `requests` or its transitive
  deps doesn't affect us.
- We control the abstraction. Custom exception types (`MLBAPIError`,
  `MLBNotFoundError`, `MLBTimeoutError`) sit on top of stdlib without
  fighting any third-party error hierarchy.

### Negative
- Less ergonomic than `requests`. Connection pooling, retries, and
  HTTP/2 are not built in. We don't need them at our scale (one
  request per minute), but if MLB rate-limits us in the future and
  retry-with-backoff becomes important, we'll have to write or import
  it.
- The `responses` mocking library doesn't intercept `urllib`. Tests
  use `unittest.mock.patch("urllib.request.urlopen")` directly. This
  is functional but slightly verbose vs `responses.add(...)`.

### When to revisit
- We need HTTP/2 (MLB doesn't currently require it).
- We add a Lambda that does parallel requests at high volume and
  benefits from `httpx`'s `AsyncClient` connection pooling.
- We need OAuth flows or other libraries that bind to `requests`.
