from __future__ import annotations

import json
from typing import Any

import server


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _distance_from_fotmob_player(player: dict[str, Any]) -> float | None:
    stats = player.get("stats") or {}
    return _num(stats.get("Distance covered (km)"))


def _distance_from_lineup_row(row: dict[str, Any]) -> float | None:
    stats = row.get("statistics") or {}
    return _num(stats.get("distanceCoveredKm"))


def _lineup_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for side in ("home", "away"):
        team = (((payload.get("basic") or {}).get("event") or {}).get(f"{side}Team") or {}).get("name")
        for row in ((((payload.get("lineups") or {}).get(side) or {}).get("players") or [])):
            player = row.get("player") or {}
            result.append({
                "side": side,
                "team": team,
                "id": str(player.get("id") or ""),
                "name": player.get("name"),
                "distance_km": _distance_from_lineup_row(row),
            })
    return result


def _fotmob_rows(players: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(player.get("id") or ""),
            "name": player.get("name"),
            "team": player.get("team"),
            "distance_km": _distance_from_fotmob_player(player),
        }
        for player in players or []
    ]


def _team_totals(rows: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in rows:
        value = _num(row.get("distance_km"))
        team = str(row.get("team") or row.get("side") or "Unknown")
        if value is not None:
            totals[team] = round(totals.get(team, 0.0) + value, 3)
    return totals


@server.app.get("/audit/physical-distance/{event_id}")
def physical_distance_audit(event_id: str):
    """Read-only audit of stored, freshly fetched and promoted physical distance data."""
    path = server.DATA_DIR / f"{event_id}.json"
    if not path.exists():
        raise server.HTTPException(404, "Match has not been imported into MatchLab yet.")

    payload = json.loads(path.read_text())
    stored = payload.get("fotmob") or {}
    stored_players = stored.get("players") or []
    stored_rows = _fotmob_rows(stored_players)
    lineup_rows = _lineup_rows(payload)

    source = str(stored.get("source") or stored.get("match_id") or "").strip()
    fresh_rows: list[dict[str, Any]] = []
    fresh_error: str | None = None
    if source:
        try:
            match_id = str(server._fotmob_match_id(source))
            url = source if source.lower().startswith(("http://", "https://")) else None
            fresh = server._fotmob_result(match_id, url)
            fresh_rows = _fotmob_rows(fresh.get("players") or [])
        except Exception as exc:
            fresh_error = str(exc)

    missing_promoted = [row for row in lineup_rows if row.get("distance_km") is None]
    missing_stored = [row for row in stored_rows if row.get("distance_km") is None]
    missing_fresh = [row for row in fresh_rows if row.get("distance_km") is None]

    return {
        "event_id": event_id,
        "fotmob_source": source or None,
        "stored": {
            "player_count": len(stored_rows),
            "distance_count": len(stored_rows) - len(missing_stored),
            "team_totals_km": _team_totals(stored_rows),
            "players": stored_rows,
        },
        "fresh": {
            "error": fresh_error,
            "player_count": len(fresh_rows),
            "distance_count": len(fresh_rows) - len(missing_fresh),
            "team_totals_km": _team_totals(fresh_rows),
            "players": fresh_rows,
        },
        "promoted_lineup": {
            "player_count": len(lineup_rows),
            "distance_count": len(lineup_rows) - len(missing_promoted),
            "team_totals_km": _team_totals(lineup_rows),
            "players": lineup_rows,
        },
        "summary": {
            "stored_missing_distance_names": [row.get("name") for row in missing_stored],
            "fresh_missing_distance_names": [row.get("name") for row in missing_fresh],
            "promoted_missing_distance_names": [row.get("name") for row in missing_promoted],
        },
    }
