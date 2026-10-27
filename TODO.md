# Implementation tasks

Only pending work belongs here. Each milestone starts after the preceding milestone is verified and integrated remotely. Keep every milestone branch for at least seven days after merge, with no automatic cleanup.

The owner authorized the first staged deployment from integrated main, ahead of the remaining application milestones. Version 1 is deployed and verified at https://labchatbot.nivelepsilon.com using the existing Cloudflare Full/Traefik pattern. Complete the remaining application and operational follow-up work without changing unrelated shared infrastructure.

The owner's next-session priority is mobile reading space and model search, ahead of the remaining modality work. Only the feedback and acceptance criteria are recorded today; implementation is deferred to the next session.

## External verification prerequisites

- [ ] Verify remaining live vision/document/comparison/video flows within the shared provider key budget. Acceptance: sanitized real status/cost evidence and refreshed provider remainder, including usage outside this application.

## M5: Video generation

- [ ] Verify dedicated video catalog, submit/status/content/cancellation contracts. Acceptance: controls derive from documented model capabilities.
- [ ] Persist provider job IDs and implement bounded restart-safe polling. Acceptance: accepted jobs are never resubmitted and unknown submission retains reservation.
- [ ] Implement explicit cancellation and authenticated media/range delivery. Acceptance: restart/retrieval/range tests pass without credential forwarding.
- [ ] Build capability-driven form, status and playback. Acceptance: explicit generation, reload and provider limitations are covered in browser tests.
- [ ] Verify one shortest live clip within approved budget or record concrete provider/access blocker.
- [ ] Integrate M5 with CI, PR, remote merge and branch retention evidence.

## M6: Local release candidate

- [ ] Reduce the mobile composer's resting footprint. Acceptance: use a compact growing text input and integrate a labeled, accessible attachment icon into the input toolbar instead of a dedicated attachment row; keep controls at least 44 px, preserve upload validation and attached-file previews, and make limits/privacy details available without permanently occupying several rows.
- [ ] Add an optional device-local preference to collapse the composer after an accepted submission through Enter or Send. Acceptance: keep desktop behavior independent, release the mobile keyboard after acceptance, leave a compact Write control and an accessible Stop control during streaming, reopen for composing/editing, and preserve drafts/attachments on validation or network failure. Preserve Shift+Enter and IME composition behavior. Verify that the response gains reading space with the real Pixel keyboard closed/open and after reload.
- [ ] Replace the long native model selector with an accessible searchable picker. Acceptance: case-insensitive substring search across model name, publisher label and model ID finds Nemotron even when the label begins with NVIDIA; distinguish model name from publisher, preserve existing compatibility/favorite rules and explicit model selection, and support touch, keyboard navigation and Escape without accidentally submitting a message or changing models while merely typing a filter.
- [ ] Review secondary mobile information for a compact Details disclosure. Acceptance: assess response timing/token metrics, context and pricing against the owner's screenshot; prioritize response reading space while keeping billing, privacy and generation status discoverable. Validate with representative long answers rather than only an empty workspace.
- [ ] Validate custom SQLite URL paths against compiled static locations, including URI/override cases. Acceptance: startup rejects every writable database/data path under public assets before opening storage.
- [ ] Add storage/rate/concurrency limits, sanitized request IDs and local readiness. Acceptance: pressure and bounded queue behavior are tested.
- [ ] Exercise encrypted backup and isolated restore with representative real application history/media during a reviewed maintenance window. Synthetic SQLite/file recovery is covered; production data must not be replaced automatically.
- [ ] Finish themes, focus, keyboard, copy/export, responsive composer and recovery. Acceptance: inspect desktop/360 px screenshots and full browser suite.
- [ ] Prioritize Chrome on Google Pixel 10 Pro for mobile validation. Acceptance: keep message input and Send reachable with the real Android keyboard open, avoid reduced-height internal-scroll dependence, check portrait/landscape and enlarged text, and record physical-device evidence separately from viewport emulation.
- [ ] Run full checks and actual container verification. Acceptance: exact source fingerprint and real results recorded with external limitations explicit.
- [ ] Integrate M6 with CI, PR, remote merge and branch retention evidence.

## M7: Deployment preparation

- [ ] Verify real Deployment CAS updates, next-tag derivation and receipt-guided rollback before the first application update. Publication, release Lease, first Deployment creation and the initial rollout are verified; update/collision/recovery regressions remain synthetic until exercised against a later release.
- [ ] Integrate any resulting deployment follow-up changes through CI and PR, retaining branches.

## M8: Production rollout

- [ ] Verify representative saved history/media and encrypted backup/restore before application updates. The real first pod replacement preserved the PVC, SQLite integrity, owner session and a temporary private file; production media recovery and compatible image rollback still require representative content and a reviewed maintenance window.
- [ ] Run only budgeted live modality checks and report unavailable account capabilities explicitly.
