#!/usr/bin/env bash
# transcript-to-epub: Wrapper to run the Python build script
# Usage: bash build.sh <input.md|youtube-url> [--title "title"] [--cover PATH]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/build.py" "$@"
