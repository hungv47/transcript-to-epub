#!/usr/bin/env bash
# Dev runner: create a venv, install deps, start the server with reload.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

[ -f .env ] && set -a && . ./.env && set +a

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
