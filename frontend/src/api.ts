export type Period = 'full' | 'first_half' | 'second_half';
export type Page = 'match' | 'player' | 'leaders';

export type MatchMeta = {
  event_id: string;
  home_name: string;
  away_name: string;
  home_score: string;
  away_score: string;
  tournament: string;
  date_text: string;
};

export type PlayerOption = {
  id: string | number;
  name: string;
  team: string;
  opponent: string;
  side: string;
};

export type BaseMatch = {
  match: MatchMeta;
  players: PlayerOption[];
  metrics: Array<{ key: string; label: string }>;
};

export type CanonicalMatch = {
  event_id: string;
  canonical_match_id: string;
  period: Period;
  match: {
    match_id: string;
    date: string;
    home_team_id: string;
    home_team: string;
    home_logo_url?: string;
    away_team_id: string;
    away_team: string;
    away_logo_url?: string;
    home_score: number | string;
    away_score: number | string;
  };
  home: Record<string, number | null>;
  away: Record<string, number | null>;
};

export type PlayerRow = { key: string; label: string; value: number; display: string };
export type CanonicalPlayer = {
  period: Period;
  player: { id: string; name: string; team: string; opponent: string; side: string };
  rows: PlayerRow[];
};

export type LeaderRow = {
  rank: number;
  player_id: string;
  player_name: string;
  team_id: string;
  team_name: string;
  team_logo_url?: string;
  value: number;
  relative_to_leader: number;
};
export type LeaderPayload = { metric: string; label: string; period: Period; leaders: LeaderRow[] };

const API = import.meta.env.VITE_MATCHLAB_API || 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data?.detail || `MatchLab API error (${response.status})`);
  return data as T;
}

export async function importSofascore(source: string) {
  return request<{ ok: boolean; event_id: string }>('/matches/import-sofascore', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source }),
  });
}

export async function getBaseMatch(eventId: string) {
  return request<BaseMatch>(`/matches/${eventId}`);
}

export async function getCanonicalMatch(eventId: string, period: Period) {
  return request<CanonicalMatch>(`/matches/${eventId}/canonical?period=${period}`);
}

export async function getCanonicalPlayer(eventId: string, playerId: string | number, period: Period) {
  return request<CanonicalPlayer>(`/matches/${eventId}/canonical-player/${playerId}?period=${period}`);
}

export async function getCanonicalLeaders(eventId: string, metric: string, period: Period, scope: 'all' | 'home' | 'away') {
  return request<LeaderPayload>(`/matches/${eventId}/canonical-leaders/${metric}?period=${period}&scope=${scope}&limit=10`);
}
