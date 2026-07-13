# Business Rules

Last updated: 2026-07-12

## Cost And Reporting

- Frontend code must never recalculate landed cost.
- Purchase reporting must use backend-provided `vw_purchases_dashboard.unit_cost`.
- eBay reward points or payment methods must not reduce inventory cost to zero.
- Single-item partial refunds where the item is kept may reduce purchase item cost.
- Multi-item partial refunds require explicit workflow/manual handling.
- Personal purchases and business supplies remain traceable but are excluded from resale reporting through `purchase_items.exclude_from_purchase_reporting`.
- Purchases on or after 2026-05-16 are MBOP-canonical, not spreadsheet-canonical.

## Status Ownership

`purchase_items.current_status` is backend-owned.

Workflow-locked statuses include:

- `cancelled`
- `listed`
- `received`
- `return_opened`
- `return_pending`

Carrier/status syncs must not downgrade workflow-owned statuses.

## Matching And Product Identity

- Video games are platform-specific.
- Never auto-match across systems.
- eBay buyer purchase sync may use eBay Browse item `localizedAspects.Platform`
  to populate `purchase_items.system` when the Trading API order title does not
  include a recognizable platform. This is backend enrichment only; it must not
  override an existing/manual system value.
- ASIN corrections may propagate only to matching normalized title + system rows and must not overwrite a different existing ASIN.
- `purchase_items.amazon_title` stores the matched Amazon/RevSeller title separately from the supplier/eBay title.
- AI-assisted RevSeller matching is allowed only as a same-system, candidate
  selection review over locally ranked RevSeller rows. It must not invent ASINs
  or override platform boundaries, and low-confidence responses must remain
  unmatched for manual review. Scheduled AI review should focus on open
  purchase-work rows and write an auditable diagnostics row for each AI match.
- If a row already has a reviewed ASIN but is missing Amazon metadata, MBOP may
  fill only `purchase_items.amazon_title` and/or `purchase_items.target_price`
  from manual match memory, RevSeller, Amazon listing snapshots, or stored Keepa
  catalog snapshots. This must not change ASIN, system, cost, status, or
  workflow state.
- ASIN is the primary Amazon product identity for MBOP operational inventory. MSKU remains stored for Amazon traceability and InventoryLab/Informed joins.
- Amazon listing/MSKU discovery should use the broadest safe Amazon seller
  listing set available, including inactive merchant listings imported into
  `amazon_skus`, when a workflow needs historical ASIN/MSKU coverage.

## Sourcing

- Sourcing opportunities are advisory and must remain separate from Purchases
  until an eBay buyer purchase has been imported and matched.
- Sourcing search and scoring must hard-exclude items outside the configured
  item-location countries, currently US and Canada.
- Excluded sourcing keywords, such as Steam, message delivery, DLC, promo, VPN,
  and disc-only signals, must prevent rows from appearing as open opportunities
  even when Best Offer or auction math would otherwise look profitable.
- Sourcing must hard-block eBay results whose meaningful title words have no
  overlap with the Amazon title after removing platform and generic words. A
  shared platform alone, such as Nintendo Wii, is not enough to keep an
  opportunity open.
- Sourcing must hard-block eBay results when known category evidence shows the
  listing is not in the Video Games category.
- Sourcing scoring must consume backend-resolved Amazon platform context from
  first-class seed `system`, then `sourcing_seed_asins.raw_context_json.inferred_system`,
  then title detection. eBay item-specific `Platform` must be used before
  title-only platform detection when available.
- Sourcing must treat explicit structured and textual evidence for accessories,
  merchandise, digital/service items, incomplete products, foreign regions,
  sequel/year conflicts, and edition/version conflicts as backend-owned
  diagnostics and hard blocks where confidence is high.
- Possible game-plus-accessory bundles should route to Review instead of being
  blindly hard-blocked unless the listing clearly lacks the game.
- eBay sourcing search uses one approved platform-aware search suffix per ASIN
  and must not add unapproved aliases. DS, original Xbox, and GameCube are not
  searched by the replenishment sourcing workflow. Wii and Wii U are separate
  platforms; a Wii seed must not accept a Wii U eBay result.
- Xbox One and Xbox Series X/S physical releases may be cross-generation for
  this workflow. Sourcing matching must not hard-block an otherwise plausible
  candidate solely because one side says Xbox One and the other says Xbox
  Series X/S.
- eBay sourcing search must constrain Browse search to the EBAY_US Video Games
  software category ID `139973`, request up to 200 first-page results, and must
  not paginate beyond that first 200-result page without a future explicit
  design.
- Unknown eBay ZIP shipping estimates may be shown as watch opportunities when
  otherwise plausible, but MBOP must not calculate profit, ROI, offer, or bid
  guidance from assumed free shipping.
- Sourcing display and scoring should trust stored `sourcing_ebay_candidates.shipping_cost`
  as the buyer-ZIP shipping quote even if a later eBay detail/availability
  refresh payload omits `shippingOptions`. Only rows with no stored shipping
  cost and no raw eBay shipping option should be treated as unknown shipping.
- Best Offer guidance subtracts eBay shipping from the landed cap and evaluates
  the item offer against the eBay asking price before shipping. Best Offer caps
  use the lower of stored Keepa 90-day price and current Amazon market price.
- Watch replaces ROI Snoozed in the sourcing operator workflow. A watched row
  can return to open Replenishment only when normal scoring passes and either
  the eBay purchase-cost reference falls below the watched baseline or the
  Amazon sale-price/profitability context raises the profitable landed-cost cap.
  Best Offer watch baselines use the suggested item offer before shipping.
- Purchased Pending Match is also used for Best Offers made by the operator. If
  no matching eBay purchase appears within 72 hours, the sourcing matcher moves
  the row back to Watchlist.
- When a sourced opportunity matches an imported eBay purchase, the matcher may
  write sourced ASIN, Amazon title, and target sell price to the matched
  `purchase_items` row. The target sell price is the highest available Last
  Sold, Keepa 90-day, and current Buy Box value.
- Daily sourcing availability cleanup may dismiss open, Watch, and ROI-snoozed
  opportunities as `no_longer_available` when eBay Browse shows the listing is
  ended, sold out, or missing. It must not dismiss Purchased Pending Match rows,
  because those often become unavailable after the operator buys or offers and
  must remain available for purchase matching/enrichment.
- Sourcing seed generation may use the full known Amazon SKU catalog, including
  inactive seller listings, so out-of-stock products with known ASIN/MSKU
  history can still become replenishment candidates. Full-listing sourcing may
  also seed ASINs known only through current stored Keepa snapshots, but not
  snapshots older than 7 days.
- Sourcing opportunity Last Sold display is backend-owned. It should use the
  seed's stored sale context when present and otherwise fall back to Amazon
  sales history by ASIN so full-listing candidates do not lose recent sale
  context.
- Daily and on-demand sourcing use the same unified coverage cycle. A cycle
  searches each eligible ASIN at most once before starting a fresh pass, while
  newly eligible ASINs are appended to the active queue. Queue priority is:
  Amazon ASINs sold in the last 90 days, purchased Amazon-bound items not yet
  sent to Amazon, then remaining eligible catalog ASINs.
- Sourcing coverage-cycle ASIN eligibility is limited to video game catalog
  items. Backend seed building should use Keepa product group/category evidence
  and platform/system evidence to exclude books, board games, pet products,
  apparel, music accessories, supplies, and other non-video-game ASINs before
  the queue is persisted.
- Sourcing discovery is quota-driven, not target-count driven. The job should
  spend the available daily eBay Browse budget, subject to any configured
  reserve, and store all qualifying opportunities found. Quota exhaustion or
  quota-reserve stops are normal "Out of quota" outcomes, not failed jobs.
- Coverage-cycle batch membership must not re-present opportunities already
  assigned to prior batches unless the operator action/workflow explicitly
  returns the row to an open sourcing state.

## Receiving

- Purchases workflow and receiving workflow are separate.
- Receiving owns physical verification and the transition to `received`.
- Amazon-bound received items require ASIN and sell price.
- eBay-bound received items do not require Amazon title, ASIN, or sell price.
- Return Pending is separate from Return Opened.
- When Receiving discovers a damaged, wrong-condition, wrong-item, packaging,
  or incomplete-item issue, it sets `purchase_items.current_status =
  return_pending` and opens or updates the active Order Problems episode as a
  receiving exception.
- Cancelled items require future refund follow-up.

## Order Problems And Returns

- Order Problems is the unified queue for delivery problem candidates,
  return-needed items, eBay return/case follow-up, missing-item/replacement
  follow-up, and cancelled/refund confirmation.
- `order_problem_cases` owns the persistent workflow case; `order_problem_events`
  owns the append-only timeline.
- A purchase item may have multiple Order Problems episodes over its lifetime.
  MBOP allows one open episode per purchase item, while closed episodes remain
  as history and must not suppress a later stale-tracking, INR, damaged-item, or
  incomplete-item episode.
- Episodes store `episode_kind`, `episode_sequence`, `opened_reason`,
  `resolved_reason`, `source_artifact_type`, and optional supersession links so
  delivery problems, eBay INR cases, damaged-item returns, and incomplete-item
  returns can be distinguished even when they happen on the same eBay order.
- `Return Pending` means MBOP identified a return need before an eBay return/case
  necessarily exists.
- `Return Opened` means an eBay return/case exists or the operator has marked it
  opened in eBay.
- Stale tracking candidates use a 14-day order-age threshold for `no_tracking`,
  `shipped_no_tracking`, and `awaiting_carrier_scan`, with a 90-day lookback.
  `in_transit` is not stale while carrier ETA is in the future. After an eBay
  ETA passes, a shipment with a usable tracking number is still suppressed from
  Order Problems while carrier activity is current.
- Late-delivery candidates require either no usable tracking number or no
  carrier activity for more than 4 days. Current EasyPost/carrier activity
  overrides an expired eBay ETA for candidate detection.
- Carrier activity showing exception language, including `return_to_sender`,
  `Returned to Sender`, or similar event text, creates a
  `carrier_exception_candidate` even when carrier activity is recent.
- Derived stale/late/carrier candidates should auto-close when the purchase no
  longer matches a candidate rule. If the item later matches a candidate rule
  again, MBOP should create a new episode rather than treating the old resolved
  case as a permanent suppressor.
- The current eBay returns integration is read-only. MBOP may store eBay return
  IDs, inquiry IDs, cancellation IDs, statuses, deadlines, escalation dates,
  refund amounts, action URLs, replacement tracking, and raw payloads, but must
  not create returns, send messages, accept offers, escalate cases, issue
  refunds, or upload files.
- When eBay provides a buyer return label/tracking number, MBOP should track it
  separately from inbound supplier shipments. EasyPost owns return-label carrier
  enrichment. Delivered return tracking should advance the episode to waiting
  for seller/eBay refund, and eBay refund-issued status should advance it to
  refund verification.
- For INR inquiries, eBay search results are not enough. MBOP must read inquiry
  details to capture seller make-it-right dates and seller-provided replacement
  tracking. Those dates display as escalation/action availability in the Order
  Problems Next Action column.
- For missing-item INR inquiries with seller-provided replacement tracking,
  carrier/eBay tracking progress should move the case to replacement-shipped
  follow-up. Delivered replacement tracking should close the case as
  `resolved_received_item` and return the purchase item to `delivered`, leaving
  physical verification to the Receiving workflow.
- If Receiving later finds the delivered item damaged or incomplete and the
  operator opens an eBay return, that return is a new episode. The old closed
  INR inquiry must not close, downgrade, or overwrite the active return episode.
- For multi-item eBay orders, eBay return/inquiry sync should attach order-level
  return data to an already open receiving/return episode for that purchase
  before falling back to generic item selection.
- `Close` means the problem is resolved with no further refund or inventory
  consequence. `Close No Refund` means the problem is closed but value was lost
  or unrecoverable and no refund will be received; it must not move the item
  back into Received, Listed, or Amazon-bound inventory.
- Operator actions in the drawer update MBOP workflow state only. The operator
  performs marketplace actions on ebay.com.
- Partial refunds where the item is kept must not automatically change item cost
  until a controlled cost-adjustment workflow exists.
- The Purchases default list is for open purchase work. It excludes Listed,
  Cancelled, Return Opened, and Return Pending rows; those rows remain available
  through explicit status filters, All Status, and the Order Problems workflow.
- Cancelled/refund-follow-up order-problem actions must preserve
  `purchase_items.current_status = cancelled` so cancelled rows do not reappear
  in Purchases Open Purchase Work.

## Amazon FBA Shipment Prep

- The FBA workflow starts from Received Amazon-bound purchase items.
- The FBA page groups rows by ASIN for InventoryLab export.
- Grouped cost is backend-owned and quantity-weighted.
- Operator-entered shipment ID links included items to FBA shipment rows.
- Included quantities move to `listed`; excluded quantities remain `received`.
- Current non-historical FBA shipment links are valued as `outbound_to_amazon` only for remaining units Amazon has not yet received or made available.
- Amazon Return Recovery rows may enter FBA shipment prep through
  `fba_shipment_source_items` when the operator marks a physically inspected
  item as New and Send to Amazon. They must not be written to `purchases` or
  `purchase_items`.
- Amazon FBA shipment sync stores Amazon inbound status, fulfillment center, carrier ETA when available, received quantity, FBA available quantity, and remaining outbound value on shipment workflow rows.
- FBA prep pricing uses explicit operator refreshes, not page-load marketplace
  calls. The prep table shows Total Cost, Total Sell Value, Total Profit, and
  Total ROI from backend/API values.
- FBA prep Profit/ROI deducts cached Amazon Product Fees. When the operator
  edits a sell price, MBOP reuses cached non-referral fee components and
  recalculates only the referral fee from the cached referral percentage so the
  row updates immediately after save without calling Amazon.
- FBA prep should warn when the saved sell price is below Last Sold, current
  Buy Box, and Keepa 90-day Buy Box average.
- The historical marker `legacy_listed_no_shipment_id` must not create outbound-to-Amazon value.
- Explicitly `listed` legacy purchase-item lots with ASIN, quantity, and cost
  may participate in Amazon sales FIFO COGS allocation even when the original
  supplier was not stored as eBay. This is for old resale inventory sources that
  should not re-enter receiving or open purchase work.

## Amazon Return Recovery

- Amazon customer return, reimbursement, and future removal data must stay in
  Amazon-specific tables.
- Amazon return reason, disposition, and customer comments are evidence only.
  They do not determine final condition or disposition without manual physical
  inspection.
- Observed condition controls the operator workflow. Items observed as New may
  be routed back to Send to Amazon; Used, Damaged, Missing Parts, and Wrong Item
  items must not be sent back to Amazon as New without an explicit future
  review/override workflow.
- Missing Parts and Wrong Item outcomes may move into reimbursement review, but
  MBOP does not infer reimbursement eligibility automatically.
- Seller Central cases are prepared manually. MBOP must not create Amazon cases
  automatically unless a future approved write workflow is designed.
- Customer return and reimbursement report imports may be run manually/on
  demand. Do not schedule unreliable Amazon removal reports while they are
  returning `FATAL`.

## Inventory And Valuation

- Current canonical inventory equals current Amazon FBA inventory plus MBOP purchase inventory that has not reached `listed`, plus non-historical MBOP FBA shipment links that are on the way to Amazon.
- Amazon-bound `listed` purchase rows without a current FBA shipment link are historical/sold-through for current inventory purposes; current Amazon inventory is represented by Amazon SP-API snapshots.
- InventoryLab valuation snapshots are legacy opening-balance valuation context for current Amazon FBA inventory.
- MBOP purchase/receiving/FBA workflows own go-forward cost.
- Opening-history boundary adjustments record units sold before MBOP's
  operating-history window and must stay separate from future inventory count or
  discrepancy adjustments.
- The Inventory Source Balance Audit checks that purchase source units equal
  sold units plus active inventory, opening-history boundary units, and explicit
  adjustments. It is a control process for close/tax confidence, not a scheduled
  external-data freshness sync.
- Business value snapshots use MBOP outbound shipment cost only for shipment quantities still unresolved by Amazon receiving/availability data, and avoid double-counting Amazon-received shipment value.
- InventoryLab valuation files are audit-only and must not overwrite MBOP inventory, costs, shipment rows, or purchase items.
- YNAB Business category balance is cash-on-hand context only.
- Amazon Finance cash is value that has moved from inventory into Amazon-held cash or Amazon-to-bank in-transit cash.
- Amazon-to-bank in-transit cash includes transfers Amazon still marks
  `Processing` plus completed/succeeded payout groups that do not yet have a
  matching YNAB Business deposit transaction. This prevents business value from
  dropping during the gap after Amazon completes a payout but before the YNAB
  bank/cash transaction is present, without double-counting deposits that YNAB
  already captured.
- Business value snapshots are reporting snapshots only.
- Business value snapshot dates and MBOP dashboard date-only displays are
  Pacific Time business dates. Date-only strings must not be parsed as UTC
  timestamps for display.
- Dashboard cash/value freshness is limited by the oldest required cash/value
  input: business value snapshot, Amazon Finance balance snapshot, or YNAB cash
  snapshot.
- Amazon reserved inventory is normal Amazon processing and should not be
  surfaced as an operator problem by itself.
- Amazon listing/catalog issue signals should be ignored when your FBA units are
  still sellable/available for sale.
- Amazon damaged/unsellable units and customer returns returned to the business
  belong in Amazon Return Recovery/removals workflows, not purchase or
  receiving cleanup.
- Amazon receiving shortages, lost units, warehouse damage, and customer returns
  that do not come back to the business belong in a future Amazon Inventory
  Discrepancy workflow.
- Seller Central Account Health and Feedback Manager values are Amazon
  channel-risk signals, not MBOP technical health. Account-health score and
  lifetime feedback rating are manual dashboard snapshots. SP-API
  `GET_SELLER_FEEDBACK_DATA` rows are used only as 1-3 star feedback alerts.

## Repricing Advisor

- The Aged Amazon Inventory Repricing Advisor is manual advice, not an automated repricer.
- Do not write prices to Amazon.
- Do not modify Informed rules, min/max prices, or managed status.
- Use Amazon Inventory Planning age buckets as the preferred active-FBA age source.
- Rows under 90 days old are excluded unless there is an actionable issue.
- Rows with any Informed sales in the last 30 days are excluded from the aged action list.
- FC transfer, inbound movement, future supply, and FC processing are not action issues by themselves.
- Buyable/discoverable Amazon catalog metadata issues are ignored unless inventory becomes suppressed/non-buyable or unsellable.
- Snoozes hide advisory rows from the default queue for 30 days and do not change inventory state.
- Keepa competition data must come from stored snapshots or explicit operator-run scripts, not from page-load token spending.
