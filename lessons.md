# Implementation lessons

## 2026-10-26: Structured assertions and shared owner history

- Inspect parsed SSE fields when asserting whether content was emitted. Searching a whole serialized event for a short substring can accidentally match an unrelated metadata field.
- Desktop and mobile browser contexts intentionally share one server-side owner history. Give test conversations distinct titles instead of assuming an empty or device-local list.

## 2026-10-27: Parser limits and streaming middleware

- macOS can reject RLIMIT_DATA despite an unlimited value from getrlimit. Apply the tested address/data limits on Linux; document the platform difference and retain byte, CPU and timeout guards on macOS.
- Place streaming upload limits inside the authentication middleware so parser exceptions are handled at the request boundary and temporary files are closed. A forged Content-Length test caught an otherwise hidden 500 response.
- Validate combined attachment size again when building saved context. Independent valid upload batches must not bypass the submission ceiling.

## 2026-10-27: Deterministic asynchronous verification

- A browser click completes before an asynchronous logout request necessarily finishes. Wait for the signed-out UI before asserting that private downloads are denied.
- Verify global concurrency by holding occupied slots behind an explicit synchronization gate. Fixed sleeps and minimum queue-delay thresholds can become flaky when database or catalog work takes longer.


## 2026-10-27: Deployment preparation and backup recovery

- Resolve backup destination parents before comparing against the live data directory. A symlink alias must not place staging/archive files inside the directory being copied.
- Test backup, restore and backup again. Archive-control metadata must not become inconsistent application content on the second snapshot.
- A release verification fingerprint must be computed for frozen public sources. Edits during a build must invalidate the evidence rather than certify a different final tree.
