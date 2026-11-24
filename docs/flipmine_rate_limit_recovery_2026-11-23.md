# Flipmine Browse quota diagnosis and recovery

## Confirmed production evidence

The diagnostic credentials were compared in memory against the deployed
production worker's Secrets Manager references. Client ID, client secret and
refresh token all matched. Tokens/credential values were not printed or changed.

At 7:33 p.m. Pacific on November 23, Developer Analytics `getRateLimits` returned:

| Resource | Limit | Count | Remaining | Window | Pacific reset |
| --- | ---: | ---: | ---: | --- | --- |
| `buy.browse` | 5,000 | 5,100 | 0 | 86,400 seconds | Nov 24, 2026, 12:00:00 a.m. PST |
| `buy.browse.item.bulk` | 5,000 | 0 | 5,000 | 86,400 seconds | Nov 24, 2026, 12:00:00 a.m. PST |
| `developer.analytics.app_rate_limit` | 5,000 | 1 | 4,999 | 86,400 seconds | Nov 24, 2026, 12:00:00 a.m. PST |

Both application-token and the existing user-token legacy-detail probes returned
HTTP 429, error 2001 / ACCESS / REQUEST: the resource request limit was reached.
Response Date headers were `Tue, 24 Nov 2026 03:33:53 GMT` and `03:33:54 GMT`.
Neither response supplied Retry-After or rate-limit headers. The authoritative
reset is `2026-11-24T08:00:00Z`. This confirms daily application quota exhaustion,
not an inferred short burst, wrong OAuth token, or a product-matching failure.
The probes were bounded; diagnosis did not launch a new import or buy anything.

The existing 558 ledger rows are 558 distinct listings and 484 distinct ASINs.
The stopped import is `c7ba90ae-7cdd-4b87-a831-c2ff33682adf`, tab
`97fc964e-a4f2-43bb-a5ca-90381d1352b8`. Six rows had quota failures and 552
remained pending; no opportunity evaluation had completed. Recovery preserves
these identities and the immutable snapshot, and retries the six quota failures
as pending work without deleting their last error or re-reading Google.

## Quota consumers and avoidable work

The dominant recorded consumer is Daily catalog sourcing. The run beginning
12:14 a.m. Pacific recorded 1,573 searches and 3,616 detail attempts, with 22
duplicate detail requests prevented. The subsequent 1:57 a.m. pass recorded
42 searches, 166 details and five retries. These historical MBOP summaries are
not a reconciled billing ledger; eBay's application-level counter is authoritative.
There was no per-resource, cross-job admission meter before this change.

Other Browse callers are sourcing listing availability and optional buyer-purchase
item enrichment. Buyer orders, declined offers and Trading availability fallback
use other API resources and must not be stopped just because Browse is exhausted.
The Flipmine attempt added six requests per failed listing (36 known attempts),
repeating the same exhausted resource while spending catalog/Keepa effort first.

Normal sourcing already applies summary filters and caches detail by item/context
inside a search run. Detail evidence that ultimately did not change a decision
cannot safely be removed blindly: it can still be required to verify a platform,
game identity or shipping assumption. The fix preserves these requirements.
Existing Flipmine seed preparation also excludes blocked, ineligible, suppressed
and stale-stock ASINs before requesting eBay details, through the shared rules.

## Bulk investigation

The [official Browse OpenAPI contract](https://developer.ebay.com/api-docs/master/buy/browse/openapi/3/buy_browse_v1_oas3.json)
defines `getItems` as Limited Release for selected partners, with up to 20 item
IDs per request. Single-SKU IDs can be constructed as `v1|legacyID|0` without
another API call; a legacy ID alone cannot identify a particular variation.
The endpoint supplies transaction-state information and contextual shipping, but
omits title, condition, localized item specifics and description required by MBOP.
Full-detail evidence would still be necessary unless sufficiently fresh evidence
already existed. A theoretical 28 bulk calls cannot replace 558 match evaluations.

The production application-token bulk probe at 7:33:55 p.m. returned HTTP 403,
error 1100 / ACCESS / REQUEST, insufficient permissions. This is an entitlement
restriction, not bulk quota exhaustion. Bulk retrieval is therefore **not enabled**;
the unused 5,000-call allocation does not prove endpoint access. No credentials or
permissions were changed to bypass this restriction. Enabling a nonfunctional
bulk path would add failures without reducing required full-detail calls.

## Implementation

Migration `20261124033839_mbop_ebay_quota_and_flipmine_recovery.sql` adds private,
RLS-protected resource state, per-job/day metering and a transient detail cache,
plus paused checkpoints and retry timestamps. RPCs use invoker security and
service-role-only grants. App keys are hashed identifiers, never credential values.

`ebay_browse_budget.py` coordinates request reservations transactionally across
jobs. Analytics refresh uses a shared lease; late observations cannot replenish
already reserved calls in the same window. All reported windows are considered.
Known exhausted resources are blocked until reset. Other workers see the same
block before issuing HTTP. Retry-After seconds and HTTP dates are honored without
the previous 90-second truncation. Temporary failures retain bounded exponential
backoff with jitter. Persistent 429 pauses after the first response; error IDs,
Retry-After and response time are retained as safe operational diagnostics.

The normal sourcing client, listing availability and optional purchase enrichment
share this gate. A paused enrichment does not prevent Trading purchase ingestion.
Normal discovery uses its existing reserve mechanism to protect the outstanding
saved-import listing count when eligible. Per-request reservations enforce it
across concurrent jobs, preventing the next catalog run from starving recovery.
The dynamic reserve becomes zero when no eligible checkpoint remains.

Detail reuse is keyed by app, marketplace, exact listing/variation ID and buyer
context, with a 15-minute TTL. Search summaries do not masquerade as full details.
Expired, mismatched or differently contextualized responses cannot be reused.
Only current full-detail calls populate the cache; existing old/uncertain raw
snapshots are not assigned invented freshness. The cache is bounded by incremental
expiry cleanup (up to ten expired entries per admitted call), not raw-history
expansion. Catalog and Keepa continue to use their existing freshness rules.
This is more conservative than the six-hour displayed-listing freshness ceiling
in the [current eBay API License Agreement](https://developer.ebay.com/join/api-license-agreement).

`import_flipmine.py` leaves quota-blocked rows pending and pauses the entire
checkpoint, before more catalog/Keepa work. It keeps completed outcomes intact and
caches terminal listing errors within the run as well as successful listing data.
`--resume-run-id` and `--resume-due` read only the saved snapshot. They cannot
discover new Google tabs. The existing global claim lease prevents duplicate
workers, and candidate/opportunity acknowledgement remains transactional.

Existing `sourcing-catalog` and 30-minute `keepa-catalog-priority` wakes run one
nonblocking saved-checkpoint recovery step, with a 15-minute work budget. A time
budget pause retains its checkpoint and yields to the next existing wake. No new
schedule, role, paid service or infrastructure is introduced. The normal catalog
and Keepa commands retain their existing settings. The original import will be
eligible after midnight, with recovery on the next existing wake (catalog at
12:10 a.m. Pacific, or an earlier due Keepa wake).

The Flipmine indicator distinguishes Processing, Paused, Resuming, Complete and
Failed. It shows completed/remaining counts, a Pacific retry timestamp, resource
allowance and per-job attempts since metering was enabled. System Health exposes
the same `ebayApiQuota` data for existing operational monitoring. A paused resource
does not become a successful empty import. Presentation still uses the normal
Buy List / Closest Excluded builder; hard mismatches remain excluded and FM
provenance is retained. Complete still requires successful persistence and list
presentation checks; partial/unverified work cannot advance full success.

## Expected savings and follow-up

This particular sheet has no duplicate listing IDs, so within-sheet deduplication
alone saves zero calls. Required fresh detail retrieval is at most 558 requests
before normal preliminary exclusions and cache hits. New cross-job/cache hits
save one request per reusable response. A known exhausted window now costs zero
Browse attempts, rather than six attempts for every remaining listing (up to
3,348 wasted attempts if all 558 rows had been allowed to continue). This is a
bound, not a claim that those requests actually occurred.

An Application Growth Check is advisable after the efficiency fixes: catalog
sourcing already approaches the general 5,000-call daily allocation before new
manual imports. Request adequate general Browse capacity, and separately discuss
partner bulk access if transaction-state refresh volume justifies it. Bulk access
alone will not replace missing identity evidence. See eBay's
[call limits and growth-check guidance](https://developer.ebay.com/develop/api/buy/api_call_limits).

Full production recovery cannot be asserted before eBay releases capacity. After
reset, verify terminal row counts total 558, zero pending/failed rows, stable
candidate/opportunity identities, shared list outcomes, FM provenance and successful
presentation completion. Keep actual review failures visible rather than forcing
the run to Complete. Do not treat local compile checks as production browser proof.

## Validation checkpoint

316 targeted Python tests passed: 33 Flipmine fixtures, 13 disposable PostgreSQL
transaction/concurrency tests, 57 eBay tests, 188 sourcing tests, 3 daily discovery
tests, 2 scheduler-capacity tests, 5 scheduler-diagnostics tests and 15 wholesale
seed tests. The disposable databases had no published ports and were removed.
Web route, real list presentation, badge and paused-status regressions passed;
TypeScript, targeted ESLint and the network-enabled Next.js production build passed.
Tests cover competing ASINs, missing/expired cache evidence, HTTP-date Retry-After,
zero-network exhausted-budget checks, one-attempt daily 429 handling, temporary
backoff, concurrency, UTC/window rollover, retained snapshots and duplicate-free
replay. No real return or purchase was created for testing.

Capacity preflight at 8:00 p.m. Pacific passed: PostgreSQL up, about 1.42 GiB RAM
available, 13.58 GiB filesystem headroom, 50% swap free. The new payload cache has
a short TTL and incremental cleanup; no broad history or snapshot backfill is run.
