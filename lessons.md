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

## 2026-11-01: Distinguish continued use from lost history

- A strict snapshot comparison can flag legitimate conversation head/timestamp changes when an owner resumes using the application after backup. Preserve the actual differences in evidence and verify original immutable fields/files, ownership, new-turn ordering, saved context and the corresponding usage entry. Do not erase differences, restore production data or repeat a healthy rollout merely to make mutable conversation metadata equal an earlier snapshot.

## 2026-11-02: Exercise real popover dismissal and complete intercepted reads

- An anchored help card can cover the draft intentionally. Test light-dismiss by clicking an uncovered area, not by forcing a click through the card; retain separate explicit-close, Escape and focus assertions.
- Await in-flight request interception with unrouteAll behavior wait before disposing a browser fixture. A lazily mounted picker can start its limits read after the visible help interaction finishes; suppressing errors or extending the timeout hides the lifecycle problem instead of resolving it.

## 2026-11-03: Keep explicit refresh results distinct from cached fallback

- A cached catalog can remain usable while an explicit provider refresh fails. Preserve the cache but report the manual failure; cache freshness alone must not produce a successful refresh response. Scope pending/success/failure feedback to the operation so a later success clears its own error without erasing unrelated generation failures.
- Derive cooldown metadata and Retry-After from the actual last provider attempt, including automatic reads. A generic 429 delay can disagree with the catalog window. Use relative wait durations and a monotonic client timer, keep server enforcement intact, and test rejected attempts without resetting the window.
- Flush timer-driven React state before clicking a control that becomes enabled in a test. Use fail-fast shell sequencing for verification gates; a later successful command must not mask an earlier formatting failure. Recheck final-added regressions before opening the PR.

## 2026-11-03: Match catalog state lifetime to its owner

- Relative cooldown metadata represents one response at receipt time. Reapplying it after a keyed composer remount restarts a delay that may already have elapsed. Keep catalog request/deadline/feedback state at workspace lifetime and render a disposable button view. Test both an expired wait and a pending response across actual New conversation reconstruction, while retaining the separate full-workspace unmount guard.

## 2026-11-03: Surface current CI evidence before integration

- Confirm completed/success checks for the exact PR head in a separate read-only step before proposing a merge. A background watcher exiting successfully while its output stays in a local log does not expose that updated state to reviewers. Refresh the evidence when the last visible status was still in progress, and preserve the same verified-head merge guard.

## 2026-11-06: Await dependent native event effects in React tests

- Seeing asynchronous state in the DOM does not prove a native event listener registered by a dependent passive effect has been refreshed. Before immediately dispatching synthetic paste after initial limit loading, flush the response and effects with awaited act. Preserve behavioral assertions and avoid arbitrary sleeps or enlarged timeouts that leave the stale-listener race intact.

## 2026-11-06: Select visible controls across mounted modes

- Chat and hidden Compare panels can both contain a System prompt label, and lazy mounting makes label-only browser selectors intermittently ambiguous. Use an accessible role with its exact name to target the visible textbox, preserving the same real UI interaction across device profiles.

## 2026-11-09: Validate instructions independently from attachments

- A ready file supplies data rather than an instruction. Admit a Chat input only when it has specific prompt text, or ready attachments plus non-whitespace System prompt. Apply the same rule to frontend eligibility and server dispatch, and validate repeat/edit against the original saved system instructions rather than current draft settings. Rejected requests must not create a reservation or change stored inputs.

## 2026-11-09: Separate history navigation from saved-input editing

- Cancelling an explicit edit restores its unrelated unsent draft, which is appropriate inside that conversation but inappropriate when selecting history. History navigation must clear editing, pending idempotency state, draft files/text and feedback atomically, then restore only the chosen conversation's settings. Otherwise historical files can influence Send eligibility and Attach remains locked in a mode the owner did not intend.
- Increment the navigation epoch for every history request, not only New conversation, and disable submission/edit/upload while it is pending. Test reversed response order and reopening history from attachment-only editing. Keyed composer reconstruction replaces DOM nodes, so unit assertions must query the current controls after navigation instead of retaining detached elements.
