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

if [ ! -d "$BACKEND_REPO/.git" ]; then
  git clone --branch matchlab-v2-web --single-branch https://github.com/lufcdata/Analysis-App.git "$BACKEND_REPO"
else
  git -C "$BACKEND_REPO" fetch origin matchlab-v2-web
  git -C "$BACKEND_REPO" checkout matchlab-v2-web >/dev/null 2>&1 || true
  git -C "$BACKEND_REPO" pull --ff-only origin matchlab-v2-web
fi

if [ ! -x "$PY" ]; then
  SYSTEM_PY="$(command -v python3 || true)"
  [ -n "$SYSTEM_PY" ] || fail_dialog "Python 3 is required to run MatchLab Studio, but macOS could not find it."
  "$SYSTEM_PY" -m venv "$VENV" || fail_dialog "MatchLab could not create its local Python environment."
fi

if ! "$PY" -c 'import fastapi, uvicorn, requests, curl_cffi, PIL' >/dev/null 2>&1; then
  "$PY" -m pip install --upgrade pip >/tmp/matchlab-pip.log 2>&1
  "$PY" -m pip install -r "$BACKEND/requirements.txt" >>/tmp/matchlab-pip.log 2>&1 || fail_dialog "MatchLab could not install its local backend requirements."
fi

# No legacy football.duckdb prerequisite. Match imports run through the local backend on this Mac.
PLAYER_ZIP="$HOME/Downloads/2026 27 Leeds Players.zip"
CLUB_ZIP="$HOME/Downloads/CLUB APP LOGOS.zip"
PLAYER_ASSETS="$BACKEND_REPO/assets/player_images"
TEAM_ASSETS="$BACKEND_REPO/assets/team_logos"
mkdir -p "$PLAYER_ASSETS" "$TEAM_ASSETS"
[ ! -f "$PLAYER_ZIP" ] || { rm -rf "$PLAYER_ASSETS"/*; unzip -oq "$PLAYER_ZIP" -d "$PLAYER_ASSETS"; }
[ ! -f "$CLUB_ZIP" ] || { rm -rf "$TEAM_ASSETS"/*; unzip -oq "$CLUB_ZIP" -d "$TEAM_ASSETS"; }

command -v npm >/dev/null 2>&1 || fail_dialog "Node/npm is required to run the MatchLab Studio frontend."

# Clear anything already occupying the Studio ports. This prevents the launcher
# accidentally validating an older backend process left running from a previous build.
for PORT in 8000 5173; do
  PIDS="$(lsof -ti tcp:$PORT 2>/dev/null || true)"
  [ -z "$PIDS" ] || kill $PIDS >/dev/null 2>&1 || true
done
sleep 1

cd "$BACKEND"
nohup "$PY" -m uvicorn studio_entry:app --host 127.0.0.1 --port 8000 > /tmp/matchlab-backend.log 2>&1 &
BACKEND_PID=$!

cd "$FRONTEND"
if [ ! -d node_modules ]; then
  npm install >/tmp/matchlab-npm.log 2>&1 || fail_dialog "MatchLab could not install its frontend packages."
fi
nohup npm run dev -- --host 127.0.0.1 --port 5173 > /tmp/matchlab-frontend.log 2>&1 &

for i in {1..60}; do
  # If our new backend died, fail rather than talking to some stale process.
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    fail_dialog "The MatchLab local backend stopped while starting. Nothing else was opened."
  fi

  HEALTH="$(curl -fsS http://127.0.0.1:8000/health 2>/dev/null || true)"
  FRONT_OK="$(curl -fsS http://127.0.0.1:5173 2>/dev/null || true)"
  if [ -n "$HEALTH" ] && [ -n "$FRONT_OK" ]; then
    SERVICE="$(printf '%s' "$HEALTH" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("service",""))' 2>/dev/null || true)"
    [ "$SERVICE" = "matchlab-studio-api" ] || { sleep 1; continue; }

    METRICS_JSON="$(curl -fsS http://127.0.0.1:8000/canonical/metrics 2>/dev/null || true)"
    [ -n "$METRICS_JSON" ] || { sleep 1; continue; }
    COUNT="$(printf '%s' "$METRICS_JSON" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("match_stats_count",-1))' 2>/dev/null || echo -1)"
    [ "$COUNT" = "33" ] || fail_dialog "MatchLab refused to open because the backend did not expose the locked 33-stat contract."

    # The app is healthy. Open Studio immediately; match import remains local and happens through the app.
    open http://127.0.0.1:5173
    exit 0
  fi
  sleep 1
done

fail_dialog "MatchLab did not finish starting. Nothing else was opened."
