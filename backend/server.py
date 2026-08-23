from __future__ import annotations

import html
import json

from fastapi import HTTPException, Query
from fastapi.responses import HTMLResponse

from main import app
from fotmob_diagnostic import diagnostic


def _fotmob_result(match_id: str, url: str | None = None):
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


@app.get("/audit/fotmob/{match_id}")
def fotmob_audit(match_id: str, url: str | None = Query(default=None)):
    """Diagnostic-only FotMob player-stat audit. Never mutates Golden data."""
    return _fotmob_result(match_id, url)


@app.get("/audit/fotmob-view/{match_id}", response_class=HTMLResponse)
def fotmob_audit_view(match_id: str, url: str | None = Query(default=None)):
    """Visible audit screen for proving FotMob supplementary player values."""
    try:
        result = _fotmob_result(match_id, url)
        error = None
    except HTTPException as exc:
        result = {"players": [], "team_totals": {}}
        error = str(exc.detail)

    labels = ["Opposition Box Touches", "Passes Into Final Third", "Line-Breaking Passes", "Headed Clearances"]
    players = result.get("players", [])
    totals = result.get("team_totals", {})

    def cell(value):
        if value is None:
            return '<td class="missing">—</td>'
        try:
            n = float(value)
            shown = str(int(n)) if n.is_integer() else str(n)
        except (TypeError, ValueError):
            shown = str(value)
        return f"<td>{html.escape(shown)}</td>"

    player_rows = "".join(
        "<tr>"
        f"<td class='player'>{html.escape(str(p.get('name') or 'Unknown'))}</td>"
        f"<td class='team'>{html.escape(str(p.get('team') or 'Unknown'))}</td>"
        + "".join(cell((p.get("stats") or {}).get(label)) for label in labels)
        + "</tr>"
        for p in sorted(players, key=lambda p: (str(p.get("team") or ""), str(p.get("name") or "")))
    )
    total_rows = "".join(
        "<tr class='total'>"
        f"<td class='player'>{html.escape(team)}</td><td class='team'>TEAM TOTAL</td>"
        + "".join(cell(values.get(label)) for label in labels)
        + "</tr>"
        for team, values in totals.items()
    )
    error_html = f"<div class='error'>{html.escape(error)}</div>" if error else ""
    source_html = html.escape(url or f"FotMob match {match_id}")
    raw = html.escape(json.dumps(result, ensure_ascii=False, indent=2))

    return f"""<!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>MatchLab FotMob Audit</title>
<style>
*{{box-sizing:border-box}} body{{margin:0;background:#11131f;color:#f5f7fb;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}} .wrap{{max-width:1180px;margin:0 auto;padding:32px}} .kicker{{font-size:12px;letter-spacing:.16em;color:#48f0ca;font-weight:800}} h1{{margin:7px 0 4px;font-size:30px}} .sub{{color:#8f94a8;margin-bottom:24px}} .safe{{display:inline-block;padding:7px 10px;border:1px solid #285c51;background:#17362f;border-radius:8px;color:#72f6d8;font-size:12px;font-weight:800;margin-bottom:20px}} .error{{padding:14px;border:1px solid #733;background:#351c22;border-radius:10px;color:#ff9aa8;margin:14px 0}} .card{{background:#191c2b;border:1px solid #2a2e43;border-radius:14px;overflow:hidden;box-shadow:0 18px 60px #0005}} table{{width:100%;border-collapse:collapse}} th,td{{padding:13px 12px;border-bottom:1px solid #292d40;text-align:center}} th{{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#9298ad;background:#151827}} td{{font-weight:750}} .player{{text-align:left}} .team{{text-align:left;color:#9298ad;font-weight:600}} .missing{{color:#555b70}} .total td{{background:#202438;color:#48f0ca}} .checks{{margin-top:18px;padding:16px 18px;background:#151827;border:1px solid #2a2e43;border-radius:12px;line-height:1.8}} .checks b{{color:#48f0ca}} details{{margin-top:18px;color:#8f94a8}} pre{{white-space:pre-wrap;word-break:break-word;background:#0d0f18;padding:16px;border-radius:10px;font-size:11px}} a{{color:#48f0ca}}
</style></head><body><div class='wrap'>
<div class='kicker'>MATCHLAB · DIAGNOSTIC ONLY</div><h1>FOTMOB AUDIT</h1><div class='sub'>Match {html.escape(match_id)} · {source_html}</div>
<div class='safe'>GOLDEN VALUES UNCHANGED</div>{error_html}
<div class='card'><table><thead><tr><th>Player</th><th>Team</th>{''.join(f'<th>{html.escape(label)}</th>' for label in labels)}</tr></thead><tbody>{player_rows}{total_rows}</tbody></table></div>
<div class='checks'><b>Leeds–Burnley acceptance checks:</b> Noah Okafor opposition-box touches = 4 · Dominic Calvert-Lewin = 2 · Joe Rodon = 2 · Leeds team total = 26.<br>If the player rows reconcile to 26, we can promote the FotMob field confidently instead of deriving it from heatmap points.</div>
<details><summary>Raw diagnostic JSON</summary><pre>{raw}</pre></details>
</div></body></html>"""
