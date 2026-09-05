from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import server

RECENT_MATCH_REFRESH_HOURS = 6


def _stored_fotmob(event_id: str) -> dict[str, Any] | None:
    path = server.DATA_DIR / f"{event_id}.json"
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text()).get("fotmob") or None
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _same_fotmob_reference(requested: str, stored: dict[str, Any]) -> bool:
    requested = (requested or "").strip()
    if not requested:
        return True
    stored_source = str(stored.get("source") or stored.get("match_id") or "").strip()
    if not stored_source:
        return False
    try:
        return str(server._fotmob_match_id(requested)) == str(server._fotmob_match_id(stored_source))
    except Exception:
        return requested.rstrip("/").casefold() == stored_source.rstrip("/").casefold()


def _match_start_timestamp(payload: dict[str, Any]) -> float | None:
    basic = payload.get("basic") or {}
    event = basic.get("event") if isinstance(basic, dict) else None
    if not isinstance(event, dict):
        event = basic if isinstance(basic, dict) else {}
    value = event.get("startTimestamp") if isinstance(event, dict) else None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _recent_match_needs_live_fotmob(payload: dict[str, Any]) -> bool:
    """Avoid freezing partially-populated FotMob physical data just after full time."""
    start = _match_start_timestamp(payload)
    if start is None:
        return False
    now = datetime.now(timezone.utc).timestamp()
    return start <= now <= start + (RECENT_MATCH_REFRESH_HOURS * 3600)


def import_linked_cached(req: server.LinkedImportRequest):
    """Refresh SofaScore and reuse FotMob only once a match is outside the live-settling window."""
    requested_event_id = server._sofascore_event_id(req.sofascore_source)
    previous_fotmob = _stored_fotmob(requested_event_id) if requested_event_id else None

    imported = server.import_sofascore(server.ImportRequest(source=req.sofascore_source))
    event_id = str(imported["event_id"])
    path = server.DATA_DIR / f"{event_id}.json"
    payload = json.loads(path.read_text())

    requested_fotmob_source = (req.fotmob_source or "").strip()
    promoted_counts: dict[str, int] = {}
    reused_fotmob = False
    recent_match_refresh = _recent_match_needs_live_fotmob(payload)

    if (
        previous_fotmob
        and not recent_match_refresh
        and _same_fotmob_reference(requested_fotmob_source, previous_fotmob)
    ):
        cached_players = previous_fotmob.get("players") or []
        if cached_players:
            promoted_counts = server._promote_validated_fotmob_fields(payload, cached_players)
            cached = dict(previous_fotmob)
            cached["validated_fields"] = list(server.PROMOTED_FOTMOB_FIELDS.keys())
            cached["provider_role"] = "supplementary"
            cached["promoted_player_counts"] = promoted_counts
            payload["fotmob"] = cached
            server._persist_payload(event_id, payload)
            reused_fotmob = True

    if not reused_fotmob:
        fotmob_source = requested_fotmob_source
        if not fotmob_source and previous_fotmob:
            fotmob_source = str(previous_fotmob.get("source") or previous_fotmob.get("match_id") or "").strip()
        if fotmob_source:
            promoted_counts = server._attach_fotmob(payload, fotmob_source)
            server._persist_payload(event_id, payload)

    fotmob = payload.get("fotmob") or {}
    return {
        "ok": True,
        "event_id": event_id,
        "sources": {
            "sofascore": True,
            "fotmob": bool(fotmob),
            "fotmob_match_id": fotmob.get("match_id"),
            "validated_fields": fotmob.get("validated_fields", []),
            "promoted_player_counts": promoted_counts,
            "fotmob_reused": reused_fotmob,
            "fotmob_recent_refresh": recent_match_refresh,
        },
    }


def install() -> None:
    """Replace only the linked-import handler; metric readers remain untouched."""
    server.import_linked = import_linked_cached
    for route in server.app.routes:
        if getattr(route, "path", "") != "/matches/import-linked":
            continue
        route.endpoint = import_linked_cached
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            dependant.call = import_linked_cached
        break


install()
