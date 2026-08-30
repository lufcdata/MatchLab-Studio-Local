const updateMinutesBars = () => {
  document.querySelectorAll<HTMLElement>('.player-stat-row--locked').forEach(row => {
    const value = row.querySelector<HTMLElement>('.player-stat-value');
    const bar = row.querySelector<HTMLElement>('.player-stat-bar > span');
    if (!value || !bar) return;

    const minutes = Number.parseFloat(value.textContent?.trim() || '');
    if (!Number.isFinite(minutes)) return;

    const percentage = Math.max(0, Math.min(100, (minutes / 90) * 100));
    bar.style.width = `${percentage}%`;
  });
};

const observer = new MutationObserver(updateMinutesBars);
observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
queueMicrotask(updateMinutesBars);
