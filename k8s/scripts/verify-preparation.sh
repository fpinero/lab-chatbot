#!/usr/bin/env bash
# Local verification only: no image push, release Lease, Secret upload or cluster apply.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${PROJECT_ROOT}"
PYTHON_BIN="${LAB_RELEASE_PYTHON:-${PROJECT_ROOT}/backend/.venv/bin/python}"
export LAB_BROWSER_API_PORT="${LAB_BROWSER_API_PORT:-28000}"
export LAB_BROWSER_UI_PORT="${LAB_BROWSER_UI_PORT:-25173}"
scripts/verify-local.sh
"${PYTHON_BIN}" -m ruff check scripts/release.py scripts/configure-deploy.py scripts/install-deploy-tools.py scripts/backup-data.py scripts/smoke-image.py
"${PYTHON_BIN}" -m ruff format --check scripts/release.py scripts/configure-deploy.py scripts/install-deploy-tools.py scripts/backup-data.py scripts/smoke-image.py
for script in k8s/scripts/*.sh; do bash -n "${script}"; done
k8s/scripts/validate.sh
docker compose config --quiet
SOURCE_FINGERPRINT="$(PYTHONPATH=scripts "${PYTHON_BIN}" -c 'import release; print(release.fingerprint())')"
SOURCE_REVISION="$(git rev-parse HEAD)"
docker buildx build --platform linux/arm64 --provenance=false --load \
  --build-arg "SOURCE_REVISION=${SOURCE_REVISION}" \
  --build-arg "SOURCE_FINGERPRINT=${SOURCE_FINGERPRINT}" \
  -t lab-chatbot-preparation:local .
"${PYTHON_BIN}" scripts/smoke-image.py lab-chatbot-preparation:local
PYTHONPATH=scripts "${PYTHON_BIN}" - <<'PY'
import json
from datetime import UTC, datetime
import release

image = json.loads(release.run(["docker", "image", "inspect", "lab-chatbot-preparation:local"]).stdout)[0]
fingerprint = release.fingerprint()
assert image["Architecture"] == "arm64" and image["Os"] == "linux"
assert image["Config"]["Labels"]["com.labchatbot.source-fingerprint"] == fingerprint
release.write_record(release.ARTIFACTS / "preparation-verification.json", {
    "fingerprint": fingerprint,
    "revision": release.run(["git", "rev-parse", "HEAD"]).stdout.strip(),
    "image_id": image["Id"],
    "platform": "linux/arm64",
    "verified_at": datetime.now(UTC).isoformat(),
    "checks": ["full_local_suite", "deployment_regressions", "schema_1.25.6", "compose", "container_restart", "production_startup"],
    "cluster_writes": False,
    "registry_publication": False,
    "paid_provider_requests": 0,
})
print("Local preparation verified. Stop here: no cluster resources or published images were changed.")
PY
