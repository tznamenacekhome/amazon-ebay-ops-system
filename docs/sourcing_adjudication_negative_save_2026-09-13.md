# Adjudication negative save repair - 2026-09-13

## Scope and diagnosis

Focused web UI/API repair after web148 (`833837d8c94d`). No SQL migration, Python matcher change, Phase 3 activation, sourcing refresh, provider search, marketplace write, routing, business-hold or lifecycle mutation.

The reported Subnautica / Below Zero exact pair is already accepted as a negative by the API and atomic RPC without Wrong fields, corrections, identity attestation or variation attestation. The deployed web148 image also saved that pair in a real headless browser against the disposable PostgreSQL database with both checkboxes unchecked. That does not reproduce or explain every aspect of the operator's production failure; authenticated production browser access remains unavailable.

Two concrete UI failure paths were identified: request construction occurred outside catch/finally (an exception could strand busy state without an inline error), and successful writes waited for a complete 16-row reload before any success indication. The old UI showed Retry save while that reload was still running. Existing tests invoked callbacks and did not exercise this browser/network interaction.

## Final behavior

- Incorrect Match is an exact-pair negative independently of parser accuracy. Zero flags, zero corrections, and both verification checkboxes unchecked are valid. Wrong-only and corrected-field negative submissions remain valid. Existing field correction validation and scopes are unchanged.
- Negative submissions do not carry a positive identity attestation, even if the operator previously checked that box. Confirm Match still requires explicit identity attestation at API and RPC boundaries. Variation verification controls positive Tier A qualification, never negative admission. Full stored item and variation identity, frozen evaluation, snapshot, actor, timestamp and identity_adjudication_queue source remain in the atomic evidence write.
- All request preparation, network and response processing runs under catch/finally. A 30-second request timeout retains the exact pending request for idempotent retry. Inline errors preserve unsaved inputs. Non-JSON responses identify HTTP status and possible session expiry.
- The action area shows Saving review during submission. Success is explicit. The server returns the latest evaluated review and revision using one exact-pair readback; the queue updates that row and its progress without reloading the other 15 rows. The queue continues to show all rows; no unreviewed-only filter was added or removed.
- A committed write followed by failed readback remains HTTP 200 with saved action/snapshot identity and a separate refresh error. The editor says the review was saved and directs the operator to close/reload, without inviting a duplicate write. Existing append-only history, stale revision guards and atomic rollback remain intact.

## Validation and evidence

UI regressions cover bare negative, Wrong without replacement, negative with correction, unchecked positive/variation boxes, request-preparation exception, pending status, retry, stale inline error with retained notes, and committed-save/refresh failure. API/RPC regressions independently exercise bare negative acceptance, provenance, positive-only guards, correction scopes, concurrency, retries, rollback and protected opportunity/hold/block rows. A new real-browser harness runs an exact packaged Next.js image through its actual UI/API against only the named disposable PostgreSQL container; no production credentials are supplied.

Implementation validation and final deployment evidence are recorded below. Phase 3 remains incomplete and shadow-only. The frozen 16 identities and 15 eligible review denominator remain unchanged. No synthetic production adjudications are used as test evidence.
