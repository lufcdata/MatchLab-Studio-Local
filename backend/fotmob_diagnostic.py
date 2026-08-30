from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import quote_plus

from curl_cffi import requests


TARGET_KEYS = {
    "touches_opp_box": "Opposition Box Touches",
    "passes_into_final_third": "Passes Into Final Third",
    "headed_clearance": "Headed Clearances",
    "line_breaking_passes": "Line-Breaking Passes",
    "accurate_passes_opposition_half": "Passes in Opposition Half",
    "accurate_passes_own_half": "Passes in Own Half",
    "clearance_off_line": "Clearances Off Line",
    "distance_covered": "Distance covered (km)",
    "number_of_sprints": "Number of sprints",
    "sprinting": "Sprinting (km)",
}
PASS_RATIO_KEYS = {"accurate_passes_opposition_half", "accurate_passes_own_half"}
PHYSICAL_DISTANCE_LABELS = {"Distance covered (km)", "Sprinting (km)"}

# FotMob has used several key spellings/shapes across page payload versions.
# Normalize all of them to one internal raw key before exposing anything.
KEY_ALIASES = {
    "distancecovered": "distance_covered",
    "physicaldistancecovered": "distance_covered",
    "totaldistance": "distance_covered",
    "totaldistancecovered": "distance_covered",
    "distancecoveredmeters": "distance_covered",
    "distancecoveredm": "distance_covered",
    "numberofsprints": "number_of_sprints",
    "sprintcount": "number_of_sprints",
    "sprints": "number_of_sprints",
    "physicalsprints": "number_of_sprints",
    "sprinting": "sprinting",
    "sprintingdistance": "sprinting",
    "sprintdistance": "sprinting",
    "distancesprinting": "sprinting",
    "sprintingmeters": "sprinting",
    "sprintingm": "sprinting",
    "touchesoppbox": "touches_opp_box",
    "passesintofinalthird": "passes_into_final_third",
    "headedclearance": "headed_clearance",
    "linebreakingpasses": "line_breaking_passes",
    "accuratepassesoppositionhalf": "accurate_passes_opposition_half",
    "accuratepassesownhalf": "accurate_passes_own_half",
    "clearanceoffline": "clearance_off_line",
}
LABEL_ALIASES = {
    "distance covered": "distance_covered",
    "total distance": "distance_covered",
    "number of sprints": "number_of_sprints",
    "sprints": "number_of_sprints",
    "sprinting": "sprinting",
    "sprinting distance": "sprinting",
    "sprint distance": "sprinting",
}


def _get(url: str):
    return requests.get(
        url,
        impersonate="chrome",
        timeout=20,
        headers={"Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8", "Referer": "https://www.fotmob.com/"},
        allow_redirects=True,
    )


def _next_payload(html: str) -> dict[str, Any]:
    match = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.I | re.S)
    if not match:
        raise RuntimeError("FotMob page did not expose a __NEXT_DATA__ match payload")
    return json.loads(unescape(match.group(1)))


def _page_props(payload: dict[str, Any]) -> dict[str, Any]:
    return ((payload.get("props") or {}).get("pageProps") or {})


def _has_player_stats(payload: dict[str, Any]) -> bool:
    content = _page_props(payload).get("content") or {}
    player_stats = content.get("playerStats") or {}
    return isinstance(player_stats, dict) and bool(player_stats)


def _query_from_match_url(match_url: str) -> str:
    path = match_url.split("?", 1)[0].rstrip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        slug = parts[-2]
        slug = re.sub(r"-(?:vs|v)-", " ", slug, flags=re.I).replace("-", " ")
        return " ".join(slug.split())
    return ""


def _resolve_numeric_match_id(match_url: str) -> str | None:
    query = _query_from_match_url(match_url)
    if not query:
        return None
    try:
        response = _get(f"https://apigw.fotmob.com/searchapi/suggest?term={quote_plus(query)}&lang=en")
        response.raise_for_status(); data = response.json()
    except Exception:
        return None
    options: list[dict[str, Any]] = []
    for group in data.get("matchSuggest", []) or []:
        options.extend(group.get("options", []) or [])
    wanted = {t for t in re.findall(r"[a-z0-9]+", query.casefold()) if len(t) > 2 and t not in {"united", "city", "football", "club"}}
    best: tuple[int, str] | None = None
    for option in options:
        item = option.get("payload") or {}; numeric_id = item.get("id")
        if numeric_id is None: continue
        haystack = " ".join(str(item.get(k) or "") for k in ("homeName", "awayName", "name", "leagueName")).casefold()
        candidate = (sum(1 for token in wanted if token in haystack), str(numeric_id))
        if best is None or candidate[0] > best[0]: best = candidate
    return best[1] if best else None


def fetch_match_details(match_id: str, match_url: str | None = None) -> dict[str, Any]:
    has_numeric_hash = bool(match_url and re.search(r"#\d+(?::|$)", match_url))
    url = f"https://www.fotmob.com/match/{match_id}" if has_numeric_hash and str(match_id).isdigit() else (match_url or f"https://www.fotmob.com/match/{match_id}")
    response = _get(url); response.raise_for_status(); payload = _next_payload(response.text)
    # A slug/localized FotMob page can contain ordinary playerStats while the
    # canonical numeric match page exposes a richer player payload. Previously
    # we returned here too early, so physical-performance fields never got a
    # chance to be discovered. Numeric references are already canonical.
    if _has_player_stats(payload) and str(match_id).isdigit(): return payload
    numeric_id = str(match_id) if str(match_id).isdigit() else (_resolve_numeric_match_id(match_url) if match_url else None)
    if numeric_id:
        retry = _get(f"https://www.fotmob.com/match/{numeric_id}"); retry.raise_for_status(); retry_payload = _next_payload(retry.text)
        if _has_player_stats(retry_payload): return retry_payload
    return payload


def _flat(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _raw_key(value: Any) -> str | None:
    if not isinstance(value, str): return None
    if value in TARGET_KEYS: return value
    return KEY_ALIASES.get(_flat(value))


def _label_key(value: Any) -> str | None:
    if not isinstance(value, str): return None
    normal = " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())
    return LABEL_ALIASES.get(normal) or KEY_ALIASES.get(_flat(value))


def _stat_value(stat: Any) -> Any:
    if isinstance(stat, dict):
        nested = stat.get("stat") if isinstance(stat.get("stat"), dict) else stat
        value = None
        for key in ("value", "rawValue", "statValue", "displayValue"):
            if key in nested and not isinstance(nested.get(key), (dict, list)):
                value = nested.get(key); break
        if value is None and nested is not stat:
            value = _stat_value(nested)
        if value is not None:
            unit = nested.get("unit") or nested.get("valueUnit") or nested.get("format")
            if isinstance(unit, str) and unit.strip() and isinstance(value, (int, float)):
                clean = unit.strip().casefold()
                if clean in {"m", "meter", "meters", "metre", "metres", "km", "kilometer", "kilometers", "kilometre", "kilometres"}:
                    return f"{value} {unit}"
            return value
    return stat if isinstance(stat, (int, float, str)) else None


def _stat_total(stat: Any) -> Any:
    if not isinstance(stat, dict): return None
    nested = stat.get("stat") if isinstance(stat.get("stat"), dict) else stat
    for key in ("total", "attempts", "max"):
        value = nested.get(key)
        if isinstance(value, (int, float)): return value
        if isinstance(value, str) and value.strip().replace(".", "", 1).isdigit(): return float(value)
    return None


def _capture(raw_key: str, stat: Any, out: dict[str, Any]) -> None:
    value = _stat_value(stat)
    if value is not None: out[raw_key] = value
    if raw_key in PASS_RATIO_KEYS:
        total = _stat_total(stat)
        if total is not None: out[f"{raw_key}__total"] = total


def _collect_stats(node: Any, out: dict[str, Any]) -> None:
    if isinstance(node, dict):
        node_key = _raw_key(node.get("key"))
        if node_key: _capture(node_key, node, out)
        descriptor = node.get("title") or node.get("label") or node.get("displayName") or node.get("statName")
        descriptor_key = _label_key(descriptor)
        if descriptor_key: _capture(descriptor_key, node, out)
        for label, value in node.items():
            label_key = _raw_key(label) or _label_key(label)
            if label_key and (isinstance(value, (int, float, str, dict))): _capture(label_key, value, out)
            if isinstance(value, dict):
                child_key = _raw_key(value.get("key"))
                if child_key: _capture(child_key, value, out)
                child_descriptor = value.get("title") or value.get("label") or value.get("displayName") or value.get("statName")
                child_descriptor_key = _label_key(child_descriptor)
                if child_descriptor_key: _capture(child_descriptor_key, value, out)
            _collect_stats(value, out)
    elif isinstance(node, list):
        for item in node: _collect_stats(item, out)


def _player_name(value: Any) -> str:
    if isinstance(value, str): return value.strip()
    if isinstance(value, dict):
        full = value.get("fullName") or value.get("displayName")
        if isinstance(full, str) and full.strip(): return full.strip()
        joined = " ".join(str(part).strip() for part in (value.get("firstName"), value.get("lastName")) if part)
        if joined: return joined
    return str(value or "").strip()


def _identity_key(name: str, team: str | None) -> tuple[str, str]:
    return " ".join(name.casefold().split()), " ".join((team or "").casefold().split())


def _to_km(value: Any) -> Any:
    text = str(value).strip().casefold().replace(",", "") if isinstance(value, str) else ""
    if text:
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match: return value
        number = float(match.group(0))
        if "km" in text: return round(number, 3)
        if re.search(r"\b(?:m|meter|meters|metre|metres)\b", text): return round(number / 1000.0, 3)
        return round(number / 1000.0, 3) if abs(number) > 100 else round(number, 3)
    if isinstance(value, (int, float)):
        number = float(value); return round(number / 1000.0, 3) if abs(number) > 100 else round(number, 3)
    return value


def _display_stats(raw: dict[str, Any]) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in TARGET_KEYS: continue
        label = TARGET_KEYS[key]; stats[label] = _to_km(value) if label in PHYSICAL_DISTANCE_LABELS else value
    for raw_key in PASS_RATIO_KEYS:
        total_key = f"{raw_key}__total"
        if total_key in raw: stats[f"{TARGET_KEYS[raw_key]} Total"] = raw[total_key]
    return stats


def _extract_explicit_player_stats(payload: dict[str, Any]) -> list[dict[str, Any]]:
    content = _page_props(payload).get("content") or {}; player_stats = content.get("playerStats") or {}
    if not isinstance(player_stats, dict): return []
    rows: list[dict[str, Any]] = []
    for fallback_id, player in player_stats.items():
        if not isinstance(player, dict): continue
        stats: dict[str, Any] = {}; _collect_stats(player, stats)
        if not any(key in TARGET_KEYS for key in stats): continue
        rows.append({"id": str(player.get("id") or fallback_id), "name": _player_name(player.get("name")), "team": player.get("teamName"), "raw_keys": stats})
    return rows


def _extract_global_player_stats(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows_by_identity: dict[tuple[str, str], dict[str, Any]] = {}
    def walk(node: Any, team: str | None = None) -> None:
        if isinstance(node, dict):
            local_team = team
            team_obj = node.get("team")
            if isinstance(team_obj, dict) and team_obj.get("name"): local_team = _player_name(team_obj.get("name"))
            elif isinstance(node.get("teamName"), str): local_team = node["teamName"]
            name = _player_name(node.get("name") or node.get("playerName"))
            player_id = node.get("id", node.get("playerId", node.get("player_id")))
            if name and player_id is not None:
                stats: dict[str, Any] = {}; _collect_stats(node, stats)
                if any(key in TARGET_KEYS for key in stats):
                    identity = _identity_key(name, local_team); existing = rows_by_identity.get(identity)
                    if existing is None: rows_by_identity[identity] = {"id": str(player_id), "name": name, "team": local_team, "raw_keys": dict(stats)}
                    else: existing.setdefault("raw_keys", {}).update(stats)
            for value in node.values(): walk(value, local_team)
        elif isinstance(node, list):
            for item in node: walk(item, team)
    walk(payload); return list(rows_by_identity.values())


def extract_player_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    # Do not stop at content.playerStats. FotMob physical-performance data can be
    # stored in a separate part of the page payload, so merge both traversals.
    combined: dict[tuple[str, str], dict[str, Any]] = {}
    by_id: dict[str, tuple[str, str]] = {}
    for row in [*_extract_explicit_player_stats(payload), *_extract_global_player_stats(payload)]:
        identity = _identity_key(row.get("name") or "", row.get("team"))
        row_id = str(row.get("id") or "")
        target_key = by_id.get(row_id) if row_id else None
        key = target_key or identity
        existing = combined.get(key)
        if existing is None:
            combined[key] = {"id": row_id, "name": row.get("name"), "team": row.get("team"), "raw_keys": dict(row.get("raw_keys") or {})}
            if row_id: by_id[row_id] = key
        else:
            existing.setdefault("raw_keys", {}).update(row.get("raw_keys") or {})
            if not existing.get("team") and row.get("team"): existing["team"] = row.get("team")
    rows: list[dict[str, Any]] = []
    for row in combined.values():
        row["stats"] = _display_stats(row.get("raw_keys", {})); rows.append(row)
    return rows


def diagnostic(match_id: str, match_url: str | None = None) -> dict[str, Any]:
    payload = fetch_match_details(match_id, match_url); rows = extract_player_rows(payload); content = _page_props(payload).get("content") or {}
    physical_counts = {label: sum(1 for row in rows if label in (row.get("stats") or {})) for label in PHYSICAL_DISTANCE_LABELS | {"Number of sprints"}}
    return {"source": "FotMob", "match_id": str(match_id), "production_values_changed": False, "target_keys": TARGET_KEYS, "players": rows, "debug": {"has_content": bool(content), "has_player_stats": bool(content.get("playerStats")) if isinstance(content, dict) else False, "player_count": len(rows), "physical_counts": physical_counts}}
