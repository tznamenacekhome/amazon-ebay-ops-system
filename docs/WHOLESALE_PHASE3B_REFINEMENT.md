# Wholesale Phase 3B Refinement

Status: implemented and production database migration applied on October 3, 2026. Web and scheduler deployment evidence is recorded below after rollout.

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

`GET /api/wholesale/full-import` owns supplier/list selection, current status derivation, filtering, and pagination. Candidate and opportunity routes continue to use the server service-role client. React does not contact Supabase or calculate ROI.

## Production evidence

The additive migration was applied to verified project `froeucjkcepuhgwisped`; local and remote migration ledgers align through `20261003213000`. The CLI emitted its known pg-delta certificate-cache warning after successful application; the ledger and live reads confirm the migration.

Bounded enrichment run `a70d2442-e0d7-4f10-bfb9-ea2ae47cbc47` processed 25 Royal products: 18 matched, 3 identity review, 4 restricted, and 0 errors. The resulting 215 candidates contain 16 identifier-only, 193 title-only, and 6 combined-source candidates; candidate eligibility is 20 eligible, 5 restricted, and 190 pending because eligibility is requested only for compatible candidates. Six exact fee estimates were refreshed without failures. Twenty-five current opportunities include one real Ready to Review row qualified on the 90-day basis, four restricted rows, three pending-match rows, and seventeen incomplete-economics rows.

## Remaining Phase 4 boundary

The workflow still has no supplier order header, submission, invoice, payment, receiving, accounting, or Amazon shipment creation. Phase 4 must atomically consume stable draft commitment IDs so Order List quantities are not double counted.

