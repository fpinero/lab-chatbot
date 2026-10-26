# Implementation tasks

Only pending work belongs here. Each milestone starts after the preceding milestone is verified and integrated remotely. Keep every milestone branch for at least seven days after merge, with no automatic cleanup.

## M1: Protected foundation

- [ ] Integrate M1 with CI, PR, remote merge and branch retention evidence.

## M2: Text chat

- [ ] Verify official catalog/chat schemas and implement cached catalog, stale metadata and refresh throttling. Acceptance: contract tests cover invalid models, unknown capabilities and sanitized provider failures.
- [ ] Add transactional USD reservations, idempotency and reconciliation. Acceptance: concurrent requests respect limits; missing usage and uncertain dispatch never become zero cost.
- [ ] Persist conversations, immutable snapshots and bounded checkpoints. Acceptance: search/rename/delete/export, retry and restart interruption preserve original evidence.
- [ ] Implement server-owned streaming, SSE reconnect, cancellation and queue bounds. Acceptance: split frames, post-200 errors, expiry and disconnected readers are tested.
- [ ] Build safe Markdown chat, capability-driven settings, drafts, usage, stop/retry. Acceptance: desktop/mobile browser and sanitization tests pass.
- [ ] Run bounded opt-in live text check with restricted key and owner-approved numeric budget, or record external limitation.
- [ ] Integrate M2 with CI, PR, remote merge and branch retention evidence.

## M3: Attachments and comparisons

- [ ] Implement bounded private uploads and isolated extraction. Acceptance: real PDF/DOCX/TXT/CSV fixtures, encrypted/scanned documents, bombs, MIME mismatch, traversal and streamed byte limits are tested.
- [ ] Forward sanitized images and extracted document text with compatibility/context checks. Acceptance: previews and warnings are accurate and no silent truncation occurs.
- [ ] Snapshot two-to-four comparison inputs once and queue independent candidates. Acceptance: identical requests, partial failure and no cross-candidate contamination are asserted.
- [ ] Build mobile comparison cards, explicit retry and continue-with-answer forks. Acceptance: browser tests cover reuse and independent candidate status.
- [ ] Add reference-aware deletion and expired abandoned-upload cleanup. Acceptance: referenced/shared assets survive and expired unreferenced files are removed.
- [ ] Run budgeted live vision/document/comparison checks when configured; record actual evidence or limitation.
- [ ] Integrate M3 with CI, PR, remote merge and branch retention evidence.

## M4: Image generation

- [ ] Verify dedicated image catalog/generation contracts and chat-only adapters. Acceptance: sanitized fixtures distinguish input capabilities from generation support.
- [ ] Implement supported settings, conservative reservations and durable local jobs. Acceptance: idempotency, restart and unknown outcome/cost tests pass.
- [ ] Save bounded validated raster outputs with restricted outbound retrieval. Acceptance: MIME/size/SSRF/redirect and authenticated persistence tests pass.
- [ ] Build explicit generation form, estimates, previews, downloads and retries. Acceptance: browser reload preserves results and selections never spend credit.
- [ ] Verify one live image within approved budget or record concrete account/credential blocker without claiming completion.
- [ ] Integrate M4 with CI, PR, remote merge and branch retention evidence.

## M5: Video generation

- [ ] Verify dedicated video catalog, submit/status/content/cancellation contracts. Acceptance: controls derive from documented model capabilities.
- [ ] Persist provider job IDs and implement bounded restart-safe polling. Acceptance: accepted jobs are never resubmitted and unknown submission retains reservation.
- [ ] Implement explicit cancellation and authenticated media/range delivery. Acceptance: restart/retrieval/range tests pass without credential forwarding.
- [ ] Build capability-driven form, status and playback. Acceptance: explicit generation, reload and provider limitations are covered in browser tests.
- [ ] Verify one shortest live clip within approved budget or record concrete provider/access blocker.
- [ ] Integrate M5 with CI, PR, remote merge and branch retention evidence.

## M6: Local release candidate

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
