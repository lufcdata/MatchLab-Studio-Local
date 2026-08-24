let manualPlayerOrder: string[] = [];
let draggedPlayerLabel = '';
let scheduled = false;

const text = (el: Element | null) => (el?.textContent || '').trim();

function isPlayerEditor(panel: Element) {
  return Array.from(panel.querySelectorAll('.stat-editor-row')).some(row => text(row).includes('Minutes Played') && text(row).includes('LOCKED'));
}

function playerEditorPanel(): Element | null {
  return Array.from(document.querySelectorAll('.stats-editor')).find(isPlayerEditor) || null;
}

function statLabel(row: Element): string {
  const spans = Array.from(row.querySelectorAll(':scope > span'));
  const label = spans.find(span => !span.classList.contains('locked-stat-label'));
  return text(label);
}

function playerGraphicRows(): HTMLElement[] {
  const list = document.querySelector('.player-graphic:not(.leaders-graphic) .player-stats-list');
  return list ? Array.from(list.querySelectorAll<HTMLElement>(':scope > .player-stat-row')) : [];
}

function numericValue(row: Element): number {
  const raw = text(row.querySelector('.player-stat-value')).replace(/,/g, '');
  const match = raw.match(/-?\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : 0;
}

function rankOrderActive(): boolean {
  return Array.from(document.querySelectorAll<HTMLButtonElement>('.clear-stats')).some(btn => text(btn) === 'Rank Order' && btn.classList.contains('clear-stats--active'));
}

function applyZeroLastToRankOrder() {
  if (!rankOrderActive()) return;
  const rows = playerGraphicRows();
  if (!rows.length) return;
  const list = rows[0].parentElement;
  if (!list) return;
  const minutes = rows.filter(row => text(row.querySelector('.player-stat-label')) === 'Minutes Played');
  const stats = rows.filter(row => text(row.querySelector('.player-stat-label')) !== 'Minutes Played');
  const nonZero = stats.filter(row => numericValue(row) !== 0);
  const zero = stats.filter(row => numericValue(row) === 0);
  [...minutes, ...nonZero, ...zero].forEach(row => list.appendChild(row));

  const editor = playerEditorPanel();
  if (!editor) return;
  const editorList = editor.querySelector('.stat-editor-list');
  if (!editorList) return;
  const byLabel = new Map(Array.from(editorList.querySelectorAll<HTMLElement>('.stat-editor-row:not(.stat-editor-row--locked)')).map(row => [statLabel(row), row]));
  [...nonZero, ...zero].forEach(graphicRow => {
    const label = text(graphicRow.querySelector('.player-stat-label'));
    const editorRow = byLabel.get(label);
    if (editorRow) editorList.appendChild(editorRow);
  });
}

function applyManualOrder() {
  if (rankOrderActive() || !manualPlayerOrder.length) return;
  const editor = playerEditorPanel();
  const editorList = editor?.querySelector('.stat-editor-list');
  if (editorList) {
    const byLabel = new Map(Array.from(editorList.querySelectorAll<HTMLElement>('.stat-editor-row:not(.stat-editor-row--locked)')).map(row => [statLabel(row), row]));
    manualPlayerOrder.forEach(label => {
      const row = byLabel.get(label);
      if (row) editorList.appendChild(row);
    });
  }
  const rows = playerGraphicRows();
  if (!rows.length) return;
  const list = rows[0].parentElement;
  if (!list) return;
  const minutes = rows.find(row => text(row.querySelector('.player-stat-label')) === 'Minutes Played');
  const byLabel = new Map(rows.filter(row => row !== minutes).map(row => [text(row.querySelector('.player-stat-label')), row]));
  if (minutes) list.appendChild(minutes);
  manualPlayerOrder.forEach(label => {
    const row = byLabel.get(label);
    if (row) list.appendChild(row);
  });
}

function installAutoSelect() {
  const panel = playerEditorPanel();
  const actions = panel?.querySelector('.stats-heading-actions');
  if (!actions || actions.querySelector('.player-auto-select')) return;
  const button = document.createElement('button');
  button.className = 'clear-stats player-auto-select';
  button.textContent = 'Auto Select';
  button.addEventListener('click', () => {
    const rows = Array.from(panel!.querySelectorAll<HTMLElement>('.stat-editor-row:not(.stat-editor-row--locked)'));
    rows.forEach((row, index) => {
      const hidden = row.classList.contains('stat-editor-row--hidden');
      const shouldShow = index < 18;
      if ((shouldShow && hidden) || (!shouldShow && !hidden)) row.querySelector<HTMLButtonElement>('.visibility-button')?.click();
    });
  });
  const clear = Array.from(actions.querySelectorAll('button')).find(btn => text(btn) === 'Clear');
  actions.insertBefore(button, clear || null);
}

function installPlayerDragOrder() {
  const panel = playerEditorPanel();
  if (!panel) return;
  const rows = Array.from(panel.querySelectorAll<HTMLElement>('.stat-editor-row:not(.stat-editor-row--locked)'));
  rows.forEach(row => {
    if (row.dataset.playerDragReady === '1') return;
    row.dataset.playerDragReady = '1';
    row.draggable = true;
    row.addEventListener('dragstart', () => {
      draggedPlayerLabel = statLabel(row);
      const rankButton = Array.from(panel.querySelectorAll<HTMLButtonElement>('.clear-stats')).find(btn => text(btn) === 'Rank Order');
      if (rankButton?.classList.contains('clear-stats--active')) rankButton.click();
    });
    row.addEventListener('dragover', event => event.preventDefault());
    row.addEventListener('drop', event => {
      event.preventDefault();
      if (!draggedPlayerLabel) return;
      const list = row.parentElement;
      if (!list) return;
      const dragged = Array.from(list.querySelectorAll<HTMLElement>('.stat-editor-row:not(.stat-editor-row--locked)')).find(item => statLabel(item) === draggedPlayerLabel);
      if (!dragged || dragged === row) return;
      const rect = row.getBoundingClientRect();
      const after = event.clientY > rect.top + rect.height / 2;
      list.insertBefore(dragged, after ? row.nextSibling : row);
      manualPlayerOrder = Array.from(list.querySelectorAll<HTMLElement>('.stat-editor-row:not(.stat-editor-row--locked)')).map(statLabel);
      draggedPlayerLabel = '';
      applyManualOrder();
    });
  });
}

function addEventIcons() {
  playerGraphicRows().forEach(row => {
    row.querySelector('.player-event-icons')?.remove();
    const label = text(row.querySelector('.player-stat-label')).toLowerCase();
    const value = Math.max(0, Math.floor(numericValue(row)));
    if (value < 1) return;
    let icon = '';
    if (label === 'goals') icon = '⚽';
    else if (label === 'assists') icon = '🅰️';
    else if (label === 'red cards') icon = '🟥';
    if (!icon) return;
    const badge = document.createElement('span');
    badge.className = 'player-event-icons';
    badge.setAttribute('aria-label', `${value} ${label}`);
    badge.textContent = Array.from({ length: value }, () => icon).join(' ');
    row.appendChild(badge);
  });
}

function enhance() {
  scheduled = false;
  installAutoSelect();
  installPlayerDragOrder();
  if (rankOrderActive()) applyZeroLastToRankOrder();
  else applyManualOrder();
  addEventIcons();
}

function scheduleEnhance() {
  if (scheduled) return;
  scheduled = true;
  requestAnimationFrame(enhance);
}

new MutationObserver(scheduleEnhance).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
window.addEventListener('load', scheduleEnhance);
scheduleEnhance();
