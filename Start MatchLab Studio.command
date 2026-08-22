#!/bin/zsh
set -e

STUDIO_ROOT="$(cd "$(dirname "$0")" && pwd)"
FRONTEND="$STUDIO_ROOT/frontend"
BACKEND_REPO="$HOME/Documents/GitHub/MatchLab-Backend-Local"
BACKEND="$BACKEND_REPO/matchlab_web/backend"
PY="$HOME/Downloads/MatchLab/sofascore_social_graphics/.venv/bin/python"

if [ ! -d "$BACKEND_REPO/.git" ]; then
  git clone --branch matchlab-v2-web --single-branch https://github.com/lufcdata/Analysis-App.git "$BACKEND_REPO"
else
  git -C "$BACKEND_REPO" fetch origin matchlab-v2-web
  git -C "$BACKEND_REPO" checkout matchlab-v2-web >/dev/null 2>&1 || true
  git -C "$BACKEND_REPO" pull --ff-only origin matchlab-v2-web
fi

if [ ! -x "$PY" ]; then
  osascript -e 'display dialog "MatchLab Python environment was not found. Open ChatGPT and tell it: MatchLab launcher cannot find the Python environment." buttons {"OK"} default button "OK" with icon stop'
  exit 1
fi

# Install ONLY the user's approved local imagery packs. No SofaScore imagery is downloaded.
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

pkill -f "uvicorn studio_entry:app" >/dev/null 2>&1 || true
pkill -f "vite.*5173" >/dev/null 2>&1 || true

cd "$BACKEND"
nohup "$PY" -m uvicorn studio_entry:app --host 127.0.0.1 --port 8000 > /tmp/matchlab-backend.log 2>&1 &

cd "$FRONTEND"
if [ ! -d node_modules ]; then
  npm install
fi
nohup npm run dev -- --host 127.0.0.1 --port 5173 > /tmp/matchlab-frontend.log 2>&1 &

for i in {1..30}; do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && curl -fsS http://127.0.0.1:5173 >/dev/null 2>&1; then
    open http://127.0.0.1:5173
    exit 0
  fi
  sleep 1
done

osascript -e 'display dialog "MatchLab did not finish starting. Open ChatGPT and say: one-click launcher failed. The logs are /tmp/matchlab-backend.log and /tmp/matchlab-frontend.log." buttons {"OK"} default button "OK" with icon caution'
exit 1
