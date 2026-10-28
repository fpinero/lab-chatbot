# Implementation log

Entries are append-only. Record verified work and evidence without credentials or private authentication details.

## 2026-10-26: Implementation started

- Read the private implementation brief and ancestor workspace instructions. The brief explicitly selects English task files, append-only history and standing milestone integration authorization.
- Initial checkout: `feature/implementation-blueprint`, commit `db87ad0`, no application code. Preserved the existing untracked IDE directory.
- Created `feature/m0-bootstrap` before modifications. Remote `main` also points to `db87ad0`.
- Inspected GitHub settings: automatic branch deletion is disabled; merge, squash and rebase are available. No initial `.github/workflows` directory or deployment workflow exists.
- Expanded M0 through M8 into pending tasks with acceptance criteria in `TODO.md`. Implementation and live/deployment validation remain pending.

## 2026-10-26: M0 local verification

- Added React 19.3.1, Vite 8.3.5, Tailwind 4.3.3, strict TypeScript 5.9 and generated OpenAPI types. Selected TypeScript 5.9 to satisfy the contract generator peer dependency without forcing resolution.
- Pinned Node 24.22.1 and Python 3.12.15; committed npm and uv resolutions. Backend resolves FastAPI 0.162.0 and Pydantic 2.14.1.
- Added network-free mock preview, sanitized JSON errors, request IDs, API-before-SPA routing and production startup rejection. No live provider calls or paid tests ran.
- Verified frozen dependency installs, Ruff check/format, mypy (5 files), pytest (4 tests), TypeScript, Vitest (2 tests) and production Vite build. npm audit reported zero vulnerabilities.
- Playwright desktop and 360 px mobile workflows both passed against real loopback servers. Inspected `artifacts/m0-desktop.png` and `artifacts/m0-mobile.png`; no horizontal overflow or clipped controls. Adjusted the mobile test to assert the visible submission workflow instead of a hidden desktop status indicator.
- Verified private brief, environment, policy, IDE and runtime paths are ignored; reviewed Docker context exclusions. Container inspection belongs to M6 because no image exists yet.
- Added CI verification without deployment steps. Pull request and remote integration remain pending.

## 2026-10-26: M0 remote integration

- Pull request: https://github.com/fpinero/lab-chatbot/pull/1. CI run `40408681075` completed successfully; no review requests or actionable feedback remained.
- Merge confirmed remotely: `b8047322990ae2f8117d4cca58f1621493fb0dbc`, at `2026-10-26T21:59:38Z`. Source commit: `468c2b1194ab0213ebb1fe5324dcb53a2e42aad7`.
- Retained branch locally and remotely: `feature/m0-bootstrap`. Earliest cleanup: `2026-11-02T21:59:38Z`; deletion requires a later owner request. Auto-delete remains disabled.
- The connected GitHub app could read but not merge (integration permission 403); the authorized local GitHub CLI completed the merge without bypassing repository protections.
- Fetched and fast-forwarded the M1 branch to the confirmed remote integration before beginning implementation. No deployment occurred.

## 2026-10-26: M1 local verification

- Added SQLite WAL/foreign keys/busy timeout, initial Alembic migration, stable owner identity and server-side sessions with random opaque tokens stored only as hashes. Verified session continuity across application restart.
- Added Argon2id password authentication, optional private constrained policy loading, production configuration rejection and Cloudflare Access JWT verification with cached key rotation and explicit owner subject. No private policy values or policy-specific fixtures are tracked.
- Added exact Origin checks, session CSRF, rotation/logout, idle/absolute expiry, persistent per-address/global login buckets, trusted proxy chain handling, bounded credential verification and actual received-body limits. API errors share a sanitized generated contract.
- Backend: Ruff check/format, mypy (12 source files) and 28 pytest tests pass. Coverage includes private route families, forged headers, JWKS rotation, production cookie attributes, placeholder credentials, restart persistence and request size enforcement.
- Frontend: formatting, TypeScript, 3 Vitest tests and production build pass. Playwright desktop/mobile flows pass sign-in, explicit mock submission, reload, navigation drawer and logout. Inspected login and workspace screenshots at 360 px; no horizontal overflow.
- Ran 15 local excluded policy checks. Only the result count is recorded publicly.
- Production identity selection, provider credentials, numeric spend budgets, live provider validation and infrastructure prerequisites remain pending. No paid traffic or deployment occurred.

## 2026-10-26: M1 remote integration

- Pull request: https://github.com/fpinero/lab-chatbot/pull/2. CI run `40410432890` completed successfully, without pending review feedback.
- Remote merge: `2206008e1d8242b336fe337e208b1495182de979`, at `2026-10-26T22:12:44Z`. Source commit: `706584515de6488b8687c520f44156ebeda3d342`.
- Retained local/remote branch: `feature/m1-protected-foundation`. Earliest cleanup: `2026-11-02T22:12:44Z`; deletion requires a later owner request.
- Synchronized local main and started `feature/m2-text-chat` from the confirmed integration. Main only runs verification, without deployment.
- Checked presence only: provider key and numeric request/daily/live-test budgets are not configured. Requested approved numeric limits without requesting secrets in chat. Local implementation continues independently.

## 2026-10-26: M2 local verification

- Added verified official text catalog/chat/key/metadata contracts, a fixed-origin httpx adapter, explicit popularity provenance, capability/price filtering, cached/stale catalog handling and throttled manual refresh. Public contract references are in `docs/provider-contracts.md`.
- Added persistent conversations, immutable context snapshots, model-preserving metadata, deliberate repeat/edit runs, history search/rename/delete, favorites and authenticated JSON/Markdown exports. Deletion retains accounting and idempotency tombstones.
- Added transactional Decimal/micro-USD reservations before dispatch, request/daily/cumulative verification allowances, bounded queue/rate limits and two global generation slots. Provider price ceilings preserve Decimal precision in outbound JSON.
- Added server-owned streaming, bounded raw SSE framing, checkpoints, cancellation, snapshot reconnect, session revalidation without extending idle expiry, interrupted-run recovery and authenticated usage reconciliation. Management/unrestricted keys are rejected; generation POSTs are never retried automatically. Unknown billing retains its reservation.
- Ruff check/format, mypy (18 source files), 52 pytest tests, generated API contract, frontend format/TypeScript, 3 Vitest tests and production build pass. Tests exercise real concurrent reservations, key rejection, split UTF-8/CRLF, post-200 errors, missing usage, metadata settlement and session expiry during SSE.
- Playwright: 3 passing scenarios and 1 explicit desktop skip for the mobile-only reduced viewport. Desktop/mobile sign-in, streaming, model repeat, history after reload and logout pass. Inspected desktop, 360 px mobile and reduced-height screenshots. A reduced viewport is a keyboard-size proxy, not a physical device test.
- Added a bounded opt-in live text command and documented its credential/budget gates. No provider key or approved numeric budgets are available, so no live or paid request ran. Live validation remains an explicit external prerequisite.
- Container and deployment verification remain pending later milestones. M2 pull request/integration are pending.

- Additional M2 gate verification: two CLI tests confirm that read-only planning cannot construct an HTTP client and that execution without an approved numeric allowance fails before network access. These pass separately from the 52-test backend run recorded above.

## 2026-10-26: M2 remote integration

- Pull request: https://github.com/fpinero/lab-chatbot/pull/3. CI run `40414412169` passed with 54 backend tests, frontend checks and browser workflows. No pending review feedback remained.
- Confirmed remote merge: `60fcf05b4618b654d8b7566087d03fe1ba1ccd7d`, at `2026-10-26T22:47:25Z`. Source: `8afdb99250bc71b8724ec9b92e7d6ada9981f5bf`.
- Retained branch: `feature/m2-text-chat`, locally and remotely. Earliest cleanup: `2026-11-02T22:47:25Z`; no automatic cleanup.
- Synchronized main before creating `feature/m3-attachments-comparisons`. The connected GitHub app is read-only for PR mutations, so authorized CLI integration was used without bypassing protections.
- Live provider evidence remains blocked by missing restricted credentials and approved numeric budgets. Local attachment/comparison work can proceed without paid calls.

## 2026-10-27: M3 local verification

- Added private bounded uploads, real PDF/DOCX/text/CSV extraction and screenshot normalization in a disposable parser process. Validated MIME/magic/path rules, encrypted/scanned files, unsafe ZIP/XML features, decoded pixels, actual streamed bytes and combined context size across separate uploads.
- Parser limits include a ten-second timeout, POSIX CPU limit and Linux 512 MiB address/data limits. macOS rejects the Linux data limit, so local macOS checks retain byte/CPU/timeout guards without claiming a memory sandbox.
- Snapshots store locally extracted document text and hashed image references. Dispatch verifies content and forwards real WebP data URLs. Compatibility, approximate context and explicit uncertain vision allowances are checked before spending.
- Comparisons validate two to four candidates, reserve their combined allowance atomically and use the shared two-call concurrency limit. Identical request assertions, partial failures, deliberate retry and continuation using only the selected answer pass. Continuing does not add a charge; shared attachments survive source deletion.
- The additive migration preserves populated M2 history and usage links. Authenticated cleanup removes expired abandoned uploads and safely collects unreferenced files.
- Full local verification passed: locked installs, Ruff, mypy (23 source files), 80 backend tests, generated API contract, frontend formatting/types, 4 Vitest tests, production build and 5 Playwright scenarios with one explicit desktop skip for the mobile-only viewport. One subsequently added combined-context regression also passes; affected backend suites are rerun before commit.
- Inspected desktop/mobile comparison and continuation screenshots. Real browser workflows upload PNG plus TXT, preserve drafts across mode changes, compare three models, reload results and continue without generation. The production build reports a non-failing 577 kB bundle warning; UX/container optimization remains in M6.
- Live text/vision/document/comparison evidence remains unavailable: no restricted provider key or approved numeric budgets are configured. No paid requests or deployment ran. M3 remote integration remains pending.

## 2026-10-27: M3 remote integration

- PR: https://github.com/fpinero/lab-chatbot/pull/4. CI `40421266990` passed; no pending review feedback. Source: `5eebbfc92d2324440c24bcd76b8e4abb20fae26c`.
- Confirmed remote merge: `90018e8b15226ab82288fd26cb3491fa55d47afa`, at `2026-10-26T23:49:15Z`. Retained local/remote branch: `feature/m3-attachments-comparisons`. Earliest cleanup: `2026-11-02T23:49:15Z`; no automatic deletion.
- Additionally passed all 27 affected backend tests in a disposable Linux ARM64 Python 3.12.15 container with network disabled, non-root UID, read-only root filesystem and dropped capabilities. Linux parser memory limits work. This is not the M6 production-container gate.
- CI reports action-runtime deprecation notices; updating maintained action versions belongs to the local release hardening work. No deployment workflow exists.
- Synchronized main before creating `feature/m4-image-generation`. Live provider checks remain blocked by missing restricted credentials and approved numeric budgets.

## 2026-10-27: M4 local implementation, live exit gate pending

- Implemented the dedicated Image API against the current official guide/schema, with separate catalog and per-provider capabilities, 15-minute durable cache/stale fallback, explicit provider pinning and no generation POST retries. Unverified chat-only image routes are excluded rather than inferred from image-input support.
- Added durable local image jobs with immutable inputs, private reference links, shared text/image concurrency and transactional request/daily/cumulative verification reservations. Unknown billing dimensions require an explicit allowance. Known response cost is persisted before output validation; missing cost retains its reservation.
- Added bounded base64 raster validation and private WebP publication without resizing. Rejected HTML/SVG, mismatched MIME, oversized output and URL-only results. The documented contract does not require URL retrieval, so no arbitrary fetch or redirect following is enabled. Assets expire after configurable retention; deletion preserves accounting/tombstones and reference-aware cleanup.
- Queued jobs resume after restart. Submitted jobs become submission-unknown and are never automatically sent again. Optional generation IDs are persisted as soon as known. Retrying uncertain work requires explicit duplicate-spend acknowledgement.
- Local full verification passes: Ruff/check/format, mypy (27 source files), 103 backend tests, generated API contract, frontend format/types, 4 Vitest tests, production build and 7 Playwright scenarios with one explicit desktop skip for the mobile-only reduced viewport. Tests include real 4096 by 4096 output parsing, expiry, restart recovery, missing usage, combined accounting and shared global concurrency.
- Browser image workflows preserve drafts across mode changes, require explicit generation, survive reload and verify authenticated download plus denial after completed logout. Inspected desktop/mobile form and result screenshots. A browser test needed to wait for logout completion before checking denial; concurrency tests now synchronize occupied slots instead of assuming a wall-clock delay.
- Added an opt-in one-image CLI with a network-free default plan, mandatory numeric allowance, server-side cumulative verification budget and sanitized evidence. Its read-only/budget gates pass. No live or paid provider request ran.
- M4 is not complete: the required approved live image remains blocked by the absent restricted provider key and approved request/daily/live-test budgets. The milestone must remain open, and M5 cannot begin under the sequential milestone rule. Container release and deployment are still unverified. A non-failing 582 kB main bundle warning remains for M6.

- Additional M4 platform verification: all 48 image/attachment/comparison/migration tests pass in Linux ARM64 under a non-root UID, without network, with read-only root and dropped capabilities. This includes real 4K parsing under Linux memory limits. The temporary check image includes only public source/fixtures and does not replace the M6 production-container gate.

## 2026-10-27: M4 draft handoff and external blocker

- Draft PR: https://github.com/fpinero/lab-chatbot/pull/5. Implementation source: `4e268b17c33920985442c9efa7c47c783f14dd40`. Retained local/remote branch: `feature/m4-image-generation`; no merge or cleanup occurred.
- Reviewed staged source and exclusions for provider keys, private policy values, local notes and forbidden punctuation. The private brief, configuration, runtime data and evidence remain excluded.
- Checked presence without echoing values: no provider key/file, approved request limit, daily allowance or cumulative live-test budget is installed in the current environment. No paid provider test can run safely.
- The draft explicitly preserves the required live-image exit gate. CI/review inspection remains part of this open PR; M5 has not started because milestones must be completed and integrated sequentially. No production release or deployment occurred.

- M4 CI run `40424832791` passed on `51edef19fb35ca9edcedc2b19fe68894eee07dd6`. No review comments or requested reviews remain. Cancelled only the superseded run `40424777419`; the current verification completed successfully.
- Confirmed all M0-M4 working branches are retained locally and remotely. The current M4 PR remains a draft and unmerged solely because the mandatory approved live-image evidence is unavailable. No secret or budget was inferred from elapsed time or standing repository authorization.

## 2026-10-27: M4 final filename regression

- Demonstrated three filename-validation failures: Unicode normalization could produce slash, backslash or drive-colon syntax after the initial raw-name check. Generated storage IDs prevented filesystem traversal, but normalized display names did not satisfy the rejection contract.
- Added rejection after normalization and retained the three regression fixtures. Full local verification now passes 106 backend tests, 4 frontend tests and 7 browser scenarios (one intentional desktop skip), plus formatting/types/build/contract checks.
- All 51 image/attachment/comparison/migration tests pass in the Linux ARM64 check container with the corrected public files mounted read-only. Network is disabled and the process is non-root. No paid provider call ran.
- Recorded explicit custom database-path/static-root validation in the M6 hardening queue; the current tests verify the normal private data-directory layout. Production packaging and release remain pending.

## 2026-10-27: First live authenticated browser text check

- The owner installed a restricted provider key and approved first-text spending limits in excluded local configuration. Verified that configuration and the owner hash load correctly with private file permissions; no credential values were printed or committed.
- Started the real loopback backend/frontend. The owner signed in through the normal application UI. Health/readiness and private-route denial without a session pass; authentication was not bypassed.
- Executed exactly one interactive browser request with `mistralai/mistral-nemo`, a 32-token output ceiling and no attachments. DekaLLM returned a completed result with 9 input and 3 output tokens. OpenRouter reported USD 0.000000252; integer ledger accounting conservatively rounded this to one micro-USD, against a 12-micro-USD reservation.
- Reloaded and reopened saved history. The completed answer, original model/provider, usage and cost remained available. A read-only SQLite check confirmed exactly one generation, settled billing and no outstanding reservation. No automatic or manual retry was sent.
- Saved sanitized metadata and an actual browser capture to excluded `artifacts/live-text-browser.json` and `artifacts/live-text-browser.jpg`. Neither includes credentials or session tokens. Prompt/response contents are not copied into this public log.
- This was an ordinary interactive workspace charge, not a CLI verification-purpose charge. Its one-micro-USD ledger cost must be included in future cumulative test planning; the approved first-text test allowance has 19,999 micro-USD remaining after this smoke check.
- Updated pending tasks and public status to distinguish this first successful live text check from the unverified remaining modalities. M4 stays a draft until its approved live-image gate is satisfied. No deployment or additional paid call occurred.


## 2026-10-27: Shared provider key spending policy

- The owner replaced preset request, daily, verification and modality allocations with the existing OpenRouter key's shared total budget. Added opt-in `SPEND_CONTROL=provider`; application-controlled spending remains the backward-compatible default for other operators.
- Provider mode verifies restricted fixed-total key metadata and refreshes remaining credit before submission. External key usage and lower effective budgets are included. Pending and uncertain chat/comparison/image reservations share that remainder atomically; settled costs are not subtracted twice. Unknown pricing reserves the reported remainder until billing settles. Failed verification or exhausted credit prevents dispatch.
- Provider mode ignores local monetary allowances and model/image price ceilings. Authentication, idempotency, queue/rate/concurrency, output, file and storage limits remain enforced. The authenticated UI shows the key budget, remaining credit and check time, with a read-only refresh. CLI plans work without a local amount in provider mode and remain network-free by default.
- Updated excluded local configuration atomically, preserving the credential and every unrelated setting byte-for-byte. Private file permissions remain 0600. Read-only metadata confirmed a USD 9.90 total limit and USD 9.845606165 remainder before any image generation. No credentials or session tokens were printed.
- Full local verification passes Ruff/check/format, mypy, 121 backend tests, generated contract, frontend format/types, 5 Vitest tests, production build and 7 browser scenarios with one intentional desktop skip. All 64 image/attachment/comparison/migration/provider-budget checks pass in the Linux ARM64 check container without network, as a non-root user with read-only source/root and dropped capabilities.
- The real loopback services were restored with SQLite/history preserved. The owner browser session expired during implementation; the correct application tab is prepared for normal sign-in. No authentication bypass or image generation occurred. The required live-image gate and draft PR remain open pending that sign-in and actual output verification.


## 2026-10-27: M4 live image exit gate verified

- The owner signed in again through the normal application UI. Submitted exactly one dedicated image request with `qwen/qwen-image-2.1-turbo` through Alibaba Cloud Int., using advertised 1K/1:1 settings and one output under the shared provider key budget.
- The job succeeded in 13,045 ms. Provider usage recorded 19 input and 4,175 output tokens, with actual cost USD 0.0184. The ledger settled 18,400 micro-USD and released its conservative 36,800-micro-USD reservation. No unknown charge or outstanding reservation remains, and no retry was sent.
- Downloaded the output through the authenticated browser and decoded the actual WebP: 28,602 bytes, 1024 by 1024 pixels, without EXIF/ICC/XMP. Its checksum matches the persisted private asset. Reload preserved the original completed job, cost and image, with exactly one image job in a read-only database check.
- Saved sanitized numeric/status evidence and the actual screenshot/download in excluded artifacts. Public documentation does not include prompts, credentials or session tokens. The live key budget remains shared across modalities; no image-specific monetary allowance was introduced.
- Fixed a dark-mode contrast defect observed in the real image card by defining the existing surface/border/text/muted theme tokens. Actual browser inspection confirms dark surfaces with readable light text. Frontend formatting/types, all 5 Vitest tests and production build pass; the existing non-failing bundle-size warning remains.
- CI run 40493416169 passed on provider-budget source `552aa613312f5326294d6076359a6be539e6942d`, which already passed 121 backend tests, 7 browser scenarios and 64 restricted Linux ARM64 checks. Final browser/CI integration checks follow the presentation correction before merge. Production deployment remains pending.

- Additional live verification: after restarting the real backend, the owner session and original completed image remained available. The browser decoded the saved 1024 by 1024 output, with exactly one image job and no outstanding or uncertain charges. OpenRouter subsequently reported USD 9.827206165 remaining after the USD 0.0184 image charge. All 7 final browser scenarios pass (one intentional desktop skip), including authenticated download and reload workflows.


## 2026-10-27: M4 integrated remotely

- PR https://github.com/fpinero/lab-chatbot/pull/5 merged at 2026-10-27T11:19:28Z. Remote merge commit: `0e11f19751fcc4d9231c7f7defa344fe120256a7`. Verified source head: `ca059fd218377c0491f4bb911efacd370fd45398`.
- Final CI run 40494860966 passed on that exact head, including the complete local-verification workflow. No required review or unresolved thread remained. The live image, authenticated download, browser reload and real backend restart exit checks passed before integration.
- Confirmed remote merged state and synchronized local main by fast-forward. The integrated tree matches the verified source. Removed completed M4 work from TODO.md and opened `feature/m5-video-generation` from the integrated main for subsequent work.
- Retained `feature/m4-image-generation` locally and remotely at `ca059fd218377c0491f4bb911efacd370fd45398`. Earliest retention end is 2026-11-03T11:19:28Z. Automatic branch deletion is disabled; no cleanup is scheduled or authorized.
- M4 is complete. The live local application remains available with the original saved image and shared provider budget. Video implementation, production containers and deployment remain pending; no production release occurred.


## 2026-10-27: Mobile usage review and Pixel priority

- The owner identified Google Pixel 10 Pro as a frequent-use device. Added explicit Chrome/Android physical-keyboard, rotation and enlarged-text validation to the pending M6 queue.
- Read-only inspection of the authenticated local chat confirmed no document-level horizontal overflow at 412 by 915 and 360 by 430 CSS pixels. The ordinary-height composer and 44-pixel Send button fit within the 915-pixel viewport. Mobile navigation opened and closed with keyboard activation. No generation or paid request was submitted.
- At 360 by 430, the composer is internally scrollable and Send initially falls below its visible area. This is a concrete remaining mobile ergonomics issue; the previous reduced-viewport browser assertion checked result attachment, not persistent Send visibility. Do not describe it as verified Android-keyboard behavior.
- Existing CI includes mobile chat/history, comparison and image workflows at 360 pixels. This additional inspection uses desktop Chrome viewport emulation, not a real Pixel or Android soft keyboard. Saved captures remain in ignored artifacts, and the browser viewport was restored. No application source changed during this review.


## 2026-10-27: Owner-requested deployment preparation

- The owner explicitly authorized preparing manifests, scripts and local deployment configuration now, then stopping before actual publication/deployment. Created `feature/k8s-preparation` without changing main or discarding earlier work. This is an explicit sequencing exception for preparation, not completion of M5/M6/M7 or authorization to continue past the stop point.
- Read every supplied reference file. Preserved the working Traefik Ingress annotations/class and the labchatbot hostname/namespace. Added seven Kustomize resources with a single Recreate replica, private PVC, least-privilege service account, read-only/non-root runtime and local health probes. No certificate issuer or shared infrastructure change is included.
- Added a pinned multi-stage ARM64 image and loopback mock-only Compose with a named volume. An actual local container smoke check passed without network: synthetic authenticated text/image history, private download, restart persistence and production startup. The process ran as UID 10001 with read-only root and dropped capabilities. An isolated Compose project also started successfully with a private synthetic hash; only its disposable resources were cleaned up.
- Added a read-only default release planner and explicit namespace/Secret/publication/deployment/rollback phases. Production tags derive from live state, registry ambiguity fails closed, publication receipts verify source/platform/digest, a renewable Kubernetes Lease excludes concurrent releases, and Deployment replacement uses resourceVersion compare-and-swap. The diff helper returns field paths without live values. No production write phase was executed.
- Prepared ignored k8s/.env and private/deploy files with restrictive permissions. Reused the existing provider key and owner hash without printing or uploading them, kept provider-controlled shared spending, generated a private backup-encryption key, and left RELEASE_READY and ORIGIN_TLS_VERIFIED false. The root local environment was preserved. Reference examples are now excluded from both Git and Docker.
- Installed an isolated checksum-verified kubectl 1.25.16 and pinned kubeconform 0.7.0 under private/tools, leaving the system client and cluster unchanged. Local strict schema validation passed for all seven resources against Kubernetes 1.25.6. Read-only planning confirmed no application Deployment and selected tag 1. Server admission/diff remains a later staged check because the namespace does not exist.
- Added authenticated encrypted offline SQLite/file snapshots and restoration into a new directory only. Regression checks cover round-trip data, re-backing up a restore, tamper rejection, traversal rejection and destination aliases. No real local or production data was restored or replaced.
- Deployment regressions cover tag parsing with registry ports, genuine NotFound, forbidden/timeouts, immutable collision/reuse, lock exclusion/expiry/loss, baseline drift, single CAS writes, architecture/source mismatch, default no-write phases and redacted diffs. The first full pass completed 158 backend tests, 5 frontend tests and 7 browser scenarios (one intentional desktop skip), then its source-fingerprint guard correctly refused the final receipt because files changed while verification was running. Final frozen-source evidence is recorded separately in ignored artifacts/k8s-preparation-verification.log and artifacts/preparation-verification.json.
- Added isolated browser-test ports so verification leaves the owner's normal loopback app running. Documented the staged commands, private prerequisites, origin TLS distinction, local-path limitations, safe rollback and recovery in English. Production namespace/Secrets/Lease/workloads, registry publication, origin TLS and real edge checks remain pending.


## 2026-10-27: Brand monogram favicon

- Converted the existing green Georgia L monogram into self-contained SVG outlines and a transparent ICO fallback at 16, 32 and 48 pixels. The vector needs no installed browser font, external service or font download.
- Linked both icons from the HTML entry point through Vite's asset pipeline. Production builds emit hashed asset URLs under the existing authenticated application's public assets mount, so no root favicon route, Docker COPY change or Kubernetes change is needed.
- Frontend formatting/types and production build pass. Verified both development responses and compiled FastAPI delivery with 200/image MIME types and exact asset bytes. The SVG contains only paths, the ICO includes all three sizes, and private API reads remain guarded. Saved a local preview and sanitized verification metadata under ignored artifacts.
- The favicon is prepared locally for the next deployment. No image was published and no Kubernetes resource or production site was changed. The deployment-preparation stop boundary remains in force.

## 2026-10-27: Local development launchers

- Added executable root start-dev.sh and stop-dev.sh wrappers for FastAPI and Vite. Startup explicitly reads the private local environment, verifies configuration, starts both services in isolated process groups with source reload, waits for readiness and prints loopback URLs. The optional private pinned Node runtime leaves system Node unchanged.
- Repeated startup reuses healthy managed services. Private process signatures, process-group checks and a checkout-scoped operation lock prevent accidental duplicate launches and unrelated-process shutdown. Startup failures clean up newly launched services; shutdown preserves data and private logs. Backend credentials are excluded from the frontend launcher environment.
- All 172 backend tests passed, including 12 new launcher safety/configuration regressions. Ruff checks/formatting, Bash syntax and Git whitespace checks passed. Isolated real-process verification covered unmanaged port conflicts, Node preparation, API proxying, repeated startup, stop/restart, data preservation and cleanup after a failing frontend.
- Verified the previous local services belonged to this checkout and had no active generations before handing them over. Default startup, repeated startup and stop/restart passed with the existing private configuration; persisted conversation, run, image, asset and session counts remained unchanged. The managed application is running on http://127.0.0.1:5173 with FastAPI on http://127.0.0.1:8000. No generation, registry publication or Kubernetes write was performed.

## 2026-10-27: Preparation PRs integrated into main

- The owner explicitly authorized merging every open PR into main. Integrated the dependent PRs in order, retargeting the favicon and development-launcher PRs to main after their prerequisites merged. Every source head passed CI, and no requested review or unresolved thread remained. Used the configured merge-commit method without deleting branches.
- PR https://github.com/fpinero/lab-chatbot/pull/6 merged at 2026-10-27T15:38:52Z as `134789e81389a4752d344a3a2ba2442664d7069a`. Source branch `feature/k8s-preparation` remains at verified head `ff95d06fdf11907363a28e88e39025b38b02b746`; CI run 40507609126 passed. Earliest retention end: 2026-11-03T15:38:52Z.
- PR https://github.com/fpinero/lab-chatbot/pull/7 merged at 2026-10-27T15:39:54Z as `0b9a9fcfeece16c65ad0ff230d895ed0976d26ca`. Source branch `feature/brand-favicon` remains at verified head `c92b1db4e7257c666f6b6a219d382f17ce64744e`; CI run 40527980915 passed. Earliest retention end: 2026-11-03T15:39:54Z.
- PR https://github.com/fpinero/lab-chatbot/pull/8 merged at 2026-10-27T15:42:33Z as `8cda9ffc35df553d8dc98eee9afa6ab7e2ad2eda`. Source branch `feature/dev-server-scripts` remains at verified head `36341979bba8af0c9267e4d526196281ba5f2c86`; CI run 40531497577 passed, including 172 backend tests, 5 frontend tests and 7 browser scenarios with one intentional desktop skip. Earliest retention end: 2026-11-03T15:42:33Z.
- Verified each remote merged state and exact source-tree equivalence after integration. Fast-forwarded local main to the final remote merge. Automatic branch deletion remains disabled; all source branches are retained locally and remotely, and no cleanup is scheduled.
- The local frontend, backend and API proxy remained healthy during integration. No paid generation, registry publication or Kubernetes write occurred. Main is the source for the later staged deployment; integration does not complete the pending application milestones or verify production prerequisites. Keep release readiness and origin TLS gates closed until the exact integrated source and deployment prerequisites are verified.

## 2026-10-27: First K3s release checkpoint

- The owner authorized deployment to the existing K3s cluster. The final main CI run 40534352261 passed. Re-ran the full exact-source preparation gate on main `c7d42b2d92eeaabc94e24047f5f79c3abe7ed543`, including 172 backend tests, 5 frontend tests, 7 browser scenarios with one intentional skip, schemas, Compose and an actual ARM64 container with restart/persistence and production-startup smoke checks. No paid generation was submitted.
- Created only namespace `labchatbot` and its private application Secret in explicit context `orc-k3s`. Credential values were neither printed nor written to public artifacts. All seven desired resources passed strict schemas and real server-side dry-run; the reviewed diff contains field paths only. No Deployment, Service, Ingress or PVC exists yet.
- Verified the restricted OpenRouter key through its read-only endpoint: fixed shared limit USD 9.9 and remaining USD 9.827206165. Application configuration preserves provider-controlled spending without modality allocations.
- Verified the GitHub source repository is public and scanned the exported image filesystem against the actual provider key and owner hash; neither credential nor private configuration was present. These checks resolved an initial automatic publication-review rejection about unconfirmed artifact visibility.
- Published `fpinero/lab-chatbot:1` at 2026-10-27T17:40:09.111609+00:00 using the real namespaced release Lease. Immutable digest: `sha256:8caa54eaf576c5fa7aeb637fdc3cd4eb3b529c9023ed08a74dc7230307a97f37`; source fingerprint: `d4942de9497a41a6e7037da1b1463222d0c669d083f9bfa4e0ecffdd11c52a73`. Verified remote source/platform labels, public repository visibility and anonymous manifest retrieval at that exact digest. Rechecked that the Deployment remains absent; the next production-derived tag is still 1 and its matching receipt must be reused.
- Public HTTPS currently reaches a Cloudflare-fronted 404. A diagnostic handshake to the Kubernetes control-plane address presents a generated Traefik certificate without the application hostname; this does not establish the DNS record's actual origin or Cloudflare SSL mode. Requested those settings from the owner and left ORIGIN_TLS_VERIFIED=false. RELEASE_READY=true reflects the verified intended source; it does not satisfy the independent origin gate.
- Rollout, public owner sign-in, authenticated reads, actual production restart/persistence and mobile verification remain pending. Published receipts, exact-source evidence and the sanitized checkpoint are under ignored artifacts. Keep the verified release checkout on the original clean main until this first release is deployed; merge this bookkeeping update afterwards so documentation changes do not invalidate the already-published source fingerprint.

## 2026-10-27: First K3s deployment verified

- The owner explicitly confirmed Cloudflare Full mode, proxied origin `141.145.211.128` and the existing default self-signed Traefik certificate, matching mouse-desktop. Recorded that intended configuration and enabled the private origin gate without claiming Full (strict), public-CA trust or origin hostname validation. No Cloudflare, Traefik, certificate issuer or shared application setting was changed.
- Deployed `fpinero/lab-chatbot:1@sha256:8caa54eaf576c5fa7aeb637fdc3cd4eb3b529c9023ed08a74dc7230307a97f37` at 2026-10-27T17:53:27.283600+00:00 from verified main `c7d42b2d92eeaabc94e24047f5f79c3abe7ed543`, fingerprint `d4942de9497a41a6e7037da1b1463222d0c669d083f9bfa4e0ecffdd11c52a73`. Previous image: none. Real server admission, scoped release Lease, immutable receipt/platform checks and first Deployment creation succeeded; the pod became ready on vm-node-one and the 10 GiB local-path PVC became Bound.
- Public HTTPS and direct-origin diagnostics returned 200 for the application and health routes. Session, conversation and image-job reads returned 401 without credentials on both paths, with no-store and no cached private response. Production/OpenRouter mode, compiled bundles and favicon responses passed. Public TLS validation remained enabled; only explicitly labeled, credential-free origin diagnostics accepted the owner-confirmed self-signed certificate.
- Observed normal owner sign-in in Chrome and authenticated model catalog/shared budget display. A real controlled pod replacement preserved the same PVC, a uniquely created private test file, SQLite integrity/schema and record counts, including the one existing owner session. Removed only the created test file. Reloading the live browser still showed the authenticated workspace. No generation was active during restart and no user data was deleted.
- Inspected the production workspace at 412 by 915 CSS pixels: no horizontal overflow, Send visible and 44 pixels tall. Restored the browser viewport and left the signed-in application open. This is browser emulation, not a physical Pixel or Android keyboard test; the existing reduced-height ergonomics work remains in M6.
- No paid generation was submitted. The shared provider limit remains USD 9.9, with the browser reporting USD 9.827206 remaining after rounding. Production uses a new persistent volume; local history/media were not migrated or replaced. Actual later-release CAS updates, rollback, representative production media recovery and remaining modalities stay in TODO.md.
- Exact publication/deployment receipts, the owner-confirmed origin mode, edge/origin statuses and real persistence evidence remain under ignored artifacts and k8s/release-state.local.json. This first application release does not complete every pending application milestone. Subsequent releases must derive tag 2 from the live version and re-run the exact-source gate after any source change, including these documentation updates.

## 2026-10-27: Mobile reading and model discovery feedback

- The owner supplied a real phone screenshot after a Nemotron response and deferred mobile implementation to the next session. The screenshot shows limited response-reading space alongside a large persistent composer, a separate attachment row and detailed response/composer metadata. This is real-device usability feedback beyond the earlier empty-workspace viewport check.
- Source inspection confirms the mobile composer can occupy up to 52dvh and contains the active Stop control. Recorded an optional device-local collapse-after-accepted-send preference, a compact expandable input, an integrated attachment control and a review of secondary metadata. Acceptance preserves cancellation, keyboard/IME behavior, recoverable drafts and attachments, and physical Pixel validation with a representative long answer.
- Recorded searchable model selection by case-insensitive name/publisher/ID substring, including Nemotron under the NVIDIA prefix, with explicit accessible selection and separate publisher presentation. The existing native selector has no application search field.
- Updated pending M6 work and next-session priorities only. Verified the documentation diff and branch isolation; application code, credentials, production resources and provider spending are unchanged. No implementation or deployment was performed for this feedback.

## 2026-10-28: Refined mobile composer plan

- The owner requested a plan centered on two changes: relocate the live OpenRouter/provider-retention disclosure to the sidebar near Usage, and place Attach at the lower left of the prompt frame with the shorter Send label at the lower right. Recorded these as the first proposed implementation pass, before evaluating more extensive folding behavior.
- Inspected the current workspace, shared attachment picker, response metadata, mobile CSS and existing browser assertions. The notice and picker/limits occupy separate composer blocks; the active Stop control is inside that same composer. Planning explicitly preserves cancellation, upload validation/feedback, descriptive accessible names and touch targets. Sidebar privacy must not depend on a successful usage request.
- Proposed follow-up evaluation of a smaller growing input, optional device-local collapse after accepted submission, and secondary metadata/settings in accessible details. The model-search requirement remains pending. Acceptance compares actual response-reading space using long answers and includes physical Pixel keyboard validation separately from emulation.
- Updated pending tasks only on the existing planning branch. Whitespace/style and file-scope checks confirm changes are restricted to TODO.md and this append-only log. No application code, production resource, credential or provider spend changed.

## 2026-10-28: Compact mobile chat and searchable models verified locally

- The owner authorized all proposed UI improvements and requested progressive local Pixel 10 review before deployment. Created `feature/mobile-composer-and-model-search` from the preserved planning branch. Production remains version 1; no registry publication, Kubernetes write or paid provider generation was performed for this change.
- Moved the shared live/simulated provider disclosure to a named Privacy section below Usage, independent of usage-request success, and removed duplicate form notices. A persistent Simulated badge keeps mock mode clear. Chat now has a growing input with Attach/Options/Send in one frame, short visible labels, full accessible names and 44-pixel controls. Limits, context/pricing and generation settings remain available under Options; comparison/image upload behavior is preserved.
- Added an opt-in, device-local boolean preference to fold the mobile composer only after acceptance. Desktop remains expanded. Hide/Write and streaming Stop remain accessible; typing during a pending acknowledgement, upload failures, rejected submissions and unknown dispatch preserve drafts, files and idempotency. Inline saved-input editing preserves immutable context/attachments, restores an unrelated prior draft on cancel/acceptance, and never dispatches merely by opening the editor.
- Added an accessible chat model combobox with explicit selection, case-insensitive name/publisher/ID matching, publisher details, favorites, arrow navigation and Escape. Nemotron matches beneath the NVIDIA prefix. Search and mode/navigation changes do not generate. Implementation follows the [WAI combobox pattern](https://www.w3.org/WAI/ARIA/apg/patterns/combobox/).
- Mobile response metrics fold under Details while cost/unknown billing remains visible. Streaming respects a reader who scrolls away from the bottom. Added Chrome's [interactive-widget resize option](https://developer.chrome.com/blog/viewport-resize-behavior) while preserving safe-area settings; actual Android keyboard behavior is still a physical-device check.
- In Chrome at 412 by 924 CSS pixels with the same synthetic long answer, measured the original reading area at 426.8 pixels, the compact version at 677 pixels and the folded version at 741 pixels. Inspected the real local browser progressively. The separate mock preview uses http://localhost:25174 with synthetic data/credentials and its own cookie host, distinct from the normal 127.0.0.1 application.
- Full local verification passed: 172 backend tests, 15 frontend tests and 10 browser workflows with one intentional desktop skip, including types, formatting, contracts and production build. New regressions cover Pixel search/discovery, mobile cancellation, stored preference/reload/desktop independence, Shift+Enter/IME, streaming scroll position, failed/retried submissions, concurrent draft typing, compact uploads and real saved-attachment editing. Checked reduced-height and landscape layouts. Initial browser failures were ambiguous test selectors and were corrected before the final full pass.
- Screenshots and sanitized logs remain in ignored artifacts, including mobile-compact-pixel.png and mobile-final-verification.log. Removed completed implementation work from TODO.md and retained physical Pixel keyboard/enlarged-text review, remaining M6 work and the owner-directed next release as pending. Local review is ready; this does not claim a production rollout of these changes.

- Follow-up polish: Options now dismisses on outside interaction or prompt focus so it cannot obscure reading after composing. Its additional regression passes; the final frontend pass has 16 tests, 10 browser workflows, type/format checks and production build. Backend/contracts remain unchanged from the full 172-test pass. The private preview also exposes an explicitly simulated NVIDIA/Nemotron choice for local search review. No live provider request or deployment was added.
