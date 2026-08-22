#!/bin/zsh
set -e

STUDIO_ROOT="$(cd "$(dirname "$0")" && pwd)"
FRONTEND="$STUDIO_ROOT/frontend"
BACKEND_REPO="$HOME/Documents/GitHub/MatchLab-Backend-Local"
BACKEND="$BACKEND_REPO/matchlab_web/backend"
VENV="$BACKEND_REPO/.venv"
PY="$VENV/bin/python"

fail_dialog() {
  osascript -e "display dialog \"$1\" buttons {\"OK\"} default button \"OK\" with icon stop"
  exit 1
}

# Keep the scraping/backend code local on this Mac and current with the working branch.
if [ ! -d "$BACKEND_REPO/.git" ]; then
  git clone --branch matchlab-v2-web --single-branch https://github.com/lufcdata/Analysis-App.git "$BACKEND_REPO"
else
  git -C "$BACKEND_REPO" fetch origin matchlab-v2-web
  git -C "$BACKEND_REPO" checkout matchlab-v2-web >/dev/null 2>&1 || true
  git -C "$BACKEND_REPO" pull --ff-only origin matchlab-v2-web
fi

# MatchLab owns its own clean Python environment.
if [ ! -x "$PY" ]; then
  SYSTEM_PY="$(command -v python3 || true)"
  [ -n "$SYSTEM_PY" ] || fail_dialog "Python 3 is required to run MatchLab Studio, but macOS could not find it."
  "$SYSTEM_PY" -m venv "$VENV" || fail_dialog "MatchLab could not create its local Python environment."
fi

if ! "$PY" -c 'import fastapi, uvicorn, requests, curl_cffi, PIL' >/dev/null 2>&1; then
  "$PY" -m pip install --upgrade pip >/tmp/matchlab-pip.log 2>&1
  "$PY" -m pip install -r "$BACKEND/requirements.txt" >>/tmp/matchlab-pip.log 2>&1 || fail_dialog "MatchLab could not install its local backend requirements."
fi

# IMPORTANT: no football.duckdb prerequisite here. Match data is imported through the
# local backend/source route when requested; the launcher must not depend on a legacy DB.

# Install ONLY the approved local imagery packs. No SofaScore imagery is downloaded or rendered.
PLAYER_ZIP="$HOME/Downloads/2026 27 Leeds Players.zip"
CLUB_ZIP="$HOME/Downloads/CLUB APP LOGOS.zip"
PLAYER_ASSETS="$BACKEND_REPO/assets/player_images"
TEAM_ASSETS="$BACKEND_REPO/assets/team_logos"
mkdir -p "$PLAYER_ASSETS" "$TEAM_ASSETS"

if [ -f "$PLAYER_ZIP" ]; then
  rm -rf "$PLAYER_ASSETS"/*
  unzip -oq "$PLAYER_ZIP" -d "$PLAYER_ASSETS"
fi
if [ -f "$CLUB_ZIP" ]; then
  rm -rf "$TEAM_ASSETS"/*
  unzip -oq "$CLUB_ZIP" -d "$TEAM_ASSETS"
fi

command -v npm >/dev/null 2>&1 || fail_dialog "Node/npm is required to run the MatchLab Studio frontend."

pkill -f "uvicorn studio_entry:app" >/dev/null 2>&1 || true
pkill -f "vite.*5173" >/dev/null 2>&1 || true

cd "$BACKEND"
nohup "$PY" -m uvicorn studio_entry:app --host 127.0.0.1 --port 8000 > /tmp/matchlab-backend.log 2>&1 &

cd "$FRONTEND"
if [ ! -d node_modules ]; then
  npm install >/tmp/matchlab-npm.log 2>&1 || fail_dialog "MatchLab could not install its frontend packages."
fi
nohup npm run dev -- --host 127.0.0.1 --port 5173 > /tmp/matchlab-frontend.log 2>&1 &

for i in {1..45}; do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && curl -fsS http://127.0.0.1:5173 >/dev/null 2>&1; then
    METRICS_JSON="$(curl -fsS http://127.0.0.1:8000/canonical/metrics 2>/dev/null || true)"
    if [ -z "$METRICS_JSON" ]; then
      fail_dialog "MatchLab started, but its metric contract endpoint did not respond."
    fi
    COUNT="$(printf '%s' "$METRICS_JSON" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("match_stats_count",-1))' 2>/dev/null || echo -1)"
    [ "$COUNT" = "33" ] || fail_dialog "MatchLab refused to open because the backend did not expose the locked 33-stat contract."

    # End-to-end local-source preflight against the known Leeds 3-1 Burnley test match.
    if ! MATCHLAB_PREFLIGHT=1 "$PY" - <<'PY' >/tmp/matchlab-preflight.log 2>&1
import json
import urllib.request

BASE = 'http://127.0.0.1:8000'
EVENT = '14023940'

def request(path, method='GET', payload=None, binary=False):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=45) as response:
        body = response.read()
        return body if binary else json.loads(body.decode('utf-8'))

metrics = request('/canonical/metrics')
assert metrics.get('match_stats_count') == 33

# This import is performed by the backend running locally on this Mac.
imported = request('/matches/import-sofascore', method='POST', payload={'source': EVENT})
assert str(imported.get('event_id')) == EVENT

base = request(f'/matches/{EVENT}')
players = base.get('players') or []
assert players, 'No players returned for preflight match'

for period in ('full', 'first_half', 'second_half'):
    stats = request(f'/matches/{EVENT}/studio-match-stats?period={period}')
    assert stats.get('metric_contract_count') == 33
    assert len(stats.get('home') or {}) == 33
    assert len(stats.get('away') or {}) == 33

caps = request(f'/matches/{EVENT}/period-capabilities')
assert caps['match_stats'] == {'full': True, 'first_half': True, 'second_half': True}
assert caps['player_stats']['full'] is True
assert caps['metric_leaders']['full'] is True

preferred = next((p for p in players if 'joe rodon' in str(p.get('name', '')).lower()), players[0])
player = request(f"/matches/{EVENT}/canonical-player/{preferred['id']}?period=full")
assert player.get('rows') is not None

catalog = metrics.get('live') or []
assert catalog, 'Metric Leaders catalog is empty'
leader_metric = next((m['key'] for m in catalog if m.get('key') == 'successful_passes'), catalog[0]['key'])
leaders = request(f'/matches/{EVENT}/canonical-leaders/{leader_metric}?period=full&scope=all&limit=15')
assert leaders.get('leaders') is not None

request('/team-logos/leeds-united.png', binary=True)
request(f"/player-images/{preferred['name'].lower().replace(' ', '-')}.png", binary=True)

print('MATCHLAB PREFLIGHT PASS')
PY
    then
      fail_dialog "MatchLab started, but the final Leeds v Burnley local-source preflight failed. The diagnostic is /tmp/matchlab-preflight.log."
    fi

    open http://127.0.0.1:5173
    exit 0
  fi
  sleep 1
done

osascript -e 'display dialog "MatchLab did not finish starting. The backend/frontend logs were saved in /tmp for diagnosis." buttons {"OK"} default button "OK" with icon caution'
exit 1
