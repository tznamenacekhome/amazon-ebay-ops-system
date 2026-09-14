# Exact-pair identity adjudication workflow - 2026-09-13

## Checkpoint

**Deployed web146 from a2552110df37; rollout COMPLETED, exact ALB target healthy.** Scheduler92 and all 20 schedules remain unchanged. **Phase 3 remains shadow-only.** No production synthetic adjudication, sourcing refresh, provider search, marketplace write or automatic historical relabel occurred. The operator has not yet created a Tier A corpus.

The initial queue is exactly the reconciliation audit's 16 receiving assertions. Its independent ID manifest and original-manifest SHA256 are in `sourcing_identity_adjudication_manifest_2026-09-13.json`; frozen, sanitized source text and unchanged parser traces live in `web/app/api/sourcing/adjudication/queue.json`. Original legacy IDs are retained alongside stored full eBay IDs. Unknown variation is not invented. Four changed purchase-ASIN cases retain the original reviewed pair and display the current assignment warning. Unavailable evidence storage keeps each affected row visible and disables its review button.

## Operator workflow

Open **Sourcing - Identity Adjudication** (`/sourcing/adjudication`). Open each Unreviewed row. Read its exact ASIN/listing identifiers, historical snapshot timestamp, original titles, Source details and stored parser token treatment. The screen has no photos. Unknown is explicit, never an invented Standard/Base/Complete/Physical value.

One Product Comparison table shows core game, installment, generation, theme, platform, edition, region, package type, completeness, digital/physical, derived core product, included contents and assigned release year. Each has an initially unchecked Wrong checkbox. Checking it enables either side; editing one side, both sides or neither is valid. Undo restores the opening value. Original parser values and source records remain available.

Choose Confirm Match only after independently verifying exact product identity. A separate variation attestation explicitly verifies the recorded variation or that variation selection does not apply. An unknown relevant variation cannot qualify as Tier A. Confirm without verified variation is evidence but not Tier A. Incorrect Match is valid without Wrong flags and applies only to this ASIN/listing pair; it never blacklists the listing against another ASIN. Not Sure is neither positive nor negative ground truth. Correction-only never creates a verdict or certifies unchanged fields.

Amazon corrections default to pair scope; only selecting Apply to this ASIN creates ASIN scope. eBay corrections stay pair-scoped. Additive v3 correction keys `coreProduct`, `includedContents`, `releaseYear` preserve canonical parser evidence in the existing correction array; they do not activate parser correction application in production. Token treatment is rendered only from recorded provenance; absent treatment reads `Token breakdown unavailable for this evaluation.` Recheck is deferred because the canonical Python comparator is outside the web image; no second frontend comparator was created.

Reload resumes the latest verdict and corrections. Report/export: `/api/sourcing/adjudication?report=1`, partitioning all 16 into qualified Tier A positives, exact-pair negatives and unresolved. Export includes actor, timestamps, source/evaluation/snapshot IDs, variation resolution, scopes, corrections and supersession lineage. Future Phase 3 must consume this evidence deliberately, preserve scoped correction provenance and revalidate admission; this task does not enable that consumer.

## Storage and isolation

The additive migration `20260913210000_mbop_identity_adjudication.sql` adds bounded state/save RPCs and reuses `sourcing_actions`, `sourcing_listing_snapshots` and `matching_intelligence_examples`. All verdicts use the existing matching_feedback action type with source `identity_adjudication_queue` and `admissionUse=evidence_only`. One transaction appends action, new snapshot and intelligence example; only the newly inserted action receives its snapshot link. Historical records are never rewritten.

The normal latest-review RPC excludes this source from verdict and correction lookup, including Amazon ASIN corrections. Thus existing Buy List, Closest Excluded and Business Excluded do not change merely because adjudication is saved. No opportunity/status, business hold, purchase, receiving or lifecycle write occurs. Python production defaults still exclude explicit v3 evidence from legacy admission; Python source is unchanged in this task.

Save validates the frozen queue pair/hash and stores frozen_historical scope. Normal reviews and adjudications share an ASIN advisory lock. The state revision is checked again inside the transaction after acquiring the lock; timestamps are assigned after lock acquisition. Concurrent different requests cannot both save the same revision. Same-request retries require identical actor/pair/fingerprint. Newer pair verdicts, newer corrections/uncertain flags and ASIN-scoped corrections invalidate stale dialogs. Legacy/full eBay aliases are considered conservatively for supersession, without propagating pair corrections across unknown variations. A changed/ambiguous newer review requires re-review; it is not silently adopted as this queue's Tier A confirmation.

## Validation

- Exact 16 IDs match the independently frozen manifest; no substitutions.
- Actual API - disposable PostgreSQL - reload/export: 97 RPC calls, passing auth rejection, stale pair/hash/revision, idempotency, verdict and correction supersession, explicit scope, positive/negative/unsure/correction-only, new canonical fields, variation attestation, separate-ASIN isolation, concurrent writers and injected failure after snapshot insertion. Opportunity, hold and blocked-ASIN rows unchanged. No remote/provider calls.
- Existing actual review API - PostgreSQL - Python analyzer suite passes, including Business Excluded, protected purchases, full rollback and actual Prey editor flow.
- Actual adjudication React component contracts pass: 13 visible comparison rows, Unknown, no photos, read-only defaults, Wrong/edit one or both sides/Undo/no replacement, verdict buttons, scope, CSRF and preserved stale dialog. Shared review controls suite also passes.
- 24 Phase 3 plus 10 feedback Python tests pass; prior matcher bytes preserved. No new matcher accuracy claim: prior annotated accuracy 98%, Amazon/eBay core-name coverage 100%/92.9%, curated 15 positives retained and original/expanded negatives remain the prior audit results.
- Focused lint, Next production build and web-only Docker build pass. Initial Google Fonts network failure resolved by rerunning the same build with approved network access.
- Built Docker runtime with networking disabled preserves all full routing fields, summaries and ordering for frozen **37 Buy List / 50 Closest Excluded / 2 Business Excluded** rows, 110 fixture reads, zero network/provider calls. Regression harness now freezes time to original capture (rolling 120-day counts otherwise cross UTC midnight); static policy guard permits only the recorded version literal `video_game_identity_phase3_shadow_v3`, not executable shadow-policy activation.
- Offline actual screen rendered and inspected at `tmp/sourcing-adjudication/editor.png`. This is not authenticated production UI verification. No Cognito redirect is treated as feature proof.
- Complete shared migration ledger read: 17 matching applied entries, only this new migration pending. The new migration is now applied; all 18 local/remote shared ledger entries match. The CLI emitted a non-fatal pg-delta catalog-cache certificate warning; ledger readback and production RPC reads both succeeded.
- Prior modified/untracked file SHA256 values all matched the start-of-task manifest before intentional documentation updates, including all Python shadow work and unrelated wholesale discovery.

## Deployment checkpoint

AWS SSO was restored through the documented login script. Commit `a2552110df3717b2e3455cc068b12fc91a326954` was pushed and deployed from a clean detached checkout through `scripts/deploy-web.ps1`; existing uncommitted Python shadow work was excluded. `scripts/aws-web-status.ps1` and final AWS readback confirm web146 COMPLETED, one running task, no pending tasks and exact healthy target 172.31.21.185:3103. Image digest: `sha256:59b03186776f35c99d8bcf03886215ddc052b1aa807f86f1ebd9b0e69259ec82`. CLOUD_DEPLOYMENT=true and LOCAL_SYNC_ENABLED=false remain set.

All 20 schedule definitions (state, expression/timezone, window and complete targets) are semantically unchanged. Scheduler stays revision92. The exact release image passes the frozen 37/50/2 routing check with networking disabled. Its packaged GET against production uses only 16 read-only state RPCs and loads all 16 available rows, 0 reviewed, 0 Tier A. No synthetic production adjudications were saved. Browser inventory returned no enabled apps/browsers, so authenticated UI remains unverified; offline actual UI and read-only packaged API evidence are the fallback, not a Cognito redirect.

Release proof, exact queue readback and artifact hashes are in `sourcing_identity_adjudication_deployment_2026-09-13.json`. Migration dry run selected only the committed new migration. The complete shared ledger was reconciled immediately before application and read back as 18 matching entries afterward. No historical data, protected lifecycle records or business holds were written by this task.

**Next action belongs to the operator:** open Sourcing > Identity Adjudication, review the 16 exact rows and choose Confirm Match / Incorrect Match / Not Sure with optional Wrong flags/corrections, then export the corpus. Stop here. A subsequent Phase 3 task must validate the new corpus; this deployment does not declare Phase 3 complete.

## Exact initial queue

| ASIN | eBay item (stored exact identity) | Receiving source ID |
|---|---|---|
| B072JZB85B | 233733278405 | 7f08f8ed-86a8-453a-aaf2-762c51acb069 |
| B07FF3F7F9 | v1|267725836968|0 | d7eb4172-eb08-4197-8c4b-360983272928 |
| B07JMHZMX1 | v1|168621770668|0 | 9ada02ce-14c4-4b90-9bbe-7c210ff07d38 |
| B08SZ1F5FB | v1|306964576833|0 | b06ded4b-90cb-48c4-a670-d30a17dc90c0 |
| B01KIH8ADS | v1|227032903283|0 | 33751f5c-b525-4991-8dad-30d3d949b729 |
| B07KTFL61P | v1|188511505771|0 | 063032b6-eeba-4661-99c5-b4581eeae259 |
| B01LDUYU60 | v1|295925010221|0 | 4ec62dd8-def1-49a2-b51a-ec1b8e9857b2 |
| B01MTQWAFN | v1|257625187330|0 | ccaffed2-c7bb-48f7-987d-da39289ce622 |
| B07JMHZMX1 | v1|158089049996|0 | 2bab0023-6a49-4817-b36d-8a3e03b473c5 |
| B009E480RS | v1|358716154387|0 | b32a22e5-e28e-4ea7-9811-b7fb5fa2baf3 |
| B00I6E6SH6 | v1|127933546536|0 | 1efb864b-a705-475e-a843-832ddf5713b6 |
| B01N3NNPAB | v1|318579237825|0 | 52261d35-1318-431e-bbc2-7ab6b8816fc0 |
| B001VLFCXW | v1|227432986138|0 | ec59476c-8dbb-4040-85b1-37fe658e98a3 |
| B07JMHZMX1 | v1|168621774190|0 | d7a5c382-bc78-434a-9ce2-d49fa072f68f |
| B00AXI9WFS | v1|318571029833|0 | 74c55b1b-2c50-4637-86e8-7c2199049be1 |
| B08HTHJ9L2 | 158136497383 | 8f04afc0-f67d-4ddf-9708-88c9ae9cdd31 |
