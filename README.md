# Lab chatbot

A private workspace for deliberate model experiments using OpenRouter. Implementation is incremental. The current bootstrap is a local-only, deterministic preview with no provider traffic or credit usage. Production startup is deliberately disabled until secure authentication is implemented.

## Local development

Install Python 3.12.15, Node 24.22.1 (see `.python-version` and `.nvmrc`), npm and [uv](https://docs.astral.sh/uv/getting-started/installation/). Node 24 satisfies the installed Vite engine requirement. Dependency resolutions live in `backend/uv.lock` and `frontend/package-lock.json`.

```sh
uv sync --project backend --locked
npm --prefix frontend ci
```

Run the backend in one terminal:

```sh
uv run --project backend uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run the frontend in another:

```sh
npm --prefix frontend run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to the backend. Both servers bind to loopback. `.env.example` documents safe development values; environment variables are read from the process, and files are never implicitly loaded.

The development preview API is unauthenticated and must remain on loopback. It cannot dispatch a paid request. Do not expose this bootstrap server through a public tunnel or ingress.

## Verification

```sh
cd frontend
npx playwright install chromium
cd ..
scripts/verify-local.sh
```

This runs frozen installs, Ruff, mypy, pytest, generated API contract verification, TypeScript, Vitest, a production build and Playwright desktop/mobile workflows. Screenshots are saved under ignored `artifacts/`. CI performs the same checks and has no deployment step.

The API contract is generated from FastAPI rather than maintained by hand:

```sh
mkdir -p artifacts
uv run --project backend python scripts/generate-contract.py > artifacts/openapi.json
npm --prefix frontend run contract
```

After `npm --prefix frontend run build`, FastAPI serves the compiled frontend on port 8000. API routes are registered before the SPA fallback; unknown `/api/...` routes return JSON 404 responses.

## Privacy and delivery status

Do not commit `.env` files, private operator policies, local notes, conversations, exports, backups or provider credentials. Ignore rules cover these paths. Container packaging will use explicit source paths when introduced. All provider requests will originate on the backend; credentials must never be sent to the browser.

`TODO.md` contains pending milestone tasks. `avances.md` records verified work and repository integration. Mock checks are not live provider evidence. No deployment or paid generation is available at this stage.
