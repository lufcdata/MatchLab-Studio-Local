let manualPlayerOrder: string[] = [];
let draggedPlayerLabel = '';
let scheduled = false;
let rankAutoHiddenLabels = new Set<string>();
let rankAutoHidePending = false;
let wasRankOrderActive = false;
const matchDateCache = new Map<string, string>();

const text = (el: Element | null) => (el?.textContent || '').trim();
const same = (a: string[], b: string[]) => a.length === b.length && a.every((value, index) => value === b[index]);

function isPlayerEditor(panel: Element) {
  return Array.from(panel.querySelectorAll('.stat-editor-row')).some(row => text(row).includes('Minutes Played') && text(row).includes('LOCKED'));
}
function playerEditorPanel(): Element | null { return Array.from(document.querySelectorAll('.stats-editor')).find(isPlayerEditor) || null; }
function statLabel(row: Element): string { const spans = Array.from(row.querySelectorAll(':scope > span')); const label = spans.find(span => !span.classList.contains('locked-stat-label')); return text(label); }
function playerGraphicRows(): HTMLElement[] { const list = document.querySelector('.player-graphic:not(.leaders-graphic) .player-stats-list'); return list ? Array.from(list.querySelectorAll<HTMLElement>(':scope > .player-stat-row')) : []; }
function graphicLabel(row: Element): string { return text(row.querySelector('.player-stat-label')); }
function numericValue(row: Element): number { const raw = text(row.querySelector('.player-stat-value')).replace(/,/g, ''); const match = raw.match(/-?\d+(?:\.\d+)?/); return match ? Number(match[0]) : 0; }
function rankOrderActive(): boolean { return Array.from(document.querySelectorAll<HTMLButtonElement>('.clear-stats')).some(btn => text(btn) === 'Rank Order' && btn.classList.contains('clear-stats--active')); }

function reorderGraphic(desiredLabels: string[]) {
  const rows = playerGraphicRows(); if (!rows.length) return;
  const list = rows[0].parentElement; if (!list) return;
  const current = rows.map(graphicLabel); const desired = desiredLabels.filter(label => current.includes(label));
  current.forEach(label => { if (!desired.includes(label)) desired.push(label); });
  if (same(current, desired)) return;
  const byLabel = new Map(rows.map(row => [graphicLabel(row), row]));
  desired.forEach(label => { const row = byLabel.get(label); if (row) list.appendChild(row); });
}

function syncRankZeroVisibility() {
  const panel = playerEditorPanel(); if (!panel) return;
  const editorRows = Array.from(panel.querySelectorAll<HTMLElement>('.stat-editor-row:not(.stat-editor-row--locked)'));
  const byLabel = new Map(editorRows.map(row => [statLabel(row), row]));
  const active = rankOrderActive();
  if (!active) {
    rankAutoHidePending = false;
    const restore = [...rankAutoHiddenLabels]; rankAutoHiddenLabels.clear();
    restore.forEach(label => { const row = byLabel.get(label); if (row?.classList.contains('stat-editor-row--hidden')) row.querySelector<HTMLButtonElement>('.visibility-button')?.click(); });
    return;
  }
  // Auto-remove zero rows only during the initial Rank Order pass. Once that
  // pass is complete every eye toggle is user-controlled, including zero stats.
  if (!rankAutoHidePending) return;
  const zeroLabels = playerGraphicRows().filter(row => graphicLabel(row) !== 'Minutes Played' && numericValue(row) === 0).map(graphicLabel);
  if (!zeroLabels.length) { rankAutoHidePending = false; return; }
  let changed = false;
  zeroLabels.forEach(label => {
    const row = byLabel.get(label); if (!row || row.classList.contains('stat-editor-row--hidden')) return;
    rankAutoHiddenLabels.add(label); changed = true; row.querySelector<HTMLButtonElement>('.visibility-button')?.click();
  });
  if (!changed) rankAutoHidePending = false;
}

function applyZeroLastToRankOrder() {
  if (!rankOrderActive()) return;
  const rows = playerGraphicRows(); if (!rows.length) return;
  const minutes = rows.filter(row => graphicLabel(row) === 'Minutes Played');
  const stats = rows.filter(row => graphicLabel(row) !== 'Minutes Played');
  const nonZero = stats.filter(row => numericValue(row) !== 0); const zero = stats.filter(row => numericValue(row) === 0);
  reorderGraphic([...minutes, ...nonZero, ...zero].map(graphicLabel));
}

function applyManualOrder() {
  if (rankOrderActive() || !manualPlayerOrder.length) return;
  const editor = playerEditorPanel(); const editorList = editor?.querySelector('.stat-editor-list');
  if (editorList) {
    const rows = Array.from(editorList.querySelectorAll<HTMLElement>('.stat-editor-row:not(.stat-editor-row--locked)'));
    const current = rows.map(statLabel); const desired = manualPlayerOrder.filter(label => current.includes(label));
    current.forEach(label => { if (!desired.includes(label)) desired.push(label); });
    if (!same(current, desired)) { const byLabel = new Map(rows.map(row => [statLabel(row), row])); desired.forEach(label => { const row = byLabel.get(label); if (row) editorList.appendChild(row); }); }
  }
  reorderGraphic(['Minutes Played', ...manualPlayerOrder]);
}

function installAutoSelect() {
  const panel = playerEditorPanel(); const actions = panel?.querySelector('.stats-heading-actions');
  if (!actions || actions.querySelector('.player-auto-select')) return;
  const button = document.createElement('button'); button.className = 'clear-stats player-auto-select'; button.textContent = 'Auto Select';
  button.addEventListener('click', () => {
    const rows = Array.from(panel!.querySelectorAll<HTMLElement>('.stat-editor-row:not(.stat-editor-row--locked)'));
    rows.forEach((row, index) => { const hidden = row.classList.contains('stat-editor-row--hidden'); const shouldShow = index < 18; if ((shouldShow && hidden) || (!shouldShow && !hidden)) row.querySelector<HTMLButtonElement>('.visibility-button')?.click(); });
  });
  const clear = Array.from(actions.querySelectorAll('button')).find(btn => text(btn) === 'Clear'); actions.insertBefore(button, clear || null);
}

function installPlayerDragOrder() {
  const panel = playerEditorPanel(); if (!panel) return;
  const rows = Array.from(panel.querySelectorAll<HTMLElement>('.stat-editor-row:not(.stat-editor-row--locked)'));
  rows.forEach(row => {
    if (row.dataset.playerDragReady === '1') return; row.dataset.playerDragReady = '1'; row.draggable = true;
    row.addEventListener('dragstart', () => { draggedPlayerLabel = statLabel(row); const rankButton = Array.from(panel.querySelectorAll<HTMLButtonElement>('.clear-stats')).find(btn => text(btn) === 'Rank Order'); if (rankButton?.classList.contains('clear-stats--active')) rankButton.click(); });
    row.addEventListener('dragover', event => event.preventDefault());
    row.addEventListener('drop', event => {
      event.preventDefault(); if (!draggedPlayerLabel) return; const list = row.parentElement; if (!list) return;
      const dragged = Array.from(list.querySelectorAll<HTMLElement>('.stat-editor-row:not(.stat-editor-row--locked)')).find(item => statLabel(item) === draggedPlayerLabel); if (!dragged || dragged === row) return;
      const rect = row.getBoundingClientRect(); const after = event.clientY > rect.top + rect.height / 2; list.insertBefore(dragged, after ? row.nextSibling : row);
      manualPlayerOrder = Array.from(list.querySelectorAll<HTMLElement>('.stat-editor-row:not(.stat-editor-row--locked)')).map(statLabel); draggedPlayerLabel = ''; applyManualOrder();
    });
  });
}

function addEventIcons() {
  playerGraphicRows().forEach(row => {
    const label = graphicLabel(row).toLowerCase(); const value = Math.max(0, Math.floor(numericValue(row))); let icon = '';
    if (label === 'goals') icon = '⚽'; else if (label === 'assists') icon = '🅰️'; else if (label === 'red cards') icon = '🟥';
    const expected = icon && value > 0 ? Array.from({ length: value }, () => icon).join(' ') : ''; const existing = row.querySelector<HTMLElement>('.player-event-icons');
    if (!expected) { existing?.remove(); return; }
    if (existing) { if (existing.textContent !== expected) existing.textContent = expected; return; }
    const badge = document.createElement('span'); badge.className = 'player-event-icons'; badge.setAttribute('aria-label', `${value} ${label}`); badge.textContent = expected; row.appendChild(badge);
  });
}

function currentEventId(): string {
  const caption = text(document.querySelector('.workspace-caption'));
  return caption.match(/\bMatch\s+(\d+)\b/i)?.[1] || '';
}
function apiOrigin(): string {
  const image = document.querySelector<HTMLImageElement>('img[src*="/team-logos/"]');
  if (image?.src) { try { return new URL(image.src).origin; } catch { /* fall through */ } }
  return 'http://localhost:8000';
}
async function addMatchDate() {
  const meta = document.querySelector<HTMLElement>('.player-graphic .player-meta');
  if (!meta || meta.dataset.matchDateAdded === '1') return;
  const eventId = currentEventId(); if (!eventId) return;
  let date = matchDateCache.get(eventId) || '';
  if (!date) {
    try {
      const response = await fetch(`${apiOrigin()}/matches/${eventId}`); if (!response.ok) return;
      const body = await response.json(); date = String(body?.match?.date_text || '').trim(); if (date) matchDateCache.set(eventId, date);
    } catch { return; }
  }
  if (!date || meta.dataset.matchDateAdded === '1') return;
  const separator = document.createElement('span'); separator.textContent = '|'; meta.append(' ', separator, ` ${date}`); meta.dataset.matchDateAdded = '1';
}

function enhance() {
  scheduled = false;
  const active = rankOrderActive();
  if (active && !wasRankOrderActive) rankAutoHidePending = true;
  wasRankOrderActive = active;
  installAutoSelect(); installPlayerDragOrder(); syncRankZeroVisibility();
  if (active) applyZeroLastToRankOrder(); else applyManualOrder();
  addEventIcons(); void addMatchDate();
}
function scheduleEnhance() { if (scheduled) return; scheduled = true; requestAnimationFrame(enhance); }
new MutationObserver(scheduleEnhance).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
window.addEventListener('load', scheduleEnhance); scheduleEnhance();
