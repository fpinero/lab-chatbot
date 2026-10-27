#!/usr/bin/env bash
# Read-only unless the caller explicitly supplies --execute to a write phase.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${PROJECT_ROOT}"
PYTHON_BIN="${LAB_RELEASE_PYTHON:-${PROJECT_ROOT}/backend/.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Install the locked development environment with uv sync --project backend --locked." >&2
  exit 1
fi
exec "${PYTHON_BIN}" scripts/release.py plan "$@"
