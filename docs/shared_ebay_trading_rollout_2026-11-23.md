# Shared eBay Trading enrichment rollout — November 23, 2026

## Result and architecture

Shared Trading enrichment is enabled for sourcing. Browse still owns discovery.
Both catalog sourcing and Flipmine use `ebay_listing_evidence.py`; normalized
evidence feeds the existing matcher/economics. See
[provider, quota and cache design](shared_ebay_listing_enrichment.md).
No new service, infrastructure, application credentials, Feed/bulk access or
marketplace mutations were introduced.

Important files:

- `integrations/ebay_listing_evidence.py`: normalization, shared router, contextual
  shipping, conservative variation/currency/availability handling and cache reuse.
- `integrations/ebay_trading.py`: read-only transport, shared reservations, bounded
  retries and HTTP/XML rate-limit handling.
- `integrations/ebay_browse_budget.py`: both resource pools, observations, cache,
  shared circuits and deduplicated in-app alerts.
- `integrations/ebay_sourcing_search.py`, `import_flipmine.py`, and the availability
  refresh: shared provider integration and durable per-row waits.
- Existing buyer purchases/tracking/order-problem and offer readers: shared
  Trading accounting, preserving their API and workflow behavior.
- `web/app/api/sourcing/ebayQuota.ts` and `web/app/system-health/EbayApiQuota.tsx`:
  quota, reservation, reset, circuit and job/event visibility.

## Migration and deployment

Applied `20261124043618_mbop_shared_ebay_trading_enrichment.sql` through linked
`supabase db push` after complete migration-list reconciliation and a dry run.
Target verified: `amazon-ebay-ops`, `froeucjkcepuhgwisped`, ACTIVE_HEALTHY.
The complete local/remote ledger matched after application. The CLI emitted a
pg-delta catalog-cache certificate warning; migration application and ledger
verification succeeded. New objects are service-only with RLS; security-advisor
review found no notices naming the new quota objects.

Production AWS account `297464765814`, region `us-west-2`:

- Final worker: `mbop-scheduler-task:176`, code `cfeb95830aca`.
- Worker image digest:
  `sha256:31c566d1d06d6bd9918319348f603038985ebb17cd77c63870c4c3bdec0dbc48`.
- Web: `mbop-web-task:230`, code `1ffadb25b13b`; ECS rollout COMPLETED,
  desired/running 1, pending 0, ALB target healthy.
- Web image digest:
  `sha256:76df49eb154b0fff799803ea3f53c972d03bf93ab23e638bbeb5fc995233c922`.
- Affected schedules: sourcing-catalog, keepa-catalog-priority, both
  purchase-ingestion schedules and the two explicitly approved order-problem
  schedules use worker 176. Commands, schedules, permissions and credentials
  remain unchanged. Other schedules were not retargeted.
- The existing on-demand ZFI purchase pin is 172, which includes the identical
  shared operational Trading accounting; subsequent worker changes affect sourcing.
- `MBOP_EBAY_TRADING_ENRICHMENT=true` enables the provider. Turning it off restores
  Browse enrichment while retaining shared admission. No migration rollback needed.

The Windows Docker credential helper failed before deployment. An isolated
temporary file-backed Docker login completed the normal deployment; existing
Docker credentials/settings were not modified. Its temporary auth file is removed
after deployment.

## Provider selection, protections and freshness

Fresh compatible evidence precedes network calls. Prefer Trading for standard
known item IDs. Use Browse for discovery, exact variations and evidence Trading
cannot establish. An unverified parent variation or foreign currency cannot be
pre-excluded using parent identity/price. Confirmed sold/ended listings cannot
enter catalog candidates. A provider failure is not a product mismatch.

All Trading methods share one application/resource admission lock. Delayed
Analytics cannot restore locally reserved calls. Defaults protect 10% for
operations and an additional 20% of Browse for discovery. While a saved import is
outstanding, each sourcing class receives half of nonessential capacity. Settings
are configurable percentages of the actual observed allowance, not assumed API
limits. Essential purchase/order calls still obey the real shared cap.

Cache identity includes application, marketplace, listing/exact variation, buyer
context and quantity. Both providers reuse the existing normalized cache. TTL is
configurable within 30–900 seconds; stable evidence was not extended to a longer
retention period. Conflicting search evidence and older adapter versions require
refresh. Candidate pair identity remains item + ASIN. Existing Buy List listing
deduplication remains intact.

Identity/condition and existing economics precede calculated-shipping requests.
Flat shipping needs explicit USD costs, applicable US/Worldwide inclusion and no
unresolved exclusion/surcharge. Missing cost never becomes zero. Calculated
shipping uses configured country/ZIP/quantity. Unknown shipping remains Watch or
excluded by the existing evaluator, never an unconditional buy.

## Validation

- Python targeted suite: 242 collected, **209 passed**, 33 isolated database cases
  skipped in that invocation. Includes 31 adapter/router/business regressions.
- Disposable PostgreSQL: **7 new shared-admission/concurrency tests and 13 existing
  Flipmine transaction/checkpoint tests passed**. No production test database,
  published port or synthetic return/purchase was used.
- Frontend: **8 targeted suites passed**, including existing Buy List/Closest
  Excluded, blocks/holds, FM provenance, completion, and competing-ASIN listing
  deduplication behavior.
- Targeted ESLint: zero errors; two pre-existing unused-component warnings in
  System Health. Local and deployed Docker Next.js builds/type checks passed.
- Final production adapter smoke: two saved listings, both Trading, two GetItem
  and one GetItemShipping request; immediate replay needed no detail requests.
  Item `137956960282`: $20.23 + $6.85 calculated shipping, one available, New,
  seller present, 113-character description. Item `860171377780`: $6.63 + $5.99
  flat shipping, one available, New, seller present, 514-character description.
- Equivalent Browse-shaped fixture evidence produces the same shared match and
  economic decisions. Live same-listing Browse parity could not be tested because
  its daily quota is exhausted; no retry loop was used to test it.
- Trading variation evaluation remains disabled; exact/ambiguous variations stay
  on Browse or pending. No live variation equivalence is claimed.

## Production recovery observation

Original run `c7ba90ae-7cdd-4b87-a831-c2ff33682adf`, tab
`97fc964e-a4f2-43bb-a5ca-90381d1352b8`: all **558 unique pairs/listings retained**.
No source tab reimport or automatic discovery occurred. Original snapshot and
provenance are preserved; completed evaluations are skipped during recovery.

The first 180-second verification task exited 0 at its checkpoint. A second
verification task was deliberately stopped during final safety review, its
specific stopped-task lease released, and work resumed on final worker 176.
Current continuation task: `b0e15b4953e24e57b3bb9e27c906c8c8`, bounded to 600 seconds.
Existing scheduled saved-checkpoint recovery uses 900-second work windows.

Snapshot **November 23, 9:08 p.m. PST**:

- Running; 21 excluded, 2 evaluated, 535 pending. Zero failed rows.
- Two persisted opportunities were rejected by existing economics; no qualifying
  Buy List opportunity had yet been observed. Closest Excluded/browser counts
  have not been verified in production. Do not interpret this as import completion.
- 18 distinct listings had normalized Trading evidence; FM provenance was present.
- Import: 22 GetItem + 5 shipping requests; 10 preliminary exclusions and 2 cache
  hits recorded. Four Browse-capacity waits were recorded across the earlier
  checkpoints. Final code persists each row's provider/reset wait to prevent
  repeating that work before due.
- Other metered jobs: 15 offer-history Trading requests, 2 purchase-ingestion
  Trading requests and 6 adapter-smoke requests. These are deployment-era counters,
  not historical daily attribution.
- Browse: limit 5,000, consumed 5,100, remaining 0.
- Trading shared: limit 5,000, locally consumed/reserved 212, remaining 4,788;
  latest Analytics observation 211 consumed. Reset: November 24, midnight PST.

This demonstrates actual recovery through Trading while Browse is exhausted.
Actual successful Browse detail requests during recovery: zero. Eighteen distinct
normalized listings have been supplied without Browse; this is not a reconciled
counterfactual net-savings estimate. Earlier checkpoint retries and schema-version
refreshes are included in the Trading counts.

Final readback **9:10 p.m. PST**: worker 176 is RUNNING; 29 excluded, 2 evaluated,
527 pending, zero failed. Three pending Browse-only rows now have durable provider
wait markers. All six approved schedules were read back on revision 176. The
558-row source snapshot hash remains
`f60131aafdf2ccd6908fc2239f3942f0972166502f870ea26ba142eae4c1c13c`.

Expected savings: N eligible details can replace N Browse calls with N+C Trading
calls, where C requires shipping. The historical 3,616 detail attempts are a
potential shift, not a promise they all fit the protected Trading budget; 1,573
historical searches still require Browse. Capacity-aware fallback and deferral are
necessary. A full scheduled catalog production savings measurement awaits its
next eligible discovery run.

## Remaining verification and follow-up

Authenticated browser verification did not complete. After explicit operator
approval to open a new MBOP tab, Computer Use stopped because it could not
confidently determine Chrome's current URL. No further browser input was attempted.
ECS/ALB and database verification are complete; they do not prove the authenticated
System Health rendering or final Buy List/Closest Excluded presentation.

At `https://mbop.midnightblueenterprises.com/system-health`, verify the single
shared Trading row, operation attribution, Pacific reset, observed freshness and
pause state. At Sourcing, verify ongoing counts, FM badge and retained pending
rows. Once all evaluations/opportunities and presentation counts finish, verify
Complete; do not force it while capacity waits or review failures remain.

Implementation code head: `cfeb95830aca` (main feature `1ffadb25b13b` plus scoped
checkpoint/safety follow-ups). The deployment receipt is committed separately.
