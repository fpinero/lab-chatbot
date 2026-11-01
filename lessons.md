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

## 2026-10-28: Upload cleanup and parent busy state

- Suppressing asynchronous results after unmount must also release any busy flag owned by a still-mounted caller. Notify that caller during detachment, then ignore the eventual completion entirely, so an old request cannot clear a newer request's state. Test both immediate cleanup and delayed resolution, including components conditionally removed while their parent remains visible.

## 2026-10-28: Inspect a completed rollout before retrying

- A ready pod and successful Deployment replacement can precede successful public routing. Version 7's first immediate public-root read returned 404, then repeated read-only root/health checks returned 200 with the same deployed image and endpoint. Inspect the deployed receipt, pod, endpoint and public responses before retrying any mutation; do not republish or increment a tag to address a transient health-check failure. The precise cause of this brief 404 was not established.

## 2026-11-01: Measure clipboard feedback layout

- Existing broad button-span rules can change the intrinsic size of a nested status label. Scope spacing for reusable controls and measure the real button before/after success in browser tests; preserving the original label through a CSS pseudo-element avoids extra accessible or textContent labels.

## 2026-11-01: Isolate growing suites without weakening throttles

- Device isolation alone is insufficient when expanded concurrent suites exceed the same owner's real upload window. Give independently heavy suites their own backend/UI/data instances rather than increasing application limits, clearing production-like throttle records or adding timing sleeps. Keep the upload limits exercised unchanged in the final full suite.

## 2026-11-01: Separate content identity from lazy readers

- A new callback reference does not imply changed displayed content. Clipboard feedback for a DOM-backed code block should track the code text independently of its reader closure, so unrelated parent rerenders preserve the timer while real code changes invalidate stale success. Verify this with an actual draft edit in a browser.
