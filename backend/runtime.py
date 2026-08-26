from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

import main
import golden_metrics

# Additive-only metric extension. Existing Golden metrics are not changed.
_NEW_METRICS = (
    {"label":"Passes in Opposition Half","sofascore":"FotMob supplement","match_keys":["passesInOppositionHalf"],"player_keys":["passesInOppositionHalf"]},
    {"label":"Passes in Own Half","sofascore":"FotMob supplement","match_keys":["passesInOwnHalf"],"player_keys":["passesInOwnHalf"]},
    {"label":"Clearances Off Line","sofascore":"FotMob supplement","match_keys":["clearancesOffLine"],"player_keys":["clearancesOffLine"],"default_zero":True},
)
for _metric in _NEW_METRICS:
    if not any(m.get("label") == _metric["label"] for m in main.METRICS):
        main.METRICS.append(dict(_metric))
    golden_metrics.REQUIRED_PLAYER_LABELS.add(_metric["label"])

# The production endpoints in main.py all resolve main._load at request time.
# Patch that single load boundary before server.py is imported so Match, Player
# and Leaders all receive the same FotMob-enriched canonical payload.
_FOTMOB_FIELDS = {
    "Opposition Box Touches": "touchesInOppBox",
    "Passes Into Final Third": "passesIntoFinalThird",
    "Line-Breaking Passes": "lineBreakingPasses",
    "Headed Clearances": "headedClearances",
    "Passes in Opposition Half": "passesInOppositionHalf",
    "Passes in Own Half": "passesInOwnHalf",
    "Clearances Off Line": "clearancesOffLine",
}
_FOTMOB_TOTAL_FIELDS = {
    "Passes in Opposition Half Total": "passesInOppositionHalfTotal",
    "Passes in Own Half Total": "passesInOwnHalfTotal",
}


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def _promote(payload: dict[str, Any]) -> bool:
    fotmob = payload.get("fotmob") or {}
    fotmob_players = fotmob.get("players") or []
    if not fotmob_players:
        return False
    by_name: dict[str, dict[str, Any]] = {}
    for player in fotmob_players:
        stats = player.get("stats") or {}
        if not stats:
            continue
        values = {label: stats.get(label, 0) for label in _FOTMOB_FIELDS}
        values.update({label: stats.get(label) for label in _FOTMOB_TOTAL_FIELDS if stats.get(label) is not None})
        by_name[_norm(player.get("name"))] = values
    changed = False
    promoted_counts = {label: 0 for label in _FOTMOB_FIELDS}
    for side in ("home", "away"):
        rows = (((payload.get("lineups") or {}).get(side) or {}).get("players") or [])
        for row in rows:
            player = row.get("player") or {}
            values = by_name.get(_norm(player.get("name")))
            if values is None:
                continue
            stats = row.setdefault("statistics", {})
            for label, value in values.items():
                key = _FOTMOB_FIELDS.get(label) or _FOTMOB_TOTAL_FIELDS.get(label)
                if key is None:
                    continue
                if stats.get(key) != value:
                    stats[key] = value
                    changed = True
                if label in promoted_counts:
                    promoted_counts[label] += 1
    fotmob["validated_fields"] = list(_FOTMOB_FIELDS)
    fotmob["promoted_player_counts"] = promoted_counts
    payload["fotmob"] = fotmob
    return changed


_base_load = main._load

def _healed_load(event_id: str) -> dict[str, Any]:
    payload = _base_load(event_id)
    if _promote(payload):
        (main.DATA_DIR / f"{event_id}.json").write_text(json.dumps(payload, ensure_ascii=False))
    return payload

main._load = _healed_load

# Preserve the linked FotMob supplement whenever SofaScore is refreshed.
_base_import_sofascore = main.import_sofascore

def _preserving_import_sofascore(req):
    event_id = main._event_id(req.source)
    path = main.DATA_DIR / f"{event_id}.json"
    previous_fotmob = None
    if path.exists():
        try:
            previous_fotmob = (json.loads(path.read_text()).get("fotmob") or None)
        except Exception:
            previous_fotmob = None
    result = _base_import_sofascore(req)
    if previous_fotmob:
        payload = json.loads(path.read_text())
        payload["fotmob"] = previous_fotmob
        _promote(payload)
        path.write_text(json.dumps(payload, ensure_ascii=False))
    return result

main.import_sofascore = _preserving_import_sofascore

# Keep the FotMob pass ratios (e.g. 2/3 and 5/5) in Player display while the
# numeric successful count remains the ranking value used by Player/Leaders.
_base_build_rows = main.build_canonical_player_rows

def _build_rows_with_fotmob_ratios(stats: dict[str, Any], hide_zero: bool = True):
    rows, minutes = _base_build_rows(stats, hide_zero=hide_zero)
    totals = {
        "passes_in_opposition_half": stats.get("passesInOppositionHalfTotal"),
        "passes_in_own_half": stats.get("passesInOwnHalfTotal"),
    }
    for row in rows:
        total = totals.get(row.get("key"))
        if total is None:
            continue
        try:
            value = float(row.get("value", 0)); total_value = float(total)
        except (TypeError, ValueError):
            continue
        if total_value < value:
            continue
        left = str(int(value)) if value.is_integer() else f"{value:.1f}"
        right = str(int(total_value)) if total_value.is_integer() else f"{total_value:.1f}"
        row["display"] = f"{left}/{right}"
    return rows, minutes

main.build_canonical_player_rows = _build_rows_with_fotmob_ratios

# Import server only after the canonical load/import boundaries are patched.
import server


def _fotmob_match_ref(source: str) -> str:
    """Accept legacy numeric IDs, alphanumeric slugs, and numeric hash URLs."""
    source = (source or "").strip()
    if re.fullmatch(r"[A-Za-z0-9]+", source):
        return source
    patterns = (
        r"#([A-Za-z0-9]+)(?::|$)",
        r"/matches/[^#?]+/([A-Za-z0-9]+)(?::|[/?#]|$)",
        r"/match/([A-Za-z0-9]+)(?::|[/?#]|$)",
        r"[?&](?:matchId|id)=([A-Za-z0-9]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, source, re.I)
        if match:
            return match.group(1)
    raise server.HTTPException(400, "Could not find a FotMob match reference in that URL.")

server._fotmob_match_id = _fotmob_match_ref
app = server.app
