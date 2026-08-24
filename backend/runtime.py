from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

import main

# The production endpoints in main.py all resolve main._load at request time.
# Patch that single load boundary before server.py is imported so Match, Player
# and Leaders all receive the same FotMob-enriched canonical payload.
_FOTMOB_FIELDS = {
    "Opposition Box Touches": "touchesInOppBox",
    "Passes Into Final Third": "passesIntoFinalThird",
    "Line-Breaking Passes": "lineBreakingPasses",
    "Headed Clearances": "headedClearances",
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
        by_name[_norm(player.get("name"))] = {
            label: stats.get(label, 0) for label in _FOTMOB_FIELDS
        }

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
                key = _FOTMOB_FIELDS[label]
                if stats.get(key) != value:
                    stats[key] = value
                    changed = True
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

# A SofaScore refresh previously replaced the whole local JSON. Preserve any
# already-linked FotMob supplement before that write and reattach it immediately.
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

# Import server only after the canonical load/import boundaries are patched.
# Its `from main import import_sofascore` binding therefore receives the
# preserving importer above.
import server

app = server.app
