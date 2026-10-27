#!/usr/bin/env bash
# Stop only services recorded and verified by this checkout's development launcher.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_ROOT}"
PYTHON_BIN="${PROJECT_ROOT}/backend/.venv/bin/python"
if [[ ! -x "${PYTHON_BIN}" ]]; then PYTHON_BIN="$(command -v python3)"; fi
exec "${PYTHON_BIN}" scripts/dev-server.py stop "$@"
