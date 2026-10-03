# Wholesale Phase 3B Refinement

Status: implemented, migrated, deployed, and browser-verified in production on October 3, 2026.

## Workflow

`/wholesale` has three primary views:

- **Ready to Review** contains only active-list products with a compatible selected ASIN, fresh eligible `new_new` evidence, complete supported economics, and at least one True ROI basis at or above 25%. An unresolved operator pass or an active Order List commitment suppresses the row.
- **Order List** contains idempotent Phase 3 draft commitments. It preserves supplier, product, ASIN, requested quantity, unit price, extended cost, and inventory/capacity context. It does not create a supplier purchase order.
- **Full Import** is the audit view for every accepted non-USED row on a selected supplier import. It defaults to the latest completed list and keeps the supplier effective date separate from MBOP's import timestamp.

Full Import supports supplier, historical list, system, text, and explicit business-status filters. Results are server-derived and paginated. Current reasons distinguish Ready, Order List, Restricted, Unmatched, Match Review Needed, Eligibility Pending, Pricing / Keepa Pending, ROI Too Low, Non-NA Version, Listing / ASIN Issue, Unsupported Product Economics, and each retained operator pass reason.

## Candidate discovery and evidence

The enrichment worker always executes identifier and title/platform searches independently, then merges by ASIN while preserving both sources. A successful UPC/EAN search does not suppress the keyword branch.

`wholesale_catalog_searches.query_context` stores the supplier identifier type/value or supplier title terms and platform term. Candidate API responses combine that context with the returned Amazon title, platform, and external identifiers. The UI uses human labels such as **Matched by UPC**, **Matched by Title + Platform**, and **Matched by UPC + Title/Platform**. Compatibility reason codes remain stored, while the popup translates them into operator-facing explanations.

Exact external-identifier evidence now participates in compatibility. An Amazon-returned identifier equal to the supplier identifier, with aligned platform and no edition, bundle, region, format, or accessory conflict, can establish compatibility despite supplier title abbreviations.

## Eligibility

Listings Restrictions remains a hard gate at condition `new_new`:

- eligible candidates can be selected and ranked;
- restricted candidates are skipped in favor of another compatible eligible candidate;
- unknown, stale, pending, and error evidence stays non-actionable and distinct from restricted;
- the product is Restricted only when no compatible candidate is eligible and all compatible candidates have current restricted evidence.

Production case `B0F2NZ8LKV` diagnosed the exact-identifier compatibility gap. Amazon Catalog returned supplier UPC `662248928180` on the ASIN, but abbreviated titles previously left it uncertain, preventing the eligibility call. After the general compatibility fix, bounded enrichment called Listings Restrictions and persisted `restricted / NOT_ELIGIBLE` for `new_new`, expiring October 10, 2026. The match state is `restricted_no_eligible`. No ASIN-specific rule exists.

## Pass persistence and conditional resurfacing

`wholesale_apply_decision` writes the pass timestamp, selected ASIN, supplier/import/effective-date context, and a reason-specific evidence snapshot into append-only `wholesale_decisions.decision_context`.

- **Too Much Inventory** captures FBA, inbound, draft, total exposure, velocity, target, and capacity. It may resurface only when capacity becomes positive and improves by at least one unit, followed by every normal readiness gate passing.
- **Price Risk** captures supplier/current/30-day/90-day prices and supplier history. A 5% or greater change in one captured price field is the auditable reconsideration trigger. Risk remains a human decision.
- **Competition** captures generic offer count and the independently sourced FBA seller count when available. A real observed count change is the trigger; generic offers are never relabeled as FBA sellers.
- **Other** never resurfaces automatically. The optional operator note is retained, and Full Import provides manual reconsideration.
- **Listing / ASIN Issue** is a persistent hard operator decision. It remains until manual reconsideration; candidate rematch remains available through candidate review.

A new supplier list or a changed full evaluation fingerprint alone does not clear any pass. Automatic resurfacing is append-only and records the prior decision plus the reason-specific change evidence.

## Persistent product exclusions

`wholesale_product_classifications` stores conservative product-level exclusions with append-only reversal history. The first supported classification is `non_na_version`. The enrichment worker creates it without provider calls only when the supplier title contains an established explicit non-US region marker. Active classifications skip repeated Catalog/Keepa discovery. The service-role RPC supports an audited manual reversal.

System states such as ROI Too Low, Restricted, Eligibility Pending, and Pricing Pending are not manual pass reasons. They remain visible in Full Import and can naturally become ready when current evidence clears the underlying gate.

## Schema and API

Migration `20261003213000_mbop_wholesale_phase3b_refinement.sql` adds:

- `wholesale_catalog_searches.query_context`;
- `wholesale_product_classifications` and its service-role classification RPC;
- the refined decision RPC with complete pass evidence snapshots and the reduced manual reason set.

`GET /api/wholesale/full-import` owns supplier/list selection, current status derivation, filtering, and pagination. It reads observations in bounded 500-row batches so imports larger than Supabase's per-request row cap remain complete. Candidate and opportunity routes continue to use the server service-role client. React does not contact Supabase or calculate ROI.

## Production evidence

The October 3 wholesale recall follow-up versioned the title-search strategy, added bounded cleaned/core fallbacks, and exposed each variant in candidate evidence. Commercial identity terms remain in the primary search, and compatibility reuses the sourcing identity parser to reject missing or conflicting sequel numbers. The pre-reprocessing Royal baseline was 18 matched, 3 identity review, 4 restricted, and 1,025 products with no match state; the latter were displayed as Unmatched but had never been enriched. Supabase capacity and a tiny read passed before any production reprocessing.

The live 12-product cross-platform diagnostic and reprocessing cohort made 24 Catalog search calls. Amazon returned rate-limit responses during per-ASIN snapshot hydration, and the shared retry/backoff path completed with zero search errors. Final cohort outcomes were 6 matched, 3 identity review, 2 restricted, and 1 explicit LATAM non-NA classification. Aggregate Royal state moved from 18 to 24 matched (+33.3%), 3 to 6 identity review, 4 to 6 restricted, and 1,025 displayed Unmatched rows to 1,013; the deliberately small cohort did not attempt a full-list backfill. The six new matches were evaluated and correctly remain Pricing / Keepa Pending because their cached economics are incomplete.

Production sampling found and corrected two unsafe result classes before expanding the cohort. Foreign-script Amazon titles now create incomplete region evidence even with an exact identifier, and PlayStation Hits, Greatest Hits, Nintendo Selects, GOTY, Bonus, Specialist, and Legacy variants participate in edition compatibility. Atomic Heart now selects the English PS4 listing `B0BSB3MWLL`; 007 First Light selects the Standard Edition `B0FQ5QBMGB`; related Black Ops titles with missing or conflicting installment numbers remain in identity review. A cached replay of all 12 products made zero Catalog search calls and produced the same final states.

Migration `20261003223500_mbop_wholesale_title_search_variants.sql` is applied to verified project `froeucjkcepuhgwisped`, and the remote migration ledger matches local. Scheduler task definition 113 runs commit `2cf506a4ce57` from digest `sha256:a3e9dd95dc11026f2f07e20b4d510975beba7ae24a715dce9b1ef108b9459f0e`; all 20 schedules target it. Web task definition 174 runs commit `63237f90d1bf` from digest `sha256:d93ead02736e68e735eaa59ab68eddc9340a2052b2aac334adfa61feed139120`; ECS reached steady state at desired/running/pending `1/1/0`.

Authenticated browser verification loaded build `63237f9`. Full Import returned 6 Restricted rows, then reopening the same status control and switching to Unmatched completed normally with 1,013 rows. The Atomic Heart candidate popup displayed the cleaned title, PS4 platform, Shared cleaned title + platform variant, merged UPC/title evidence, and the selected eligible ASIN. `/sourcing` loaded its completed cycle and empty current Buy List without application console errors; the only logged errors came from an unrelated Chrome extension.

The additive migration was applied to verified project `froeucjkcepuhgwisped`; local and remote migration ledgers align through `20261003213000`. The CLI emitted its known pg-delta certificate-cache warning after successful application; the ledger and live reads confirm the migration.

Bounded enrichment run `a70d2442-e0d7-4f10-bfb9-ea2ae47cbc47` processed 25 Royal products: 18 matched, 3 identity review, 4 restricted, and 0 errors. The resulting 215 candidates contain 16 identifier-only, 193 title-only, and 6 combined-source candidates; candidate eligibility is 20 eligible, 5 restricted, and 190 pending because eligibility is requested only for compatible candidates. Six exact fee estimates were refreshed without failures. Twenty-five current opportunities include one real Ready to Review row qualified on the 90-day basis, four restricted rows, three pending-match rows, and seventeen incomplete-economics rows.

Scheduler task definition 110 runs refinement commit `c2ea94775d40` from image digest `sha256:40e5183bed149dd145ee0764816b9ae456553ec05a68d77a4b5050248c91f9c7`; all 20 production schedules target it with unchanged cadence. Web task definition 172 runs filter-responsiveness commit `f8dc7fc8e3ce` from image digest `sha256:f1ba86d22943499647831abea72a44d8b6bcb95a0c911cdf616e28de7051b978`. ECS reported desired/running/pending `1/1/0`, completed rollout, and steady state.

The Full Import filter follow-up cancels superseded browser requests, prevents stale responses from overwriting current filter state, keeps the filter controls and existing results mounted while an update runs, and projects only the database columns required for status derivation. The live-data Restricted query returns all four restricted rows across the 1,050-product import in about two seconds from the local production build. The production container and deployed SHA are verified; authenticated browser replay was unavailable for this follow-up because the browser-control connection was offline.

Authenticated production browser verification confirmed build `1c780a3`, exactly three workflow tabs, the required Ready column order, one real Ready row, all 1,050 accepted products in Full Import, explicit audit filters, and an empty draft Order List. The One Piece Odyssey candidate popup showed combined UPC plus title/platform evidence with an eligible selected listing. The `B0F2NZ8LKV` popup showed exact-identifier/platform compatibility, `Restricted for New condition`, `NOT ELIGIBLE`, and a disabled selection control. The browser console contained no warnings or errors.

Validation includes 78 wholesale tests with 3 expected database/integration skips, 26 disposable-PostgreSQL tests with 1 optional workbook skip, 182 sourcing regressions, 44 Amazon tests, 5 Keepa tests, Python compilation, the local Next.js production build, and the Docker in-container production build.

## Remaining Phase 4 boundary

The workflow still has no supplier order header, submission, invoice, payment, receiving, accounting, or Amazon shipment creation. Phase 4 must atomically consume stable draft commitment IDs so Order List quantities are not double counted.

