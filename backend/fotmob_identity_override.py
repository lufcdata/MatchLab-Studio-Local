from __future__ import annotations

import re
import sys
import unicodedata
from collections import Counter
from typing import Any

import server

_TRANSLITERATION = str.maketrans({
    "ı": "i", "İ": "I", "ł": "l", "Ł": "L", "ø": "o", "Ø": "O",
    "đ": "d", "Đ": "D", "ð": "d", "Ð": "D", "þ": "th", "Þ": "Th",
    "æ": "ae", "Æ": "Ae", "œ": "oe", "Œ": "Oe",
})


def _norm_name(value: Any) -> str:
    text = str(value or "").translate(_TRANSLITERATION)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def _surname_key(value: Any) -> str:
    parts = _norm_name(value).split()
    return parts[-1] if parts else ""


def _build_lookup(fotmob_players: list[dict[str, Any]], fields: dict[str, str], zero_when_missing: set[str], total_fields: dict[str, str] | None = None):
    total_fields = total_fields or {}
    records: list[tuple[str, str, dict[str, Any]]] = []
    for player in fotmob_players or []:
        stats = player.get("stats") or {}
        if not stats:
            continue
        values: dict[str, Any] = {}
        for label in fields:
            if label in stats:
                values[label] = stats[label]
            elif label in zero_when_missing:
                values[label] = 0
        values.update({label: stats.get(label) for label in total_fields if stats.get(label) is not None})
        name = player.get("name")
        norm = _norm_name(name)
        surname = _surname_key(name)
        if norm:
            records.append((norm, surname, values))

    exact = {norm: values for norm, _surname, values in records}
    surname_counts = Counter(surname for _norm, surname, _values in records if surname)
    unique_surname = {
        surname: values
        for _norm, surname, values in records
        if len(surname) >= 4 and surname_counts[surname] == 1
    }
    return exact, unique_surname


def _lookup_player(name: Any, exact: dict[str, dict[str, Any]], unique_surname: dict[str, dict[str, Any]]):
    norm = _norm_name(name)
    values = exact.get(norm)
    if values is not None:
        return values
    surname = _surname_key(name)
    if surname:
        return unique_surname.get(surname)
    return None


def _server_promote(payload: dict, fotmob_players: list) -> dict[str, int]:
    exact, unique_surname = _build_lookup(
        fotmob_players,
        server.PROMOTED_FOTMOB_FIELDS,
        server.ZERO_WHEN_MISSING_FOTMOB_FIELDS,
    )
    promoted = {label: 0 for label in server.PROMOTED_FOTMOB_FIELDS}
    for side in ("home", "away"):
        rows = (((payload.get("lineups") or {}).get(side) or {}).get("players") or [])
        for row in rows:
            player = row.get("player", {}) or {}
            values = _lookup_player(player.get("name"), exact, unique_surname)
            if values is None:
                continue
            stats = row.setdefault("statistics", {})
            for label, value in values.items():
                stats[server.PROMOTED_FOTMOB_FIELDS[label]] = value
                promoted[label] += 1
    return promoted


server._norm_name = _norm_name
server._promote_validated_fotmob_fields = _server_promote

# runtime.py has its own healing promotion path. Patch that path too so initial
# imports, cached supplements and later self-heals all use one identity rule.
runtime = sys.modules.get("runtime")
if runtime is not None:
    def _runtime_promote(payload: dict[str, Any]) -> bool:
        fotmob = payload.get("fotmob") or {}
        fotmob_players = fotmob.get("players") or []
        if not fotmob_players:
            return False
        exact, unique_surname = _build_lookup(
            fotmob_players,
            runtime._FOTMOB_FIELDS,
            runtime._ZERO_WHEN_MISSING,
            runtime._FOTMOB_TOTAL_FIELDS,
        )
        changed = False
        promoted_counts = {label: 0 for label in runtime._FOTMOB_FIELDS}
        for side in ("home", "away"):
            rows = (((payload.get("lineups") or {}).get(side) or {}).get("players") or [])
            for row in rows:
                player = row.get("player") or {}
                values = _lookup_player(player.get("name"), exact, unique_surname)
                if values is None:
                    continue
                stats = row.setdefault("statistics", {})
                for label, value in values.items():
                    key = runtime._FOTMOB_FIELDS.get(label) or runtime._FOTMOB_TOTAL_FIELDS.get(label)
                    if key is None:
                        continue
                    if stats.get(key) != value:
                        stats[key] = value
                        changed = True
                    if label in promoted_counts:
                        promoted_counts[label] += 1
        fotmob["validated_fields"] = list(runtime._FOTMOB_FIELDS)
        fotmob["promoted_player_counts"] = promoted_counts
        payload["fotmob"] = fotmob
        return changed

    runtime._norm = _norm_name
    runtime._promote = _runtime_promote
