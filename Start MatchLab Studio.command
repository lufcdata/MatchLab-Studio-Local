#!/bin/zsh
set -e
STUDIO_ROOT="$(cd "$(dirname "$0")" && pwd)"
FRONTEND="$STUDIO_ROOT/frontend"
BACKEND_REPO="$HOME/Documents/GitHub/MatchLab-Backend-Local"
BACKEND="$BACKEND_REPO/matchlab_web/backend"
VENV="$BACKEND_REPO/.venv"
PY="$VENV/bin/python"
fail_dialog(){ osascript -e "display dialog \"$1\" buttons {\"OK\"} default button \"OK\" with icon stop"; exit 1; }

if [ ! -d "$BACKEND_REPO/.git" ]; then
  git clone --branch matchlab-v2-web --single-branch https://github.com/lufcdata/Analysis-App.git "$BACKEND_REPO"
else
  # This folder is launcher-managed. Always put it on the exact remote branch so
  # an older/stale local backend can never masquerade as the current MatchLab API.
  git -C "$BACKEND_REPO" fetch origin matchlab-v2-web
  git -C "$BACKEND_REPO" checkout -B matchlab-v2-web origin/matchlab-v2-web >/dev/null 2>&1
fi

if [ ! -x "$PY" ]; then
  SYSTEM_PY="$(command -v python3 || true)"
  [ -n "$SYSTEM_PY" ] || fail_dialog "Python 3 is required to run MatchLab Studio."
  "$SYSTEM_PY" -m venv "$VENV" || fail_dialog "MatchLab could not create its local Python environment."
fi

if ! "$PY" -c 'import fastapi, uvicorn, requests, curl_cffi, PIL' >/dev/null 2>&1; then
  "$PY" -m pip install --upgrade pip >/tmp/matchlab-pip.log 2>&1
  "$PY" -m pip install -r "$BACKEND/requirements.txt" >>/tmp/matchlab-pip.log 2>&1 || fail_dialog "MatchLab could not install its local backend requirements."
fi

command -v npm >/dev/null 2>&1 || fail_dialog "Node/npm is required to run MatchLab Studio."

for PORT in 8000 5173; do
  PIDS="$(lsof -ti tcp:$PORT 2>/dev/null || true)"
  [ -z "$PIDS" ] || kill $PIDS >/dev/null 2>&1 || true
done
sleep 1

cd "$BACKEND"
nohup "$PY" -m uvicorn main:app --host 127.0.0.1 --port 8000 > /tmp/matchlab-backend.log 2>&1 &
BACKEND_PID=$!

cd "$FRONTEND"
if [ ! -d node_modules ]; then
  npm install >/tmp/matchlab-npm.log 2>&1 || fail_dialog "MatchLab could not install its frontend packages."
fi
nohup npm run dev -- --host 127.0.0.1 --port 5173 > /tmp/matchlab-frontend.log 2>&1 &

for i in {1..60}; do
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    fail_dialog "The MatchLab local backend stopped while starting."
  fi

  HEALTH="$(curl -fsS http://127.0.0.1:8000/health 2>/dev/null || true)"
  FRONT_OK="$(curl -fsS http://127.0.0.1:5173 2>/dev/null || true)"
  OPENAPI="$(curl -fsS http://127.0.0.1:8000/openapi.json 2>/dev/null || true)"

  if [ -n "$HEALTH" ] && [ -n "$FRONT_OK" ] && [ -n "$OPENAPI" ]; then
    SERVICE="$(printf '%s' "$HEALTH" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("service",""))' 2>/dev/null || true)"
    ROUTES_OK="$(printf '%s' "$OPENAPI" | "$PY" -c 'import json,sys; p=json.load(sys.stdin).get("paths",{}); required=["/matches/import-sofascore","/matches/{event_id}","/matches/{event_id}/period-capabilities","/matches/{event_id}/studio-match-stats","/canonical/metrics"]; print("yes" if all(x in p for x in required) else "no")' 2>/dev/null || echo no)"
    if [ "$SERVICE" = "matchlab-api" ] && [ "$ROUTES_OK" = "yes" ]; then
      open http://127.0.0.1:5173
      exit 0
    fi
  fi
  sleep 1
done

fail_dialog "MatchLab started an outdated or incomplete local API. The launcher has stopped it rather than opening a broken Studio."
