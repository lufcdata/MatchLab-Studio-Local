from __future__ import annotations

from typing import Any

from curl_cffi import requests


FOTMOB_MATCH_DETAILS_URL = "https://www.fotmob.com/api/data/matchDetails"

TARGET_KEYS = {
    "touches_opp_box": "Opposition Box Touches",
    "passes_into_final_third": "Passes Into Final Third",
    "headed_clearance": "Headed Clearances",
    "line_breaking_passes": "Line-Breaking Passes",
}


def fetch_match_details(match_id: str) -> dict[str, Any]:
    """Fetch FotMob match details for diagnostics only.

    This module deliberately does not mutate MatchLab's Golden data. It exists
    so we can prove the supplementary source before wiring it into production.
    """
    response = requests.get(
        FOTMOB_MATCH_DETAILS_URL,
        params={"matchId": str(match_id)},
        impersonate="chrome",
        timeout=20,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.fotmob.com/",
        },
    )
    response.raise_for_status()
    return response.json()


def _stat_value(stat: Any) -> Any:
    if isinstance(stat, dict):
        if isinstance(stat.get("stat"), dict) and "value" in stat["stat"]:
            return stat["stat"]["value"]
        if "value" in stat:
            return stat["value"]
    return stat if isinstance(stat, (int, float, str)) else None


def _collect_stats(node: Any, out: dict[str, Any]) -> None:
    """Recursively collect FotMob stat objects by their stable raw key."""
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


def _looks_like_player(node: dict[str, Any]) -> bool:
    return bool(
        node.get("name")
        and (
            node.get("id") is not None
            or node.get("playerId") is not None
            or node.get("player_id") is not None
        )
    )


def extract_player_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Find player-shaped nodes that contain at least one target stat."""
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def walk(node: Any, team: str | None = None) -> None:
        if isinstance(node, dict):
            local_team = team
            team_obj = node.get("team")
            if isinstance(team_obj, dict) and team_obj.get("name"):
                local_team = str(team_obj["name"])
            elif isinstance(node.get("teamName"), str):
                local_team = node["teamName"]

            if _looks_like_player(node):
                stats: dict[str, Any] = {}
                _collect_stats(node, stats)
                if stats:
                    player_id = str(node.get("id", node.get("playerId", node.get("player_id", ""))))
                    name = str(node.get("name"))
                    identity = (player_id, name)
                    if identity not in seen:
                        seen.add(identity)
                        rows.append({
                            "id": player_id,
                            "name": name,
                            "team": local_team,
                            "stats": {TARGET_KEYS[key]: value for key, value in stats.items()},
                            "raw_keys": stats,
                        })

            for value in node.values():
                walk(value, local_team)
        elif isinstance(node, list):
            for item in node:
                walk(item, team)

    walk(payload)
    return rows


def diagnostic(match_id: str) -> dict[str, Any]:
    payload = fetch_match_details(match_id)
    rows = extract_player_rows(payload)
    return {
        "source": "FotMob",
        "match_id": str(match_id),
        "production_values_changed": False,
        "target_keys": TARGET_KEYS,
        "players": rows,
    }
