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
