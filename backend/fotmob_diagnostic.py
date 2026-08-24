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
}


def _get(url: str):
    return requests.get(
        url,
        impersonate="chrome",
        timeout=20,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Referer": "https://www.fotmob.com/",
        },
        allow_redirects=True,
    )


def _next_payload(html: str) -> dict[str, Any]:
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    )
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
        slug = re.sub(r"-(?:vs|v)-", " ", slug, flags=re.I)
        slug = slug.replace("-", " ")
        return " ".join(slug.split())
    return ""


def _resolve_numeric_match_id(match_url: str) -> str | None:
    """Resolve new FotMob alphanumeric page slugs through the public search API."""
    query = _query_from_match_url(match_url)
    if not query:
        return None
    url = f"https://apigw.fotmob.com/searchapi/suggest?term={quote_plus(query)}&lang=en"
    try:
        response = _get(url)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    options: list[dict[str, Any]] = []
    for group in data.get("matchSuggest", []) or []:
        options.extend(group.get("options", []) or [])

    wanted_tokens = {t for t in re.findall(r"[a-z0-9]+", query.casefold()) if len(t) > 2 and t not in {"united", "city", "football", "club"}}
    best: tuple[int, str] | None = None
    for option in options:
        payload = option.get("payload") or {}
        numeric_id = payload.get("id")
        if numeric_id is None:
            continue
        haystack = " ".join(str(payload.get(k) or "") for k in ("homeName", "awayName", "name", "leagueName")).casefold()
        score = sum(1 for token in wanted_tokens if token in haystack)
        candidate = (score, str(numeric_id))
        if best is None or candidate[0] > best[0]:
            best = candidate
    return best[1] if best else None


def fetch_match_details(match_id: str, match_url: str | None = None) -> dict[str, Any]:
    """Fetch FotMob page data; retry via numeric match ID for new slug URLs."""
    # FotMob also emits a third URL shape such as:
    # /matches/team-a-vs-team-b/2fh3fh#4813705
    # Browser fragments are never sent to the server. When an explicit numeric
    # ID is present after #, skip the slug page entirely and use the canonical
    # numeric route. This preserves old numeric IDs and the newer slug resolver.
    has_numeric_hash = bool(match_url and re.search(r"#\d+(?::|$)", match_url))
    if has_numeric_hash and str(match_id).isdigit():
        url = f"https://www.fotmob.com/match/{match_id}"
    else:
        url = match_url or f"https://www.fotmob.com/match/{match_id}"

    response = _get(url)
    response.raise_for_status()
    payload = _next_payload(response.text)
    if _has_player_stats(payload):
        return payload

    # New FotMob page codes (e.g. 2vqauu) can serve a deferred shell. Resolve
    # the underlying numeric match ID from the public search API and retry the
    # canonical /match/<id> route, which is more likely to include playerStats.
    numeric_id = str(match_id) if str(match_id).isdigit() else None
    if not numeric_id and match_url:
        numeric_id = _resolve_numeric_match_id(match_url)
    if numeric_id:
        retry = _get(f"https://www.fotmob.com/match/{numeric_id}")
        retry.raise_for_status()
        retry_payload = _next_payload(retry.text)
        if _has_player_stats(retry_payload):
            return retry_payload
        # Return the richer retry payload even when deferred; diagnostic metadata
        # below will make the absence visible instead of silently inventing stats.
        return retry_payload
    return payload


def _stat_value(stat: Any) -> Any:
    if isinstance(stat, dict):
        if isinstance(stat.get("stat"), dict) and "value" in stat["stat"]:
            return stat["stat"]["value"]
        if "value" in stat:
            return stat["value"]
    return stat if isinstance(stat, (int, float, str)) else None


def _collect_stats(node: Any, out: dict[str, Any]) -> None:
    if isinstance(node, dict):
        key = node.get("key")
        if isinstance(key, str) and key in TARGET_KEYS:
            value = _stat_value(node)
            if value is not None:
                out[key] = value
        for label, value in node.items():
            if isinstance(value, dict):
                raw_key = value.get("key")
                if isinstance(raw_key, str) and raw_key in TARGET_KEYS:
                    stat_value = _stat_value(value)
                    if stat_value is not None:
                        out[raw_key] = stat_value
                elif label in TARGET_KEYS:
                    stat_value = _stat_value(value)
                    if stat_value is not None:
                        out[label] = stat_value
            _collect_stats(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_stats(item, out)


def _player_name(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        full = value.get("fullName") or value.get("displayName")
        if isinstance(full, str) and full.strip():
            return full.strip()
        first = value.get("firstName")
        last = value.get("lastName")
        joined = " ".join(str(part).strip() for part in (first, last) if part)
        if joined:
            return joined
    return str(value or "").strip()


def _identity_key(name: str, team: str | None) -> tuple[str, str]:
    normalized_name = " ".join(name.casefold().split())
    normalized_team = " ".join((team or "").casefold().split())
    return normalized_name, normalized_team


def _extract_explicit_player_stats(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse the canonical content.playerStats map used by current FotMob pages."""
    content = _page_props(payload).get("content") or {}
    player_stats = content.get("playerStats") or {}
    if not isinstance(player_stats, dict):
        return []
    rows: list[dict[str, Any]] = []
    for fallback_id, player in player_stats.items():
        if not isinstance(player, dict):
            continue
        stats: dict[str, Any] = {}
        _collect_stats(player.get("stats") or [], stats)
        if not stats:
            continue
        rows.append({
            "id": str(player.get("id") or fallback_id),
            "name": _player_name(player.get("name")),
            "team": player.get("teamName"),
            "raw_keys": stats,
            "stats": {TARGET_KEYS[key]: value for key, value in stats.items() if key in TARGET_KEYS},
        })
    return rows


def extract_player_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract target stats, preferring FotMob's explicit playerStats structure."""
    explicit = _extract_explicit_player_stats(payload)
    if explicit:
        return explicit

    rows_by_identity: dict[tuple[str, str], dict[str, Any]] = {}

    def walk(node: Any, team: str | None = None) -> None:
        if isinstance(node, dict):
            local_team = team
            team_obj = node.get("team")
            if isinstance(team_obj, dict) and team_obj.get("name"):
                local_team = _player_name(team_obj.get("name"))
            elif isinstance(node.get("teamName"), str):
                local_team = node["teamName"]

            name = _player_name(node.get("name"))
            player_id = node.get("id", node.get("playerId", node.get("player_id")))
            if name and player_id is not None:
                stats: dict[str, Any] = {}
                _collect_stats(node, stats)
                if stats:
                    identity = _identity_key(name, local_team)
                    existing = rows_by_identity.get(identity)
                    if existing is None:
                        rows_by_identity[identity] = {
                            "id": str(player_id), "name": name, "team": local_team, "raw_keys": dict(stats)
                        }
                    else:
                        existing.setdefault("raw_keys", {}).update(stats)
            for value in node.values():
                walk(value, local_team)
        elif isinstance(node, list):
            for item in node:
                walk(item, team)

    walk(payload)
    rows: list[dict[str, Any]] = []
    for row in rows_by_identity.values():
        raw_keys = row.get("raw_keys", {})
        row["stats"] = {TARGET_KEYS[key]: value for key, value in raw_keys.items() if key in TARGET_KEYS}
        rows.append(row)
    return rows


def diagnostic(match_id: str, match_url: str | None = None) -> dict[str, Any]:
    payload = fetch_match_details(match_id, match_url)
    rows = extract_player_rows(payload)
    page_props = _page_props(payload)
    content = page_props.get("content") or {}
    return {
        "source": "FotMob",
        "match_id": str(match_id),
        "production_values_changed": False,
        "target_keys": TARGET_KEYS,
        "players": rows,
        "debug": {
            "has_content": bool(content),
            "has_player_stats": bool(content.get("playerStats")) if isinstance(content, dict) else False,
            "player_count": len(rows),
        },
    }
