from __future__ import annotations

from typing import Any

import golden_metrics
import main

KM_TO_MILES = 0.62
_DISTANCE_RENAME = {
    "Distance covered (km)": "Distance covered (miles)",
}
_REMOVED_LABELS = {"Sprinting (km)", "Sprinting (metres)", "Sprinting (miles)"}

# Sprinting distance is intentionally removed from the authoritative catalogue,
# so it disappears together from Match Stats, Player Stats and Leaders.
golden_metrics.METRICS[:] = [
    metric for metric in golden_metrics.METRICS
    if str(metric.get("label") or "") not in _REMOVED_LABELS
]

# Keep FotMob's stored/source distance-covered value in native normalised km.
# Convert once at the canonical metric-value boundary so all surfaces consume
# the same miles value.
for metric in golden_metrics.METRICS:
    old_label = str(metric.get("label") or "")
    if old_label in _DISTANCE_RENAME:
        metric["label"] = _DISTANCE_RENAME[old_label]

golden_metrics.METRIC_BY_LABEL = {m["label"]: m for m in golden_metrics.METRICS}
for removed_label in _REMOVED_LABELS:
    golden_metrics.REQUIRED_PLAYER_LABELS.discard(removed_label)
for old_label, new_label in _DISTANCE_RENAME.items():
    golden_metrics.REQUIRED_PLAYER_LABELS.discard(old_label)
    golden_metrics.REQUIRED_PLAYER_LABELS.add(new_label)

_base_player_metric_value = golden_metrics.player_metric_value
_base_format_metric_value = golden_metrics.format_metric_value


def player_metric_value(stats: dict[str, Any], metric: dict[str, Any]) -> float | None:
    value = _base_player_metric_value(stats, metric)
    if value is not None and metric.get("label") == "Distance covered (miles)":
        return round(float(value) * KM_TO_MILES, 3)
    return value


def format_metric_value(value: float, metric: dict[str, Any]) -> str:
    if metric.get("label") == "Distance covered (miles)":
        return f"{value:.2f}"
    return _base_format_metric_value(value, metric)


golden_metrics.player_metric_value = player_metric_value
golden_metrics.format_metric_value = format_metric_value
main.player_metric_value = player_metric_value
main.format_metric_value = format_metric_value

# Provider identity normalisation: exact names remain first choice, with a safe
# unique-surname fallback for provider spelling/diacritic/first-name variants.
# This keeps the player-level FotMob supplement complete before Match Stats,
# Player Stats and Leaders consume it.
import fotmob_identity_override  # noqa: E402,F401

# Performance-only linked-import patch: SofaScore still refreshes on every load,
# but a validated FotMob supplement is reused for the same match instead of
# re-downloading and re-parsing FotMob unnecessarily.
import linked_import_cache  # noqa: E402,F401
