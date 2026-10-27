#!/usr/bin/env bash
# Start this checkout's FastAPI and Vite development services.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_ROOT}"
if [[ ! -x backend/.venv/bin/python ]]; then
  echo "Prepare the backend first: uv sync --project backend --locked" >&2
  exit 1
fi
exec backend/.venv/bin/python scripts/dev-server.py start "$@"
