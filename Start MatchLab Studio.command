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
  git -C "$BACKEND_REPO" fetch origin matchlab-v2-web
  git -C "$BACKEND_REPO" checkout -B matchlab-v2-web origin/matchlab-v2-web >/dev/null 2>&1
fi

# Wire in the exact MatchLab crests/player images supplied by the user.
# No SofaScore/FPL/third-party imagery is downloaded here.
TEAM_ASSET_DIR="$BACKEND_REPO/assets/team_logos"
PLAYER_ASSET_DIR="$BACKEND_REPO/assets/player_images"
mkdir -p "$TEAM_ASSET_DIR" "$PLAYER_ASSET_DIR"

ASSET_ZIP=""
for candidate in \
  "$STUDIO_ROOT/MatchLab-Studio-Assets.zip" \
  "$HOME/Downloads/MatchLab-Studio-Assets.zip" \
  "$HOME/Desktop/MatchLab-Studio-Assets.zip" \
  "$HOME/Documents/MatchLab-Studio-Assets.zip"; do
  if [ -f "$candidate" ]; then ASSET_ZIP="$candidate"; break; fi
done
if [ -z "$ASSET_ZIP" ] && command -v mdfind >/dev/null 2>&1; then
  ASSET_ZIP="$(mdfind 'kMDItemFSName == "MatchLab-Studio-Assets.zip"c' | head -1 || true)"
fi

if [ -n "$ASSET_ZIP" ] && [ -f "$ASSET_ZIP" ]; then
  TMP_ASSETS="$(mktemp -d /tmp/matchlab-assets.XXXXXX)"
  /usr/bin/unzip -q -o "$ASSET_ZIP" -d "$TMP_ASSETS"
  if [ -d "$TMP_ASSETS/public/team-logos" ]; then
    /bin/cp -f "$TMP_ASSETS/public/team-logos/"* "$TEAM_ASSET_DIR/" 2>/dev/null || true
  fi
  if [ -d "$TMP_ASSETS/public/player-images" ]; then
    /bin/cp -f "$TMP_ASSETS/public/player-images/"* "$PLAYER_ASSET_DIR/" 2>/dev/null || true
  fi
  /bin/rm -rf "$TMP_ASSETS"
fi

# Also recognise the original supplied folders directly if they are already on this Mac.
if command -v mdfind >/dev/null 2>&1; then
  if [ ! -f "$TEAM_ASSET_DIR/leeds-united.png" ]; then
    FOUND_TEAM="$(mdfind 'kMDItemFSName == "leeds-united.png"c' | head -1 || true)"
    if [ -n "$FOUND_TEAM" ]; then
      SOURCE_DIR="${FOUND_TEAM:h}"
      /bin/cp -f "$SOURCE_DIR/"*.png "$TEAM_ASSET_DIR/" 2>/dev/null || true
    fi
  fi
  if [ ! -f "$PLAYER_ASSET_DIR/joe-rodon.png" ]; then
    FOUND_PLAYER="$(mdfind 'kMDItemFSName == "joe-rodon.png"c' | head -1 || true)"
    if [ -n "$FOUND_PLAYER" ]; then
      SOURCE_DIR="${FOUND_PLAYER:h}"
      /bin/cp -f "$SOURCE_DIR/"*.png "$PLAYER_ASSET_DIR/" 2>/dev/null || true
    fi
  fi
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

find_free_port(){
  START="$1"
  END="$2"
  PORT="$START"
  while [ "$PORT" -le "$END" ]; do
    if [ -z "$(lsof -ti tcp:$PORT 2>/dev/null || true)" ]; then
      echo "$PORT"
      return 0
    fi
    PORT=$((PORT+1))
  done
  return 1
}

BACKEND_PORT="$(find_free_port 8000 8099 || true)"
FRONTEND_PORT="$(find_free_port 5173 5273 || true)"
[ -n "$BACKEND_PORT" ] || fail_dialog "MatchLab could not find a free local backend port."
[ -n "$FRONTEND_PORT" ] || fail_dialog "MatchLab could not find a free local frontend port."

cd "$BACKEND"
: > /tmp/matchlab-backend.log
nohup "$PY" -m uvicorn main:app --host 127.0.0.1 --port "$BACKEND_PORT" > /tmp/matchlab-backend.log 2>&1 &
BACKEND_PID=$!

sleep 1
if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
  LAST_LINE="$(tail -1 /tmp/matchlab-backend.log 2>/dev/null | tr '"' "'" | cut -c1-220)"
  [ -n "$LAST_LINE" ] || LAST_LINE="The backend process exited before reporting an error."
  fail_dialog "The MatchLab local backend could not start. Last backend message: $LAST_LINE"
fi

cd "$FRONTEND"
if [ ! -d node_modules ]; then
  npm install >/tmp/matchlab-npm.log 2>&1 || fail_dialog "MatchLab could not install its frontend packages."
fi
: > /tmp/matchlab-frontend.log
MATCHLAB_BACKEND_URL="http://127.0.0.1:$BACKEND_PORT" VITE_MATCHLAB_API="/api" nohup npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort > /tmp/matchlab-frontend.log 2>&1 &
FRONTEND_PID=$!

for i in {1..60}; do
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    LAST_LINE="$(tail -1 /tmp/matchlab-backend.log 2>/dev/null | tr '"' "'" | cut -c1-220)"
    [ -n "$LAST_LINE" ] || LAST_LINE="The backend process exited unexpectedly."
    fail_dialog "The MatchLab local backend stopped while starting. Last backend message: $LAST_LINE"
  fi
  if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    LAST_LINE="$(tail -1 /tmp/matchlab-frontend.log 2>/dev/null | tr '"' "'" | cut -c1-220)"
    [ -n "$LAST_LINE" ] || LAST_LINE="The frontend process exited unexpectedly."
    fail_dialog "The MatchLab frontend stopped while starting. Last frontend message: $LAST_LINE"
  fi

  HEALTH="$(curl -fsS "http://127.0.0.1:$BACKEND_PORT/health" 2>/dev/null || true)"
  FRONT_OK="$(curl -fsS "http://127.0.0.1:$FRONTEND_PORT" 2>/dev/null || true)"
  PROXY_OK="$(curl -fsS "http://127.0.0.1:$FRONTEND_PORT/api/health" 2>/dev/null || true)"

  if [ -n "$HEALTH" ] && [ -n "$FRONT_OK" ] && [ -n "$PROXY_OK" ]; then
    SERVICE="$(printf '%s' "$PROXY_OK" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("service",""))' 2>/dev/null || true)"
    if [ "$SERVICE" = "matchlab-api" ]; then
      open "http://127.0.0.1:$FRONTEND_PORT"
      exit 0
    fi
  fi
  sleep 1
done

fail_dialog "MatchLab did not finish starting its local API and frontend proxy."
