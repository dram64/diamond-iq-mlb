/**
 * Static MLB team table.
 *
 * IDs are MLB Stats API team IDs (the integers returned in
 * `teams.away.team.id` / `teams.home.team.id` on every schedule
 * response). Colors are official primary/secondary from each club's
 * brand guidelines.
 *
 * If a team's id is not in this table, callers should use
 * `getMlbTeam(id)` (returns undefined) and fall back to whatever the
 * API's response itself supplies — that way the UI never crashes
 * when a new team is added or an id changes upstream.
 */

export type League = 'AL' | 'NL';
export type Division = 'East' | 'Central' | 'West';

export interface MlbTeam {
  id: number;
  abbreviation: string;
  locationName: string;
  teamName: string;
  fullName: string;
  primaryColor: string;
  secondaryColor: string;
  league: League;
  division: Division;
  /** Static asset path (under `frontend/public/`) to the team's cap logo SVG. */
  logoPath: string;
}

const LOGO = (id: number): string => `/images/teams/${id}.svg`;

const TEAMS: readonly MlbTeam[] = [
  // ── AL East ──────────────────────────────────────────────────
  { id: 110, abbreviation: 'BAL', locationName: 'Baltimore',  teamName: 'Orioles',     fullName: 'Baltimore Orioles',  primaryColor: '#DF4601', secondaryColor: '#000000', league: 'AL', division: 'East', logoPath: LOGO(110) },
  { id: 111, abbreviation: 'BOS', locationName: 'Boston',     teamName: 'Red Sox',     fullName: 'Boston Red Sox',     primaryColor: '#BD3039', secondaryColor: '#0C2340', league: 'AL', division: 'East', logoPath: LOGO(111) },
  { id: 147, abbreviation: 'NYY', locationName: 'New York',   teamName: 'Yankees',     fullName: 'New York Yankees',   primaryColor: '#003087', secondaryColor: '#0C2340', league: 'AL', division: 'East', logoPath: LOGO(147) },
  { id: 139, abbreviation: 'TB',  locationName: 'Tampa Bay',  teamName: 'Rays',        fullName: 'Tampa Bay Rays',     primaryColor: '#092C5C', secondaryColor: '#8FBCE6', league: 'AL', division: 'East', logoPath: LOGO(139) },
  { id: 141, abbreviation: 'TOR', locationName: 'Toronto',    teamName: 'Blue Jays',   fullName: 'Toronto Blue Jays',  primaryColor: '#134A8E', secondaryColor: '#1D2D5C', league: 'AL', division: 'East', logoPath: LOGO(141) },

  // ── AL Central ───────────────────────────────────────────────
  { id: 145, abbreviation: 'CWS', locationName: 'Chicago',    teamName: 'White Sox',   fullName: 'Chicago White Sox',  primaryColor: '#27251F', secondaryColor: '#C4CED4', league: 'AL', division: 'Central', logoPath: LOGO(145) },
  { id: 114, abbreviation: 'CLE', locationName: 'Cleveland',  teamName: 'Guardians',   fullName: 'Cleveland Guardians', primaryColor: '#00385D', secondaryColor: '#E50022', league: 'AL', division: 'Central', logoPath: LOGO(114) },
  { id: 116, abbreviation: 'DET', locationName: 'Detroit',    teamName: 'Tigers',      fullName: 'Detroit Tigers',     primaryColor: '#0C2340', secondaryColor: '#FA4616', league: 'AL', division: 'Central', logoPath: LOGO(116) },
  { id: 118, abbreviation: 'KC',  locationName: 'Kansas City', teamName: 'Royals',     fullName: 'Kansas City Royals', primaryColor: '#004687', secondaryColor: '#BD9B60', league: 'AL', division: 'Central', logoPath: LOGO(118) },
  { id: 142, abbreviation: 'MIN', locationName: 'Minnesota',  teamName: 'Twins',       fullName: 'Minnesota Twins',    primaryColor: '#002B5C', secondaryColor: '#D31145', league: 'AL', division: 'Central', logoPath: LOGO(142) },

  // ── AL West ──────────────────────────────────────────────────
  { id: 117, abbreviation: 'HOU', locationName: 'Houston',    teamName: 'Astros',      fullName: 'Houston Astros',     primaryColor: '#002D62', secondaryColor: '#EB6E1F', league: 'AL', division: 'West', logoPath: LOGO(117) },
  { id: 108, abbreviation: 'LAA', locationName: 'Los Angeles', teamName: 'Angels',     fullName: 'Los Angeles Angels', primaryColor: '#BA0021', secondaryColor: '#003263', league: 'AL', division: 'West', logoPath: LOGO(108) },
  { id: 133, abbreviation: 'ATH', locationName: 'Athletics',  teamName: 'Athletics',   fullName: 'Athletics',          primaryColor: '#003831', secondaryColor: '#EFB21E', league: 'AL', division: 'West', logoPath: LOGO(133) },
  { id: 136, abbreviation: 'SEA', locationName: 'Seattle',    teamName: 'Mariners',    fullName: 'Seattle Mariners',   primaryColor: '#0C2C56', secondaryColor: '#005C5C', league: 'AL', division: 'West', logoPath: LOGO(136) },
  { id: 140, abbreviation: 'TEX', locationName: 'Texas',      teamName: 'Rangers',     fullName: 'Texas Rangers',      primaryColor: '#003278', secondaryColor: '#C0111F', league: 'AL', division: 'West', logoPath: LOGO(140) },

  // ── NL East ──────────────────────────────────────────────────
  { id: 144, abbreviation: 'ATL', locationName: 'Atlanta',    teamName: 'Braves',      fullName: 'Atlanta Braves',     primaryColor: '#CE1141', secondaryColor: '#13274F', league: 'NL', division: 'East', logoPath: LOGO(144) },
  { id: 146, abbreviation: 'MIA', locationName: 'Miami',      teamName: 'Marlins',     fullName: 'Miami Marlins',      primaryColor: '#00A3E0', secondaryColor: '#EF3340', league: 'NL', division: 'East', logoPath: LOGO(146) },
  { id: 121, abbreviation: 'NYM', locationName: 'New York',   teamName: 'Mets',        fullName: 'New York Mets',      primaryColor: '#002D72', secondaryColor: '#FF5910', league: 'NL', division: 'East', logoPath: LOGO(121) },
  { id: 143, abbreviation: 'PHI', locationName: 'Philadelphia', teamName: 'Phillies',  fullName: 'Philadelphia Phillies', primaryColor: '#E81828', secondaryColor: '#002D72', league: 'NL', division: 'East', logoPath: LOGO(143) },
  { id: 120, abbreviation: 'WSH', locationName: 'Washington', teamName: 'Nationals',   fullName: 'Washington Nationals', primaryColor: '#AB0003', secondaryColor: '#14225A', league: 'NL', division: 'East', logoPath: LOGO(120) },

  // ── NL Central ───────────────────────────────────────────────
  { id: 112, abbreviation: 'CHC', locationName: 'Chicago',    teamName: 'Cubs',        fullName: 'Chicago Cubs',       primaryColor: '#0E3386', secondaryColor: '#CC3433', league: 'NL', division: 'Central', logoPath: LOGO(112) },
  { id: 113, abbreviation: 'CIN', locationName: 'Cincinnati', teamName: 'Reds',        fullName: 'Cincinnati Reds',    primaryColor: '#C6011F', secondaryColor: '#000000', league: 'NL', division: 'Central', logoPath: LOGO(113) },
  { id: 158, abbreviation: 'MIL', locationName: 'Milwaukee',  teamName: 'Brewers',     fullName: 'Milwaukee Brewers',  primaryColor: '#12284B', secondaryColor: '#FFC52F', league: 'NL', division: 'Central', logoPath: LOGO(158) },
  { id: 134, abbreviation: 'PIT', locationName: 'Pittsburgh', teamName: 'Pirates',     fullName: 'Pittsburgh Pirates', primaryColor: '#FDB827', secondaryColor: '#27251F', league: 'NL', division: 'Central', logoPath: LOGO(134) },
  { id: 138, abbreviation: 'STL', locationName: 'St. Louis',  teamName: 'Cardinals',   fullName: 'St. Louis Cardinals', primaryColor: '#C41E3A', secondaryColor: '#0C2340', league: 'NL', division: 'Central', logoPath: LOGO(138) },

  // ── NL West ──────────────────────────────────────────────────
  { id: 109, abbreviation: 'AZ',  locationName: 'Arizona',    teamName: 'Diamondbacks', fullName: 'Arizona Diamondbacks', primaryColor: '#A71930', secondaryColor: '#000000', league: 'NL', division: 'West', logoPath: LOGO(109) },
  { id: 115, abbreviation: 'COL', locationName: 'Colorado',   teamName: 'Rockies',     fullName: 'Colorado Rockies',   primaryColor: '#33006F', secondaryColor: '#C4CED4', league: 'NL', division: 'West', logoPath: LOGO(115) },
  { id: 119, abbreviation: 'LAD', locationName: 'Los Angeles', teamName: 'Dodgers',    fullName: 'Los Angeles Dodgers', primaryColor: '#005A9C', secondaryColor: '#EF3E42', league: 'NL', division: 'West', logoPath: LOGO(119) },
  { id: 135, abbreviation: 'SD',  locationName: 'San Diego',  teamName: 'Padres',      fullName: 'San Diego Padres',   primaryColor: '#2F241D', secondaryColor: '#FFC425', league: 'NL', division: 'West', logoPath: LOGO(135) },
  { id: 137, abbreviation: 'SF',  locationName: 'San Francisco', teamName: 'Giants',   fullName: 'San Francisco Giants', primaryColor: '#FD5A1E', secondaryColor: '#27251F', league: 'NL', division: 'West', logoPath: LOGO(137) },
];

const byId: ReadonlyMap<number, MlbTeam> = new Map(TEAMS.map((t) => [t.id, t]));

/** Look up an MLB team by id. Returns undefined for unknown ids — callers fall back to API-supplied team data. */
export function getMlbTeam(id: number): MlbTeam | undefined {
  return byId.get(id);
}

/** Look up an MLB team by id. Throws on unknown — use only when the id is known to be in the table. */
export function getMlbTeamRequired(id: number): MlbTeam {
  const team = byId.get(id);
  if (!team) throw new Error(`Unknown MLB team id: ${id}`);
  return team;
}

/** All 30 teams in the table, in their declared order. */
export function getAllMlbTeams(): readonly MlbTeam[] {
  return TEAMS;
}
