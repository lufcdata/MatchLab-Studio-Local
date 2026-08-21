import { useEffect, useMemo, useState } from 'react';
import { Sparkles, Trophy } from 'lucide-react';
import {
  getBaseMatch,
  getCanonicalLeaders,
  getCanonicalMatch,
  getCanonicalPlayer,
  importSofascore,
  type BaseMatch,
  type CanonicalMatch,
  type CanonicalPlayer,
  type LeaderPayload,
  type Page,
  type Period,
} from './api';

const MATCH_FIELDS = [
  ['goals', 'Goals'],
  ['possession', 'Possession'],
  ['touches', 'Touches'],
  ['penalty_box_touches', 'Penalty Box Touches'],
  ['shots', 'Shots'],
  ['shots_on_target', 'Shots On-Target'],
  ['set_piece_goals', 'Set-Piece Goals'],
  ['big_chances', 'Big Chances'],
  ['chances_created', 'Chances Created'],
  ['progressive_passes', 'Progressive Passes'],
  ['successful_passes', 'Successful Passes'],
  ['successful_final_third_passes', 'Successful Final Third Passes'],
  ['pass_accuracy', 'Pass Accuracy'],
  ['accurate_long_passes', 'Accurate Long Passes'],
  ['accurate_crosses', 'Accurate Crosses'],
  ['ground_duels_won', 'Ground Duels Won'],
  ['aerial_duels_won', 'Aerial Duels Won'],
  ['duels_won', 'Duels Won'],
  ['ball_recoveries', 'Ball Recoveries'],
  ['successful_take_ons', 'Successful Take-Ons'],
  ['tackles_won', 'Tackles Won'],
  ['interceptions', 'Interceptions'],
  ['clearances', 'Clearances'],
  ['corners', 'Corners'],
  ['saves', 'Saves'],
  ['red_cards', 'Red Cards'],
] as const;

const PERIODS: Array<[Period, string]> = [
  ['full', 'Full Match'],
  ['first_half', '1st Half'],
  ['second_half', '2nd Half'],
];

const slug = (value: string) => value.toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const isPercent = (key: string) => key === 'possession' || key === 'pass_accuracy' || key.includes('percentage');
const fmt = (value: number | null | undefined, key = '') => value == null ? '—' : `${Number.isInteger(value) ? value : value.toFixed(1).replace(/\.0$/, '')}${isPercent(key) ? '%' : ''}`;
const periodLabel = (period: Period) => period === 'full' ? 'FULL MATCH' : period === 'first_half' ? '1ST HALF' : '2ND HALF';

function Logo({ team, remote }: { team: string; remote?: string }) {
  return <div className="team-logo"><img src={`/team-logos/${slug(team)}.png`} alt={team} onError={(e) => {
    if (remote && e.currentTarget.src !== remote) e.currentTarget.src = remote;
    else e.currentTarget.style.display = 'none';
  }} /></div>;
}

function MatchView({ data }: { data: CanonicalMatch }) {
  return <div className="card match-card">
    <div className="card-glow" />
    <div className="match-head">
      <Logo team={data.match.home_team} remote={data.match.home_logo_url} />
      <div className="match-title-wrap">
        <div className="match-title">{data.match.home_team} <strong>{data.match.home_score}–{data.match.away_score}</strong> {data.match.away_team}</div>
        <div className="meta">{data.match.date} <i>|</i> Premier League <i>|</i> {periodLabel(data.period)}</div>
      </div>
      <Logo team={data.match.away_team} remote={data.match.away_logo_url} />
    </div>
    <div className="stats-list">
      {MATCH_FIELDS.map(([key, label]) => {
        const home = data.home[key]; const away = data.away[key];
        const h = Number(home || 0); const a = Number(away || 0); const total = Math.max(h + a, 1);
        return <div className="stat-row" key={key}>
          <div className="track left"><span style={{ width: `${h / total * 100}%` }} /></div>
          <b className={h >= a ? 'winner' : 'muted'}>{fmt(home, key)}</b>
          <span className="stat-name">{label}</span>
          <b className={a >= h ? 'winner' : 'muted'}>{fmt(away, key)}</b>
          <div className="track right"><span style={{ width: `${a / total * 100}%` }} /></div>
        </div>;
      })}
    </div>
  </div>;
}

function PlayerView({ data }: { data: CanonicalPlayer }) {
  const max = Math.max(...data.rows.map(r => Math.abs(Number(r.value || 0))), 1);
  return <div className="card player-card">
    <div className="card-glow" />
    <div className="player-head">
      <div className="player-photo"><img src={`/player-images/${slug(data.player.name)}.png`} alt={data.player.name} onError={e => e.currentTarget.style.display = 'none'} /></div>
      <h1>{data.player.name}</h1>
      <div className="meta">v {data.player.opponent} <i>|</i> {periodLabel(data.period)} <i>|</i> {data.player.team}</div>
    </div>
    <div className="player-list">
      {data.rows.slice(0, 20).map(row => <div className="player-row" key={row.key}>
        <Logo team={data.player.team} />
        <span>{row.label}</span>
        <b>{row.display}</b>
        <div className="mini-track"><span style={{ width: `${Math.max(4, Math.min(100, Math.abs(Number(row.value || 0)) / max * 100))}%` }} /></div>
        <em>MATCH</em>
      </div>)}
    </div>
  </div>;
}

function LeadersView({ data }: { data: LeaderPayload }) {
  return <div className="card player-card">
    <div className="card-glow" />
    <div className="player-head leader-head">
      <div className="trophy"><Trophy size={50} /></div>
      <h1>{data.label}</h1>
      <div className="meta">Metric Leaders <i>|</i> {periodLabel(data.period)} <i>|</i> Top {data.leaders.length}</div>
    </div>
    <div className="player-list">
      {data.leaders.map(row => <div className="player-row leader-row" key={`${row.player_id}-${row.rank}`}>
        <Logo team={row.team_name} remote={row.team_logo_url} />
        <span><strong>#{row.rank}</strong>{row.player_name}<small>{row.team_name}</small></span>
        <b>{fmt(row.value)}</b>
        <div className="mini-track"><span style={{ width: `${Math.max(4, row.relative_to_leader * 100)}%` }} /></div>
        <em>#{row.rank}</em>
      </div>)}
    </div>
  </div>;
}

export default function App() {
  const [page, setPage] = useState<Page>('match');
  const [period, setPeriod] = useState<Period>('full');
  const [source, setSource] = useState('14023940');
  const [eventId, setEventId] = useState('');
  const [base, setBase] = useState<BaseMatch | null>(null);
  const [match, setMatch] = useState<CanonicalMatch | null>(null);
  const [player, setPlayer] = useState<CanonicalPlayer | null>(null);
  const [leaders, setLeaders] = useState<LeaderPayload | null>(null);
  const [playerId, setPlayerId] = useState<string>('');
  const [metric, setMetric] = useState('successful_passes');
  const [scope, setScope] = useState<'all' | 'home' | 'away'>('all');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const metrics = useMemo(() => base?.metrics || [], [base]);

  async function loadMatch() {
    setLoading(true); setError('');
    try {
      const imported = await importSofascore(source.trim());
      const id = imported.event_id;
      const baseData = await getBaseMatch(id);
      const canonical = await getCanonicalMatch(id, period);
      setEventId(id); setBase(baseData); setMatch(canonical);
      const first = baseData.players?.[0];
      if (first) setPlayerId(String(first.id));
      if (baseData.metrics?.[0]?.key) setMetric(baseData.metrics[0].key);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not load MatchLab data.'); }
    finally { setLoading(false); }
  }

  useEffect(() => {
    if (!eventId) return;
    getCanonicalMatch(eventId, period).then(setMatch).catch(e => setError(e.message));
  }, [eventId, period]);

  useEffect(() => {
    if (!eventId || !playerId) return;
    getCanonicalPlayer(eventId, playerId, period).then(setPlayer).catch(e => setError(e.message));
  }, [eventId, playerId, period]);

  useEffect(() => {
    if (!eventId || !metric) return;
    getCanonicalLeaders(eventId, metric, period, scope).then(setLeaders).catch(e => setError(e.message));
  }, [eventId, metric, period, scope]);

  return <main className="app-shell">
    <header className="topbar">
      <div className="brand"><Sparkles size={20} /> <span>MATCHDAY STUDIO</span></div>
      <nav>
        <button className={page === 'match' ? 'active' : ''} onClick={() => setPage('match')}>Match</button>
        <button className={page === 'player' ? 'active' : ''} onClick={() => setPage('player')}>Player</button>
        <button className={page === 'leaders' ? 'active' : ''} onClick={() => setPage('leaders')}>Metric Leaders</button>
      </nav>
    </header>

    <section className="toolbar">
      <div className="source-box">
        <label>SofaScore match URL or event ID</label>
        <div><input value={source} onChange={e => setSource(e.target.value)} placeholder="Paste SofaScore URL" /><button onClick={loadMatch} disabled={loading}>{loading ? 'Loading…' : 'Load Match'}</button></div>
      </div>
      <div className="periods">{PERIODS.map(([key, label]) => <button key={key} className={period === key ? 'active' : ''} onClick={() => setPeriod(key)}>{label}</button>)}</div>
      {page === 'player' && base && <select value={playerId} onChange={e => setPlayerId(e.target.value)}>{base.players.map(p => <option key={String(p.id)} value={String(p.id)}>{p.name} — {p.team}</option>)}</select>}
      {page === 'leaders' && <>
        <select value={metric} onChange={e => setMetric(e.target.value)}>{metrics.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}</select>
        <div className="scope">{(['all','home','away'] as const).map(s => <button key={s} className={scope === s ? 'active' : ''} onClick={() => setScope(s)}>{s === 'all' ? 'Both' : s[0].toUpperCase()+s.slice(1)}</button>)}</div>
      </>}
      {error && <div className="error">{error}</div>}
    </section>

    <section className="stage">
      {!eventId && <div className="empty"><Sparkles size={38} /><h2>Matchday Studio</h2><p>Paste a SofaScore match URL or event ID to load the real MatchLab data.</p></div>}
      {page === 'match' && match && <MatchView data={match} />}
      {page === 'player' && player && <PlayerView data={player} />}
      {page === 'leaders' && leaders && <LeadersView data={leaders} />}
    </section>
  </main>;
}
