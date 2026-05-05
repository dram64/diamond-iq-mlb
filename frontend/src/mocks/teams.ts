import type { Team, TeamId } from '@/types';

export const TEAMS: readonly Team[] = [
  { id: 'STR', city: 'Sierra',      name: 'Steelhead',     abbr: 'STR', color: '#4a6b7a', rec: '78-52', pct: 0.600 },
  { id: 'KNG', city: 'Kingsport',   name: 'Foxes',         abbr: 'KNG', color: '#a8632a', rec: '76-54', pct: 0.585 },
  { id: 'MNT', city: 'Monterrey',   name: 'Cartographers', abbr: 'MNT', color: '#6a4a7a', rec: '71-59', pct: 0.546 },
  { id: 'ALD', city: 'Alder',       name: 'Nines',         abbr: 'ALD', color: '#3a5a4a', rec: '70-60', pct: 0.538 },
  { id: 'HRB', city: 'Harbor',      name: 'Wardens',       abbr: 'HRB', color: '#2a4a6a', rec: '68-62', pct: 0.523 },
  { id: 'CRS', city: 'Cresthill',   name: 'Larks',         abbr: 'CRS', color: '#8a5a3a', rec: '66-64', pct: 0.508 },
  { id: 'MER', city: 'Meridian',    name: 'Typhoon',       abbr: 'MER', color: '#4a5a8a', rec: '65-65', pct: 0.500 },
  { id: 'RVR', city: 'Riverbend',   name: 'Pilots',        abbr: 'RVR', color: '#7a4a4a', rec: '63-67', pct: 0.485 },
  { id: 'CED', city: 'Cedar Point', name: 'Ironsides',     abbr: 'CED', color: '#5a5a5a', rec: '60-70', pct: 0.462 },
  { id: 'OAK', city: 'Oakmoor',     name: 'Brickmakers',   abbr: 'OAK', color: '#8a3a3a', rec: '58-72', pct: 0.446 },
  { id: 'NVL', city: 'Northvale',   name: 'Grenadiers',    abbr: 'NVL', color: '#3a3a5a', rec: '55-75', pct: 0.423 },
  { id: 'SHL', city: 'Shoreline',   name: 'Anchors',       abbr: 'SHL', color: '#4a4a3a', rec: '52-78', pct: 0.400 },
];

const byId: ReadonlyMap<TeamId, Team> = new Map(TEAMS.map((t) => [t.id, t]));

/** Look up a team by id. Throws if not found — fail loudly on bad data. */
export function teamBy(id: TeamId): Team {
  const t = byId.get(id);
  if (!t) throw new Error(`Unknown team: ${id}`);
  return t;
}
