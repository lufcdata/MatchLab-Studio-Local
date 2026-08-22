import { useEffect, useMemo, useRef, useState, type CSSProperties, type RefObject } from 'react';
import { toPng } from 'html-to-image';
import { ArrowUpRight, Check, Download, Eye, EyeOff, GripVertical, Sparkles, Trophy } from 'lucide-react';

type Page = 'match' | 'player' | 'leaders';
type Period = 'full' | 'first_half' | 'second_half';

type MatchMeta = {
  event_id: string;
  home_name: string;
  away_name: string;
  home_score: string;
  away_score: string;
  tournament: string;
  date_text: string;
};

type PlayerOption = { id: string | number; name: string; team: string; opponent: string; side: string };
type BaseMatch = { match: MatchMeta; players: PlayerOption[]; metrics: Array<{ key: string; label: string }> };
type CanonicalMatch = {
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
  availability?: { missing_fields?: string[] };
};

type PlayerRow = { key: string; label: string; value: number; display: string };
type CanonicalPlayer = {
  period: Period;
  player: { id: string; name: string; team: string; opponent: string; side: string };
  rows: PlayerRow[];
};

type LeaderRow = {
  rank: number;
  player_id: string;
  player_name: string;
  team_id: string;
  team_name: string;
  team_logo_url?: string;
  value: number;
  relative_to_leader: number;
};
type LeaderPayload = { metric: string; label: string; period: Period; leaders: LeaderRow[] };

type Stat = { key: string; label: string; home: number; away: number; homeDisplay: string; awayDisplay: string };

const API = import.meta.env.VITE_MATCHLAB_API || 'http://localhost:8000';

const MATCH_FIELDS: Array<{ key: string; label: string; percent?: boolean }> = [
  { key: 'goals', label: 'Goals' },
  { key: 'possession', label: 'Possession', percent: true },
  { key: 'touches', label: 'Touches' },
  { key: 'penalty_box_touches', label: 'Penalty Box Touches' },
  { key: 'shots', label: 'Shots' },
  { key: 'shots_on_target', label: 'Shots On-Target' },
  { key: 'set_piece_goals', label: 'Set-Piece Goals' },
  { key: 'big_chances', label: 'Big Chances' },
  { key: 'chances_created', label: 'Chances Created' },
  { key: 'progressive_passes', label: 'Progressive Passes' },
  { key: 'successful_passes', label: 'Successful Passes' },
  { key: 'successful_final_third_passes', label: 'Successful Final Third Passes' },
  { key: 'pass_accuracy', label: 'Pass Accuracy', percent: true },
  { key: 'accurate_long_passes', label: 'Accurate Long Passes' },
  { key: 'accurate_crosses', label: 'Accurate Crosses' },
  { key: 'ground_duels_won', label: 'Ground Duels Won' },
  { key: 'aerial_duels_won', label: 'Aerial Duels Won' },
  { key: 'duels_won', label: 'Duels Won' },
  { key: 'ball_recoveries', label: 'Ball Recoveries' },
  { key: 'successful_take_ons', label: 'Successful Take-Ons' },
  { key: 'tackles_won', label: 'Tackles Won' },
  { key: 'interceptions', label: 'Interceptions' },
  { key: 'clearances', label: 'Clearances' },
  { key: 'corners', label: 'Corners' },
  { key: 'saves', label: 'Saves' },
  { key: 'red_cards', label: 'Red Cards' },
];

const slug = (value: string) => value.toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const formatNumber = (value: number | null | undefined, percent = false) => {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const text = Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, '');
  return percent ? `${text}%` : text;
};
const periodLabel = (period: Period) => period === 'full' ? 'FULL MATCH' : period === 'first_half' ? '1ST HALF' : '2ND HALF';

function TeamBadge({ name, logo }: { name: string; logo?: string }) {
  const local = `/team-logos/${slug(name)}.png`;
  return <div className="team-badge" aria-label={`${name} badge`}><div className="team-badge__inner"><img className="team-badge__image" src={local} alt={name} onError={(event) => { const img = event.currentTarget; if (logo && img.src !== logo) img.src = logo; else img.style.display = 'none'; }} /></div></div>;
}

function StatRow({ stat, homeColor, awayColor }: { stat: Stat; homeColor: string; awayColor: string }) {
  const homeLeads = stat.home > stat.away;
  const awayLeads = stat.away > stat.home;
  const total = Math.max(Math.abs(stat.home) + Math.abs(stat.away), 1);
  const homePct = (Math.abs(stat.home) / total) * 100;
  const awayPct = 100 - homePct;
  return <div className="stat-row">
    <div className="stat-row__bar stat-row__bar--left"><div className="stat-row__bar-seg stat-row__bar-seg--home" style={{ width: `${homePct}%`, backgroundColor: homeLeads ? homeColor : `${homeColor}66` }} /></div>
    <span className={`stat-row__value stat-row__value--home ${homeLeads ? 'stat-row__value--leader' : 'stat-row__value--muted'}`}>{stat.homeDisplay}</span>
    <span className="stat-row__label">{stat.label}</span>
    <span className={`stat-row__value stat-row__value--away ${awayLeads ? 'stat-row__value--leader' : 'stat-row__value--muted'}`}>{stat.awayDisplay}</span>
    <div className="stat-row__bar stat-row__bar--right"><div className="stat-row__bar-seg stat-row__bar-seg--away" style={{ width: `${awayPct}%`, backgroundColor: awayLeads ? awayColor : `${awayColor}66` }} /></div>
  </div>;
}

function MatchGraphic({ graphicRef, data, stats, homeColor, awayColor }: { graphicRef: RefObject<HTMLDivElement>; data: CanonicalMatch; stats: Stat[]; homeColor: string; awayColor: string }) {
  const match = data.match;
  return <div className="graphic" ref={graphicRef}>
    <div className="graphic__noise" />
    <header className="graphic-header"><div className="matchup">
      <TeamBadge name={match.home_team} logo={match.home_logo_url} />
      <div className="matchup__center"><div className="matchup__title"><span>{match.home_team}</span> <strong>{match.home_score}–{match.away_score}</strong> <span>{match.away_team}</span></div><div className="matchup__meta">{match.date} <span>|</span> {periodLabel(data.period)} <span>|</span> Match Stats</div></div>
      <TeamBadge name={match.away_team} logo={match.away_logo_url} />
    </div></header>
    <section className="stats-panel"><div className="stats-list">{stats.map((stat) => <StatRow key={stat.key} stat={stat} homeColor={homeColor} awayColor={awayColor} />)}</div></section>
    <GraphicFooter />
  </div>;
}

function PlayerGraphic({ graphicRef, data, accentColor }: { graphicRef: RefObject<HTMLDivElement>; data: CanonicalPlayer; accentColor: string }) {
  const maxValue = Math.max(...data.rows.map((row) => Math.abs(row.value || 0)), 1);
  const image = `/player-images/${slug(data.player.name)}.png`;
  return <div className="graphic player-graphic" ref={graphicRef}>
    <div className="graphic__noise" />
    <header className="player-header"><div className="player-badge player-badge--photo"><img src={image} alt={data.player.name} onError={(event) => { event.currentTarget.style.display = 'none'; }} /></div><h2>{data.player.name}</h2><div className="player-meta">v {data.player.opponent} <span>|</span> {periodLabel(data.period)} <span>|</span> {data.player.team}</div></header>
    <section className="player-stats-panel"><div className="player-stats-list">{data.rows.slice(0, 18).map((row) => <div className="player-stat-row" key={row.key}>
      <div className="player-stat-club"><img src={`/team-logos/${slug(data.player.team)}.png`} alt={data.player.team} /></div>
      <span className="player-stat-label">{row.label}</span><strong className="player-stat-value">{row.display}</strong>
      <div className="player-stat-bar"><span style={{ width: `${Math.max(5, Math.min(100, (Math.abs(row.value || 0) / maxValue) * 100))}%`, backgroundColor: accentColor }} /></div>
      <span className="rank-button rank-button--label" style={{ backgroundColor: accentColor }}>MATCH</span>
    </div>)}</div></section>
    <GraphicFooter />
  </div>;
}

function LeadersGraphic({ graphicRef, data, accentColor }: { graphicRef: RefObject<HTMLDivElement>; data: LeaderPayload; accentColor: string }) {
  return <div className="graphic player-graphic" ref={graphicRef}>
    <div className="graphic__noise" />
    <header className="player-header leaders-header"><div className="player-badge"><Trophy size={60} strokeWidth={1.5} /></div><h2>{data.label}</h2><div className="player-meta">Metric Leaders <span>|</span> {periodLabel(data.period)} <span>|</span> Top {data.leaders.length}</div></header>
    <section className="player-stats-panel"><div className="player-stats-list">{data.leaders.map((row) => <div className="player-stat-row leader-stat-row" key={`${row.player_id}-${row.rank}`}>
      <div className="player-stat-club"><img src={`/team-logos/${slug(row.team_name)}.png`} alt={row.team_name} /></div>
      <span className="player-stat-label"><b className="leader-rank">{row.rank}</b>{row.player_name}<small>{row.team_name}</small></span>
      <strong className="player-stat-value">{formatNumber(row.value)}</strong>
      <div className="player-stat-bar"><span style={{ width: `${Math.max(4, row.relative_to_leader * 100)}%`, backgroundColor: accentColor }} /></div>
      <span className="rank-button rank-button--label" style={{ backgroundColor: accentColor }}>#{row.rank}</span>
    </div>)}</div></section>
    <GraphicFooter />
  </div>;
}

function GraphicFooter() { return <footer className="graphic-footer"><span className="footer-spacer" /><span className="footer-page"><img src="/lufcdata-logo.webp" alt="LUFCDATA.LAB" /></span><span className="footer-url">LUFCDATA.LAB</span></footer>; }

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...(options?.headers || {}) } });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
  return body as T;
}

function App() {
  const graphicRef = useRef<HTMLDivElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.5);
  const [page, setPage] = useState<Page>('match');
  const [period, setPeriod] = useState<Period>('full');
  const [source, setSource] = useState('14023940');
  const [eventId, setEventId] = useState<string>('');
  const [base, setBase] = useState<BaseMatch | null>(null);
  const [canonical, setCanonical] = useState<CanonicalMatch | null>(null);
  const [player, setPlayer] = useState<CanonicalPlayer | null>(null);
  const [leaders, setLeaders] = useState<LeaderPayload | null>(null);
  const [selectedPlayerId, setSelectedPlayerId] = useState('');
  const [metricCatalog, setMetricCatalog] = useState<Array<{ key: string; label: string }>>([]);
  const [selectedMetric, setSelectedMetric] = useState('successful_passes');
  const [leaderScope, setLeaderScope] = useState<'all' | 'home' | 'away'>('all');
  const [homeColor, setHomeColor] = useState('#48f0ca');
  const [awayColor, setAwayColor] = useState('#48f0ca');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [isExporting, setIsExporting] = useState(false);
  const [exported, setExported] = useState(false);
  const [statOrder, setStatOrder] = useState(MATCH_FIELDS.map((item) => item.key));
  const [visibleKeys, setVisibleKeys] = useState(MATCH_FIELDS.map((item) => item.key));
  const [draggedKey, setDraggedKey] = useState<string | null>(null);

  useEffect(() => { api<{ live: Array<{ key: string; label: string }> }>('/canonical/metrics').then((result) => { setMetricCatalog(result.live); if (result.live.length && !result.live.some((m) => m.key === selectedMetric)) setSelectedMetric(result.live[0].key); }).catch(() => undefined); }, []);

  const loadMatch = async () => {
    setLoading(true); setError(''); setExported(false);
    try {
      const imported = await api<{ event_id: string }>('/matches/import-sofascore', { method: 'POST', body: JSON.stringify({ source }) });
      const baseData = await api<BaseMatch>(`/matches/${imported.event_id}`);
      setEventId(imported.event_id); setBase(baseData);
      const preferred = baseData.players.find((p) => /joe rodon/i.test(p.name)) || baseData.players.find((p) => p.side === 'home') || baseData.players[0];
      setSelectedPlayerId(preferred ? String(preferred.id) : '');
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    if (!eventId) return;
    setError('');
    api<CanonicalMatch>(`/matches/${eventId}/canonical?period=${period}`).then(setCanonical).catch((err) => setError(err.message));
  }, [eventId, period]);

  useEffect(() => {
    if (!eventId || !selectedPlayerId) return;
    api<CanonicalPlayer>(`/matches/${eventId}/canonical-player/${selectedPlayerId}?period=${period}`).then(setPlayer).catch((err) => { if (page === 'player') setError(err.message); });
  }, [eventId, selectedPlayerId, period, page]);

  useEffect(() => {
    if (!eventId || !selectedMetric) return;
    api<LeaderPayload>(`/matches/${eventId}/canonical-leaders/${selectedMetric}?period=${period}&scope=${leaderScope}&limit=15`).then(setLeaders).catch((err) => { if (page === 'leaders') setError(err.message); });
  }, [eventId, selectedMetric, period, leaderScope, page]);

  useEffect(() => {
    const preview = previewRef.current; if (!preview) return;
    const updateScale = () => setScale(Math.min(preview.clientWidth / 1080, preview.clientHeight / 1350));
    updateScale(); const observer = new ResizeObserver(updateScale); observer.observe(preview); return () => observer.disconnect();
  }, []);

  const matchStats = useMemo(() => {
    if (!canonical) return [] as Stat[];
    const byKey = new Map(MATCH_FIELDS.map((item) => [item.key, item]));
    return statOrder.map((key) => {
      const def = byKey.get(key); if (!def || !visibleKeys.includes(key)) return null;
      const home = Number(canonical.home[key] ?? 0); const away = Number(canonical.away[key] ?? 0);
      return { key, label: def.label, home, away, homeDisplay: formatNumber(canonical.home[key], def.percent), awayDisplay: formatNumber(canonical.away[key], def.percent) };
    }).filter((row): row is Stat => Boolean(row));
  }, [canonical, statOrder, visibleKeys]);

  const exportPng = async () => {
    if (!graphicRef.current) return; setIsExporting(true); setExported(false);
    try { const dataUrl = await toPng(graphicRef.current, { width: 1080, height: 1350, pixelRatio: 2, cacheBust: true }); const link = document.createElement('a'); link.download = `matchlab-${page}-${eventId || 'preview'}-${period}.png`; link.href = dataUrl; link.click(); setExported(true); }
    finally { setIsExporting(false); }
  };

  const dropStat = (targetKey: string) => { if (!draggedKey || draggedKey === targetKey) return; setStatOrder((current) => { const next = [...current]; const from = next.indexOf(draggedKey); const to = next.indexOf(targetKey); next.splice(from, 1); next.splice(to, 0, draggedKey); return next; }); setDraggedKey(null); };
  const toggleStat = (key: string) => setVisibleKeys((current) => current.includes(key) ? current.filter((item) => item !== key) : [...current, key]);
  const graphicStyle = { transform: `scale(${scale})` } as CSSProperties;
  const pageTitle = page === 'match' ? 'MATCHDAY STUDIO' : page === 'player' ? 'PLAYER STATS' : 'METRIC LEADERS';

  return <main className="studio-shell"><div className="ambient-line ambient-line--one" /><div className="ambient-line ambient-line--two" /><div className="studio-layout">
    <section className="workspace">
      <div className="workspace-topline"><span className="workspace-kicker"><Sparkles size={14} /> {pageTitle}</span><span className="page-switcher"><button className={page === 'match' ? 'page-switcher__active' : ''} onClick={() => setPage('match')}>Match</button><button className={page === 'player' ? 'page-switcher__active' : ''} onClick={() => setPage('player')}>Player</button><button className={page === 'leaders' ? 'page-switcher__active' : ''} onClick={() => setPage('leaders')}>Leaders</button></span></div>
      <div className="preview-frame" ref={previewRef}><div className="graphic-scale" style={graphicStyle}>
        {page === 'match' && canonical ? <MatchGraphic graphicRef={graphicRef} data={canonical} stats={matchStats} homeColor={homeColor} awayColor={awayColor} /> : null}
        {page === 'player' && player ? <PlayerGraphic graphicRef={graphicRef} data={player} accentColor={homeColor} /> : null}
        {page === 'leaders' && leaders ? <LeadersGraphic graphicRef={graphicRef} data={leaders} accentColor={homeColor} /> : null}
        {!eventId ? <div className="graphic empty-graphic"><Sparkles size={44} /><h2>Paste a SofaScore match URL</h2><p>MatchLab will import the match locally and render the canonical metrics here.</p></div> : null}
      </div></div>
      <div className="workspace-caption"><span><i className="caption-dot" /> {loading ? 'Loading…' : eventId ? `Match ${eventId}` : 'Ready for match'}</span><span>1080 × 1350 px <b>•</b> 4:5 portrait</span></div>
    </section>

    <aside className="control-panel">
      <div className="panel-brand"><div className="panel-brand__icon"><Trophy size={19} /></div><div><strong>MatchLab</strong><span>Local Studio</span></div><span className="panel-status">LOCAL</span></div>
      <div className="panel-divider" />
      <div className="panel-section source-panel"><div className="panel-section__heading"><span>SOFASCORE MATCH</span><span className="edit-label">LOCAL IMPORT</span></div><input className="studio-input" value={source} onChange={(e) => setSource(e.target.value)} placeholder="Paste SofaScore URL or event ID" /><button className="load-button" onClick={loadMatch} disabled={loading}>{loading ? 'Loading match…' : 'Load Match'}</button>{error ? <div className="studio-error">{error}</div> : null}</div>
      <div className="panel-divider" />
      {base && page === 'player' ? <div className="panel-section"><div className="panel-section__heading"><span>PLAYER</span><span className="edit-label">{base.players.length} AVAILABLE</span></div><select className="studio-select" value={selectedPlayerId} onChange={(e) => setSelectedPlayerId(e.target.value)}>{base.players.map((p) => <option key={String(p.id)} value={String(p.id)}>{p.name} — {p.team}</option>)}</select></div> : null}
      {page === 'leaders' ? <div className="panel-section"><div className="panel-section__heading"><span>LEADERBOARD METRIC</span><span className="edit-label">CANONICAL</span></div><select className="studio-select" value={selectedMetric} onChange={(e) => setSelectedMetric(e.target.value)}>{metricCatalog.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}</select><div className="scope-toggle"><button className={leaderScope === 'all' ? 'period-toggle__active' : ''} onClick={() => setLeaderScope('all')}>All</button><button className={leaderScope === 'home' ? 'period-toggle__active' : ''} onClick={() => setLeaderScope('home')}>Home</button><button className={leaderScope === 'away' ? 'period-toggle__active' : ''} onClick={() => setLeaderScope('away')}>Away</button></div></div> : null}
      {(base && page !== 'leaders') ? <><div className="panel-section team-controls"><div className="panel-section__heading"><span>TEAM COLOURS</span><span className="edit-label">LIVE</span></div><div className="colour-row"><label><span className="colour-swatch" style={{ background: homeColor }} />{base.match.home_name}</label><input type="color" value={homeColor} onChange={(e) => setHomeColor(e.target.value)} /></div><div className="colour-row"><label><span className="colour-swatch" style={{ background: awayColor }} />{base.match.away_name}</label><input type="color" value={awayColor} onChange={(e) => setAwayColor(e.target.value)} /></div></div></> : null}
      <div className="panel-divider" />
      <div className="panel-section period-toggle"><div className="panel-section__heading"><span>MATCH PERIOD</span><span className="edit-label">{periodLabel(period)}</span></div><div className="period-toggle__group"><button className={period === 'full' ? 'period-toggle__active' : ''} onClick={() => setPeriod('full')}>Full Match</button><button className={period === 'first_half' ? 'period-toggle__active' : ''} onClick={() => setPeriod('first_half')}>1st Half</button><button className={period === 'second_half' ? 'period-toggle__active' : ''} onClick={() => setPeriod('second_half')}>2nd Half</button></div></div>
      {page === 'match' ? <><div className="panel-divider" /><div className="panel-section stats-editor"><div className="panel-section__heading"><span>STAT SELECTION</span><span className="stats-heading-actions"><span className="edit-label">{visibleKeys.length} / {MATCH_FIELDS.length}</span><button className="clear-stats" onClick={() => setVisibleKeys([])}>Clear</button></span></div><p className="editor-hint">Canonical Metrics Bible names. Drag to reorder; hide or show any row.</p><div className="stat-editor-list">{statOrder.map((key) => { const item = MATCH_FIELDS.find((x) => x.key === key)!; const visible = visibleKeys.includes(key); return <div key={key} className={`stat-editor-row ${visible ? '' : 'stat-editor-row--hidden'}`} draggable onDragStart={() => setDraggedKey(key)} onDragOver={(e) => e.preventDefault()} onDrop={() => dropStat(key)}><GripVertical size={14} className="drag-handle" /><span>{item.label}</span><button className="visibility-button" onClick={() => toggleStat(key)}>{visible ? <Eye size={15} /> : <EyeOff size={15} />}</button></div>; })}</div></div></> : null}
      <div className="panel-divider" />
      <button className="export-button" onClick={exportPng} disabled={isExporting || !eventId}>{exported ? <Check size={20} /> : <Download size={20} />}<span>{isExporting ? 'Preparing PNG…' : exported ? 'PNG exported' : 'Export PNG'}</span>{!isExporting && !exported && <ArrowUpRight size={17} className="export-button__arrow" />}</button>
      <div className="export-note"><span className="note-check"><Check size={13} /></span><span>Canonical V2</span><span className="note-separator" /><span>Real period data</span><span className="note-separator" /><span>Local</span></div>
      <div className="panel-divider" /><div className="panel-footer"><span><span className="footer-live-dot" /> Local API</span><span>Studio v2</span></div>
    </aside>
  </div></main>;
}

export default App;
