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

## Dedicated images

Checked on 2026-10-27 against the official [Image API guide](https://openrouter.ai/docs/guides/overview/multimodal/image-generation), [generation reference](https://openrouter.ai/docs/api/api-reference/images/generate-an-image), [model catalog](https://openrouter.ai/docs/api/api-reference/images/list-image-generation-models), [endpoint reference](https://openrouter.ai/docs/api/api-reference/images/list-endpoints-for-an-image-model) and [OpenAPI schema](https://openrouter.ai/openapi.json).

The dedicated family uses `GET /images/models`, `GET /images/models/{author}/{slug}/endpoints` and `POST /images` under the fixed `/api/v1/` origin. Endpoint descriptors, rather than the model-level capability union, define accepted options. Provider tags pin routing with fallbacks disabled. Pricing lines identify billable dimensions, units, cost and optional variants. Estimates conservatively include known image/request lines; unknown dimensions require an approved allowance.

The documented buffered response carries `data[].b64_json`, optional `media_type` and optional usage/cost. Outputs are never interpreted as HTML/SVG or retrieved through arbitrary URLs. The adapter bounds the received response and does not retry generation POSTs. Optional generation headers are persisted immediately; no unsupported polling/cancellation endpoint is invented. Models requiring chat-based image output are excluded from this dedicated adapter until separately verified. Fixtures use synthetic identifiers and small generated raster bytes. No approved live image has run yet.
