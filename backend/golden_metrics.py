from __future__ import annotations

import re
from typing import Any

# MATCHLAB GOLDEN METRIC MAP
# MatchLab display labels remain separate from SofaScore source fields.
METRICS: list[dict[str, Any]] = [
    {"label":"Goals","sofascore":"Goals","match_keys":["goals"],"player_keys":["goals"]},
    {"label":"xG","sofascore":"Expected Goals (xG)","match_aliases":["Expected goals"],"match_keys":["expectedGoals"],"player_keys":["expectedGoals","expectedGoalsValue"]},
    {"label":"Possession","sofascore":"Ball Possession","match_aliases":["Ball possession"],"match_keys":["ballPossession"],"player_keys":["ballPossession","possession"]},
    {"label":"Touches","sofascore":"Touches","match_aliases":["Total touches"],"match_keys":["touches","totalTouches"],"player_keys":["touches","totalTouches"]},
    {"label":"Opposition Box Touches","sofascore":"Penalty Box Touches","match_aliases":["Penalty box touches","Touches in opposition box","Touches in Opposition Box","Touches in penalty area","Touches in penalty box","Touches inside opposition box"],"match_keys":["touchesInOppBox","touchesInOppositionBox","penaltyBoxTouches","touchesInPenaltyArea","touchesInPenaltyBox","touchesInsideOppositionBox"],"player_keys":["touchesInOppBox","touchesInOppositionBox","penaltyBoxTouches","touchesInPenaltyArea","touchesInPenaltyBox","touchesInsideOppositionBox"]},
    {"label":"Shots","sofascore":"Total Shots","match_aliases":["Total shots"],"match_keys":["totalShotsOnGoal","totalShots"],"player_keys":["totalShots"]},
    {"label":"Shots On-Target","sofascore":"Shots on target","match_keys":["shotsOnGoal","shotsOnTarget"],"player_keys":["onTargetScoringAttempt","shotsOnTarget"]},
    {"label":"Shots Outside Box","sofascore":"Shots outside box","match_keys":["totalShotsOutsideBox","shotsOutsideBox"],"player_keys":["shotFromOutsideTheBox","shotsOutsideBox","shotsFromOutsideTheBox","totalShotsOutsideBox"]},
    {"label":"Shots Inside The Box","sofascore":"Shots inside box","match_aliases":["Shots inside the box","Shots from inside box","Shots from inside the box"],"match_keys":["totalShotsInsideBox","shotsInsideBox"],"player_keys":["shotFromInsideTheBox","shotsInsideBox","shotsFromInsideTheBox","totalShotsInsideBox"]},
    {"label":"Big Chances","sofascore":"Big Chances","match_aliases":["Big chances"],"match_keys":["bigChanceCreated","bigChances"],"player_keys":["bigChances","bigChance","bigChanceCreated"],"default_zero":True},
    {"label":"Big Chances Created","sofascore":"Big Chances Created","match_aliases":["Big chances created"],"match_keys":["bigChanceCreated","bigChancesCreated"],"player_keys":["bigChanceCreated","bigChancesCreated"],"default_zero":True},
    {"label":"Big Chances Missed","sofascore":"Big Chances Missed","match_aliases":["Big chances missed"],"match_keys":["bigChanceMissed","bigChancesMissed"],"player_keys":["bigChanceMissed","bigChancesMissed"],"default_zero":True},
    {"label":"Chances Created","sofascore":"Key Passes","match_aliases":["Key passes","Key Pass","Chances created"],"match_keys":["keyPasses","keyPass","chancesCreated"],"player_keys":["keyPass","keyPasses","chancesCreated"]},
    {"label":"Successful Passes","sofascore":"Accurate Passes","match_aliases":["Accurate passes"],"match_keys":["accuratePasses"],"player_keys":["accuratePass","accuratePasses"]},
    {"label":"Total Passes","sofascore":"Passes","match_aliases":["Total passes"],"match_keys":["passes","totalPasses"],"player_keys":["totalPass","totalPasses"]},
    {"label":"Successful Final Third Passes","sofascore":"Passes In Final Third","match_aliases":["Passes in final third"],"match_keys":["finalThirdPhaseStatistic","accurateFinalThirdPasses","passesInFinalThird"],"player_keys":["accurateFinalThirdPasses","successfulFinalThirdPasses","passesInFinalThird"]},
    {"label":"Pass Accuracy","sofascore":"Pass Accuracy","match_aliases":["Pass accuracy","Passing accuracy","Accurate passes percentage","Accurate passes %"],"match_keys":["passAccuracy","accuratePassesPercentage","accuratePassPercentage","passAccuracyPercentage"],"player_keys":["passAccuracy","accuratePassPercentage","accuratePassesPercentage","passAccuracyPercentage"],"suffix":"%"},
    {"label":"Ball Carries","sofascore":"Carries","match_aliases":["Ball carries","Total carries"],"match_keys":["ballCarriesCount","ballCarries","carries","totalCarries"],"player_keys":["ballCarriesCount","ballCarries","carries","totalCarries"]},
    {"label":"Progressive Carries","sofascore":"Progressive Carries","match_aliases":["Progressive carries","Progressive ball carries"],"match_keys":["progressiveBallCarriesCount","progressiveBallCarries","progressiveCarries"],"player_keys":["progressiveBallCarriesCount","progressiveBallCarries","progressiveCarries"]},
    {"label":"Progressive Carrying Distance (m)","sofascore":"Progressive Carrying Distance","match_aliases":["Progressive carrying distance","Progressive carry distance","Progressive ball carries distance"],"match_keys":["totalProgressiveBallCarriesDistance","progressiveBallCarriesDistance","progressiveCarryingDistance","progressiveCarryDistance"],"player_keys":["totalProgressiveBallCarriesDistance","progressiveBallCarriesDistance","progressiveCarryingDistance","progressiveCarryDistance"]},
    {"label":"Accurate Long Passes","sofascore":"Long Balls","match_aliases":["Long balls","Accurate long balls"],"match_keys":["accurateLongBalls"],"player_keys":["accurateLongBalls"]},
    {"label":"Final Third Entries","sofascore":"Final Third Entries","match_aliases":["Final third entries"],"match_keys":["finalThirdEntries"],"player_keys":["finalThirdEntries","entriesIntoFinalThird"]},
    {"label":"Accurate Crosses","sofascore":"Crosses","match_aliases":["Accurate crosses"],"match_keys":["accurateCross","accurateCrosses"],"player_keys":["accurateCross","accurateCrosses"]},
    {"label":"Ground Duels Won","sofascore":"Ground Duels","match_aliases":["Ground duels"],"match_keys":["groundDuelsPercentage","groundDuelsWon"],"player_keys":["groundDuelWon","groundDuelsWon","groundDuelsWonCount"]},
    {"label":"Aerial Duels Won","sofascore":"Aerial Duels","match_aliases":["Aerial duels"],"match_keys":["aerialDuelsPercentage","aerialDuelsWon"],"player_keys":["aerialWon","aerialDuelsWon"]},
    {"label":"Duels Won","sofascore":"Duels","match_aliases":["Duels won"],"match_keys":["duelWonPercent","duelsWon"],"player_keys":["duelWon","totalDuelsWon"]},
    {"label":"Ball Recoveries","sofascore":"Recoveries","match_aliases":["Ball recoveries","Recoveries"],"match_keys":["ballRecovery"],"player_keys":["ballRecovery"]},
    {"label":"Successful Take-Ons","sofascore":"Dribbles","match_aliases":["Successful dribbles","Dribbles"],"match_keys":["dribblesPercentage","successfulDribbles"],"player_keys":["wonContest","successfulDribbles"]},
    {"label":"Tackles Won","sofascore":"Tackles Won","match_aliases":["Tackles won"],"match_keys":["wonTacklePercent","wonTackle","tacklesWon"],"player_keys":["wonTackle","tacklesWon","totalTackle"]},
    {"label":"Interceptions","sofascore":"Interceptions","match_keys":["interceptionWon","interceptions"],"player_keys":["interceptionWon","interceptions"]},
    {"label":"Clearances","sofascore":"Clearances","match_keys":["totalClearance","clearances"],"player_keys":["totalClearance","clearances"]},
    {"label":"Fouls","sofascore":"Fouls","match_keys":["fouls"],"player_keys":["fouls"]},
    {"label":"Fouled","sofascore":"Was Fouled","match_aliases":["Was fouled"],"match_keys":["wasFouled"],"player_keys":["wasFouled"]},
    {"label":"Possession Lost","sofascore":"Possession Lost","match_aliases":["Possession lost"],"match_keys":["possessionLost","dispossessed"],"player_keys":["possessionLostCtrl","possessionLost"]},
    {"label":"Corners","sofascore":"Corner Kicks","match_aliases":["Corner kicks"],"match_keys":["cornerKicks","corners"],"player_keys":[]},
    {"label":"Saves","sofascore":"Goalkeeper Saves","match_aliases":["Goalkeeper saves"],"match_keys":["goalkeeperSaves","saves"],"player_keys":["saves"]},
    {"label":"Assists","sofascore":"Assists","match_keys":["assists"],"player_keys":["goalAssist","assists"]},
    {"label":"Penalties Won","sofascore":"Penalties Won","match_aliases":["Penalties won","Penalty won","Penalty awarded","Penalties awarded"],"match_keys":["penaltiesWon","penaltyWon","penaltyAwarded","penaltiesAwarded"],"player_keys":["penaltyWon","penaltiesWon","penaltyAwarded","penaltiesAwarded"],"default_zero":True},
    {"label":"Saves From Inside Box","sofascore":"Saves From Inside Box","match_aliases":["Saves from inside box","Saves inside box"],"match_keys":["savedShotsFromInsideTheBox","savesFromInsideBox"],"player_keys":["savedShotsFromInsideTheBox","savesFromInsideBox"]},
    {"label":"High Claims","sofascore":"High Claims","match_aliases":["High claims"],"match_keys":["highClaims","goodHighClaim"],"player_keys":["highClaims","goodHighClaim"],"default_zero":True},
    {"label":"Red Cards","sofascore":"Red Cards","match_aliases":["Red cards"],"match_keys":["redCards"],"player_keys":["redCards","redCard","directRedCards"],"default_zero":True},
    {"label":"Defensive Actions","sofascore":"Calculated: Tackles + Interceptions + Blocks + Clearances + Ball Recoveries + Aerial Duels + Fouls","match_keys":[],"player_keys":["totalTackle","wonTackle","tacklesWon","interceptionWon","interceptions","blockedScoringAttempt","blockedShots","blocks","totalClearance","clearances","ballRecovery","aerialWon","aerialDuelsWon","fouls"],"calculated":"defensive_actions"},
]

METRIC_BY_LABEL = {m["label"]: m for m in METRICS}
REQUIRED_PLAYER_LABELS = {"Opposition Box Touches","Shots Outside Box","Shots Inside The Box","Big Chances Created","Big Chances Missed","Successful Final Third Passes","Pass Accuracy","Final Third Entries","Ground Duels Won","Penalties Won","High Claims","Red Cards","Defensive Actions"}

def metric_key(label: str) -> str: return "_".join("".join(ch.lower() if ch.isalnum() else " " for ch in label).split())
def _norm(value: Any) -> str:
    text=str(value or "").strip(); text=re.sub(r"([a-z0-9])([A-Z])",r"\1 \2",text); text=text.replace("&"," and "); text=re.sub(r"[^A-Za-z0-9]+"," ",text); return " ".join(text.lower().split())
def canonical_match_label(raw_name: str, raw_key: str | None = None) -> str | None:
    needles={_norm(raw_name),_norm(raw_key)}-{""}
    for metric in METRICS:
        candidates=[metric.get("sofascore"),*metric.get("match_aliases",[])]; candidates.extend(metric.get("match_keys",[]))
        if needles & {_norm(x) for x in candidates if x}: return str(metric["label"])
    return None
def _number(value: Any) -> float | None:
    if isinstance(value,bool): return None
    if isinstance(value,(int,float)): return float(value)
    if isinstance(value,str):
        text=value.strip().replace(",",""); text=text[:-1].strip() if text.endswith("%") else text
        try: return float(text)
        except ValueError: return None
    return None
def _first_number(stats: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        value=_number(stats.get(key))
        if value is not None: return value
    return None
def _defensive_actions(stats: dict[str, Any]) -> float | None:
    values=[
        _first_number(stats,["totalTackle","wonTackle","tacklesWon"]),
        _first_number(stats,["interceptionWon","interceptions"]),
        _first_number(stats,["blockedScoringAttempt","blockedShots","blocks"]),
        _first_number(stats,["totalClearance","clearances"]),
        _first_number(stats,["ballRecovery"]),
        _first_number(stats,["aerialWon","aerialDuelsWon"]),
        _first_number(stats,["fouls"]),
    ]
    if all(value is None for value in values): return None
    return sum(value or 0.0 for value in values)
def _looks_goalkeeper(stats: dict[str, Any]) -> bool:
    goalkeeper_keys={"saves","savedShotsFromInsideTheBox","savesFromInsideBox","goalsPrevented","goodHighClaim","highClaims","punches","runsOut","successfulRunsOut"}
    return any(key in stats for key in goalkeeper_keys)
def _has_participated(stats: dict[str, Any]) -> bool:
    minutes=_number(stats.get("minutesPlayed"))
    if minutes is not None and minutes > 0: return True
    participation_keys={"touches","totalTouches","totalPass","totalPasses","accuratePass","accuratePasses","rating"}
    return any(_number(stats.get(key)) is not None for key in participation_keys)
def player_metric_value(stats: dict[str, Any], metric: dict[str, Any]) -> float | None:
    if metric.get("calculated")=="defensive_actions": return _defensive_actions(stats)
    for key in metric.get("player_keys",[]):
        value=_number(stats.get(key))
        if value is not None: return value
    if metric.get("label")=="Pass Accuracy":
        accurate=_number(stats.get("accuratePass")); accurate=_number(stats.get("accuratePasses")) if accurate is None else accurate
        total=_number(stats.get("totalPass")); total=_number(stats.get("totalPasses")) if total is None else total
        if accurate is not None and total and total>0: return accurate/total*100.0
    if metric.get("label")=="High Claims" and metric.get("default_zero"):
        return 0.0 if _looks_goalkeeper(stats) and _has_participated(stats) else None
    if metric.get("default_zero"): return 0.0 if _has_participated(stats) else None
    return None
def format_metric_value(value: float, metric: dict[str, Any]) -> str:
    if metric.get("label")=="xG": return f"{value:.2f}"
    text=str(int(value)) if float(value).is_integer() else f"{value:.1f}"; return f"{text}%" if metric.get("suffix")=="%" else text
def format_player_metric(stats: dict[str, Any], metric: dict[str, Any], value: float) -> str: return format_metric_value(value,metric)
def available_player_metrics(players) -> list[dict[str, Any]]:
    available=[]
    for metric in METRICS:
        if not metric.get("player_keys"): continue
        if metric["label"] in REQUIRED_PLAYER_LABELS or any(player_metric_value(p.stats,metric) is not None for p in players): available.append({**metric,"key":metric_key(metric["label"])})
    return available
def build_canonical_player_rows(stats: dict[str, Any], hide_zero: bool = True) -> tuple[list[dict[str, Any]], Any]:
    rows=[]
    for metric in METRICS:
        if not metric.get("player_keys"): continue
        value=player_metric_value(stats,metric)
        if value is None: continue
        if hide_zero and value==0 and metric["label"] not in REQUIRED_PLAYER_LABELS: continue
        rows.append({"key":metric_key(metric["label"]),"label":metric["label"],"display":format_player_metric(stats,metric,value),"rank":value,"value":value})
    return rows,stats.get("minutesPlayed")
