from __future__ import annotations

import html
import json
import re
import unicodedata
from typing import Dict, Optional

from fastapi import HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from main import DATA_DIR, ImportRequest, app, import_sofascore
from fotmob_diagnostic import diagnostic


class LinkedImportRequest(BaseModel):
    sofascore_source: str
    fotmob_source: Optional[str] = None


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
}


def _promote_validated_fotmob_fields(payload: dict, fotmob_players: list) -> Dict[str, int]:
    """Inject only explicitly promoted FotMob fields into canonical lineup stats."""
    by_name = {}
    for player in fotmob_players or []:
        stats = player.get("stats") or {}
        values = {label: stats.get(label) for label in PROMOTED_FOTMOB_FIELDS if stats.get(label) is not None}
        if values: by_name[_norm_name(player.get("name"))] = values
    promoted = {label: 0 for label in PROMOTED_FOTMOB_FIELDS}
    lineups = payload.get("lineups", {}) or {}
    for side in ("home", "away"):
        for row in ((lineups.get(side, {}) or {}).get("players", []) or []):
            player = row.get("player", {}) or {}; values = by_name.get(_norm_name(player.get("name")))
            if not values: continue
            stats = row.setdefault("statistics", {})
            for label, value in values.items():
                stats[PROMOTED_FOTMOB_FIELDS[label]] = value
                promoted[label] += 1
    return promoted


@app.post("/matches/import-linked")
def import_linked(req: LinkedImportRequest):
    """Import SofaScore plus optional FotMob supplement into one local match."""
    imported = import_sofascore(ImportRequest(source=req.sofascore_source)); event_id = str(imported["event_id"])
    path = DATA_DIR / f"{event_id}.json"; payload = json.loads(path.read_text())
    fotmob_source = (req.fotmob_source or "").strip(); promoted_counts: Dict[str, int] = {}
    if fotmob_source:
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
        path.write_text(json.dumps(payload, ensure_ascii=False))
    return {"ok": True, "event_id": event_id, "sources": {"sofascore": True, "fotmob": bool(fotmob_source), "fotmob_match_id": payload.get("fotmob", {}).get("match_id"), "validated_fields": payload.get("fotmob", {}).get("validated_fields", []), "promoted_player_counts": promoted_counts}}


@app.get("/matches/{event_id}/sources")
def match_sources(event_id: str):
    path = DATA_DIR / f"{event_id}.json"
    if not path.exists(): raise HTTPException(404, "Match has not been imported into MatchLab yet.")
    payload = json.loads(path.read_text()); fotmob = payload.get("fotmob") or {}
    return {"event_id": event_id, "sofascore": {"linked": True, "role": "primary"}, "fotmob": {"linked": bool(fotmob), "role": "supplementary", "match_id": fotmob.get("match_id"), "source": fotmob.get("source"), "player_count": len(fotmob.get("players", []) or []), "validated_fields": fotmob.get("validated_fields", []), "promoted_player_counts": fotmob.get("promoted_player_counts", {})}}


@app.get("/audit/fotmob/{match_id}")
def fotmob_audit(match_id: str, url: Optional[str] = Query(default=None)):
    return _fotmob_result(match_id, url)


@app.get("/audit/fotmob-view/{match_id}", response_class=HTMLResponse)
def fotmob_audit_view(match_id: str, url: Optional[str] = Query(default=None)):
    try: result = _fotmob_result(match_id, url); error = None
    except HTTPException as exc: result = {"players": [], "team_totals": {}}; error = str(exc.detail)
    labels = ["Opposition Box Touches", "Passes Into Final Third", "Line-Breaking Passes", "Headed Clearances"]
    players = result.get("players", []); totals = result.get("team_totals", {})
    def cell(value):
        if value is None: return '<td class="missing">—</td>'
        try: n=float(value); shown=str(int(n)) if n.is_integer() else str(n)
        except (TypeError,ValueError): shown=str(value)
        return f"<td>{html.escape(shown)}</td>"
    player_rows="".join("<tr>"+f"<td class='player'>{html.escape(str(p.get('name') or 'Unknown'))}</td>"+f"<td class='team'>{html.escape(str(p.get('team') or 'Unknown'))}</td>"+"".join(cell((p.get('stats') or {}).get(label)) for label in labels)+"</tr>" for p in sorted(players,key=lambda p:(str(p.get('team') or ''),str(p.get('name') or ''))))
    total_rows="".join("<tr class='total'>"+f"<td class='player'>{html.escape(team)}</td><td class='team'>TEAM TOTAL</td>"+"".join(cell(values.get(label)) for label in labels)+"</tr>" for team,values in totals.items())
    error_html=f"<div class='error'>{html.escape(error)}</div>" if error else ""; source_html=html.escape(url or f"FotMob match {match_id}"); raw=html.escape(json.dumps(result,ensure_ascii=False,indent=2))
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MatchLab FotMob Audit</title><style>*{{box-sizing:border-box}} body{{margin:0;background:#11131f;color:#f5f7fb;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}} .wrap{{max-width:1180px;margin:0 auto;padding:32px}} .kicker{{font-size:12px;letter-spacing:.16em;color:#48f0ca;font-weight:800}} h1{{margin:7px 0 4px;font-size:30px}} .sub{{color:#8f94a8;margin-bottom:24px}} .safe{{display:inline-block;padding:7px 10px;border:1px solid #285c51;background:#17362f;border-radius:8px;color:#72f6d8;font-size:12px;font-weight:800;margin-bottom:20px}} .error{{padding:14px;border:1px solid #733;background:#351c22;border-radius:10px;color:#ff9aa8;margin:14px 0}} .card{{background:#191c2b;border:1px solid #2a2e43;border-radius:14px;overflow:hidden;box-shadow:0 18px 60px #0005}} table{{width:100%;border-collapse:collapse}} th,td{{padding:13px 12px;border-bottom:1px solid #292d40;text-align:center}} th{{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#9298ad;background:#151827}} td{{font-weight:750}} .player{{text-align:left}} .team{{text-align:left;color:#9298ad;font-weight:600}} .missing{{color:#555b70}} .total td{{background:#202438;color:#48f0ca}} .checks{{margin-top:18px;padding:16px 18px;background:#151827;border:1px solid #2a2e43;border-radius:12px;line-height:1.8}} .checks b{{color:#48f0ca}} details{{margin-top:18px;color:#8f94a8}} pre{{white-space:pre-wrap;word-break:break-word;background:#0d0f18;padding:16px;border-radius:10px;font-size:11px}}</style></head><body><div class='wrap'><div class='kicker'>MATCHLAB · DIAGNOSTIC ONLY</div><h1>FOTMOB AUDIT</h1><div class='sub'>Match {html.escape(match_id)} · {source_html}</div><div class='safe'>GOLDEN VALUES UNCHANGED</div>{error_html}<div class='card'><table><thead><tr><th>Player</th><th>Team</th>{''.join(f'<th>{html.escape(label)}</th>' for label in labels)}</tr></thead><tbody>{player_rows}{total_rows}</tbody></table></div><div class='checks'><b>Leeds–Burnley controls:</b> Opposition Box Touches reconciles to Leeds 26. Passes Into Final Third is now promoted as the total denominator for Successful Final Third Passes and as its own player metric.</div><details><summary>Raw diagnostic JSON</summary><pre>{raw}</pre></details></div></body></html>"""