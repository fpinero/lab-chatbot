# Lab chatbot

A private workspace for deliberate model experiments using OpenRouter. The application includes secure sign-in, streaming chat, screenshots/documents, model comparisons, image jobs, persistent history and transactional spend reservations. The OpenRouter text/vision and dedicated image adapters are implemented. Authenticated local browser text and image flows are live-verified; the remaining paid modalities are pending. No paid call or deployment is performed by the default test suite.

## Local development

Install Python 3.12.15, Node 24.22.1 (see `.python-version` and `.nvmrc`), npm and [uv](https://docs.astral.sh/uv/getting-started/installation/). Node 24 satisfies the installed Vite engine requirement. Resolutions live in `backend/uv.lock` and `frontend/package-lock.json`.

```sh
uv sync --project backend --locked
npm --prefix frontend ci
uv run --project backend python scripts/configure-local.py
```

The setup script prompts for a passphrase and writes an Argon2id hash to ignored `private/owner.hash`. It never prints the passphrase. Once dependencies and the owner hash are ready, start both development servers from the repository root:

```sh
./start-dev.sh
```

The launcher waits for FastAPI and Vite, prints their addresses, and leaves them running in the background with automatic source reload. Open `http://127.0.0.1:5173` and sign in. Stop both services with:

```sh
./stop-dev.sh
```

The launcher explicitly loads ignored `.env.local` as backend configuration, without executing shell commands or printing credentials. File settings override inherited settings, and `private/owner.hash` is detected when no hash setting exists. Vite receives no backend credentials from this file. Production configuration is refused. The frontend origin and API proxy follow the selected ports. Both services bind to `127.0.0.1`, with FastAPI on port 8000 by default.

Repeating `start-dev.sh` reuses healthy managed servers. Occupied ports belonging to unmanaged processes cause an error without stopping those processes. `stop-dev.sh` verifies recorded process identities before stopping their process groups, including reload workers. It preserves SQLite, files and logs. Private logs and process metadata are stored in ignored `private/dev/`. SQLite, hashed sessions and throttle counters persist under ignored `data/`; Alembic upgrades the database during startup.

When the pinned Node version is unavailable, the launcher can use npm to prepare it once under ignored `private/tools/node-runtime/`, leaving system Node unchanged. Use `--no-install` to disable that preparation, or set `DEV_NODE_BIN` to an existing pinned Node binary. Dependencies still require the initial installation commands above.

Optional ports and environment file:

```sh
./start-dev.sh --backend-port 8001 --frontend-port 5174 --env-file .env.local
./stop-dev.sh
```

`DEV_BACKEND_PORT`, `DEV_FRONTEND_PORT`, `DEV_ENV_FILE` and `DEV_STATE_DIR` provide equivalent launcher defaults. Use a separate state directory and data directory for simultaneous isolated instances. Outside these launchers, application settings come from the process environment; `.env` files are not implicitly loaded.

After `npm --prefix frontend run build`, FastAPI can serve the compiled frontend on port 8000. Set `APP_ORIGIN=http://127.0.0.1:8000` when using that origin. API routes precede the SPA fallback and unknown API paths return JSON errors.

## Authentication configuration

`AUTH_MODE=password` requires `AUTH_PASSWORD_HASH_FILE` or `AUTH_PASSWORD_HASH` containing an owner Argon2id hash. The setup tool requires at least 16 characters. Use a unique strong passphrase and keep the hash private.

`AUTH_MODE=access` requires `ACCESS_ISSUER` (the official Cloudflare Access team origin), `ACCESS_AUDIENCE` and `ACCESS_OWNER_SUBJECT`. Configure an explicit owner identity allow policy on the entire host. The backend validates the signed JWT, issuer, audience, expiry and selected subject on login and every private API request. An email header alone is never trusted. See [Cloudflare JWT validation](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/).

An optional private operator policy may be mounted through `AUTH_POLICY_FILE` alongside either secure identity mode. Production requires a read-only policy file. Its deployment values and fixtures must remain outside Git and container layers. Local policy testing requires explicit configuration and a loopback development origin. Policy-only authentication is rejected in production.

Production settings require `APP_ENV=production`, an HTTPS `APP_ORIGIN`, `PROVIDER_MODE=openrouter` and secure identity. Mock mode, disabled authentication, missing Access configuration and placeholder credentials are rejected. This startup validation does not establish production readiness: provider adapters, release gates, container validation and real infrastructure verification remain pending.

Sessions use opaque random cookies with only a hash stored server-side. Production cookies use `__Host-`, Secure, HttpOnly, SameSite=Lax and Path=/ without Domain. Default idle expiry is 30 minutes; absolute expiry is 12 hours. Writes require both an exact allowed Origin and the session CSRF token. Login also validates Origin. All private API families are guarded before route handling, including unknown paths and event streams.

Forwarded addresses are ignored by default. `TRUSTED_PROXY_NETWORKS` accepts a JSON list of explicitly verified proxy CIDRs. Keep Uvicorn proxy rewriting disabled so the application can validate the actual peer. A persistent per-address/global throttle and bounded password verification concurrency protect sign-in. Do not enable broad CORS or request-body/credential logging.

## Verification

```sh
cd frontend
npx playwright install chromium
cd ..
scripts/verify-local.sh
```

This runs frozen installs, Ruff, mypy, pytest, generated contract verification, formatting, TypeScript, Vitest, production build and Playwright desktop/mobile workflows. Browser tests use an isolated temporary database and synthetic credentials, without changing local owner settings. Screenshots stay in ignored `artifacts/`. CI runs verification and has no deployment step.

Regenerate API types after a schema change:

```sh
mkdir -p artifacts
uv run --project backend python scripts/generate-contract.py > artifacts/openapi.json
npm --prefix frontend run contract
npm --prefix frontend run format
```

## Privacy and status

Keep `.env` files, private policies, local notes, credentials, conversations, exports and backups outside Git. Container packaging uses explicit source paths. Provider credentials must remain on the backend.

`TODO.md` contains pending work. `avances.md` records verified work and integration. Mock checks do not establish provider or account availability. See [Kubernetes preparation](k8s/README.md) for the local container, private deployment configuration, read-only planning and explicitly executed release phases. Preparation does not deploy or establish production readiness; remaining live modalities, application milestones and staged production checks remain pending.

## Text chat and spend controls

The text workspace now supports streaming, stop, explicit repeat with a selected model, edits as new immutable runs, search/rename/delete, favorites and authenticated Markdown/JSON exports. History and sessions survive application restart. The mock catalog is visibly simulated; live models are discovered server-side from OpenRouter with ranking provenance and a 15-minute cache. Stale catalogs retain their timestamp. Unsupported parameters and unknown billing dimensions are rejected before dispatch.

The chat model field searches any part of a model name, publisher or ID, so `Nemotron` matches an `NVIDIA: Nemotron` label. Typing filters choices; clicking a result or pressing Enter commits the selection. Escape restores the current selection, and searching never submits a message.

The compact chat composer groups Attach, Options and Send in one frame. Options contains upload limits, generation settings, context/pricing and the optional mobile setting **Collapse after sending on this device**. That setting stores only a boolean in this browser for this origin and never folds the desktop composer. An accepted submission can dismiss the mobile keyboard and leave Write/Stop controls; failed submissions preserve the draft and attachments. Hide also folds manually without clearing a draft. Editing a saved run opens the composer and preserves its saved context/attachments; canceling or accepting the edit restores any earlier unsent draft.

Privacy information appears below Usage in the sidebar, including through mobile navigation. Mobile response statistics are available under Details while actual or unknown cost remains visible. Streaming follows new output only while the reader remains near the bottom. Pixel 10-sized browser checks do not replace testing the physical Android keyboard.

Live mode requires a restricted non-management key through `OPENROUTER_API_KEY_FILE` (recommended) or `OPENROUTER_API_KEY`, and `PROVIDER_MODE=openrouter`. Set `SPEND_CONTROL=provider` to use the fixed total budget already configured on that OpenRouter key across chat, comparisons and media. No request, daily, test or modality allowance is required. The server refreshes the key remainder before reserving each submission, including usage outside this app. The sidebar shows the verified limit, remaining credit and check time. Provider mode ignores local model/image price ceilings; `MODEL_ALLOWLIST` remains optional. The key itself enforces billing limits; local estimates are not guaranteed final prices.

The backward-compatible `SPEND_CONTROL=application` default instead requires approved positive `MAX_REQUEST_USD` and `DAILY_BUDGET_USD`, with separate verification and uncertain-modality allowances. These default to zero. `MODEL_PRICE_CEILING_PER_MILLION` and `IMAGE_PRICE_CEILING_USD` apply only in application mode. The example configuration selects provider control; no actual key or monetary budget is supplied by this repository.

Each new request persists an immutable input snapshot and an idempotency key before dispatch. Transactions reserve conservative input/output estimates using Decimal and integer micro-USD. Provider routing stays within the selected model. Application mode also includes catalog-derived routing price ceilings. Generation POSTs are never automatically retried. Global concurrency is two, with bounded queue depth and a separate submission throttle. Provider costs can still change, so estimates and local guards are not guaranteed billing caps.

Cancellation preserves partial text and may not stop billing. Missing usage, interrupted requests and uncertain outcomes keep reservations. An authenticated billing check can retrieve known generation metadata without creating another generation. Usage records remain after conversation deletion, including an idempotency tombstone so replaying a deleted request cannot spend again.

## Attachments and comparisons

Chat and Compare accept PNG/JPEG/WebP screenshots and PDF, UTF-8 TXT/Markdown, CSV and DOCX documents. Defaults are five files, 10 MiB per file, 25 MiB per upload, 50 PDF pages, 20 megapixels and 100,000 extracted characters per document. Images are normalized to WebP with metadata removed and a visible resize warning above 2,048 pixels per edge. Documents provide locally extracted text; scanned PDFs without selectable text explicitly require another input because OCR is unavailable. Extraction previews are shortened visibly, while submitted context is never silently truncated.

Files remain outside static assets and require authentication. Screenshot input requires an image-capable model; document text works with text models. Context estimates include saved history and output allowance and are approximate. In provider mode, uncertain vision pricing temporarily reserves the remaining shared key budget until billing settles. In application mode, it requires `VISION_REQUEST_ALLOWANCE_USD` within request/daily limits. Prepared provider payloads include base64 overhead and are capped at 32 MiB.

Compare validates two to four models before reserving their combined allowance atomically. Each candidate receives the same immutable context, without another candidate's response. Two global generation slots distinguish queue delay from provider latency. Cards show independent results, actual or unknown cost, usage and errors. Retry requires an explicit click and preserves previous attempts. Continue with this answer creates a normal conversation from that answer without another paid call. Saved comparisons and their files survive reload; switching modes preserves unsent drafts in memory.

Referenced files remain until their conversations are deleted. Shared files survive deletion of only one reference; abandoned uploads expire after 24 hours. The application rejects uploads before its configurable 5 GiB ceiling or low disk space. The parser runs in a disposable process with a stripped environment, timeout, CPU limit on POSIX and 512 MiB address/data limits on Linux. macOS does not enforce those Linux memory limits. This process isolation is not a full operating-system sandbox; container hardening is a later gate.

## Image generation status

Image mode uses the dedicated image catalog and per-provider capability records, cached for 15 minutes with visible timestamps and stale fallback. Controls expose only advertised raster formats, resolution tiers, ratios, quality and counts, defaulting to one image and the smallest advertised tier. References require explicit image-input and reference capabilities. Models available only through another generation API are excluded until a separate adapter is verified; image-input support never implies image generation.

Generate creates a durable local job and reserves spending before contacting OpenRouter. Image jobs share the two global generation slots, queue/rate ceilings, ledger and selected spending policy with chat. Requests pin the chosen provider without silent fallback. Known image/request dimensions produce a conservative estimate; unknown token/megapixel dimensions reserve the remaining shared key budget in provider mode, temporarily blocking further reservations until billing is known. Application mode instead requires an approved `IMAGE_REQUEST_ALLOWANCE_USD`. Its `IMAGE_PRICE_CEILING_USD` only filters advertised per-unit prices.

Successful outputs are decoded, bounded, validated as PNG/JPEG/WebP and saved privately as WebP with metadata removed and dimensions preserved. The default maximum is 20 MiB per output and 20 megapixels, with a 64 MiB provider response ceiling. HTML/SVG, mismatched MIME and URL-only outputs are rejected. The documented dedicated contract uses base64, so this adapter performs no arbitrary output URL retrieval and follows no redirects. Downloads require authentication. Assets expire after `MEDIA_RETENTION_DAYS`, default 30; explicit deletion keeps accounting and idempotency tombstones.

Reload retrieves saved jobs and outputs. Reusing settings does not generate. Unknown cost retains its reservation; an uncertain retry requires acknowledgement of possible duplicate spend. Restart resumes queued work, while already submitted synchronous requests become submission-unknown and are never sent again automatically. The API does not currently expose a verified image status-reconciliation/cancellation contract, so unknown jobs require inspection before deliberate retry.

M4 local checks and one approved live browser image pass. The live check used `qwen/qwen-image-2.1-turbo` through Alibaba Cloud Int., produced a 1024 by 1024 image for USD 0.0184, and verified the private WebP download and saved history after reload. Only one image request was sent. This establishes access to the tested endpoint; other models and modalities still require verification.

## Opt-in live verification

The default suite never contacts a paid provider. A separate command can perform exactly one cheap text request through the application's authenticated API:

```sh
uv run --project backend python scripts/live-text.py \
  --model YOUR_VERIFIED_MODEL_ID
```

Without `--execute`, this only prints a network-free plan. Export `SPEND_CONTROL=provider` in the test process to use the backend's verified key budget without a local amount. An optional `--max-usd` adds a caller-selected cap for that one test. In application mode, configure approved `LIVE_TEST_BUDGET_USD` in both processes, ordinary request/daily limits and `--max-usd`; verification runs reserve against that cumulative allowance. Add `--execute` explicitly to perform the test. Credentials are prompted privately; Access mode can read an already obtained token from excluded `CF_ACCESS_TOKEN_FILE`. `APP_ORIGIN` must reach the application. The CLI never prints credentials, prompts or answers and writes sanitized evidence to ignored `artifacts/live-text.json`.

A separate image command uses the same explicit gates:

```sh
uv run --project backend python scripts/live-image.py \
  --model YOUR_VERIFIED_IMAGE_MODEL --provider YOUR_VERIFIED_PROVIDER_TAG
```

Its default only prints a plan and cannot construct an HTTP client. `--execute` performs one image request with the smallest advertised tier under the selected server spending policy, checks the authenticated download and records sanitized status/cost evidence in ignored `artifacts/live-image.json`. Unknown cost or an incomplete output causes a failed verification result without an automatic retry. Provider mode needs no separate image allowance; application mode retains its explicit allowance requirements.

One authenticated browser text smoke check passed with a restricted provider key and approved limits. It verified a completed response, actual usage/cost, persisted history after reload and exactly one generation. This was ordinary interactive workspace usage, not the opt-in CLI verification path; its cost is included in the provider key usage. Application mode must also include it when planning cumulative test allowances. One live image is also verified, as described above. Live vision/document/comparison verification, video generation, container release validation and deployment remain pending.
