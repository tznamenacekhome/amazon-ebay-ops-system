# Phase 3 hold-scope repair passed; fresh routing safety blocked deployment

> Historical pre-closeout report. Superseded by the successful [final closeout](sourcing_matching_30_day_reprocess_2026-09-13.md); Phase 3 is now active on sourcing scheduler93.

The inventory/ROI guard repair passes. The strict frozen identity gate also passes. Work resumed through a new bounded production capture and a read-only routing dry run. That dry run exposed unsupported deterministic exclusions for FIFA 23 / PS5 and Madden NFL 12 / Wii. Production deployment, SQL application and refresh stopped. The required work-order status at the end denotes the overall safety stop; it does **not** mean the repaired inventory-scope regression is still failing.

## Hold semantics and atomic repair

Legacy encoding: `action_type=roi_snoozed` with `raw_action_context.actionType=inventory_snooze`. Current action records use `inventory_snoozed`, with `inventorySnooze.baselineUnits` / `representAtUnits` in context. The current action API still labels the associated snapshot event `roi_snoozed`; snapshot event names are not hold state. UI request aliases include `inventory_snooze` and `snooze_roi`; the normalizer also recognizes `roi_snooze`. A reason string alone does not create an inventory hold.

`sourcing_guard_hold_type` is the single guard normalization function. `sourcing_guard_active_hold` selects the latest ASIN inventory threshold and applies ASIN-wide protection independently of listing, opportunity or run. ROI/price holds remain pair-scoped, using the latest relevant pair action. These functions do not write actions, release holds, change their scope in existing workflows or alter matcher semantics.

There is no invented time-based expiry. Inventory release uses the existing scorer rule: proposed normal status must be open, and owned units must be at or below `representAtUnits`; if absent, derive the threshold from baseline minus at least one unit / ten percent rounded up. Missing thresholds remain active. Owned units include seed inventory, qualifying purchased/received units and active outbound FBA quantities. Cancelled/return/eBay purchases and closed/legacy-placeholder shipments are excluded using existing rules. Later inventory snoozes supersede the prior threshold. ROI release retains the existing 0.009 price-improvement / landed-cost-cap comparison. Missing or zero fallback item price cannot fabricate release. Current protected lifecycle rows still cannot be refreshed; the existing workflow owns their release.

The guard state now includes six purchase pipeline fields and ten shipment projection fields. Those tables are locked with the existing NOWAIT transaction locks, so a new purchase or changed shipment cannot race an inventory release decision. Active inventory protection is checked after capture-hash validation but before stale-state comparison: a hold committed after capture yields `protected_skip`, no update and no audit mutation. Lock contention remains a safe stale skip. Full canonical state comparison, numeric normalization, typed UPDATE checks, explicit bounds and idempotency remain intact.

Other ASIN-wide controls were inspected: blocked-ASIN records and active velocity suppression already use ASIN scope in the state reader/admission checks. Their scope was not broadened. Pipeline tables are read/locked only; the guard never writes purchases, receiving or FBA data. The UI reports stored lifecycle holds and delegates release to sync; the guard uses the scorer's actual release inputs rather than inferring release from age or display text.

## Tests

- 59 existing atomic guard checks pass, including numeric/timestamp/JSON equivalence, genuine stale changes, lifecycle protection, concurrent activity, bounded IDs, rollback and retries.
- The original legacy inventory regression now returns `protected_skip`, unchanged state and zero audit rows.
- 24 additional hold checks pass: legacy/current ASIN scope, different-ASIN isolation, ROI pair isolation, repeated protected attempts, after-capture hold insertion, threshold/baseline release, missing threshold, supersession, purchase/FBA pipeline protection, closed/excluded pipeline release, aliases and ROI fallback inputs.
- An initial existing-suite lifecycle assertion did not preserve its actual returned skip reason. Its isolated rerun returned protected with no write; a full rerun passed all 59 after diagnostics were improved. The cause of that first assertion is unproven; no unexpected production write occurred.
- 170 relevant Python tests pass, including Crystal Harbor corrected platform, genuine PS4/PS5 conflict, scoped corrections, variation and Disney generation cases. 257 API/RPC calls pass. All 1,609 legacy outputs match the frozen baseline exactly.
- Strict replay: 12/12 Tier A Match; three negatives excluded as two nonmatches and one Review; 17 scoped corrections applied; zero saved Compatible relationships. All 15 curated positives eligible and all 18 curated negatives excluded. Minecraft's separate condition block remains intact.
- Full deployment image/container/lint stages were not reached after the fresh routing failure. Narrow Python compilation and `git diff --check` are closeout checks, not production verification.

## Fresh production capture and dry run

Read-only current views: Buy List 28; Closest Excluded 50 returned of 129; Business Excluded 2; 33 active velocity holds globally. Latest rejected bound: 500. Deduplicated union: 529 rows, including one inventory-snoozed row. Scoped action count: 2,899; four linked explicit review snapshots; 304 purchase inputs; 270 shipment items; five declined-offer records. No blocked-ASIN or velocity suppression record belonged to the scoped ASIN set. All ordered view IDs and raw source evidence are frozen under `tmp/sourcing-hold-scope/fresh/`.

Capture used the actual API handler through a read-only client, not an authenticated browser. Only unused `raw_ebay_json` was omitted from the supporting 5,000-row listing-identity lookup. It still transferred 192,943,302 bytes because that query also selects large unused diagnostics. The lookup only consumes identifiers; future captures should reduce that supporting projection further. No broad source refresh or provider search ran. Full source hydration and hold inputs used explicit scoped IDs. This multi-read capture is not an atomic authorized write manifest; final DB guard-state hashes and recapture were not reached.

Provisional full-score dry run: 529 evaluated; eight protected; identity counts 92 Match / 330 nonmatch / 107 Review. Transitions:

| Before | Proposed logical route | Rows |
| --- | --- | ---: |
| Buy List | Buy List | 18 |
| Buy List | Closest Excluded | 10 |
| Closest Excluded | Closest Excluded | 48 |
| Closest Excluded | Buy List | 1 |
| Closest Excluded | Business Excluded | 1 |
| Business Excluded | Business Excluded | 2 |
| Rejected | Buy List | 19 |
| Rejected | Closest Excluded | 379 |
| Rejected | Business Excluded | 48 |
| Rejected | Rejected/protected | 3 |

These are per-row proposed classifications, **not actual post-refresh view counts**. Existing API deduplication, sorting and Closest Excluded scope/limits were not reapplied. The provisional scorer used captured seed/candidate/settings, scoped correction snapshots, declines and owned-unit inputs; it is not a completed production refresh client or deployment approval. Twenty logical recoveries were proposed, but none were written.

## Exact fresh routing blocker

| Opportunity | Captured reference / listing | Proposed reason |
| --- | --- | --- |
| `b08c8dc1-bf28-4936-a8e3-3f55794a0c73` / `B0B6JR3YDW` | FIFA 23 - PlayStation 5 / EA SPORTS FIFA 23 HyperMotion2 Soccer Game for Sony PlayStation 5 (PS5) | Core-game/product conflict from extra HyperMotion2 Soccer Game wording |
| `f1d32a0b-6030-4ffe-8ff6-cef8e4fea0bd` / `B002I08U20` | Madden NFL 12 - Nintendo Wii / EA SPORTS Madden NFL 12 Nintendo Wii E 2011 Manual Included | Core-game/product conflict from Manual Included wording |

Both current Buy List rows become deterministic nonmatches, rejected with `no_profitable_source_found`. The captured title/platform evidence does not establish a different game for either pair. They are new routing counterexamples, not newly operator-adjudicated Tier A labels. Treating these added words as established conflicting identity is insufficiently supported for deploying this dry run. This work order prohibits matcher semantics changes; none were made. The complete sources, comparison fields and proposed score outputs are frozen in `fresh/routing-blocker.json`. The prior strict curated set still passes; this failure was found only when operational work resumed on fresh rows.

## Deployment and continuation

No remote SQL, deployment, schedule update or bounded refresh occurred. No new image was built. Last recorded web151/scheduler92 were not freshly inspected; all twenty schedules remain untouched and no new comparison is claimed. Historical local image digest remains `sha256:905302756651d8ff2a6e3a88e378c737b7bb16935a135827908d4f3d85115403`, which does not validate the current guard candidate.

Production writes, protected rows touched, historical review/action rewrites, provider searches and marketplace writes are all zero. Eight dry-run rows were classified protected; production stale/protected skip counts are not applicable because no write was attempted. No final pre-write recapture or post-refresh view verification occurred. Rollback was unnecessary; fresh rollback targets remain required before a future deployment. The disposable test container was stopped at closeout.

Next continuation must resolve or adjudicate the two fresh routing counterexamples without assuming unverified positives, then rerun gates and finish the explicit guarded refresh tool/runtime integration, fresh canonical guard-state manifest, exact images, rollback/schedule checks, deployment, final recapture and post-refresh API verification. Do not reuse this capture for writes or claim Phase 3 completion. The hold repair and all evidence are checkpointed before a separate immutable commit-reference handoff update.

PHASE 3 NOT DEPLOYED — PROTECTED-STATE SAFETY GATE FAILED
