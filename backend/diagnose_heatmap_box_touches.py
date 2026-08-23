from __future__ import annotations

from typing import Any

from curl_cffi import requests

BASE = "https://www.sofascore.com/api/v1"
TARGET_DATE = "2026-05-01"
TARGET_HOME = "Leeds United"
TARGET_AWAY = "Burnley"
TARGET_PLAYERS = {"Noah Okafor", "Dominic Calvert-Lewin"}

# Standard football penalty area, projected onto SofaScore's documented 0-100 pitch.
# Pitch: 105m x 68m. Penalty-area depth: 16.5m. Width: 40.32m.
BOX_X_MIN = (105.0 - 16.5) / 105.0 * 100.0
BOX_Y_MIN = ((68.0 - 40.32) / 2.0) / 68.0 * 100.0
BOX_Y_MAX = 100.0 - BOX_Y_MIN


def get_json(path: str) -> dict[str, Any]:
    url = f"{BASE}/{path.lstrip('/')}"
    response = requests.get(
        url,
        impersonate="chrome",
        timeout=30,
        headers={"Accept": "application/json", "Referer": "https://www.sofascore.com/"},
    )
    response.raise_for_status()
    return response.json()


def event_name(event: dict[str, Any], side: str) -> str:
    return str((event.get(f"{side}Team") or {}).get("name") or "")


def find_target_event() -> dict[str, Any]:
    payload = get_json(f"sport/football/scheduled-events/{TARGET_DATE}")
    events = payload.get("events") or []
    for event in events:
        home = event_name(event, "home")
        away = event_name(event, "away")
        if home == TARGET_HOME and away == TARGET_AWAY:
            return event
    candidates = [
        (event.get("id"), event_name(event, "home"), event_name(event, "away"))
        for event in events
        if "Leeds" in event_name(event, "home") + event_name(event, "away")
        or "Burnley" in event_name(event, "home") + event_name(event, "away")
    ]
    raise RuntimeError(f"Target event not found. Nearby candidates: {candidates}")


def lineup_players(lineups: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for side in ("home", "away"):
        for row in ((lineups.get(side) or {}).get("players") or []):
            player = row.get("player") or {}
            stats = row.get("statistics") or {}
            out.append(
                {
                    "id": player.get("id"),
                    "name": player.get("name"),
                    "side": side,
                    "stats": stats,
                }
            )
    return out


def heatmap_points(payload: dict[str, Any]) -> list[dict[str, float]]:
    raw = payload.get("heatmap")
    if not isinstance(raw, list):
        raw = payload.get("points")
    if not isinstance(raw, list):
        raw = payload.get("data")
    if not isinstance(raw, list):
        return []
    points: list[dict[str, float]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            x = float(item.get("x"))
            y = float(item.get("y"))
        except (TypeError, ValueError):
            continue
        points.append({"x": x, "y": y})
    return points


def inside_opposition_box(point: dict[str, float]) -> bool:
    return point["x"] >= BOX_X_MIN and BOX_Y_MIN <= point["y"] <= BOX_Y_MAX


def first_number(stats: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = stats.get(key)
        if value is not None:
            return value
    return None


def main() -> None:
    event = find_target_event()
    event_id = str(event["id"])
    print(f"EVENT {event_id}: {event_name(event, 'home')} vs {event_name(event, 'away')}")
    print(f"BOX x >= {BOX_X_MIN:.4f}; y {BOX_Y_MIN:.4f}..{BOX_Y_MAX:.4f}")

    lineups = get_json(f"event/{event_id}/lineups")
    players = lineup_players(lineups)

    found = set()
    for player in players:
        name = str(player.get("name") or "")
        if name not in TARGET_PLAYERS:
            continue
        found.add(name)
        player_id = str(player["id"])
        stats = player["stats"]
        official_touches = first_number(stats, ["touches", "totalTouches"])
        direct_box = first_number(
            stats,
            [
                "touchesInOppBox",
                "touchesInOppositionBox",
                "penaltyBoxTouches",
                "touchesInPenaltyArea",
                "touchesInPenaltyBox",
                "touchesInsideOppositionBox",
            ],
        )
        heatmap = get_json(f"event/{event_id}/player/{player_id}/heatmap")
        points = heatmap_points(heatmap)
        box_points = [point for point in points if inside_opposition_box(point)]

        print("---")
        print(f"PLAYER {name} ({player_id})")
        print(f"official_touches={official_touches}")
        print(f"direct_touchesInOppBox={direct_box}")
        print(f"heatmap_points={len(points)}")
        print(f"derived_box_touches={len(box_points)}")
        print(f"box_points={box_points}")
        print(f"lineup_stat_keys={sorted(stats.keys())}")

    missing = TARGET_PLAYERS - found
    if missing:
        raise RuntimeError(f"Target players missing from lineups: {sorted(missing)}")


if __name__ == "__main__":
    main()
