# Testing

Run `scripts/verify-local.sh` with the pinned toolchain. Backend coverage includes real ASGI routing, session rotation/expiry/logout, hashed-token persistence across restart, additive generic policies, origin/CSRF checks, forwarded-header forgery, persistent throttling, received-body limits and private-route denial.

Synthetic RSA tokens exercise JWT signature, issuer, audience, expiry, owner matching and cached JWKS rotation without external network calls. Production tests check secure cookie attributes, invalid configuration and absence of mock routes. Public policy tests use unrelated synthetic configuration. Real deployment policy fixtures remain excluded and are tested separately by the operator.

Frontend tests cover sign-in gating, in-memory CSRF, deliberate submission and failed-request draft preservation. Playwright uses actual loopback servers and an isolated temporary database, checking sign-in, preview, reload, mobile navigation and logout on desktop and 360 px screens. Inspect screenshots under ignored `artifacts/`; CI retains browser evidence for seven days.

No default test contacts OpenRouter. Live checks require restricted credentials and an explicit approved numeric spending allowance. Mock success never establishes provider or account availability. Container restart, restore and real ingress checks belong to later milestones.

Text tests add catalog freshness/throttling, strict capability checks, immutable model-repeat snapshots, received SSE framing, safe Markdown, partial failures, cancellation, idempotency conflicts/tombstones and concurrent budget reservations. Unknown usage and restarts retain uncertain charges. HTTP mocks verify fixed provider origin, bounded frames, Decimal costs, key restrictions, safe GET retries and absence of generation POST retries.

Browser coverage now follows sign-in, streaming chat, saved history, repeating with another model, logout and a reduced 360 by 430 viewport as a keyboard-size proxy. This is emulation, not evidence from a physical phone keyboard. The opt-in live command is separate and requires approved request, daily and cumulative verification budgets.
