from __future__ import annotations

import html
import json
import re
import unicodedata
from typing import Dict, Optional

from fastapi import HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from main import DATA_DIR, ImportRequest, METRICS, app, import_sofascore
from golden_metrics import REQUIRED_PLAYER_LABELS
from fotmob_diagnostic import diagnostic


# FotMob supplement metrics are canonical MatchLab metrics. Keep Successful Final
# Third Passes separate: Passes Into Final Third is the FotMob total field.
for _existing in METRICS:
    if _existing.get("label") == "Final Third Passes":
        _existing["label"] = "Passes Into Final Third"
        _existing["sofascore"] = "FotMob supplement"
        _existing["match_keys"] = ["passesIntoFinalThird", "totalFinalThirdPasses"]
        _existing["player_keys"] = ["passesIntoFinalThird", "totalFinalThirdPasses"]
        break

for _metric in (
    {"label":"Line-Breaking Passes","sofascore":"FotMob supplement","match_keys":["lineBreakingPasses"],"player_keys":["lineBreakingPasses"]},
    {"label":"Headed Clearances","sofascore":"FotMob supplement","match_keys":["headedClearances"],"player_keys":["headedClearances"]},
):
    if not any(m.get("label") == _metric["label"] for m in METRICS):
        METRICS.append(_metric)
    else:
        existing = next(m for m in METRICS if m.get("label") == _metric["label"])
        existing["sofascore"] = "FotMob supplement"
        existing["match_keys"] = list(_metric["match_keys"])
        existing["player_keys"] = list(_metric["player_keys"])

# Possession is always a percentage in MatchLab.
for _existing in METRICS:
    if _existing.get("label") == "Possession":
        _existing["suffix"] = "%"
        break


class LinkedImportRequest(BaseModel):
    sofascore_source: str
    fotmob_source: Optional[str] = None


def _sofascore_event_id(source: str) -> str:
    source = (source or "").strip()
    if source.isdigit():
        return source
    match = re.search(r"(?:id:|event/)(\d+)", source, re.I) or re.search(r"[?&#]id=(\d+)", source, re.I)
    return match.group(1) if match else ""


def _fotmob_match_id(source: str) -> str:
    source = (source or "").strip()
    if source.isdigit(): return source
    for pattern in [r"#(\d+)(?::|$)", r"/matches/[^#?]+/(\d+)(?::|$)", r"/match/(\d+)", r"[?&](?:matchId|id)=(\d+)"]:
        match = re.search(pattern, source, re.I)
        if match: return match.group(1)
    raise HTTPException(400, "Could not find a FotMob match ID in that URL.")


def _fotmob_result(match_id: str, url: Optional[str] = None):
    try: result = diagnostic(match_id, url)
    except Exception as exc: raise HTTPException(502, f"FotMob diagnostic failed: {exc}") from exc
    players = result.get("players", [])
    team_totals: Dict[str, Dict[str, float]] = {}
    for player in players:
        team = str(player.get("team") or "Unknown"); totals = team_totals.setdefault(team, {})
        for label, value in (player.get("stats") or {}).items():
            try: numeric = float(value)
            except (TypeError, ValueError): continue
            totals[label] = totals.get(label, 0.0) + numeric
    result["team_totals"] = team_totals; result["audit_only"] = True; result["golden_values_changed"] = False
    return result


def _norm_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")); text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


PROMOTED_FOTMOB_FIELDS = {
    "Opposition Box Touches": "touchesInOppBox",
    "Passes Into Final Third": "passesIntoFinalThird",
    "Line-Breaking Passes": "lineBreakingPasses",
    "Headed Clearances": "headedClearances",
    "Clearances Off Line": "clearancesOffLine",
    "Distance covered (km)": "distanceCoveredKm",
    "Number of sprints": "numberOfSprints",
    "Sprinting (km)": "sprintingKm",
}
# These established event-derived supplements historically use 0 when a player
# has no event. Physical fields must never be fabricated as zero when FotMob did
# not supply tracking data for that player.
ZERO_WHEN_MISSING_FOTMOB_FIELDS = {
    "Opposition Box Touches", "Passes Into Final Third", "Line-Breaking Passes",
    "Headed Clearances", "Clearances Off Line",
}
REQUIRED_PLAYER_LABELS.update(PROMOTED_FOTMOB_FIELDS.keys())


def _promote_validated_fotmob_fields(payload: dict, fotmob_players: list) -> Dict[str, int]:
    """Inject validated FotMob values into the exact SofaScore lineup rows consumed by all APIs."""
    by_name = {}
    for player in fotmob_players or []:
        stats = player.get("stats") or {}
        if not stats:
            continue
        values = {}
        for label in PROMOTED_FOTMOB_FIELDS:
            if label in stats:
                values[label] = stats[label]
            elif label in ZERO_WHEN_MISSING_FOTMOB_FIELDS:
                values[label] = 0
        by_name[_norm_name(player.get("name"))] = values
    promoted = {label: 0 for label in PROMOTED_FOTMOB_FIELDS}
    for side in ("home", "away"):
        for row in (((payload.get("lineups") or {}).get(side) or {}).get("players") or []):
            player = row.get("player", {}) or {}
            values = by_name.get(_norm_name(player.get("name")))
            if values is None:
                continue
            stats = row.setdefault("statistics", {})
            for label, value in values.items():
                stats[PROMOTED_FOTMOB_FIELDS[label]] = value
                promoted[label] += 1
    return promoted


def _promote_stored_fotmob(payload: dict) -> Dict[str, int]:
    """Self-heal older local match JSONs that already contain a FotMob supplement."""
    fotmob = payload.get("fotmob") or {}
    players = fotmob.get("players") or []
    if not players:
        return {}
    counts = _promote_validated_fotmob_fields(payload, players)
    fotmob["validated_fields"] = list(PROMOTED_FOTMOB_FIELDS.keys())
    fotmob["promoted_player_counts"] = counts
    payload["fotmob"] = fotmob
    return counts


def _attach_fotmob(payload: dict, fotmob_source: str) -> Dict[str, int]:
    fotmob_id = _fotmob_match_id(fotmob_source)
    fotmob_url = fotmob_source if fotmob_source.lower().startswith(("http://", "https://")) else None
    supplement = _fotmob_result(fotmob_id, fotmob_url); players = supplement.get("players", [])
    promoted_counts = _promote_validated_fotmob_fields(payload, players)
    payload["fotmob"] = {
        "match_id": fotmob_id, "source": fotmob_source, "players": players,
        "team_totals": supplement.get("team_totals", {}),
        "validated_fields": list(PROMOTED_FOTMOB_FIELDS.keys()), "provider_role": "supplementary",
        "promoted_player_counts": promoted_counts,
    }
    return promoted_counts


def _persist_payload(event_id: str, payload: dict) -> None:
    (DATA_DIR / f"{event_id}.json").write_text(json.dumps(payload, ensure_ascii=False))


def _heal_event(event_id: str) -> dict:
    path = DATA_DIR / f"{event_id}.json"
    if not path.exists():
        raise HTTPException(404, "Match has not been imported into MatchLab yet.")
    payload = json.loads(path.read_text())
    counts = _promote_stored_fotmob(payload)
    if counts:
        _persist_payload(event_id, payload)
    return payload


@app.post("/matches/import-linked")
def import_linked(req: LinkedImportRequest):
    """Import SofaScore and keep/reapply the linked FotMob supplement."""
    requested_event_id = _sofascore_event_id(req.sofascore_source)
    previous_fotmob = None
    if requested_event_id:
        previous_path = DATA_DIR / f"{requested_event_id}.json"
        if previous_path.exists():
            try: previous_fotmob = (json.loads(previous_path.read_text()).get("fotmob") or None)
            except Exception: previous_fotmob = None

    imported = import_sofascore(ImportRequest(source=req.sofascore_source)); event_id = str(imported["event_id"])
    path = DATA_DIR / f"{event_id}.json"; payload = json.loads(path.read_text())
    fotmob_source = (req.fotmob_source or "").strip()
    if not fotmob_source and previous_fotmob:
        fotmob_source = str(previous_fotmob.get("source") or previous_fotmob.get("match_id") or "").strip()

    promoted_counts: Dict[str, int] = {}
    if fotmob_source:
        promoted_counts = _attach_fotmob(payload, fotmob_source)
        _persist_payload(event_id, payload)

    return {"ok": True, "event_id": event_id, "sources": {"sofascore": True, "fotmob": bool(payload.get("fotmob")), "fotmob_match_id": payload.get("fotmob", {}).get("match_id"), "validated_fields": payload.get("fotmob", {}).get("validated_fields", []), "promoted_player_counts": promoted_counts}}


@app.get("/matches/{event_id}/sources")
def match_sources(event_id: str):
    payload = _heal_event(event_id); fotmob = payload.get("fotmob") or {}
    return {"event_id": event_id, "sofascore": {"linked": True, "role": "primary"}, "fotmob": {"linked": bool(fotmob), "role": "supplementary", "match_id": fotmob.get("match_id"), "source": fotmob.get("source"), "player_count": len(fotmob.get("players", []) or []), "validated_fields": fotmob.get("validated_fields", []), "promoted_player_counts": fotmob.get("promoted_player_counts", {})}}


# Wrap the production readers. Before Match, Player or Leaders reads a local
# payload, any stored FotMob supplement is re-promoted into canonical lineup stats.
def _install_healing_route_wrappers() -> None:
    for route in app.routes:
        path = getattr(route, "path", "")
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        if path not in {
            "/matches/{event_id}",
            "/matches/{event_id}/studio-match-stats",
            "/matches/{event_id}/players/{player_id}",
            "/matches/{event_id}/canonical-leaders/{metric_key_value}",
        }:
            continue
        original = endpoint
        if path == "/matches/{event_id}":
            def healed_match(event_id: str, _original=original):
                _heal_event(event_id); return _original(event_id)
            route.endpoint = healed_match
        elif path == "/matches/{event_id}/studio-match-stats":
            def healed_stats(event_id: str, period: str = Query("full"), _original=original):
                _heal_event(event_id); return _original(event_id, period)
            route.endpoint = healed_stats
        elif path == "/matches/{event_id}/players/{player_id}":
            def healed_player(event_id: str, player_id: str, _original=original):
                _heal_event(event_id); return _original(event_id, player_id)
            route.endpoint = healed_player
        else:
            def healed_leaders(event_id: str, metric_key_value: str, period: str = Query("full"), scope: str = Query("all"), limit: int = Query(20, ge=1, le=50), _original=original):
                _heal_event(event_id); return _original(event_id, metric_key_value, period, scope, limit)
            route.endpoint = healed_leaders

_install_healing_route_wrappers()


@app.get("/audit/fotmob/{match_id}")
def fotmob_audit(match_id: str, url: Optional[str] = Query(default=None)):
    return _fotmob_result(match_id, url)


@app.get("/audit/fotmob-view/{match_id}", response_class=HTMLResponse)
def fotmob_audit_view(match_id: str, url: Optional[str] = Query(default=None)):
    try: result = _fotmob_result(match_id, url); error = None
    except HTTPException as exc: result = {"players": [], "team_totals": {}}; error = str(exc.detail)
    labels = ["Opposition Box Touches", "Passes Into Final Third", "Line-Breaking Passes", "Headed Clearances", "Clearances Off Line", "Distance covered (km)", "Number of sprints", "Sprinting (km)"]
    players = result.get("players", []); totals = result.get("team_totals", {})
    def cell(value):
        if value is None: return '<td class="missing">—</td>'
        try: n=float(value); shown=str(int(n)) if n.is_integer() else str(n)
        except (TypeError,ValueError): shown=str(value)
        return f"<td>{html.escape(shown)}</td>"
    player_rows="".join("<tr>"+f"<td class='player'>{html.escape(str(p.get('name') or 'Unknown'))}</td>"+f"<td class='team'>{html.escape(str(p.get('team') or 'Unknown'))}</td>"+"".join(cell((p.get('stats') or {}).get(label)) for label in labels)+"</tr>" for p in sorted(players,key=lambda p:(str(p.get('team') or ''),str(p.get('name') or ''))))
    total_rows="".join("<tr class='total'>"+f"<td class='player'>{html.escape(team)}</td><td class='team'>TEAM TOTAL</td>"+"".join(cell(values.get(label)) for label in labels)+"</tr>" for team,values in totals.items())
    error_html=f"<div class='error'>{html.escape(error)}</div>" if error else ""; source_html=html.escape(url or f"FotMob match {match_id}"); raw=html.escape(json.dumps(result,ensure_ascii=False,indent=2))
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MatchLab FotMob Audit</title><style>*{{box-sizing:border-box}} body{{margin:0;background:#11131f;color:#f5f7fb;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}} .wrap{{max-width:1380px;margin:0 auto;padding:32px}} .kicker{{font-size:12px;letter-spacing:.16em;color:#48f0ca;font-weight:800}} h1{{margin:7px 0 4px;font-size:30px}} .sub{{color:#8f94a8;margin-bottom:24px}} .safe{{display:inline-block;padding:7px 10px;border:1px solid #285c51;background:#17362f;border-radius:8px;color:#72f6d8;font-size:12px;font-weight:800;margin-bottom:20px}} .error{{padding:14px;border:1px solid #733;background:#351c22;border-radius:10px;color:#ff9aa8;margin:14px 0}} .card{{background:#191c2b;border:1px solid #2a2e43;border-radius:14px;overflow:auto;box-shadow:0 18px 60px #0005}} table{{width:100%;border-collapse:collapse}} th,td{{padding:13px 12px;border-bottom:1px solid #292d40;text-align:center;white-space:nowrap}} th{{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#9298ad;background:#151827}} td{{font-weight:750}} .player{{text-align:left}} .team{{text-align:left;color:#9298ad;font-weight:600}} .missing{{color:#555b70}} .total td{{background:#202438;color:#48f0ca}} .checks{{margin-top:18px;padding:16px 18px;background:#151827;border:1px solid #2a2e43;border-radius:12px;line-height:1.8}} .checks b{{color:#48f0ca}} details{{margin-top:18px;color:#8f94a8}} pre{{white-space:pre-wrap;word-break:break-word;background:#0d0f18;padding:16px;border-radius:10px;font-size:11px}}</style></head><body><div class='wrap'><div class='kicker'>MATCHLAB · DIAGNOSTIC ONLY</div><h1>FOTMOB AUDIT</h1><div class='sub'>Match {html.escape(match_id)} · {source_html}</div><div class='safe'>GOLDEN VALUES UNCHANGED</div>{error_html}<div class='card'><table><thead><tr><th>Player</th><th>Team</th>{''.join(f'<th>{html.escape(label)}</th>' for label in labels)}</tr></thead><tbody>{player_rows}{total_rows}</tbody></table></div><div class='checks'><b>FotMob supplementary fields:</b> validated event supplements plus Distance covered, Number of sprints and Sprinting are available for linked imports. Physical distance values are normalised to km.</div><details><summary>Raw diagnostic JSON</summary><pre>{raw}</pre></details></div></body></html>"""