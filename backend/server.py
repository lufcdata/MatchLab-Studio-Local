from __future__ import annotations

from fastapi import HTTPException, Query

from main import app
from fotmob_diagnostic import diagnostic


@app.get("/audit/fotmob/{match_id}")
def fotmob_audit(match_id: str, url: str | None = Query(default=None)):
    """Diagnostic-only FotMob player-stat audit.

    This endpoint deliberately does not mutate MatchLab Golden/SofaScore data.
    It exposes the four supplementary FotMob fields so they can be reconciled
    against known player values and team totals before promotion.
    """
    try:
        result = diagnostic(match_id, url)
    except Exception as exc:
        raise HTTPException(502, f"FotMob diagnostic failed: {exc}") from exc

    players = result.get("players", [])
    team_totals: dict[str, dict[str, float]] = {}
    for player in players:
        team = str(player.get("team") or "Unknown")
        totals = team_totals.setdefault(team, {})
        for label, value in (player.get("stats") or {}).items():
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            totals[label] = totals.get(label, 0.0) + numeric

    result["team_totals"] = team_totals
    result["audit_only"] = True
    result["golden_values_changed"] = False
    return result
