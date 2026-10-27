# Testing

Run `scripts/verify-local.sh` with the pinned toolchain. Backend coverage includes real ASGI routing, session rotation/expiry/logout, hashed-token persistence across restart, additive generic policies, origin/CSRF checks, forwarded-header forgery, persistent throttling, received-body limits and private-route denial.

Synthetic RSA tokens exercise JWT signature, issuer, audience, expiry, owner matching and cached JWKS rotation without external network calls. Production tests check secure cookie attributes, invalid configuration and absence of mock routes. Public policy tests use unrelated synthetic configuration. Real deployment policy fixtures remain excluded and are tested separately by the operator.

Frontend tests cover sign-in gating, in-memory CSRF, deliberate submission and failed-request draft preservation. Playwright uses actual loopback servers and an isolated temporary database, checking sign-in, preview, reload, mobile navigation and logout on desktop and 360 px screens. Inspect screenshots under ignored `artifacts/`; CI retains browser evidence for seven days.

No default test contacts OpenRouter. Live checks require restricted credentials and the approved spending policy: the verified fixed key budget in provider mode, or explicit local allowances in application mode. Mock success never establishes provider or account availability. Container restart, restore and real ingress checks belong to later milestones.

Text tests add catalog freshness/throttling, strict capability checks, immutable model-repeat snapshots, received SSE framing, safe Markdown, partial failures, cancellation, idempotency conflicts/tombstones and concurrent budget reservations. Unknown usage and restarts retain uncertain charges. HTTP mocks verify fixed provider origin, bounded frames, Decimal costs, key restrictions, safe GET retries and absence of generation POST retries.

Browser coverage now follows sign-in, streaming chat, saved history, repeating with another model, logout and a reduced 360 by 430 viewport as a keyboard-size proxy. This is emulation, not evidence from a physical phone keyboard. The opt-in live command is separate and follows the selected server spending policy.

Attachment tests execute the real subprocess against generated PDF/DOCX/text/CSV/image fixtures. They check extracted context, WebP bytes reaching the provider adapter, metadata removal, encrypted/scanned documents, unsafe ZIP features, MIME/path rejection, actual streamed limits despite forged Content-Length and reference-aware cleanup. These are local extraction tests, not live provider evidence.

Comparison tests assert identical request messages, no candidate contamination, combined-budget atomicity, compatibility rejection before any paid dispatch, independent failure/retry, global concurrency and continuation without another charge. A populated M2 database is upgraded to verify that history and settled usage remain linked. Browser tests upload an image plus text, compare three models, reload saved results and continue into chat on desktop and 360 px mobile. Mode changes and continuation must not dispatch generation.

Image tests exercise dedicated endpoint routing, pinned provider capabilities, absence of POST retries/redirect following, output byte/MIME/raster validation, idempotency/tombstones, authenticated download, missing usage, uncertain submissions, shared chat/image concurrency, reference cleanup and stale catalogs. Recovery tests cover both queued work and a simulated hard restart after submission. Existing assets and sessions are read through a new application instance. Browser tests change image settings without dispatch, preserve mode drafts, generate explicitly, reload output and verify download denial after logout. These use deterministic fixtures, not live generation.

The opt-in image CLI has a network-free default plan and requires an approved spending policy before execution. Provider mode needs no preset local monetary amount. Actual live image evidence remains a mandatory incomplete M4 gate when credentials/budgets are absent. Full production-container restart/restore and edge checks are separate later gates.

## First live browser text evidence

On 2026-10-27, one authenticated interactive request used `mistralai/mistral-nemo` through OpenRouter with a 32-token output ceiling. It completed through DekaLLM with 9 input and 3 output tokens. Reported provider cost was USD 0.000000252; conservative ledger rounding recorded one micro-USD. Session/history survived reload, with exactly one persisted generation and no outstanding reservation.

This is real browser/provider evidence. It is an ordinary workspace charge and does not establish successful execution of the opt-in CLI's cumulative-verification path. The provider remainder includes this manual cost; application-mode verification planning must also account for it. Sanitized metadata and the browser screenshot stay in ignored `artifacts/live-text-browser.json` and `artifacts/live-text-browser.jpg`. No prompt, response, credentials or session tokens are copied into public evidence. Other live modalities remain unverified.

Provider-budget regression tests use HTTP metadata fixtures and synthetic generation adapters only. They verify fixed restricted limits, external usage, effective remaining credit, explicit refresh, unavailable/exhausted budgets, shared uncertain image/comparison reservations and bypass of local monetary caps and catalog price ceilings. Both CLI plans remain network-free without a local amount in provider mode.
