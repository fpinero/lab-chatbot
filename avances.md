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
