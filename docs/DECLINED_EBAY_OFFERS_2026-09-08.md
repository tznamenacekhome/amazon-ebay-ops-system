# Declined eBay offers in sourcing

Status: migration applied and import activated September 8, 2026. Scheduler
revision 86 and web revision 138 use release commit `11dfabd0a41c`.
See `RELEASE_2026-09-08_SOURCING_OFFERS.md` for deployment verification.

## Behavior

The buyer's explicit eBay `Declined` status is retained against the exact eBay listing ID.
For offer-dependent (`best_offer`) opportunities, hide the listing when MBOP's
current maximum profitable **item** offer is at or below the highest observed
declined item offer. A $60 decline suppresses limits of $55 and $60; a recomputed
$60.01 or greater limit can qualify again. Full shipping remains in the landed
cost calculation; shipping is never added to the declined offer before comparing.

The existing conservative pricing reference (including ASIN average/current
prices), fees, ROI/profit targets, and item-price offer floor remain authoritative.
There is no time-based reset and no new profitability formula. A lower prior offer
does not suppress a currently higher profitable recommendation. As with other
opportunities, a price change takes effect when the opportunity is rescored.

The API checks evidence before filtering/ranking/summary/presentation metadata,
including Watch and prior-run listings. Scoring rejects otherwise-open suppressed
opportunities; duplicate-ASIN selection also skips suppressed listings so a
different seller can qualify. This is not permanent matching feedback or an
ASIN block. Existing operator actions and purchase history are preserved.

## Import and storage

`integrations/sync_ebay_buying_offers.py` calls Trading `GetMyeBayBuying` with
`BestOfferList`. It uses the existing server-side eBay OAuth refresh credentials
and the verified Trading authentication envelope. There are no offer submission,
acceptance, counteroffer, or other eBay mutations.

Default execution is read-only; `--apply` stores evidence using
`public.record_sourcing_declined_offers(offers jsonb)` into
`public.sourcing_declined_ebay_offers`:

- `ebay_legacy_item_id`: primary key
- `declined_offer_amount`: highest observed positive USD amount, numeric(12,2)
- `currency`: USD
- `first_seen_at`, `last_seen_at`: observation times, not eBay offer timestamps

The atomic maximum prevents concurrent/repeated imports or lower offers from
erasing higher declines. Empty responses never delete evidence. Only explicit
declines are stored; pending/countered/expired/accepted/unknown statuses do not
create a decline. Non-USD and variation-specific evidence is excluded to avoid
comparing different currencies/products. Only compact evidence is stored, not
raw XML or buyer personal information. RLS and grants restrict access to the
existing server service role; no browser access or new public API is introduced.

Pagination is bounded at 20 pages of 100. Failure, Warning, malformed XML, or
exceeding the bound fails the job rather than claiming an empty successful sync.
Database failure during apply fails the job; already stored evidence survives.
The opportunities API fails visibly if it cannot check the evidence table.

The new nonblocking scheduler step runs before purchases/catalog work inside
the existing purchase-ingestion/purchases/dashboard and sourcing-catalog groups
(and existing core/daily/catalog compatibility groups). Existing EventBridge
schedules and cadence are not modified. Failures are visible through ordinary
scheduler job telemetry; other work can proceed using retained decline evidence.
New declines are not instant: they become effective after the next successful
offer import. This API supplies the latest offer state exposed by My eBay, not a
complete negotiation history; declines already absent before the first import
cannot be recovered by this feature. A relisted item with a different eBay ID is
a distinct listing. A later counteroffer does not erase a prior observed decline.

## Verification on September 8, 2026

- Live read-only import: 99 offers; 36 Declined, 29 Countered, 26 Expired, 8 Pending.
- Bounded impact preview: 769 stored open/Watch best-offer rows; 90 rows matched
  observed declines; 31 rows across 7 distinct listings would be suppressed.
  These counts include historical run copies and other presentation filters have
  not been applied; they are not 31 currently visible UI cards.
- Example: listing `307144877450`, ASIN `B00ARCWQOO`, declined $17 versus MBOP
  maximum $14.07; listing `257716145551`, ASIN `B097FP294Y`, declined $27 versus
  maximum $22.08.
- Zero production database writes during verification.
- 102 sourcing Python tests and 7 buyer-offer/import-stream tests passed.
- Node declined-offer tests passed (amount boundaries, reappearance, listing
  identity, currency/variation handling, Watch/history, batching, DB failure).
- `npm.cmd run build` passed. This is local compile/type verification, not
  verification of deployed Cognito-protected production behavior.

## Activation and rollback

1. Apply `supabase/migrations/20260908000000_mbop_declined_buying_offers.sql`
   to verified MBOP project `froeucjkcepuhgwisped` through the documented shared
   migration workflow. Run `supabase migration list` first and reconcile the
   complete shared ledger; never modify College Planner migrations. The exact
   additive SQL is in that file. No purchase/COGS backfill is required.
2. Run `.venv\Scripts\python.exe integrations/sync_ebay_buying_offers.py --apply`
   once and verify the retained evidence before web activation.
3. Commit/review the release, deploy scheduler using `scripts/deploy-scheduler.ps1`,
   and update only affected existing task targets to the new revision while
   preserving schedule expressions, timezones, state, networking and overrides.
   Capture current task/schedule configurations for rollback first.
4. Deploy web using `scripts/deploy-web.ps1`; confirm stability with
   `scripts/aws-web-status.ps1`, then verify opportunities at
   `https://mbop.midnightblueenterprises.com` through the authenticated browser.
   Compare the example listings and a still-eligible higher-offer listing.
5. Observe a scheduled offer import and the next catalog scoring run. Check that
   declines remain excluded and alternate listings can qualify. No broad resync
   or database-heavy historical rescore is needed for immediate API suppression.

Rollback uses the captured prior web task and scheduler targets. Leave the
additive evidence table/migration in place; prior revisions ignore it. Do not
delete the table or historical purchase data as part of rollback.

The earlier item-only shipping floor changes and sourcing status report were
already uncommitted before this work; release review must account for them.

Reference: https://developer.ebay.com/devzone/xml/docs/reference/ebay/GetMyeBayBuying.html
