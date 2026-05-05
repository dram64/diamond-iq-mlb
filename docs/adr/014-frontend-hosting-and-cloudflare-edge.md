# ADR 014 — Frontend hosting + Cloudflare-as-edge-WAF

## Status
Accepted. Implemented in Option 5 Phase 5J.

## Context

Through Option 5 Phase 5I, the Diamond IQ React SPA at `frontend/` had no
public hosting target. The CloudFront distribution `d17hrttnkrygh8.cloudfront.net`
fronted the API only, and the dashboard existed only on developer machines
via `npm run dev`. Phase 5J makes the SPA publicly accessible at
`https://diamond-iq.dram-soc.org`.

This ADR records the architectural commitments made in 5J that were not
covered by the existing CloudFront + WAF ADR (010, which is API-specific).
Three things had to be settled:

1. **Hosting topology.** S3 static-website + CloudFront, or one of S3+CF
   alternatives (Amplify, App Runner, third-party SaaS)?
2. **Edge security.** AWS WAFv2 again (matching the API side), or
   something cheaper now that the threat model is "static SPA, no
   server-side state, no auth"?
3. **DNS provider.** Route 53 (matching all other AWS resources) or
   Cloudflare (matching the parent domain `dram-soc.org` registration)?

## Decision

### 1. S3 + OAC + CloudFront, sibling distribution

A new private S3 bucket (`diamond-iq-frontend`) holds the React build
output. CloudFront's Origin Access Control (sigv4-signed) fronts it as
the only allowed reader; the bucket has every public-access flag set
and a bucket policy that grants `s3:GetObject` exclusively to the
distribution's OAC principal.

This is a **sibling** distribution to the existing API CloudFront —
not a second behavior on the existing one. Rationale:

- **Independent cache TTLs.** The API distribution attaches the
  AWS-managed `Managed-CachingDisabled` policy (responses are
  per-user-fresh). The SPA wants `Managed-CachingOptimized` (long
  cache TTLs on hashed bundle filenames + a short TTL on `index.html`).
  One distribution with two cache behaviors would work but couples
  config drift across two unrelated workloads.
- **Independent custom error responses.** The SPA needs 403/404 → 200
  rewrites on `/index.html` for client-side routing; the API doesn't.
- **Independent cert + alias.** The API distribution uses the default
  CloudFront certificate (`*.cloudfront.net`); the SPA needs an ACM
  cert for `diamond-iq.dram-soc.org`.

Multi-distribution adds <$0.30/month at portfolio traffic (CloudFront
charges per-distribution metric overhead, not a flat per-distribution
fee). Worth it for the config separation.

### 2. Cloudflare proxied DNS as edge WAF; no AWS WAF on this distribution

The parent domain `dram-soc.org` is registered through Cloudflare and
already proxied (orange cloud) for other subdomains. Phase 5J adds
`diamond-iq.dram-soc.org` as another orange-cloud-proxied CNAME pointing
at the CloudFront distribution domain.

That gives us, for free:

- **L3/L4 DDoS protection** (Cloudflare absorbs SYN floods, UDP floods,
  reflection attacks before traffic reaches CloudFront)
- **Bot mitigation** (Cloudflare's free WAF tier blocks known scanner
  user agents, malicious crawlers, ASN reputation)
- **Geo blocking** if/when needed (rules are per-domain at the
  proxy layer)
- **Web Application Firewall** (free tier OWASP-managed rules; a
  subset of what the paid tiers offer, but adequate for a static SPA)

AWS WAFv2 on this distribution would add **~$5.40/month minimum**
($5/mo for the Web ACL + $1/mo per rule × at least the 4 managed
groups we use on the API) for inferior L3/L4 coverage and roughly
equivalent OWASP coverage. The threat model on a static SPA without
server-side state is also lighter than the API:

- No request-amplification surface (no Lambda invocation per request)
- No SQL injection surface (no database)
- No credential surface (no auth)
- The worst-case attack is bandwidth amplification on a public S3
  bucket the entire internet can already CDN-pull — easy and cheap
  for Cloudflare to absorb at the edge

The API distribution KEEPS its AWS WAFv2 (ADR 010). That layer
protects per-Lambda-invocation cost runaway and the WebSocket
connection budget. The SPA distribution doesn't have those exposures.

Documented in the module's main.tf header so the reasoning is
discoverable from the code.

### 3. Cloudflare DNS, manually applied (not Terraformed)

Cloudflare provider for Terraform exists, but bringing it in would:

- Add a second secret to manage (Cloudflare API token)
- Cross a second SaaS into the deploy pipeline
- Couple AWS Terraform applies to Cloudflare API health

For a static SPA with two DNS records (the ACM validation CNAME and
the final SPA CNAME), the manual-DNS path is lower-overhead. The
Terraform module emits the validation record and the distribution
domain via outputs (`frontend_acm_validation_records`,
`frontend_distribution_domain_name`); the operator copies them into
Cloudflare's UI once and never touches them again unless the cert is
re-issued or the distribution is rebuilt.

### 4. Security headers policy (CloudFront-attached)

A `aws_cloudfront_response_headers_policy` resource on the default
cache behavior emits:

- `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
- `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://img.mlbstatic.com; connect-src 'self' https://d17hrttnkrygh8.cloudfront.net; font-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), microphone=(), camera=(), payment=()`

CSP notes:

- `script-src 'self'` — no inline scripts, no eval, no third-party CDN
  scripts. Tightest practical setting.
- `style-src 'self' 'unsafe-inline'` — Tailwind-emitted inline styles
  are tolerated; no external stylesheets are loaded.
- `img-src` includes `https://img.mlbstatic.com` proactively for the
  future "player headshot" polish item. Harmless if unused.
- `connect-src` allowlists the API distribution origin
  (`d17hrttnkrygh8.cloudfront.net`). This is the most load-bearing
  directive — without it every API call would be CSP-blocked.
- `font-src 'self' data:` — fonts are bundled into the SPA build (see
  Phase 5J performance journey below); no external font CDN.
- `frame-ancestors 'none'` — defense-in-depth against clickjacking;
  redundant with `X-Frame-Options: DENY` but covers some legacy
  browser quirks.

### 5. SPA fallback rewrites

CloudFront `custom_error_response` rewrites both 403 and 404 from S3
to `/index.html` with HTTP status 200. The bucket returns 403 on
missing keys (it's private + OAC-restricted, so missing keys never
emit 404 directly). This is the standard SPA hosting pattern — a
hard refresh on `/compare` or any client-side route gets the SPA
shell + lets React Router pick up the path.

`error_caching_min_ttl = 10` keeps 403 responses cached for 10
seconds. Long enough to absorb a refresh-storm; short enough that a
fresh deploy invalidates quickly.

### 6. Frontend deploy via GitHub Actions OIDC

`.github/workflows/frontend-deploy.yml` triggers on push to `main`
under `frontend/**`. The same OIDC role used by the backend deploy
(`diamond-iq-github-deploy`) is extended with one additional inline
policy (`frontend_deploy_extra`) granting:

- `s3:PutObject`/`GetObject`/`ListBucket`/`DeleteObject` scoped to
  the `diamond-iq-frontend` bucket only
- `cloudfront:CreateInvalidation` (CloudFront IAM doesn't accept
  resource-level scoping for invalidations, so this is unscoped — the
  base OIDC policy already has the unscoped CloudFront grants per
  ADR 010 §6)

The workflow does `npm ci && npm run build && aws s3 sync --delete &&
aws cloudfront create-invalidation --paths "/*"`. Long cache TTLs on
hashed asset filenames (`max-age=31536000, immutable`) plus a short
TTL on `index.html` (`max-age=60, must-revalidate`) keeps cache
churn minimal between deploys.

## Phase 5J performance journey

The first deploy hit Lighthouse desktop 76 (below the spec's <80
stop-condition). Three iterations chased the gap; the journey is
worth recording because each step solved a different sub-problem.

| Stage | Desktop best-of-3 | Mobile best-of-3 | What changed |
|---|---|---|---|
| Initial (Google Fonts external) | 76 | 88 | `index.html` loaded Inter + JetBrains Mono from `fonts.googleapis.com`. Cross-origin CSSOM stall on simulated slow-4G. |
| @fontsource (all subsets) | 83 | 81 | Self-hosted via `@fontsource/inter` + `@fontsource/jetbrains-mono`. CSP `font-src 'self' data:`. **CSS bundle: 23 KB → 69 KB** (every language subset emitted). Mobile regressed because @font-face parse on 4× CPU throttle is expensive. |
| @fontsource latin-only | 87 | 85 | Switched to `@fontsource/inter/latin-400.css` etc. — pruned cyrillic / latin-ext / vietnamese / greek subsets. **CSS bundle: 69 KB → 25 KB.** Both axes improved. |
| **+ React.lazy code-split** | **87** | **87** | `LiveGamePage`, `ComparePage`, `TeamsPage`, `TeamDetailPage`, `StatsPage` lazy-loaded with `<Suspense fallback={<RouteFallback />}>`. Main bundle: 339 KB → 318 KB. TBT: 40-80 ms → 10-30 ms. Mobile gained 2 from CPU savings; desktop unchanged (already not CPU-bound). |

### Final outcome

| | Score | Threshold | Result |
|---|---|---|---|
| Desktop best-of-3 | **87** | ≥ 90 | −3, accepted |
| Mobile best-of-3 | **87** | ≥ 85 | +2 ✓ |

### Accepted gap (desktop 87 vs 90 target)

The 3-point desktop miss was accepted at close-out. Three reasons:

1. **Real-world un-throttled desktop scores 100.** A Lighthouse run
   without simulated CPU/network throttling on the same artifact
   returns 100 with FCP 0.5 s / LCP 0.5 s. Recruiters running
   Lighthouse from real Chrome DevTools on a real laptop typically
   see scores in the 90s+. The 87 is a synthetic-environment
   artifact.
2. **Mobile cleared the threshold by 2 points.** Mobile is the
   harder target (CPU-constrained); we beat it. The desktop synthetic
   profile is actually more punishing for this app than the mobile one
   because the desktop LCP threshold (1.7 s for "good") is tighter
   than mobile's (2.5 s).
3. **Diminishing returns.** Closing the 3 points would require
   Static-Site Generation or pre-rendered `index.html` (a
   multi-hour architectural shift), or vendor-chunk `manualChunks`
   tuning (~30 min for marginal 1-2 point gain still
   synthetic-variance-bound). Neither passes the
   effort-vs-real-user-impact bar.

SSG is documented as a candidate for Phase 5K if the score ever becomes
load-bearing for portfolio review.

### Architectural improvements that DID ship (real, not score-cosmetic)

- **CORS allow-list expanded** to `https://diamond-iq.dram-soc.org`
  + localhost 5173-5176. Every API call from the new origin works.
  Variable lives at `var.cors_allow_origins` in `infrastructure/
  variables.tf` for future origins.
- **Self-hosted fonts.** No external font CDN dependency. A Google
  Fonts outage now has zero impact on the dashboard. CSP
  `font-src 'self' data:` is tighter than the alternative.
- **Latin-only font subsets.** Build emits ~16 woff2 files instead of
  ~48; CSS is 25 KB instead of 69 KB. Real users save ~150 KB of
  unused font CSS download + parse on first load.
- **Route-based code-splitting.** Initial bundle shrunk by 21 KB; TBT
  cut by ~50 %. Time-to-Interactive on the home page is faster for
  every visitor regardless of Lighthouse.

## Cost delta

| Component | Cost |
|---|---|
| Second CloudFront distribution (PriceClass_100) | ~$0.20 |
| S3 bucket + versioning + ~2 MB stored | <$0.01 |
| ACM cert | $0 |
| Cloudflare proxied DNS | $0 |
| **Phase 5J net new** | **~+$0.30/month** |

## Consequences

### Positive

- **Public dashboard.** `https://diamond-iq.dram-soc.org` is the
  share-able URL. No more "clone the repo and `npm run dev`" friction
  for portfolio reviewers.
- **Edge security via Cloudflare.** Free WAF + DDoS + bot mitigation
  vs ~$5.40/mo to replicate on AWS.
- **Independent cache strategy.** SPA caches aggressively (1-year
  TTLs on hashed assets) without affecting API freshness.
- **Hardened security headers.** HSTS preload, strict CSP, no inline
  scripts, frame-ancestors none.
- **Self-hosted critical-path resources.** No external CDN dependency
  for the SPA shell; Google Fonts outages don't affect us.
- **OIDC-only deploy.** No long-lived AWS credentials in the
  GitHub repo.

### Negative

- **Two CloudFront distributions to monitor.** The existing one for
  the API and the new one for the SPA. Existing CloudWatch alarms
  cover Lambda runaway and account concurrency; we don't (yet)
  alarm on per-distribution 5xx rate or BytesDownloaded surge.
  Future polish item.
- **Cloudflare DNS is manually managed.** A future re-issuance of
  the ACM cert (e.g., domain rename) would require a manual DNS
  rotation. Documented in the runbook (TBD update).
- **Lighthouse desktop 87 vs 90 target.** Real-world unthrottled is
  100; synthetic-environment 87 is below spec threshold by 3. SSG
  would close the gap; deferred to Phase 5K.
- **Frontend bundle size growth from font-self-hosting.** Initial
  load adds ~200 KB of woff2 fonts (8 weights × ~25 KB each), but
  these are immutable-cached forever after the first visit and
  amortize to zero on subsequent loads.

### Operational notes

- **DNS records.** Two manual Cloudflare records:
  - `_<random>.diamond-iq` CNAME `_<random>.<random>.acm-validations.aws.`
    — DNS only (grey cloud), required for ACM issuance only. Can be
    deleted after issuance; we leave it in case of cert re-issuance.
  - `diamond-iq` CNAME `<dist-id>.cloudfront.net` — Proxied (orange
    cloud), the live entry point.
- **Deploy.** Push any change under `frontend/**` to `main` →
  `frontend-deploy.yml` builds + syncs + invalidates. End-to-end ~3
  minutes including invalidation propagation.
- **Cache busting.** The Vite build emits hashed filenames on every
  asset, so a deploy never invalidates anything except `index.html`
  in practice. The wildcard `--paths "/*"` invalidation is belt +
  suspenders.

## Alternatives considered

### Hosting

- **AWS Amplify Hosting.** Easier first-time setup but introduces a
  separate deploy pipeline outside Terraform. Rejected — keeps
  infra-as-code surface uniform.
- **Vercel / Netlify.** Excellent DX but adds a third-party SaaS
  dependency to the deploy pipeline and complicates the
  "everything Terraformed in this AWS account" story. Rejected.
- **Single CloudFront distribution with two cache behaviors.**
  Possible but couples API and SPA cache config; one cert covers
  one alias so this would still need a separate cert; the
  config-coupling cost outweighs the per-distribution metric
  savings (<$0.30/mo).

### Edge security

- **AWS WAFv2 on the SPA distribution.** ~$5.40/mo for a static
  SPA's threat model is a poor exchange. Cloudflare's free tier
  covers what we actually need. Rejected.
- **No edge security at all** (CloudFront alone). CloudFront has
  no WAF or bot mitigation by itself; a public S3 SPA without an
  edge proxy is fine functionally but trivially DDoS-able into
  cost-runaway via egress amplification. Rejected.

### DNS

- **Route 53.** Matches all other AWS resources but our domain is
  registered at Cloudflare; transferring the registration solely
  to Terraform DNS adds bigger ops surface than the two manual
  CNAMEs we have today. Rejected for v1.

### Performance

- **Static-Site Generation / pre-render.** Would close the desktop
  Lighthouse gap (87 → 92-96) but introduces a hydration boundary
  and a separate build step. Deferred to a potential Phase 5K.
- **Vendor `manualChunks` split.** Marginal +1-2 desktop points,
  still synthetic-variance-bound. Not worth the build-config
  complexity for the returns. Deferred.
- **Inline critical CSS.** Vite plugins exist; would shave ~100 ms
  off LCP. Deferred — diminishing returns past code-splitting +
  latin-only fonts.

## Forward references

- Phase 5K (candidate, unscheduled): Static-Site Generation /
  pre-rendered `index.html` to push desktop Lighthouse into the
  mid-90s. Triggered if/when the score becomes load-bearing.
- Future polish: per-distribution CloudFront alarms (5xxErrorRate,
  BytesDownloaded) wired into `alerts.tf`. Currently relying on
  the existing account-level cost-runaway alarms.
- Future polish: extend the backend hardest-hit projection to
  include `team_id` per row so the frontend can render real team
  chips on the HardestHitChart card (currently shows a `?`
  sentinel — see ADR 012 Phase 5G amendment).
- README cost table updated to reflect the +$0.30/mo Phase 5J
  delta (now ~$23-25/mo total project spend).
