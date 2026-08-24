from __future__ import annotations

from typing import Any

import server

app = server.app

_TARGET_PATHS = {
    "/matches/{event_id}",
    "/matches/{event_id}/studio-match-stats",
    "/matches/{event_id}/players/{player_id}",
    "/matches/{event_id}/canonical-leaders/{metric_key_value}",
}


def _wrap(call):
    def healed(**kwargs: Any):
        event_id = str(kwargs.get("event_id") or "")
        if event_id:
            server._heal_event(event_id)
        return call(**kwargs)
    return healed


for route in app.routes:
    if getattr(route, "path", "") not in _TARGET_PATHS:
        continue
    dependant = getattr(route, "dependant", None)
    if dependant is None or getattr(dependant, "call", None) is None:
        continue
    dependant.call = _wrap(dependant.call)
