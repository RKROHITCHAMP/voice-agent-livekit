#!/usr/bin/env bash
# Push this project to a GitHub repo.
#
# Usage:
#   1. Create an EMPTY repo on GitHub (no README/license), copy its URL.
#   2. From the voice-agent-livekit/ directory run:
#        bash scripts/git_push.sh https://github.com/<you>/<repo>.git
#
# Auth: when prompted for a password, paste a GitHub Personal Access Token
# (Settings → Developer settings → Tokens), NOT your account password.
set -euo pipefail

REMOTE_URL="${1:-}"
if [[ -z "$REMOTE_URL" ]]; then
  echo "Usage: bash scripts/git_push.sh <github-repo-url>"
  exit 1
fi

# Run from the repo root (parent of this script's dir).
cd "$(dirname "$0")/.."

# If a previous (possibly broken) .git exists but isn't a valid repo, reset it.
if [[ -d .git ]] && ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Removing a broken/partial .git directory…"
  rm -rf .git
fi

if [[ ! -d .git ]]; then
  git init
  git branch -M main
  git config user.name "Rohit Kumar"
  git config user.email "rk8826177@gmail.com"
fi

git add .
git commit -m "Conversational voice agent: booking, live monitoring, take-over, warm transfer" || \
  echo "Nothing new to commit."

if git remote | grep -q '^origin$'; then
  git remote set-url origin "$REMOTE_URL"
else
  git remote add origin "$REMOTE_URL"
fi

git push -u origin main
echo "✅ Pushed to $REMOTE_URL"
