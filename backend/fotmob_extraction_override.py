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


def _full_match_team_distance(payload: dict[str, Any]) -> tuple[dict[str, float], dict[str, str]]:
    """Read FotMob's authoritative full-match team Distance covered values, when exposed."""
    page = fd._page_props(payload)
    content = page.get("content") or {}
    periods = ((content.get("stats") or {}).get("Periods") or {})
    all_period = periods.get("All") or periods.get("ALL") or periods.get("all") or {}

    pair: list[Any] | tuple[Any, ...] | None = None
    for group in all_period.get("stats", []) or []:
        if not isinstance(group, dict):
            continue
        for stat in group.get("stats", []) or []:
            if not isinstance(stat, dict):
                continue
            label = str(stat.get("title") or stat.get("name") or stat.get("key") or "")
            if fd._label_key(label) != "distance_covered":
                continue
            values = stat.get("stats")
            if isinstance(values, (list, tuple)) and len(values) >= 2:
                pair = values
                break
        if pair is not None:
            break

    if pair is None:
        return {}, {}

    general = page.get("general") or content.get("general") or {}
    home = general.get("homeTeam") or {}
    away = general.get("awayTeam") or {}
    teams = (
        (str(home.get("id") or ""), fd._player_name(home.get("name")) or "home", pair[0]),
        (str(away.get("id") or ""), fd._player_name(away.get("name")) or "away", pair[1]),
    )

    by_id: dict[str, float] = {}
    names: dict[str, str] = {}
    for team_id, team_name, raw in teams:
        value = fd._to_km(fd._stat_value(raw))
        try:
            km = float(value)
        except (TypeError, ValueError):
            continue
        if km <= 0:
            continue
        if team_id:
            by_id[team_id] = km
            names[team_id] = team_name
    return by_id, names


def _reconcile_single_missing_distance(payload: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    """Recover one omitted player distance from FotMob's own team total.

    This is deliberately conservative: it runs only when FotMob exposes a full-match
    team Distance covered total and exactly one *participating* player for that team
    lacks a player distance. No fixture/player constants are used.
    """
    team_totals, team_names = _full_match_team_distance(payload)
    if not team_totals:
        return

    content = fd._page_props(payload).get("content") or {}
    player_stats = content.get("playerStats") or {}
    if not isinstance(player_stats, dict):
        return

    participants_by_team: dict[str, list[str]] = {}
    identity_by_id: dict[str, dict[str, Any]] = {}
    for fallback_id, player in player_stats.items():
        if not isinstance(player, dict):
            continue
        player_id = str(player.get("id") or fallback_id or "")
        team_id = str(player.get("teamId") or player.get("team_id") or "")
        stat_groups = player.get("stats")
        # FotMob gives unused substitutes an empty stats collection. Restrict the
        # reconciliation population to players who actually have match statistics.
        if not player_id or not team_id or not stat_groups:
            continue
        participants_by_team.setdefault(team_id, []).append(player_id)
        identity_by_id[player_id] = {
            "name": fd._player_name(player.get("name")),
            "team": player.get("teamName") or team_names.get(team_id),
        }

    by_id: dict[str, dict[str, Any]] = {
        str(row.get("id")): row
        for row in rows
        if row.get("id") not in (None, "")
    }

    for team_id, total_km in team_totals.items():
        participants = participants_by_team.get(team_id) or []
        if not participants:
            continue

        known_sum = 0.0
        missing: list[str] = []
        for player_id in participants:
            row = by_id.get(player_id)
            value = None
            if row is not None:
                value = (row.get("stats") or {}).get("Distance covered (km)")
            try:
                known_sum += float(value)
            except (TypeError, ValueError):
                missing.append(player_id)

        if len(missing) != 1:
            continue

        residual = round(float(total_km) - known_sum, 3)
        # A conservative football-distance sanity range prevents accidental
        # reconciliation against a malformed/partial team statistic.
        if residual < 0.5 or residual > 20.0:
            continue

        player_id = missing[0]
        row = by_id.get(player_id)
        if row is None:
            identity = identity_by_id.get(player_id) or {}
            if not identity.get("name"):
                continue
            row = {
                "id": player_id,
                "name": identity.get("name"),
                "team": identity.get("team"),
                "raw_keys": {},
            }
            rows.append(row)
            by_id[player_id] = row

        row.setdefault("raw_keys", {})["distance_covered"] = residual
        row["stats"] = fd._display_stats(row.get("raw_keys") or {})
        row.setdefault("provenance", {})["Distance covered (km)"] = {
            "source": "FotMob full-match team stats",
            "method": "team total minus known participating-player distances",
            "team_total_km": round(float(total_km), 3),
            "known_player_sum_km": round(known_sum, 3),
            "derived_value_km": residual,
        }


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

    _reconcile_single_missing_distance(payload, existing)
    return existing


# diagnostic() resolves extract_player_rows through fotmob_diagnostic's module
# globals at call time, so patching this one canonical extractor automatically
# reaches the existing server audit/import path without duplicating provider logic.
fd.extract_player_rows = extract_player_rows
