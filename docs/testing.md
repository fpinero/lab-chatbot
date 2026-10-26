# Testing

Run `scripts/verify-local.sh` with the pinned toolchain. Backend tests exercise actual ASGI routing through HTTP, mock isolation, sanitized validation errors and production startup rejection. Frontend tests cover deliberate submission and draft preservation on failure. Playwright calls the actual backend through Vite at desktop and 360 px mobile widths, asserting visible results and no horizontal overflow.

The generated TypeScript contract must match the FastAPI schema. The verification script regenerates it and rejects changes relative to the reviewed tree. Browser artifacts stay ignored locally and CI retains screenshots for seven days.

No test in the default suite contacts OpenRouter. Live checks will require an explicit restricted credential and approved numeric spending allowance in a later milestone. A mock success never establishes provider or account availability.
