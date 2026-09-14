# Phase 3 numeric guard repaired; inventory protection gate failed

PHASE 3 NOT DEPLOYED — ATOMIC GUARD SAFETY GATE FAILED

The numeric false-stale defect is repaired locally. All 59 numeric/timestamp/JSON and existing guard checks pass. A subsequent compatibility check against the production scorer exposed a separate protected-state failure. Per the work order, operational work stopped immediately before fresh production reads, remote SQL, deployment or refresh. Phase 3 remains incomplete.

## Numeric root cause and repair

The old fingerprint hashed `jsonb::text`, so stored `25.00` and client `25.0` produced different hashes despite native numeric equality. `sourcing_guard_canonical` now recursively removes numeric scale using exact PostgreSQL `numeric`/`trim_scale`, preserves null and booleans, uses deterministic object ordering, preserves array order and exact text/identifiers, and normalizes allowlisted native timestamps to UTC at six-digit microsecond precision. Embedded raw JSON strings are not interpreted as dates. Request fingerprints use the same canonical representation, including normalized before-state, so equivalent retries remain idempotent.

The transaction compares the full canonical state with database-native JSONB equality while holding the existing non-waiting locks. Hash equality alone cannot admit a write. Critical opportunity UPDATE predicates additionally use native UUID, text, timestamp and numeric equality against the captured database row. Locks, bounds, protected-state checks, append-only audit and rollback behavior remain in place. The [field audit](sourcing_guard_field_audit_2026-09-13.md) classifies every selected column and the history projection. This unshipped migration has only been loaded into the disposable database, never production.

## Exact new blocker

The scorer's `fetch_historical_status_by_key` recognizes an action with `action_type=roi_snoozed` and `raw_action_context.actionType=inventory_snooze` as an **ASIN-wide inventory hold**. The guard only recognizes literal `inventory_snoozed` as ASIN-wide; its `roi_snoozed` protection requires the same listing ID.

The regression creates two listings of one ASIN, stores that legacy inventory action on one, and tries to refresh the other. Expected: `protected_skip`, unchanged state, zero audit writes. Actual: `written`, state changed, one disposable refresh-log row. This is a real local protection failure, unlike the previous numeric test's mislabeled bypass. No production row was involved. The failing test remains in the repo and the migration remains explicitly unapproved. No protection repair or further deployment gate was attempted after this failure.

## Validation and operational checkpoint

- 59 checks passed: exact numeric equivalence including 25/25.0/25.00/25.000, zero/negative zero, 1.5/1.50 and arbitrary-precision SQL tokens; actual numeric changes; null/zero/empty/false distinctions; timestamp offset/precision equivalence and retry; actual microsecond changes; nested JSON key ordering/value changes; all prior stale, lifecycle, action, business-hold, bounded-write, retry, rollback and concurrent-insert checks.
- One additional inventory compatibility regression failed. Frozen proof: `tmp/sourcing-guard-canonicalization/inventory-compatibility.json`.
- No parser/matcher/runtime changes. The last passing identity evidence remains 12/12 Tier A Match; 3/3 adjudicated negatives excluded (2 nonmatch, 1 Review); 15/15 curated positives eligible; 18/18 curated negatives excluded; Crystal Harbor corrected platform passes; genuine PS4/PS5 blocked; Disney first-generation convention intact; 1,609 default outputs unchanged. These were **not rerun in this attempt**, because the guard failed first.
- Previous validation evidence remains 170 Python tests, 66 packaged container tests, 257 API/RPC transaction calls and 150 API/UI indicators. No new full-suite/lint/image-build result is claimed. Narrow Python compilation and `git diff --check` are closeout checks only.
- No new production manifest or dry run. Previous capture is historical only: Buy List 28, Closest Excluded 50 of 129, Business Excluded 2; 33 active holds; 500 rejected; 529 deduplicated rows. It must not be reused for writes. The prior 324 MB supporting capture is preserved, not repeated.
- No new production image or revision. Historical local image `mbop-scheduler:reference-metadata-final`: `sha256:905302756651d8ff2a6e3a88e378c737b7bb16935a135827908d4f3d85115403`; it predates this SQL candidate and is not a deployable proof of this repair. Last recorded production revisions are web151/scheduler92, not freshly inspected.
- All 20 schedules untouched; no new comparison. No remote migration application or ledger change. No final pre-write recapture, write plan execution, refresh or postdeployment routing verification.
- Production writes, protected rows touched, historical action/review rewrites, business holds changed, provider searches and marketplace writes: all zero. Production stale/protected skip counts are not applicable because no write attempt occurred.
- Disposable `mbop-phase2-review-test` stopped. Rollback not needed because production was unchanged; fresh rollback targets are still required before any deployment.

## Continuation requirements

Resolve the legacy ASIN-wide inventory protection mismatch without weakening the guard or rewriting history. Rerun the failing regression and the full guard suite before continuing the strict identity suite and complete authorized operational order. A production transport must preserve exact decimal tokens. Fresh bounded manifest, read-only routing dry run, production images/rollback targets, all twenty schedule comparisons, deployment health, immediate pre-write recapture, guarded refresh and post-refresh API verification remain outstanding. Do not treat the passing numeric fix as deployment approval.

The previous metadata repair and failed numeric checkpoint remain in Git at `5ad2b27` / `fbb52da`. The current [manifest](sourcing_phase3_final_manifest_2026-09-13.json) preserves their evidence and separately records this attempt. Commit IDs are recorded in a subsequent handoff update to avoid self-reference.

PHASE 3 NOT DEPLOYED — ATOMIC GUARD SAFETY GATE FAILED
