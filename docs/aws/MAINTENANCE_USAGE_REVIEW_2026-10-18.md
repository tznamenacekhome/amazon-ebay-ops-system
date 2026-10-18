# Maintenance path usage verification — October 18, 2026

Read-only verification requested before migration work. Deprecation dates are
parent-supplied context, not independently researched in this review. No jobs,
provider inference calls, Orders API calls, schema changes, configuration
changes, or migrations were initiated. Existing sourcing edits were preserved.

## Result

| Path | Verified state | Last observed execution (Pacific, October 18) |
| --- | --- | --- |
| Orders v0 list orders | Active scheduled production dependency | 07:50:54.503 |
| Orders v0 order items | Active scheduled production dependency | 07:50:55.167 |
| Orders v0 single-order lookup | Optional `--order-id` path; recent execution not established | Unknown |
| RevSeller GPT-4.1-mini matching | Active scheduled AI inference, not just an enabled flag | 08:36:26.323 completion counter |
| Manual eBay draft search-link AI | Manual/unscheduled; recent execution not established | Unknown |

These are last observations in the inspected representative streams, not a
claim that no later execution is possible. Log retention is 30 days. A broad
seven-day scan was stopped because it was slow; it produced no completed
aggregate. Supplemental 24-hour searches reached a 20-page cap with no matches
for single-order lookup or the draft script and were **incomplete**. They cannot
establish absence of use. No historical last-execution date is asserted for
those two optional/manual paths.

## Deployed configuration and artifact evidence

STS verified account `297464765814`. Enabled EventBridge schedules inspected:

| Schedule | Expression | Timezone | Group |
| --- | --- | --- | --- |
| `mbop-amazon-sales-recent-catchup` | `cron(30 4 ? * * *)` | America/Los_Angeles | amazon-sales-recent |
| `mbop-amazon-sales-recent-day` | `cron(50 7,9,11,13,15,17,19,21 ? * * *)` | America/Los_Angeles | amazon-sales-recent |
| `mbop-purchase-enrichment` | `cron(35 8/2 ? * * *)` | America/Los_Angeles | purchase-enrichment |

All three use `mbop-scheduler-task:141`, container `mbop-scheduler`, image:

`297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler@sha256:bfab60ad62443b0bfa98be5f9362bc685dce034b062474858a890a902b60a80a`

Task definition and schedule overrides contain no `--ai-model`, no model
environment override, and no model-specific secret reference. Credential
values were not read. The exact image was already cached locally. An ephemeral
local container with `--network none --read-only` inspected source text only:

- Both `sync_revseller_sheet.py` and `price_ebay_draft_listings.py` default to
  `gpt-4.1-mini`, with `OPENAI_MATCHING_MODEL` and
  `OPENAI_DRAFT_PRICING_MODEL` override hooks respectively.
- Deployed `run_all_syncs.py` contains RevSeller's `--ai-review` registration;
  the manual draft script is absent from that orchestrator.
- Deployed Amazon client contains `/orders/v0/orders`.

The scheduled matching path therefore selects the deployed GPT-4.1-mini
default. Logs do not record the provider response's model identifier; actual
provider-side resolved-model/usage records were not queried. Manual CLI users
could supply a different model, and their invocation settings are not known.

## Orders: actual API calls and downstream consumption

CloudWatch group `/ecs/mbop-scheduler`, stream
`scheduled/mbop-scheduler/a4135722c9764d78bc61d7ec2587afdb`:

- 14:50:51.462 UTC: group `amazon-sales-recent` started, scheduler run
  `4ffe9c7f-2661-4359-825e-89fa8916d665`.
- 14:50:54.503 UTC: logged GET `/orders/v0/orders` (list orders).
- 14:50:55.167 UTC: logged GET order-items endpoint. Order identifiers omitted
  from this report.
- 14:50:57.773 UTC: order sync completed successfully, `orders=94 items=1`.
  The normal command uses `--apply`. Unchanged order items are skipped, so one
  fetched item does not imply the other orders have no stored items.
- 14:54:26.161 UTC: finance sync completed with 273 financial rows and 92
  transaction rows.
- 14:55:18.489 UTC: profitability completed with 120 rows.
- 14:55:26.594 UTC: ZFI business summary push completed for September 18 through
  October 18.

Source confirms normalization writes `amazon_sales_orders` and
`amazon_sales_order_items`, consumed by the observed finance/profitability jobs.
API code also reads these tables for Sales Orders, dashboards, sourcing, FBA,
and return recovery. Repository reads establish available consumers, not actual
browser visits; screen usage was not independently measured. Runtime downstream
job completions above establish this is not unused legacy ingestion.

The direct `get_order` operation is only used by this sync when `--order-id` is
provided. None of the inspected enabled schedules supplies it. The ordinary
scheduled job uses list-orders and order-items instead. Recent manual targeted
invocations remain unverified.

## RevSeller: actual AI decision and operational effect

CloudWatch stream
`scheduled/mbop-scheduler/1fd2f58518ee4c6d9ef10613dbfaabcd`:

- 15:35:42.178 UTC: group `purchase-enrichment` started, run
  `565dbe69-6486-4815-9042-7899b48649f2`.
- 15:35:44.458 UTC: `AI review enabled: True`; `Dry run: False`.
- 15:36:23.236 UTC: one purchase item scanned.
- 15:36:26.323 UTC: `skipped_ai_no_match: 1`,
  `matched_ai_with_system: 0`, `skipped_ai_error: 0`.
- `updated: 0`, `would_update: 0`, `errors: 0`; a diagnostic CSV was written
  inside the task.

The deployed code emits `skipped_ai_no_match` only after receiving a nonempty AI
decision whose decision is not `match`; no-candidate, disabled and failed
requests have different counters. This proves the inference/decision branch
was exercised, not just that AI review was configured. The client has an
in-process cache, so counters are not an exact provider-request count. This
run rejected the candidate and made no purchase updates. Successful accepted
matches would update the purchase item's ASIN, Amazon title and target price;
recent AI-accepted updates were not established by this bounded review.

## Manual draft workflow: do not assume active use

`docs/subsystems/ebay_draft_pricing.md` documents a manual spreadsheet workflow:
title column D to optimized sold-search hyperlink column E, with manual price
columns untouched. Despite the script filename, it does not automatically
price or publish listings. It uses AI only when a key is available; otherwise,
or on provider failure, it falls back to heuristic search terms.

No inspected EventBridge target or deployed orchestrator invokes it. No
dedicated recent local draft log was found in the existing `logs` directory.
Local terminal history, provider usage records, and Google Sheet revision
history were not inspected. Thus the executable remains available but recent
human use and its effective model override are unknown. Do not migrate this
manual path based solely on repository presence.

## Follow-up boundary

Orders list/items and RevSeller inference are confirmed active dependencies
and merit migration planning before their parent-reported retirement dates.
That is a recommendation for subsequent work, not authorization exercised in
this review. Single-order and draft paths need usage confirmation if separate
migration scope is proposed. No code or deployed configuration was changed.
