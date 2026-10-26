# Provider contracts

Checked the official reference on 2026-10-26. These describe API contracts, not account availability or successful paid verification.

- [Model catalog](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties): explicit text output filtering, most-popular sorting, modalities, supported parameters, context and pricing.
- [Chat completions](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion): fixed chat endpoint, selected model, messages and output controls.
- [Streaming](https://openrouter.ai/docs/api/reference/streaming): SSE framing, comments, final accounting and errors inside HTTP 200 streams. The adapter bounds raw frames and handles split UTF-8/CRLF chunks.
- [Provider routing](https://openrouter.ai/docs/guides/routing/provider-selection): required parameters and per-token/per-request price ceilings while retaining the selected model.
- [Current key](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key): verify non-management credentials and an explicit key spend limit without exposing the key response to the browser.
- [Generation metadata](https://openrouter.ai/docs/api/api-reference/generations/get-request-%26-usage-metadata-for-a-generation): reconcile known generation IDs using sanitized cost/token fields.
- [Decimal JSON encoding](https://simplejson.readthedocs.io/en/latest/): preserve exact numeric price ceilings in outbound JSON without binary floating-point currency arithmetic.

Contract tests use synthetic fixtures and HTTP transports. Successful mocks do not establish a working live model, provider or balance.
