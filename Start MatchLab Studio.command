#!/bin/zsh
set -e
STUDIO_ROOT="$(cd "$(dirname "$0")" && pwd)"
FRONTEND="$STUDIO_ROOT/frontend"
BACKEND="$STUDIO_ROOT/backend"
VENV="$BACKEND/.venv"
PY="$VENV/bin/python"

fail_dialog(){ osascript -e "display dialog \"$1\" buttons {\"OK\"} default button \"OK\" with icon stop"; exit 1; }

# MatchLab is fully self-contained. No other repository is cloned, fetched or imported.
[ -f "$BACKEND/main.py" ] || fail_dialog "MatchLab backend is missing. Please Fetch/Pull the latest MatchLab Studio first."
[ -f "$BACKEND/golden_metrics.py" ] || fail_dialog "MatchLab Golden metrics file is missing. Please Fetch/Pull the latest MatchLab Studio first."
[ -f "$BACKEND/server.py" ] || fail_dialog "MatchLab API wrapper is missing. Please Fetch/Pull the latest MatchLab Studio first."

# Wire in only the crests/player images supplied for MatchLab.
TEAM_ASSET_DIR="$STUDIO_ROOT/assets/team_logos"
PLAYER_ASSET_DIR="$STUDIO_ROOT/assets/player_images"
mkdir -p "$TEAM_ASSET_DIR" "$PLAYER_ASSET_DIR"
ASSET_ZIP=""
for candidate in "$STUDIO_ROOT/MatchLab-Studio-Assets.zip" "$HOME/Downloads/MatchLab-Studio-Assets.zip" "$HOME/Desktop/MatchLab-Studio-Assets.zip" "$HOME/Documents/MatchLab-Studio-Assets.zip"; do
  if [ -f "$candidate" ]; then ASSET_ZIP="$candidate"; break; fi
done
if [ -z "$ASSET_ZIP" ] && command -v mdfind >/dev/null 2>&1; then ASSET_ZIP="$(mdfind 'kMDItemFSName == "MatchLab-Studio-Assets.zip"c' | head -1 || true)"; fi
if [ -n "$ASSET_ZIP" ] && [ -f "$ASSET_ZIP" ]; then
  TMP_ASSETS="$(mktemp -d /tmp/matchlab-assets.XXXXXX)"
  /usr/bin/unzip -q -o "$ASSET_ZIP" -d "$TMP_ASSETS"
  [ -d "$TMP_ASSETS/public/team-logos" ] && /bin/cp -f "$TMP_ASSETS/public/team-logos/"* "$TEAM_ASSET_DIR/" 2>/dev/null || true
  [ -d "$TMP_ASSETS/public/player-images" ] && /bin/cp -f "$TMP_ASSETS/public/player-images/"* "$PLAYER_ASSET_DIR/" 2>/dev/null || true
  /bin/rm -rf "$TMP_ASSETS"
fi

# Footer artwork supplied for MatchLab.
mkdir -p "$FRONTEND/public"
find_footer_asset(){
  NAME="$1"
  for candidate in "$STUDIO_ROOT/$NAME" "$HOME/Downloads/$NAME" "$HOME/Desktop/$NAME" "$HOME/Documents/$NAME"; do
    if [ -f "$candidate" ]; then echo "$candidate"; return 0; fi
  done
  if command -v mdfind >/dev/null 2>&1; then mdfind "kMDItemFSName == \"$NAME\"c" | head -1 || true; fi
}
ROSE_SOURCE="$(find_footer_asset 'Logo Rose.png')"
STRAP_SOURCE="$(find_footer_asset 'Logo strap.png')"
[ -n "$ROSE_SOURCE" ] && [ -f "$ROSE_SOURCE" ] && /bin/cp -f "$ROSE_SOURCE" "$FRONTEND/public/logo-rose.png"
[ -n "$STRAP_SOURCE" ] && [ -f "$STRAP_SOURCE" ] && /bin/cp -f "$STRAP_SOURCE" "$FRONTEND/public/logo-strap.png"

if [ ! -x "$PY" ]; then
  SYSTEM_PY="$(command -v python3 || true)"
  [ -n "$SYSTEM_PY" ] || fail_dialog "Python 3 is required to run MatchLab Studio."
  "$SYSTEM_PY" -m venv "$VENV" || fail_dialog "MatchLab could not create its local Python environment."
fi
if ! "$PY" -c 'import fastapi, uvicorn, curl_cffi' >/dev/null 2>&1; then
  "$PY" -m pip install --upgrade pip >/tmp/matchlab-pip.log 2>&1
  "$PY" -m pip install -r "$BACKEND/requirements.txt" >>/tmp/matchlab-pip.log 2>&1 || fail_dialog "MatchLab could not install its local backend requirements."
fi
command -v npm >/dev/null 2>&1 || fail_dialog "Node/npm is required to run MatchLab Studio."

find_free_port(){ START="$1"; END="$2"; PORT="$START"; while [ "$PORT" -le "$END" ]; do if [ -z "$(lsof -ti tcp:$PORT 2>/dev/null || true)" ]; then echo "$PORT"; return 0; fi; PORT=$((PORT+1)); done; return 1; }
BACKEND_PORT="$(find_free_port 8000 8099 || true)"
FRONTEND_PORT="$(find_free_port 5173 5273 || true)"
[ -n "$BACKEND_PORT" ] || fail_dialog "MatchLab could not find a free local backend port."
[ -n "$FRONTEND_PORT" ] || fail_dialog "MatchLab could not find a free local frontend port."

cd "$BACKEND"
: > /tmp/matchlab-backend.log
nohup "$PY" -m uvicorn server:app --host 127.0.0.1 --port "$BACKEND_PORT" > /tmp/matchlab-backend.log 2>&1 &
BACKEND_PID=$!
sleep 1
if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then LAST_LINE="$(tail -1 /tmp/matchlab-backend.log 2>/dev/null | tr '"' "'" | cut -c1-220)"; [ -n "$LAST_LINE" ] || LAST_LINE="The backend process exited before reporting an error."; fail_dialog "The MatchLab local backend could not start. Last backend message: $LAST_LINE"; fi

cd "$FRONTEND"
if [ ! -d node_modules ]; then npm install >/tmp/matchlab-npm.log 2>&1 || fail_dialog "MatchLab could not install its frontend packages."; fi
: > /tmp/matchlab-frontend.log
MATCHLAB_BACKEND_URL="http://127.0.0.1:$BACKEND_PORT" VITE_MATCHLAB_API="/api" nohup npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort > /tmp/matchlab-frontend.log 2>&1 &
FRONTEND_PID=$!

for i in {1..60}; do
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then LAST_LINE="$(tail -1 /tmp/matchlab-backend.log 2>/dev/null | tr '"' "'" | cut -c1-220)"; fail_dialog "The MatchLab local backend stopped while starting. Last backend message: $LAST_LINE"; fi
  if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then LAST_LINE="$(tail -1 /tmp/matchlab-frontend.log 2>/dev/null | tr '"' "'" | cut -c1-220)"; fail_dialog "The MatchLab frontend stopped while starting. Last frontend message: $LAST_LINE"; fi
  PROXY_OK="$(curl -fsS "http://127.0.0.1:$FRONTEND_PORT/api/health" 2>/dev/null || true)"
  if [ -n "$PROXY_OK" ]; then
    RUNTIME="$(printf '%s' "$PROXY_OK" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("runtime",""))' 2>/dev/null || true)"
    if [ "$RUNTIME" = "self-contained" ]; then open "http://127.0.0.1:$FRONTEND_PORT"; exit 0; fi
  fi
  sleep 1
done
fail_dialog "MatchLab did not finish starting its self-contained local API and frontend proxy."
