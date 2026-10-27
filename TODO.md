# Implementation tasks

Only pending work belongs here. Each milestone starts after the preceding milestone is verified and integrated remotely. Keep every milestone branch for at least seven days after merge, with no automatic cleanup.

## External verification prerequisites

- [ ] Install a restricted provider key privately and obtain approved request/daily/cumulative live-test budgets. Acceptance: opt-in real text/vision/comparison/media checks record sanitized status and actual cost; no mock result is reported as live evidence.

## M4: Image generation

- [ ] Obtain restricted credentials and approved budgets, then generate one live image and verify its saved output after reload. Acceptance: sanitized real status and cost evidence; M4 stays incomplete until this passes.
- [ ] Complete the M4 live exit gate, then merge the draft PR remotely and record retained-branch evidence. CI and local verification already pass.

## M5: Video generation

- [ ] Verify dedicated video catalog, submit/status/content/cancellation contracts. Acceptance: controls derive from documented model capabilities.
- [ ] Persist provider job IDs and implement bounded restart-safe polling. Acceptance: accepted jobs are never resubmitted and unknown submission retains reservation.
- [ ] Implement explicit cancellation and authenticated media/range delivery. Acceptance: restart/retrieval/range tests pass without credential forwarding.
- [ ] Build capability-driven form, status and playback. Acceptance: explicit generation, reload and provider limitations are covered in browser tests.
- [ ] Verify one shortest live clip within approved budget or record concrete provider/access blocker.
- [ ] Integrate M5 with CI, PR, remote merge and branch retention evidence.

## M6: Local release candidate

- [ ] Validate custom SQLite URL paths against compiled static locations, including URI/override cases. Acceptance: startup rejects every writable database/data path under public assets before opening storage.
- [ ] Package explicit-source multi-stage image and loopback Compose with named volume. Acceptance: non-root/read-only execution and no secrets/private brief in image.
- [ ] Add storage/rate/concurrency limits, sanitized request IDs and local readiness. Acceptance: pressure and bounded queue behavior are tested.
- [ ] Add consistent SQLite/file backup and isolated restore. Acceptance: restart preserves sessions/history/media and restore reproduces referenced data.
- [ ] Finish themes, focus, keyboard, copy/export, responsive composer and recovery. Acceptance: inspect desktop/360 px screenshots and full browser suite.
- [ ] Run full checks and actual container verification. Acceptance: exact source fingerprint and real results recorded with external limitations explicit.
- [ ] Integrate M6 with CI, PR, remote merge and branch retention evidence.

## M7: Deployment preparation

- [ ] Inspect working Ingress and cluster versions/class/entrypoints/architecture/storage/registry/TLS. Acceptance: read-only evidence replaces assumptions; request missing example path when needed.
- [ ] Prepare scoped Kustomize manifests with single Recreate replica, PVC and hardened existing Traefik integration. Acceptance: render/schema/server-side dry-run/diff pass without exposing Secrets.
- [ ] Implement read-only release planner and explicit build/push/deploy phases. Acceptance: source gate, distributed lock, production-derived integer tag, collisions, architecture and optimistic concurrency tests pass.
- [ ] Test first deploy, inaccessible/forbidden cluster, registry ports, collision/reuse and concurrency. Acceptance: only confirmed NotFound permits initial tag; existing tags never overwritten.
- [ ] Document prerequisites, secrets, TLS, rollout/rollback, backups and diagnosis in k8s/README.md. Acceptance: no private authentication details or credentials in public docs.
- [ ] Produce concrete live-state release plan and collect missing identity/budget/registry prerequisites.
- [ ] Integrate M7 with CI, PR, remote merge and branch retention evidence.

## M8: Production rollout

- [ ] Verify restricted key, approved numeric budgets, secure identity, origin TLS and deployment access without echoing secrets.
- [ ] Lock release, verify exact source, publish immutable next tag and recheck production baseline. Acceptance: digest/source/tag and dry-run/diff evidence recorded.
- [ ] Deploy exact image and inspect rollout, edge/origin TLS, auth and protected reads. Acceptance: real hostname works on mobile and direct-origin access cannot bypass auth.
- [ ] Verify history/media persistence and compatible rollback with consistent backup. Acceptance: restart checks pass without deleting production data.
- [ ] Run only budgeted live modality checks and report unavailable account capabilities explicitly.
- [ ] Record revision/digest/old-new tags/fingerprint and outstanding limitations. Acceptance: local and production status reported separately.
