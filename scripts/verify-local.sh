#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --project backend --locked
(
  cd backend
  uv run ruff check app tests migrations
  uv run ruff format --check app tests migrations
  uv run mypy
  uv run pytest
)
mkdir -p artifacts
uv run --project backend python scripts/generate-contract.py > artifacts/openapi.json
npm --prefix frontend ci
npm --prefix frontend run contract
git diff --exit-code -- frontend/src/generated/api.ts
npm --prefix frontend run format:check
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:browser
