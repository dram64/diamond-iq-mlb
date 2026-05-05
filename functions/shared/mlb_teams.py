"""Static MLB team metadata used by content-generation logic.

Mirrors `frontend/src/lib/mlbTeams.ts` for backend code. Two parallel
tables are intentional: the frontend ships its table to the browser
without making the backend a dependency, the backend keeps a Python
version close to the heuristic that needs it. If a team id changes
upstream, both files must be updated.

`pacific_time` flags only the six clubs whose home parks are in
Pacific Time (LAA, OAK/Athletics, SEA, LAD, SD, SF). HOU and TEX are
"AL West" but Central Time, so they are intentionally not flagged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

League = Literal["AL", "NL"]
Division = Literal["East", "Central", "West"]


@dataclass(frozen=True)
class MlbTeam:
    id: int
    abbreviation: str
    location_name: str
    team_name: str
    full_name: str
    league: League
    division: Division
    pacific_time: bool


_TEAMS: tuple[MlbTeam, ...] = (
    # AL East
    MlbTeam(110, "BAL", "Baltimore", "Orioles", "Baltimore Orioles", "AL", "East", False),
    MlbTeam(111, "BOS", "Boston", "Red Sox", "Boston Red Sox", "AL", "East", False),
    MlbTeam(147, "NYY", "New York", "Yankees", "New York Yankees", "AL", "East", False),
    MlbTeam(139, "TB", "Tampa Bay", "Rays", "Tampa Bay Rays", "AL", "East", False),
    MlbTeam(141, "TOR", "Toronto", "Blue Jays", "Toronto Blue Jays", "AL", "East", False),
    # AL Central
    MlbTeam(145, "CWS", "Chicago", "White Sox", "Chicago White Sox", "AL", "Central", False),
    MlbTeam(114, "CLE", "Cleveland", "Guardians", "Cleveland Guardians", "AL", "Central", False),
    MlbTeam(116, "DET", "Detroit", "Tigers", "Detroit Tigers", "AL", "Central", False),
    MlbTeam(118, "KC", "Kansas City", "Royals", "Kansas City Royals", "AL", "Central", False),
    MlbTeam(142, "MIN", "Minnesota", "Twins", "Minnesota Twins", "AL", "Central", False),
    # AL West
    MlbTeam(117, "HOU", "Houston", "Astros", "Houston Astros", "AL", "West", False),
    MlbTeam(108, "LAA", "Los Angeles", "Angels", "Los Angeles Angels", "AL", "West", True),
    MlbTeam(133, "ATH", "Athletics", "Athletics", "Athletics", "AL", "West", True),
    MlbTeam(136, "SEA", "Seattle", "Mariners", "Seattle Mariners", "AL", "West", True),
    MlbTeam(140, "TEX", "Texas", "Rangers", "Texas Rangers", "AL", "West", False),
    # NL East
    MlbTeam(144, "ATL", "Atlanta", "Braves", "Atlanta Braves", "NL", "East", False),
    MlbTeam(146, "MIA", "Miami", "Marlins", "Miami Marlins", "NL", "East", False),
    MlbTeam(121, "NYM", "New York", "Mets", "New York Mets", "NL", "East", False),
    MlbTeam(143, "PHI", "Philadelphia", "Phillies", "Philadelphia Phillies", "NL", "East", False),
    MlbTeam(120, "WSH", "Washington", "Nationals", "Washington Nationals", "NL", "East", False),
    # NL Central
    MlbTeam(112, "CHC", "Chicago", "Cubs", "Chicago Cubs", "NL", "Central", False),
    MlbTeam(113, "CIN", "Cincinnati", "Reds", "Cincinnati Reds", "NL", "Central", False),
    MlbTeam(158, "MIL", "Milwaukee", "Brewers", "Milwaukee Brewers", "NL", "Central", False),
    MlbTeam(134, "PIT", "Pittsburgh", "Pirates", "Pittsburgh Pirates", "NL", "Central", False),
    MlbTeam(138, "STL", "St. Louis", "Cardinals", "St. Louis Cardinals", "NL", "Central", False),
    # NL West
    MlbTeam(109, "AZ", "Arizona", "Diamondbacks", "Arizona Diamondbacks", "NL", "West", False),
    MlbTeam(115, "COL", "Colorado", "Rockies", "Colorado Rockies", "NL", "West", False),
    MlbTeam(119, "LAD", "Los Angeles", "Dodgers", "Los Angeles Dodgers", "NL", "West", True),
    MlbTeam(135, "SD", "San Diego", "Padres", "San Diego Padres", "NL", "West", True),
    MlbTeam(137, "SF", "San Francisco", "Giants", "San Francisco Giants", "NL", "West", True),
)

_BY_ID: dict[int, MlbTeam] = {t.id: t for t in _TEAMS}


def get_team(team_id: int) -> MlbTeam | None:
    return _BY_ID.get(team_id)


def all_teams() -> tuple[MlbTeam, ...]:
    return _TEAMS
