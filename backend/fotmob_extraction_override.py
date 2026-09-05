from __future__ import annotations

from typing import Any

import fotmob_diagnostic as fd

_base_extract_player_rows = fd.extract_player_rows


def _player_registry(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build a conservative player-id registry from named player-shaped nodes."""
    registry: dict[str, dict[str, Any]] = {}

    def walk(node: Any, team: str | None = None) -> None:
        if isinstance(node, dict):
            local_team = team
            team_obj = node.get("team")
            if isinstance(team_obj, dict) and team_obj.get("name"):
                local_team = fd._player_name(team_obj.get("name"))
            elif isinstance(node.get("teamName"), str):
                local_team = node.get("teamName")

            name = fd._player_name(node.get("playerName") or node.get("name"))
            explicit_player_id = node.get("playerId", node.get("player_id"))
            generic_id = node.get("id")
            looks_player_shaped = any(
                key in node
                for key in ("playerName", "position", "shirtNumber", "isCaptain", "minutesPlayed", "rating")
            )
            player_id = explicit_player_id if explicit_player_id is not None else (generic_id if looks_player_shaped else None)
            if name and player_id is not None:
                key = str(player_id)
                current = registry.get(key) or {}
                if not current.get("name"):
                    current["name"] = name
                if local_team and not current.get("team"):
                    current["team"] = local_team
                registry[key] = current

            for value in node.values():
                walk(value, local_team)
        elif isinstance(node, list):
            for item in node:
                walk(item, team)

    walk(payload)
    return registry


def _id_only_physical_rows(payload: dict[str, Any], registry: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Recover stat blocks that FotMob exposes by player id without repeating the player's name."""
    recovered: dict[str, dict[str, Any]] = {}

    def capture(node: dict[str, Any], candidate_id: Any) -> None:
        if candidate_id is None:
            return
        player_id = str(candidate_id)
        identity = registry.get(player_id)
        if not identity or not identity.get("name"):
            return
        stats: dict[str, Any] = {}
        fd._collect_stats(node, stats)
        if not any(key in fd.TARGET_KEYS for key in stats):
            return
        row = recovered.get(player_id)
        if row is None:
            recovered[player_id] = {
                "id": player_id,
                "name": identity.get("name"),
                "team": identity.get("team"),
                "raw_keys": dict(stats),
            }
        else:
            row.setdefault("raw_keys", {}).update(stats)

    def walk(node: Any, parent_key: Any = None) -> None:
        if isinstance(node, dict):
            candidate_id = node.get("playerId", node.get("player_id"))
            if candidate_id is None and parent_key is not None and str(parent_key).isdigit():
                candidate_id = parent_key
            if candidate_id is not None:
                capture(node, candidate_id)
            for key, value in node.items():
                walk(value, key)
        elif isinstance(node, list):
            for item in node:
                walk(item, parent_key)

    walk(payload)
    return list(recovered.values())


def extract_player_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    existing = _base_extract_player_rows(payload)
    registry = _player_registry(payload)
    recovered = _id_only_physical_rows(payload, registry)

    by_id: dict[str, dict[str, Any]] = {
        str(row.get("id")): row
        for row in existing
        if row.get("id") not in (None, "")
    }

    for row in recovered:
        row_id = str(row.get("id") or "")
        current = by_id.get(row_id)
        if current is None:
            row["stats"] = fd._display_stats(row.get("raw_keys") or {})
            existing.append(row)
            by_id[row_id] = row
            continue
        current.setdefault("raw_keys", {}).update(row.get("raw_keys") or {})
        current["stats"] = fd._display_stats(current.get("raw_keys") or {})
        if not current.get("team") and row.get("team"):
            current["team"] = row.get("team")

    return existing


# diagnostic() resolves extract_player_rows through fotmob_diagnostic's module
# globals at call time, so patching this one canonical extractor automatically
# reaches the existing server audit/import path without duplicating provider logic.
fd.extract_player_rows = extract_player_rows
