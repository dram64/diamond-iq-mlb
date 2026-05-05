# Credits & attribution

## MLB team logos

The 30 cap-on-light SVG logos under
[`frontend/public/images/teams/`](frontend/public/images/teams/) are
sourced from MLB's own static CDN at
`https://www.mlbstatic.com/team-logos/team-cap-on-light/{teamId}.svg`,
and are served from this repo's static directory rather than hot-linked
to the MLB CDN.

### Use

The logos are rendered exclusively to **identify each MLB club in its
own scoring data** — on game cards, scoreboards, and live-game headers,
alongside the team's own scores and stats. They are not used as
decorative or unrelated marketing imagery.

### Industry precedent

This pattern matches the use of MLB team logos on widely-referenced
public baseball-analytics tools, including Baseball Savant
([baseballsavant.mlb.com](https://baseballsavant.mlb.com/)),
Statcast leaderboards, FanGraphs ([fangraphs.com](https://www.fangraphs.com/)),
Baseball Reference, and dozens of other public-facing analytics sites
that present MLB scoring data alongside team identifiers.

### Ownership and removal

All MLB team logos remain the trademark and intellectual property of
their respective Major League Baseball clubs and Major League Baseball
Properties. Use here is for editorial identification only on a
non-commercial portfolio project. **If a Major League Baseball club or
MLB Properties requests removal of any team logo from this project,
remove it immediately** and either restore the abbreviation-only
fallback chip (already supported in code) or substitute a generic
placeholder. The fallback path is implemented in
[`frontend/src/components/primitives/TeamChip.tsx`](frontend/src/components/primitives/TeamChip.tsx)
and triggers automatically on any image load failure.

## Project description

This is a personal portfolio project demonstrating cloud engineering,
data ingestion, and AI-integration skills. It is not a commercial
product, is not intended for monetization, and is publicly viewable
solely to demonstrate technical capabilities to potential employers.
