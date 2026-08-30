from __future__ import annotations

from typing import Any

import golden_metrics
import main

KM_TO_MILES = 0.62
KM_TO_METRES = 1000.0
_RENAMES = {
    "Distance covered (km)": "Distance covered (miles)",
    "Sprinting (km)": "Sprinting (metres)",
}

# Keep FotMob's stored/source values in their native normalised kilometres.
# Conversion happens once at the canonical metric-value boundary, so Match
# Stats, Player Stats and Leaders all consume the same converted values.
for metric in golden_metrics.METRICS:
    old_label = str(metric.get("label") or "")
    if old_label in _RENAMES:
        metric["label"] = _RENAMES[old_label]

golden_metrics.METRIC_BY_LABEL = {m["label"]: m for m in golden_metrics.METRICS}
for old_label, new_label in _RENAMES.items():
    golden_metrics.REQUIRED_PLAYER_LABELS.discard(old_label)
    golden_metrics.REQUIRED_PLAYER_LABELS.add(new_label)

_base_player_metric_value = golden_metrics.player_metric_value
_base_format_metric_value = golden_metrics.format_metric_value


def player_metric_value(stats: dict[str, Any], metric: dict[str, Any]) -> float | None:
    value = _base_player_metric_value(stats, metric)
    if value is None:
        return None
    label = metric.get("label")
    if label == "Distance covered (miles)":
        return round(float(value) * KM_TO_MILES, 3)
    if label == "Sprinting (metres)":
        return round(float(value) * KM_TO_METRES, 3)
    return value


def format_metric_value(value: float, metric: dict[str, Any]) -> str:
    label = metric.get("label")
    if label == "Distance covered (miles)":
        return f"{value:.2f}"
    if label == "Sprinting (metres)":
        return str(int(round(value)))
    return _base_format_metric_value(value, metric)


golden_metrics.player_metric_value = player_metric_value
golden_metrics.format_metric_value = format_metric_value
main.player_metric_value = player_metric_value
main.format_metric_value = format_metric_value
