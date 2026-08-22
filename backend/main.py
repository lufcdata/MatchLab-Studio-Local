from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from curl_cffi import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from golden_metrics import METRICS, available_player_metrics, build_canonical_player_rows, canonical_match_label, format_metric_value, metric_key, player_metric_value

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(__file__).resolve().parent / "data" / "matches"
DATA_DIR.mkdir(parents=True, exist_ok=True)
TEAM_ASSET_ROOTS = (ROOT / "assets" / "team_logos", ROOT / "assets" / "club_logos")
PLAYER_ASSET_ROOTS = (ROOT / "assets" / "player_images", ROOT / "assets" / "players")

app = FastAPI(title="MatchLab API", version="4.0.0-self-contained")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class ImportRequest(BaseModel):
    source: str


def _slug(value: Any) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool): return None
    if isinstance(value, (int, float)): return float(value)
    text = str(value).strip().replace(",", "").rstrip("%").strip()
    try: return float(text)
    except ValueError: return None


def _event_id(source: str) -> str:
    source = source.strip()
    if source.isdigit(): return source
    m = re.search(r"(?:id:|event/)(\d+)", source, re.I) or re.search(r"[?&#]id=(\d+)", source, re.I)
    if not m: raise HTTPException(400, "Could not find a SofaScore event ID in that URL.")
    return m.group(1)


def _get_json(path: str) -> dict[str, Any]:
    url = f"https://www.sofascore.com/api/v1/{path.lstrip('/')}"
    try:
        r = requests.get(url, impersonate="chrome", timeout=20, headers={"Accept":"application/json","Referer":"https://www.sofascore.com/"})
        if r.status_code != 200: raise RuntimeError(f"SofaScore returned HTTP {r.status_code}")
        return r.json()
    except Exception as exc:
        raise HTTPException(502, f"SofaScore import failed: {exc}") from exc


def _load(event_id: str) -> dict[str, Any]:
    p = DATA_DIR / f"{event_id}.json"
    if not p.exists(): raise HTTPException(404, "Match has not been imported into MatchLab yet.")
    return json.loads(p.read_text())


def _match(payload: dict[str, Any]) -> dict[str, Any]:
    e = payload["basic"].get("event", payload["basic"])
    hs = e.get("homeScore", {}) or {}; aws = e.get("awayScore", {}) or {}
    return {
        "event_id": str(e.get("id", "")),
        "home_name": (e.get("homeTeam", {}) or {}).get("name", "Home"),
        "away_name": (e.get("awayTeam", {}) or {}).get("name", "Away"),
        "home_score": str(hs.get("display", hs.get("current", ""))),
        "away_score": str(aws.get("display", aws.get("current", ""))),
        "tournament": (((e.get("tournament", {}) or {}).get("uniqueTournament", {}) or {}).get("name") or (e.get("tournament", {}) or {}).get("name", "")),
        "date_text": "",
    }


def _players(payload: dict[str, Any]) -> list[dict[str, Any]]:
    m = _match(payload); out=[]
    for side in ("home", "away"):
        team = m["home_name"] if side == "home" else m["away_name"]
        opp = m["away_name"] if side == "home" else m["home_name"]
        block = (payload.get("lineups", {}).get(side, {}) or {}).get("players", []) or []
        for row in block:
            p=row.get("player", {}) or {}; stats=row.get("statistics", {}) or {}
            if p.get("name"):
                out.append({"id":str(p.get("id", p.get("slug", p["name"]))),"name":p["name"],"team":team,"opponent":opp,"side":side,"stats":stats})
    return out


def _period_rows(payload: dict[str, Any], period: str) -> list[dict[str, Any]]:
    code={"full":"ALL","first_half":"1ST","second_half":"2ND"}[period]
    aliases={"ALL":{"ALL"},"1ST":{"1ST","FIRST"},"2ND":{"2ND","SECOND"}}
    block=next((b for b in payload.get("statistics",{}).get("statistics",[]) or [] if str(b.get("period","")).upper() in aliases[code]),None)
    if not block: return []
    rows=[]; seen=set()
    for group in block.get("groups",[]) or []:
        for item in group.get("statisticsItems",[]) or []:
            label=canonical_match_label(str(item.get("name",item.get("key",""))),str(item.get("key","")))
            if not label or label in seen: continue
            seen.add(label)
            rows.append({"name":label,"home":item.get("home"),"away":item.get("away"),"home_value":item.get("homeValue"),"away_value":item.get("awayValue")})
    return rows


def _asset_stem(path: Path) -> str:
    return re.sub(r"-(icon|icon-v2|icon-2|png|logo|crest|badge|player)$", "", _slug(path.stem))


def _find_asset(wanted: str, roots: tuple[Path,...]) -> Path | None:
    aliases={"leeds":"leeds-united","brighton":"brighton-hove-albion","tottenham":"tottenham-hotspur","west-ham":"west-ham-united","wolves":"wolverhampton-wanderers","man-city":"manchester-city","man-utd":"manchester-united","newcastle":"newcastle-united","forest":"nottingham-forest"}
    wanted=aliases.get(_slug(wanted),_slug(wanted))
    for root in roots:
        if not root.exists(): continue
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".png",".webp",".jpg",".jpeg"} and aliases.get(_asset_stem(p),_asset_stem(p))==wanted: return p
    return None

@app.get("/health")
def health(): return {"ok":True,"service":"matchlab-api","runtime":"self-contained"}

@app.post("/matches/import-sofascore")
def import_sofascore(req: ImportRequest):
    eid=_event_id(req.source)
    payload={"event_id":eid,"basic":_get_json(f"event/{eid}"),"statistics":_get_json(f"event/{eid}/statistics"),"lineups":_get_json(f"event/{eid}/lineups")}
    (DATA_DIR/f"{eid}.json").write_text(json.dumps(payload,ensure_ascii=False))
    return {"ok":True,"event_id":eid}

@app.get("/matches/{event_id}")
def get_match(event_id: str):
    payload=_load(event_id); m=_match(payload); players=_players(payload)
    return {"match":m,"players":[{k:p[k] for k in ("id","name","team","opponent","side")} for p in players],"statistics":_period_rows(payload,"full"),"metrics":[{"key":x["key"],"label":x["label"]} for x in available_player_metrics([type("P",(),{"stats":p["stats"]}) for p in players])]}

@app.get("/canonical/metrics")
def metrics_catalog():
    live=[{"key":metric_key(m["label"]),"label":m["label"]} for m in METRICS if m.get("player_keys")]
    return {"live":live,"match_stats":[{"key":metric_key(m["label"]),"label":m["label"],"percent":m.get("suffix")=="%"} for m in METRICS]}

@app.get("/matches/{event_id}/period-capabilities")
def capabilities(event_id: str):
    payload=_load(event_id); periods={str(b.get("period","")).upper() for b in payload.get("statistics",{}).get("statistics",[]) or []}
    return {"match_stats":{"full":"ALL" in periods,"first_half":bool(periods&{"1ST","FIRST"}),"second_half":bool(periods&{"2ND","SECOND"})},"player_stats":{"full":True,"first_half":False,"second_half":False},"metric_leaders":{"full":True,"first_half":False,"second_half":False},"reason":"Full-match player data available from this SofaScore feed."}

@app.get("/matches/{event_id}/studio-match-stats")
def match_stats(event_id: str, period: str=Query("full")):
    if period not in {"full","first_half","second_half"}: raise HTTPException(400,"Invalid period")
    payload=_load(event_id); m=_match(payload); by={r["name"]:r for r in _period_rows(payload,period)}; home={}; away={}
    for metric in METRICS:
        key=metric_key(metric["label"]); row=by.get(metric["label"])
        home[key]=_number(row.get("home_value")) if row else None; away[key]=_number(row.get("away_value")) if row else None
        if row and home[key] is None: home[key]=_number(row.get("home"))
        if row and away[key] is None: away[key]=_number(row.get("away"))
    if period=="full": home["goals"]=_number(m["home_score"]); away["goals"]=_number(m["away_score"])
    return {"event_id":event_id,"canonical_match_id":event_id,"period":period,"match":{"match_id":event_id,"date":m["date_text"],"home_team_id":_slug(m["home_name"]),"home_team":m["home_name"],"away_team_id":_slug(m["away_name"]),"away_team":m["away_name"],"home_score":m["home_score"],"away_score":m["away_score"]},"home":home,"away":away,"availability":{"missing_fields":[k for k in home if home[k] is None or away[k] is None]}}

@app.get("/matches/{event_id}/players/{player_id}")
def player_stats(event_id: str, player_id: str):
    p=next((p for p in _players(_load(event_id)) if p["id"]==str(player_id)),None)
    if not p: raise HTTPException(404,"Player not found")
    rows,minutes=build_canonical_player_rows(p["stats"],hide_zero=True)
    return {"player":{"player_id":p["id"],"name":p["name"],"team":p["team"],"opponent":p["opponent"],"side":p["side"]},"rows":rows,"minutes":minutes}

@app.get("/matches/{event_id}/canonical-leaders/{metric_key_value}")
def leaders(event_id: str, metric_key_value: str, period: str=Query("full"), scope: str=Query("all"), limit: int=Query(20,ge=1,le=50)):
    if period!="full": raise HTTPException(400,"Metric Leader period data is only available for the full match from this SofaScore feed.")
    metric=next((m for m in METRICS if metric_key(m["label"])==metric_key_value),None)
    if not metric: raise HTTPException(404,"Metric not available")
    ranked=[]
    for p in _players(_load(event_id)):
        if scope!="all" and p["side"]!=scope: continue
        v=player_metric_value(p["stats"],metric)
        if v is not None: ranked.append((p,v))
    ranked.sort(key=lambda x:(-x[1],x[0]["name"])); top=ranked[:limit]; lead=top[0][1] if top else 0
    return {"metric":metric_key_value,"label":metric["label"],"period":period,"leaders":[{"rank":i,"player_id":p["id"],"player_name":p["name"],"team_id":_slug(p["team"]),"team_name":p["team"],"value":v,"display":format_metric_value(v,metric),"relative_to_leader":v/lead if lead else 0} for i,(p,v) in enumerate(top,1)]}

@app.get("/team-logos/{team_slug}.png")
def team_logo(team_slug: str):
    p=_find_asset(team_slug,TEAM_ASSET_ROOTS)
    if p:return FileResponse(p)
    raise HTTPException(404,"No approved local club crest is available.")

@app.get("/player-images/{player_slug}.png")
def player_image(player_slug: str):
    p=_find_asset(player_slug,PLAYER_ASSET_ROOTS)
    if p:return FileResponse(p)
    for fp in sorted(DATA_DIR.glob("*.json"),key=lambda x:x.stat().st_mtime,reverse=True):
        try:
            for pl in _players(json.loads(fp.read_text())):
                if _slug(pl["name"])==_slug(player_slug):
                    crest=_find_asset(pl["team"],TEAM_ASSET_ROOTS)
                    if crest:return FileResponse(crest)
        except Exception: pass
    raise HTTPException(404,"No approved local player image or club crest is available.")
