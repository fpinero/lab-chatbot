# Lab chatbot

A private workspace for deliberate model experiments using OpenRouter. The application includes secure sign-in, streaming text chat, persistent history and transactional spend reservations. The OpenRouter text adapter is implemented; live provider verification is pending. No paid call or deployment is performed by the default test suite.

## Local development

Install Python 3.12.15, Node 24.22.1 (see `.python-version` and `.nvmrc`), npm and [uv](https://docs.astral.sh/uv/getting-started/installation/). Node 24 satisfies the installed Vite engine requirement. Resolutions live in `backend/uv.lock` and `frontend/package-lock.json`.

```sh
uv sync --project backend --locked
npm --prefix frontend ci
uv run --project backend python scripts/configure-local.py
```

The setup script prompts for a passphrase and writes an Argon2id hash to ignored `private/owner.hash`. It never prints the passphrase. Run the backend from the repository root:

```sh
export AUTH_PASSWORD_HASH_FILE=private/owner.hash
uv run --project backend uvicorn app.main:create_app --factory \
  --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
```

Run the frontend in another terminal:

```sh
npm --prefix frontend run dev
```

Open `http://127.0.0.1:5173` and sign in. Vite proxies `/api` to FastAPI. Both servers bind to loopback. Environment variables are read from the process; `.env` files are not implicitly loaded. SQLite, hashed sessions and throttle counters persist under ignored `data/`. Alembic upgrades the database during startup.

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

Keep `.env` files, private policies, local notes, credentials, conversations, exports and backups outside Git. Container packaging will use explicit source paths. Provider credentials must remain on the backend.

`TODO.md` contains pending work. `avances.md` records verified work and integration. Mock checks do not establish provider or account availability. Live provider verification, packaging and deployment remain pending.

## Text chat and spend controls

The text workspace now supports streaming, stop, explicit repeat with a selected model, edits as new immutable runs, search/rename/delete, favorites and authenticated Markdown/JSON exports. History and sessions survive application restart. The mock catalog is visibly simulated; live models are discovered server-side from OpenRouter with ranking provenance and a 15-minute cache. Stale catalogs retain their timestamp. Unsupported parameters and unknown billing dimensions are rejected before dispatch.

Live mode requires a restricted non-management key through `OPENROUTER_API_KEY_FILE` (recommended) or `OPENROUTER_API_KEY`, `PROVIDER_MODE=openrouter`, and explicitly approved positive `MAX_REQUEST_USD` and `DAILY_BUDGET_USD`. Budgets default to zero. The backend verifies the key's documented type and spend limit before generation. Keep provider-side key limits conservative as well. `MODEL_ALLOWLIST` is a JSON list; `MODEL_PRICE_CEILING_PER_MILLION` filters catalog token prices. No actual key or budget is supplied by this repository.

Each new request persists an immutable input snapshot and an idempotency key before dispatch. Transactions reserve conservative input/output estimates using Decimal and integer micro-USD. Provider routing stays within the selected model and includes price ceilings. Generation POSTs are never automatically retried. Global concurrency is two, with bounded queue depth and a separate submission throttle. Provider costs can still change, so estimates and local guards are not guaranteed billing caps.

Cancellation preserves partial text and may not stop billing. Missing usage, interrupted requests and uncertain outcomes keep reservations. An authenticated billing check can retrieve known generation metadata without creating another generation. Usage records remain after conversation deletion, including an idempotency tombstone so replaying a deleted request cannot spend again.

## Opt-in live verification

The default suite never contacts a paid provider. A separate command can perform exactly one cheap text request through the application's authenticated API:

```sh
uv run --project backend python scripts/live-text.py \
  --model YOUR_VERIFIED_MODEL_ID --max-usd YOUR_APPROVED_REQUEST_ALLOWANCE
```

Without `--execute`, this only prints a plan after validating the configured numeric allowance. Before execution, configure the approved `LIVE_TEST_BUDGET_USD` in both the backend and test process, as well as ordinary request/daily limits. Verification runs reserve against a cumulative server-side verification allowance. Then add `--execute` explicitly. Credentials are prompted privately; Access mode can read an already obtained token from excluded `CF_ACCESS_TOKEN_FILE`. The configured `APP_ORIGIN` must reach the app, including any required edge authentication. The CLI never prints credentials, prompts or answers and writes sanitized evidence to ignored `artifacts/live-text.json`.

Live text verification is currently pending because credentials and approved numeric budgets have not been supplied. Image/video generation, attachments, comparisons, container validation and deployment remain pending milestones.
