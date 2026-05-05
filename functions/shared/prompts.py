"""Prompt templates for daily content generation.

Three content types — recap (yesterday's Final game), preview (today's
Preview game), featured (extended analysis on the day's top games).
All three share a writer persona, a strict no-fabrication rule, and a
shared anti-cliche list.

Templates use Python str.format placeholders. Callers must supply
every named field; missing-fact sections should be omitted by the
caller rather than passed as empty strings, since Claude treats
"recent_form: " as a fact ("their recent form is nothing").
"""

from __future__ import annotations

ANTI_CLICHE_PHRASES: tuple[str, ...] = (
    "left it all on the field",
    "battle of attrition",
    "gritty performance",
    "wanted it more",
    "punched their ticket",
    "in the books",
    "showed up to play",
    "clutch when it mattered most",
    "a tale of two halves",
    "all the marbles",
)

_VOICE = (
    "You are a professional baseball writer for an analytics-leaning publication. "
    "Your prose is informed, specific, and economical. You assume the reader knows "
    "how baseball works and would rather hear what was distinctive about a game than "
    "be told a game happened. You never fabricate facts: if a detail is not present "
    "in the input, you do not invent it, and you do not paper over a missing detail "
    "with vague language designed to sound knowledgeable. You especially avoid the "
    "following clichés and constructions like them: "
    + "; ".join(f'"{p}"' for p in ANTI_CLICHE_PHRASES)
    + "."
)

# ── RECAP ─────────────────────────────────────────────────────────────

# prose). The model emits a JSON object inside <json>...</json> sentinel tags
# so the frontend can parse a deterministic shape:
#
#   {
#     "headline": str,                    // ≤ 16 words, lead-with-the-fact
#     "score_summary": str,               // one short sentence with the score
#     "top_performers": [                 // 1-3 items
#       {"name": str, "team": str,
#        "line": str,                     // "3-for-4, HR, 2 RBI"
#        "context": str | null}           // optional one-liner of significance
#     ],
#     "head_to_head": [                   // 0-1 items (often the marquee duel)
#       {"player_a": {"name": str, "line": str},
#        "player_b": {"name": str, "line": str},
#        "takeaway": str}                 // one analytical sentence
#     ],
#     "tidbits": [                        // 0-3 items, ≤ 22 words each
#       str                               // a stat-grounded observation
#     ]
#   }
#
# Tidbits stay short and verifiable from the input. The model does not invent
# season-context numbers ("third double-digit-K game of the season") unless
# the template explicitly supplies them. The renderer treats the entire
# response as a stable contract; if JSON parsing fails it falls back to
# rendering the raw text as a paragraph (legacy narrative recap rows).
RECAP_SYSTEM = (
    _VOICE + " Produce an analytical, numbers-driven recap of a single Major League "
    "Baseball game in structured JSON. Lead with the most distinguishing statistical "
    "fact from the input. Do not write narrative paragraphs. Do not invent stats, "
    "season context, projections, or player names that are not in the input. If a "
    "field has no data, return an empty list for that field. Keep prose elements "
    "tight: the headline must be at most 16 words; each tidbit at most 22 words. "
    "Avoid hype words and exclamation points. Do not address the reader. "
    "Emit exactly one JSON object inside a single <json>...</json> tag pair, "
    "with these keys: headline (string), score_summary (string), top_performers "
    "(array of {name, team, line, context?}), head_to_head (array of "
    "{player_a:{name,line}, player_b:{name,line}, takeaway}), tidbits (array of "
    "strings). Output only the <json> block — no preamble, no explanation."
)

RECAP_TEMPLATE = (
    "Game: {away_full_name} ({away_score}) at {home_full_name} ({home_score})\n"
    "Final status: {detailed_state}\n"
    "Date: {date}\n"
    "Venue: {venue_or_unknown}\n"
    "{linescore_block}{top_performers_block}"
)

# ── PREVIEW ───────────────────────────────────────────────────────────

PREVIEW_SYSTEM = (
    _VOICE + " Write a brief preview of an upcoming Major League Baseball game. The preview "
    "should be two to three short paragraphs, roughly 80–120 words. Focus on what "
    "makes this matchup interesting today: the venue, the rivalry, the time of year. "
    "Do not predict a final score, do not predict any specific player's performance, "
    "and do not invent starting pitchers or lineups. If recent_form data is supplied, "
    "you may reference it; if it is not, omit any reference to recent results."
)

PREVIEW_TEMPLATE = (
    "Matchup: {away_full_name} at {home_full_name}\n"
    "First pitch (UTC): {start_time_utc}\n"
    "Venue: {venue_or_unknown}\n"
    "{recent_form_block}"
)

# ── FEATURED ──────────────────────────────────────────────────────────

FEATURED_SYSTEM = (
    _VOICE + " Write an extended analysis of one of today's marquee Major League Baseball "
    "matchups. The piece should be four to five paragraphs, roughly 250–350 words. "
    "Develop a single thread — a divisional storyline, a stadium quirk, a series "
    "context — and stay with it. Do not predict a final score and do not predict any "
    "specific player's performance. If recent_form data is provided, weave it in; "
    "otherwise, build the analysis from the matchup itself, the date, and the venue, "
    "and do not pretend to recent context you were not given."
)

FEATURED_TEMPLATE = (
    "Featured matchup: {away_full_name} at {home_full_name}\n"
    "First pitch (UTC): {start_time_utc}\n"
    "Venue: {venue_or_unknown}\n"
    "Same-division game: {same_division}\n"
    "{recent_form_block}"
)


def render_linescore_block(linescore: dict[str, object] | None) -> str:
    """Format a linescore dict for inclusion in the recap prompt.

    Returns an empty string when the linescore is missing — callers should pass
    that through verbatim so the prompt does not contain empty fields.
    """
    if not linescore:
        return ""
    parts: list[str] = []
    inning = linescore.get("inning")
    if inning is not None:
        parts.append(f"Final inning reached: {inning}")
    away_runs = linescore.get("away_runs")
    home_runs = linescore.get("home_runs")
    if away_runs is not None and home_runs is not None:
        parts.append(f"Runs by line: away={away_runs}, home={home_runs}")
    if not parts:
        return ""
    return "Linescore:\n  " + "\n  ".join(parts) + "\n"


def render_top_performers_block(top_performers: list[dict[str, object]] | None) -> str:
    """Format a list of top-performer hints (analytical recap).

    Each item is a dict with at least `name`, `team`, and `line` keys.
    Optional `context` appends a half-line of season-relevance ("4th HR
    in 5 games"). Returns an empty string when no performers were
    supplied — the caller should pass through verbatim so the prompt
    contains no empty key.
    """
    if not top_performers:
        return ""
    lines: list[str] = []
    for item in top_performers:
        name = item.get("name") or ""
        team = item.get("team") or ""
        line = item.get("line") or ""
        ctx = item.get("context")
        if not (name and line):
            continue
        if ctx:
            lines.append(f"  {name} ({team}): {line} — {ctx}")
        else:
            lines.append(f"  {name} ({team}): {line}")
    if not lines:
        return ""
    return "Top performers:\n" + "\n".join(lines) + "\n"


def render_recent_form_block(recent_form: dict[str, str] | None) -> str:
    """Format optional recent-form input. Returns "" when absent — see module docstring."""
    if not recent_form:
        return ""
    lines = [f"  {team}: {form}" for team, form in recent_form.items() if form]
    if not lines:
        return ""
    return "Recent form:\n" + "\n".join(lines) + "\n"
