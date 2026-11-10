# Non-eBay receipt intake

Initial deployment: approved and deployed 2026-11-09 (web212, worker164).

## Draft review improvements (2026-11-09)

The draft displays ASIN, sell price and automatically recalculated backend landed
cost. Platform/condition and currency controls are removed; existing extracted
platform/condition and USD validation remain internal. The acknowledgment
checkbox and its text are removed. Save remains subject to backend validation.

On opening, the server tries exact matches in existing MBOP Amazon SKU, MF offer
and reviewed match records. It fills a unique ASIN and a suggested sell price
from the existing metadata resolver, without replacing a manual price or ASIN.
Uncertain matches remain blank with a Search Amazon link. Game platform guards
remain enforced using backend/extracted platform data. This uses cached Amazon
records, not a new live Amazon catalog query; the first 30 product lines receive
automatic lookup per request, and broad/truncated matches are not auto-selected.

Known non-resale packing/handling fee lines move to Other charges and are
allocated across merchandise. A known fee removed from a draft can be recovered
from the immutable original extraction when it explains an outstanding gap.
Arbitrary missing products are never reclassified from a numerical difference.
Charge lineage is retained in `charge_lines`, and preparation is idempotent.
Example: Rainforest Flora invoice INV/2026/00714 has 50 Tilly Tacker units at
$300 merchandise + $23 shipping + $10 packing = $333, or $6.66 landed per unit.
The packing charge creates no inventory.

Follow-up SQL: `20261110040733_mbop_receipt_review_costs_and_matching.sql`. It
replaces the invoker cost/save RPCs, adding allocated charges and persistence
of reviewed ASIN, Amazon title and target sell price. Existing imports, exact
unit-cent allocation and duplicate-save locks remain in place.

Validation includes 11 isolated PostgreSQL transaction tests, the TypeScript
receipt preparation/matching test (removed fees, repeated preparation, real
supplies, ambiguity, game platform protection and manual prices), focused lint
and a production build. The operator's existing draft is inspected read-only;
no purchase is saved by deployment or verification.

## Operator workflow

Purchases -> Non-eBay purchases -> Upload receipt / paste screenshot. Choose a PDF,
PNG, JPEG or WebP, drag a file, or click the paste area and press Ctrl+V. One order
per document, maximum 12 MB and 100 product lines. Originals remain private in
`mbop-purchase-receipts` and are sent to the existing OpenAI integration for
extraction. The UI explicitly discloses this. Unsupported formats such as HEIC
must be converted first.

Extraction creates a persistent draft, never a purchase or physical inventory.
The existing ECS scheduler task runs the extraction command on demand (no new
service or schedule). Startup can take a minute. Close the progress window and
reopen the draft later. Failed extraction can be retried or reviewed manually.

Review supplier, actual purchase date, order reference, currency, all product
lines, quantities, conditions, platform and resale flags. Unknown fields remain
blank; verify before entering zero. Merchandise line totals include line-specific
discounts and exclude order-wide discount, shipping and tax. The receipt total
must reconcile. Only USD is supported. Non-resale items retain their share of
costs but are explicitly excluded from resale reports and operational queues.
ASIN and Amazon sell price are established through existing matching/Receiving,
not guessed by the receipt extractor. Purchase date is not the warehouse date.

For a one-product invoice showing only quantity and the grand total (such as the
Eastern Leaf receipt), explicitly select the grand-total-only checkbox. The
backend allocates that total to its units while leaving merchandise subtotal,
shipping and tax unknown. It does not manufacture a zero breakdown. This option
is rejected for several products because their cost weights are not established.

Preview landed costs, then Save purchase. Save
draft preserves incomplete edits. Every dialog permits dismissal without saving,
regardless of missing fields; an upload completed after dismissal does not reopen
the review automatically. The original extraction and final reviewed snapshot
are retained separately.

Saved items start as Ordered. A narrow Receiving view includes receipt-entered
Ordered resale items for explicit physical verification, without inventing a
carrier delivery event. Receiving links search by the stable purchase ID. The
existing receive -> ASIN/marketplace -> listing preparation path remains in use.
The original Purchases tab remains the combined operational item workspace;
the new tab lists receipt drafts and non-eBay supplier orders with server paging.

## Cost and retry invariants

`mbop_purchase_intake_costs` is the shared server-side authority for preview and
save. Shipping, tax and order-wide discounts are allocated by merchandise value.
For all-free merchandise, quantities supply the weights. Largest remainder
allocation preserves exact order cents. Because `purchase_items.unit_cost` is
numeric(12,2), uneven per-unit division creates at most two item allocations for
one receipt line. Example: $172.91 for 20 units becomes 9 at $8.64 and 11 at $8.65,
not 20 at a rounded average that changes total acquisition cost. Both rows retain
the same original receipt line and draft lineage. The preview shows the weighted
average, while ordinary purchases/reporting use their authoritative stored costs.
The historical MF opening-lot precision is unaffected.

The save RPC locks the draft and creates the parent purchase, item allocations,
cost snapshot and saved marker in one transaction. A saved draft returns the
original purchase ID on retries, without adding rows. Document SHA-256 is unique;
distinct scans with the same nonblank supplier/order reference are serialized
and rejected when already recorded. Without a supplier reference, different
images of the same transaction cannot be conclusively deduplicated; the operator
must review existing purchases. Uploads do not match or amend historical records.
No eBay supplier is accepted in this intake, protecting eBay import ownership.

Dispatch and extraction have separate database leases. Concurrent dispatches are
bounded for two minutes; an extraction worker claims once for fifteen minutes.
Each worker update checks its token and current status so a late response cannot
overwrite a newer attempt or a saved purchase. RunTask uses an idempotency token.
Original objects are immutable content-addressed paths. Reuploads reuse the
existing draft. Storage upload and the draft insert cannot be one transaction;
an unsuccessful insert can leave a private orphan object (a later identical
upload reuses it). No automatic deletion or retention job is introduced.

## Implementation and security

- `web/app/purchases/NonEbayPurchases.tsx`: bounded order/draft lists, uploads,
  paste/drop, extraction progress. `ReceiptReview.tsx`: editable review and costs.
- `/api/purchase-intake` and `/api/purchase-intake/[id]`: server-only Supabase
  access, existing same-origin/ALB mutation checks, magic-byte/size validation,
  60-second private original-document download URLs, worker launch and save.
- `integrations/purchase_receipt_intake.py`: strict structured output with the
  existing Responses API and `gpt-6-luna`; optional `OPENAI_RECEIPT_MODEL` override.
  `store=false`; no tools, external URLs, document instructions or ASIN inference.
  Unknown amounts stay null. Bounded provider retries; no sensitive provider body
  or original document data in logs. Extraction is review-only.
- `20261109030118_mbop_non_ebay_purchase_intake.sql`: private bucket, service-role
  draft table, invoker RPCs and Receiving view. No browser Supabase access or
  storage object policies. Anonymous/authenticated database access is revoked.
- Existing scheduler `OPENAI_API_KEY`, network and web RunTask/PassRole permissions
  are reused. Receipt processing adds no recurring broad synchronization.

Official interface references checked for this implementation:
[file/PDF inputs](https://developers.openai.com/api/docs/guides/file-inputs),
[structured output](https://developers.openai.com/api/docs/guides/structured-outputs),
[Luna modalities and Responses support](https://developers.openai.com/api/docs/models/gpt-6-luna).

## Validation and activation

Focused checks:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -p test_purchase_receipt_intake.py
.venv/Scripts/python.exe tests/test_purchase_intake_transactions.py
cd web
npx.cmd eslint app/page.tsx app/purchases/NonEbayPurchases.tsx app/purchases/ReceiptReview.tsx app/purchases/receiptTypes.ts app/purchases/PurchasesTable.tsx app/purchases/PurchaseDetailDrawer.tsx app/purchases/types.ts app/api/purchase-intake
npm.cmd run build
```

The PostgreSQL tests start a disposable postgres:17 container without publishing
a port. They cover exact unit allocations, weighted charges/discounts, free
merchandise, simultaneous saves, same-invoice overlap, invalid/unknown totals,
worker leases, source lineage, resale exclusions, Receiving eligibility and RPC
access denial. Python extraction tests cover PDF/image payloads, invalid/oversize
files, transient retries, unknown amounts, credential failures and incomplete or
refused responses. Receiving's existing 25 API lint errors and 2 page lint errors
are unrelated; comparison against HEAD confirmed identical findings. All new
intake files pass focused lint. The real configured `gpt-6-luna` API successfully
extracted a synthetic PDF's supplier, invoice/date, quantity, merchandise,
shipping/tax/discount and $22 total; no purchase or inventory was created.

Initial private-bucket approval was received and the initial migration is applied.
For each follow-up migration, verify project `froeucjkcepuhgwisped`, run `supabase migration list --linked`,
reconcile the entire shared migration ledger, and apply the committed migration
through `supabase db push --linked`. Do not apply it as ad-hoc remote SQL.

Build from an isolated clean checkout of this commit: the operator workspace
contains unrelated shipping changes that must not be deployed with this feature.
Use the normal AWS scheduler Dockerfile/ECR/task-definition rollout, then pin
web environment `MBOP_RECEIPT_TASK_DEFINITION` to that new worker task revision.
No saved scheduler cadence or existing EventBridge targets need changing for
receipt extraction. Deploy web using the documented AWS web workflow, confirm
the stable service with `scripts/aws-web-status.ps1`, and verify authenticated
production UI upload/paste, draft reopen, totals preview, dismissal, saved-source
links and Receiving access. Do not create fictitious production purchases for
verification. Local build results do not constitute production verification.

Current limits: USD only; one document/order; no automatic ASIN inference,
shipping tracking import, historical stock reconciliation, automatic returns or
marketplace writes. AI extraction may need manual correction, especially cropped
screenshots, ambiguous discounts, or missing tax/shipping details.
