# Dedicated variation save button fix - 2026-09-13

## Production defect

On web150, the selector was rendered in every adjudication dialog, but Save variation scope was conditional on opening the filtered follow-up view. It appeared at the bottom of that special dialog, not directly below the selector. Opening a confirmed row from the normal queue therefore showed no dedicated save action. The prior browser test only covered the filtered entry point and missed this production path.

## Corrected behavior

For an existing eligible Confirm Match, both normal and filtered dialogs now show **Save variation scope** immediately after the selector. It is enabled when the selected value differs from the current persisted value, subject to the existing stale/review guard and in-flight state. The dedicated handler sends only exact queue/evaluation identity, current revision, stable request ID, `reviewKind=variation_scope`, the original confirmation action ID and selected variation resolution. It sends no new pair verdict, Wrong flags, corrections, notes or platform relationship.

The existing RPC still appends the independent variation event and source snapshot atomically, with stale revision protection, ASIN locking and idempotent request fingerprints. No SQL or RPC definition change. Original Confirm Match/Incorrect Match/Not Sure events and their provenance remain untouched. Variation does not change sourcing status, routing, holds, lifecycle or buying eligibility.

A successful variation save leaves the dialog open, shows **Variation scope saved**, updates **Current saved qualification** and Tier A from the server readback, and replaces the editor's saved revision for any subsequent action. The queue receives the same readback immediately, so its reviewed progress is current on return. The button disables after the selected value is saved. Unsaved corrections and notes stay in the editor but are not included in a variation save. Actual inline errors retain the selected value; uncertain outcomes retain the exact request for retry. A committed write with failed readback is reported as saved and cannot be blindly resubmitted.

**Save corrections only audit:** web150 submitted `variationResolution` with ordinary correction-only payloads. The API stored that context, but qualification did not select it because it was neither a pair verdict nor a variation-only event. This was hidden, unused scope data. The UI now omits variation fields for correction-only saves, and the API independently omits variation fields from correction-only event context, even if a client supplies them. Dedicated variation and correction-only actions are separate.

## Verification

Actual component regressions exercise the normal dialog, exact selector/button adjacency, changed-value enablement, all three scope states, retained unsaved edits, inline stale errors, idempotent retries, immediate qualification, and correction-only separation. The actual API/RPC suite passes 257 calls against the disposable database, including original verdict history preservation, all scope states, qualification, supersession, stale rejection, atomic rollback and retries. Existing shared controls and diagnostic panel tests pass. TypeScript, focused lint, Next.js and Docker/web builds pass.

The packaged browser/API/RPC regression now starts from the **normal full queue**. It saves Not Applicable, Exact Verified and Unknown using only the dedicated button; confirms the dialog stays open and qualification updates; checks the visible queue progress increment, saved-state reload, original pair-verdict history, notes/corrections/relationship preservation and stale inline errors. The test uses local disposable records only. Screenshots verify the button directly below the selector and the success/qualification readback. The network-disabled routing replay preserves exact 37 Buy List / 50 Closest Excluded / 2 Business Excluded rows, full fields, summaries and order (110 frozen reads).

## Release boundary

Baseline web150 / scheduler92; all 20 schedules captured before deployment. This is a focused web/UI/API fix: no Python/matcher changes, no Phase 3 activation, no sourcing refresh/provider search, no marketplace writes and no business-hold/lifecycle changes. Deployment is web-only. Browser inventory has no enabled production surface, so authenticated production UI verification remains unavailable; packaged-browser verification is explicitly separate.

Operator instruction after deployment: reload Identity Adjudication, open an existing confirmed row from either queue view, change Variation scope, and use **Save variation scope** directly beneath the selector. Confirm Match is not required. The updated qualification stays visible in the dialog; Close returns to updated progress. Phase 3 remains incomplete and shadow-only.

## Completed release

Deployed web151 from `29eab7a16cf9`, pushed to origin/main. Rollout COMPLETED, one running task, exact target `172.31.41.133:3103` healthy. Image: `297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-web@sha256:f5203b41d8ea2b8288ae4d55aaa8c17f4653521741983cf6e8d15a78a5ef5f1f`. The exact release image passes the normal-dialog browser and network-disabled routing regressions. Scheduler92's full task definition and all 20 schedule configurations/targets are unchanged. No matcher, Python, schema, routing or hold/lifecycle change; no refresh/provider search or synthetic production review. The disposable database is stopped after testing.

The regression now covers the production entry point that the previous release missed: open a confirmation directly from the full queue. All nine requested behaviors pass across the actual component, API/RPC and packaged-browser tests. Authenticated production browser verification remains unavailable because the browser inventory is empty. AWS exact task/image/target checks and local exact-image browser tests are separate evidence. See [release proof](sourcing_variation_save_button_deployment_2026-09-13.json). Phase 3 remains incomplete and shadow-only.
