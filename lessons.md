# Implementation lessons

## 2026-10-26: Structured assertions and shared owner history

- Inspect parsed SSE fields when asserting whether content was emitted. Searching a whole serialized event for a short substring can accidentally match an unrelated metadata field.
- Desktop and mobile browser contexts intentionally share one server-side owner history. Give test conversations distinct titles instead of assuming an empty or device-local list.
