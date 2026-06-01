#!/usr/bin/env bash
# Dev runner: create a venv, install deps, start the server with reload.
# Uses uv when available (fast, no pip needed), else stdlib venv + pip.
set -euo pipefail
cd "$(dirname "$0")"

if command -v uv >/dev/null 2>&1; then
  [ -d .venv ] || uv venv .venv
  uv pip install -q -r requirements.txt
else
  [ -d .venv ] || python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install -q --upgrade pip
  python -m pip install -q -r requirements.txt
fi

# Put the venv's binaries (uvicorn, weasyprint) on PATH for both paths.
export PATH="$PWD/.venv/bin:$PATH"

[ -f .env ] && set -a && . ./.env && set +a

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
