# Phase 3 reference metadata repaired; operational guard blocked

PHASE 3 NOT DEPLOYED — METADATA/ADMISSION SAFETY GATE FAILED

The metadata/admission repair passes the full required identity gate. The original operational work order resumed, including local atomic-guard implementation, mutation tests, a fresh production read-only capture and migration-ledger reconciliation. An expanded guard test then exposed numeric fingerprint instability. Work stopped before production SQL, deployment or refresh. The final status denotes the failed overall deployment gate; it does not mean the metadata repair lost its passing results.

## Exact metadata loss and repair

All four curated references had `seed.system=null`. Their titles omitted platform. The old resolver read `raw_context_json.inferred_system`, with `inferred_system_source=keepa_category_tree`; the previous canonical constructor accepted only `seed.system`. Its effective Amazon platform therefore became unknown, and the downstream canonical-only platform check removed admission.

| Reference | ASIN | Lost inferred_system | Restored canonical platform | Full scorer |
| --- | --- | --- | --- | --- |
| Zelda: Twilight Princess | B000FQBPCQ | Wii | Nintendo Wii | open |
| White Knight Chronicles II | B004WL4LOY | PS 3 | PlayStation 3 | open |
| Persona 5 Royal: Phantom Thieves | B081W4X9RW | PS 4 | PlayStation 4 | open |
| New Super Mario Bros. 2 | B0088MVPFQ | 3DS | Nintendo 3DS | open |

`resolve_seed_system` moved unchanged to `system_detection.py` and is shared by static and canonical construction. `_exact_reference` caches the complete reference metadata inputs, resolves the fallback before comparison, preserves the original raw context and exact-ASIN catalog metadata, and records normalized system, source and inference provenance. Metadata changes affect the cache key and material-evidence hash. Cross-ASIN catalog data is retained only as source provenance; it is not accepted as parser input.

Corrections still overlay a deep copy of the constructed identity. Corrected fields retain their `before` value and underlying source spans, with correction provenance added. Unrelated Amazon/eBay fields, catalog, generation, package/theme and compatibility metadata are preserved. Platform, digital/physical, completeness and region overlay preservation is covered. Stored source snapshots are never mutated. No title/ASIN whitelist or platform relaxation was introduced.

The source files changed are `system_detection.py`, `video_game_identity.py`, `sourcing_match_rules.py` and `matching_feedback.py`. Tests add four exact captured metadata fixtures and overlay/cache coverage to `test_sourcing_effective_identity.py`. The original Crystal Harbor/static consistency repair remains intact.

## Identity and application gates

- Crystal Harbor raw PS4, valid exact-pair correction to PS5: canonical Match, static Probable Match, no stale platform hard block, scorer open.
- Uncorrected PS4/PS5: canonical Conflict, static Blocked, scorer rejected. Stale/wrong-scope/wrong-variation corrections remain ignored; supersession and correction-to-Xbox conflict checks pass.
- 12/12 Tier A positives Match; three adjudicated negatives excluded as two nonmatches and one Review. The BIGS remains Review, never Match.
- All 15 curated positives eligible; all 18 curated negatives excluded. All four prior losses restored.
- All 17 scoped corrections apply. Twelve variation qualifications remain Not Applicable. Saved Compatible examples remain zero; synthetic compatibility tests are not operator attestations.
- Minecraft remains identity Match with its independent condition-related block. Disney unnumbered=1.0 policy and explicit later-generation conflicts remain intact.
- 170 Python tests at the metadata stage, 66 tests in the final networking-disabled image, 257 disposable API/RPC calls, and 150 Python-to-API-to-UI indicators across 15 rendered panels pass.
- All 1,609 legacy static/full scorer outputs are identical to the prior baseline. An incidental dash-encoding edit was restored exactly before the final default replay and final image build. The image and final replay contain the restored expression.
- Frozen shadow identity counts remain 187 Match/746 nonmatch/67 Review; current frozen-input counts remain 114/378/108. These are offline cohorts, not production routing counts.

## Operational work resumed

The new, unshipped migration `supabase/migrations/20260914045624_mbop_guarded_sourcing_decision_refresh.sql` adds a service-role-only state reader, guarded decision RPC and append-only refresh log. It constrains explicit bounded IDs and decision fields, compares full opportunity/source/action/history/hold/settings state inside a transaction, protects lifecycle and exact-pair operator history, and uses non-waiting locks to skip concurrent writers. It includes ASIN-wide inventory-hold and declined-offer state. Short locks cover operator paths that do not share the review advisory lock. No production application occurred.

The initial 31 disposable guard checks passed, including stale source/variation changes, newer actions/reviews, protected states, historical dismissals, retry idempotency, failure rollback, bounded IDs and concurrent operator insertion. The expanded acceptance run did not pass.

### Exact blocker: unchanged numeric state is falsely stale

For the disposable Best Offer row capped at $20 with a saved $25 decline, PostgreSQL emits the numeric value as `25.00`; the JSON client round-trip serializes it as `25.0`. PostgreSQL confirms the two `jsonb` states are semantically equal, but the guard hashes their textual representations and obtains different fingerprints:

- Server state: `c07d8fe15187522899a04e4d39daeeefb9f8a8db959e176020d9ee1b86cf2541`
- Client round-trip: `49d37e045cae947b43acf1f950ff90ca8f9c8602c2c24079260932e63496e52b`

The state is skipped at `before_hash` before business-hold validation. The test originally expected a SQL business rejection and mislabeled the returned skip as a bypass. **Audit log count for that case is zero: no declined-offer bypass or write was observed.** The assertion now describes false staleness explicitly. The actual operational blocker is failure to accept unchanged numeric state reliably, so the guard is not approved for production. No fingerprint repair was attempted after this gate failure. A continuation must establish a representation-stable fingerprint without weakening semantic stale-state or operator-activity comparison, then rerun the complete guard suite.

The implementation follows PostgreSQL's [explicit locking semantics](https://www.postgresql.org/docs/current/explicit-locking.html); this reference does not establish that the candidate guard passes acceptance.

## Fresh production capture and stopped closeout

1. Fresh actual-handler API-equivalent views: Buy List 28; Closest Excluded 50 returned of 129; Business Excluded 2, with 33 active velocity holds captured.
2. Bounded latest rejected scope: 500; displayed view selections: 80; distinct union: 529, including one inventory-snoozed row. The artifact's legacy `open` array name denotes displayed selections, not 80 open lifecycle rows.
3. Scoped actions captured: 2,899. Exact ordered IDs, source rows, latest action/review references, variation identities and evaluation metadata are persisted in ignored artifacts and the continuation index.
4. Capture is multi-read, not an atomic write manifest. Final database guard-state recapture was not performed. Do not use these artifacts for writes without fresh state checks.
5. Actual API capture read 324,117,970 bytes. The Closest Excluded handler accounted for about 308 MB of additional supporting reads. This unexpected volume is a Supabase I/O risk; reuse the capture and avoid blindly repeating that broad supporting query. Full source hydration used 18 additional requests over the explicit 529 IDs.
6. No duplicate listing identities were found within the three captured views. No authenticated production browser verification was performed.
7. Shared migration ledger: all 18 applied migrations match; only this new local guard migration is pending. No shared or College Planner migration was modified/applied remotely.
8. Full production routing dry run and deployable write plan: not completed because the expanded guard gate failed. The earlier frozen replay is not a substitute.
9. Deployment: none. Last recorded web151/scheduler92 were not freshly inspected. All twenty schedules remain untouched; no new configuration comparison is claimed.
10. Final local image: `mbop-scheduler:reference-metadata-final`, digest `sha256:905302756651d8ff2a6e3a88e378c737b7bb16935a135827908d4f3d85115403`. Built/tested locally, never pushed or deployed. Guard SQL was tested separately in the disposable DB.
11. Final pre-write recapture and bounded refresh: not started. Production evaluated-for-write/written/stale-skip/protected-skip counts are all zero.
12. Buy List/Closest Excluded/Business Excluded after refresh: not applicable; there was no refresh.
13. Protected production rows touched, historical reviews/actions rewritten, business holds changed, provider searches, marketplace writes, runtime/schema/scheduler changes: all zero.
14. No rollback is needed because production runtime/data was not changed. A future deployment still needs fresh rollback targets and a pre-write recapture.
15. Disposable `mbop-phase2-review-test` was stopped. No test data was written to production.
16. The candidate and failed operational gate are checkpointed separately from documentation commit metadata. The metadata fix is passing; the guard migration remains unapproved for production application. Phase 3 is incomplete.

Evidence: `tmp/sourcing-reference-metadata/` and `tmp/sourcing-phase3-final-fresh/`. Exact metadata loss traces, curated/strict/defaults proofs, test logs, numeric fingerprint proof, fresh read-only responses and source hashes are indexed by the [manifest](sourcing_phase3_final_manifest_2026-09-13.json). Earlier failed-candidate records remain in Git at `682c46e` and `1aa82cb`.

PHASE 3 NOT DEPLOYED — METADATA/ADMISSION SAFETY GATE FAILED
