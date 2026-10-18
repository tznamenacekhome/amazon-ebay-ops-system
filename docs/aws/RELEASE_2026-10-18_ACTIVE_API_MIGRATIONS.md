# Active integration migrations — October 18, 2026

Scope is the production paths verified in
`MAINTENANCE_USAGE_REVIEW_2026-10-18.md`: scheduled Amazon sales ingestion and
RevSeller AI matching. Existing uncommitted sourcing UI/API work is excluded.
There is no web change or schema migration in this release.

## Changes

- Scheduled sales ingestion uses Orders API `2026-01-01` search with embedded
  items. Requests include only `FULFILLMENT,PROCEEDS,CANCELLATION`; buyer,
  recipient, payment and package datasets are not requested. The existing
  optional `--order-id` v0 path is unchanged.
- A projection adapter preserves MBOP's existing sales-order/item column
  contract. It maps statuses/channels/conditions, keeps second-precision dates,
  derives shipment counts only from supplied item quantities, and separates
  shipping discounts from item discounts. Explicit projection prevents new or
  unsolicited personal fields from entering stored raw payloads.
- Missing provider values retain known normalized database values, including
  payment method and flags omitted by the replacement API. Explicit zero/false
  values still update normally. Existing context reads remain bounded by order
  ID batches; item context is paginated without fetching raw payloads.
- Pagination repeats the search filters, handles the new token envelope, and
  fails on repeated tokens or a missing orders/items collection. No extra
  per-order API call is made for scheduled ingestion. Existing retry handling
  and unchanged-item skipping remain in use.
- RevSeller's default is `gpt-6-luna`, the official recommended replacement for
  GPT-4.1 mini. Responses structured JSON, prompts, platform restrictions,
  confidence threshold, cache, retry handling and the 25-review scheduler limit
  remain intact. The new default uses `reasoning.effort=none` for its focused
  classification role. `OPENAI_MATCHING_MODEL` / `--ai-model` overrides remain
  supported, and startup logs report the selected model without credentials.
  The manual draft-search workflow is unchanged.

Sources: [Amazon migration guide](https://developer-docs.amazon/sp-api/docs/orders-api-migration-guide),
[official API schema](https://github.com/amzn/selling-partner-api-models/blob/main/models/orders-api-model/orders_2026-01-01.json),
[OpenAI deprecation replacement](https://developers.openai.com/api/docs/deprecations#2026-10-14-gpt-4-series-model-deprecations),
[Luna model compatibility](https://developers.openai.com/api/docs/models/gpt-6-luna).
The requested general GPT-6 migration markdown guide could not be fetched;
implementation compatibility was verified from the fetched model page and live
bounded API evaluation instead. No prompt rewrite was required.

## Validation before deployment

- `python -m unittest tests.test_amazon_orders_2026 tests.test_revseller_model_migration tests.test_amazon_sales_profitability_fees`:
  19 tests passed after the canary correction. Coverage includes pagination/filter retention, no PII datasets,
  missing/repeated-response failure, status/channel/quantity mapping, monetary
  separation, preserved missing values versus zero, optional-path preservation,
  the applied sync's destination tables, platform separation and AI error gates.
- Live read-only comparison over two recent days: both APIs returned the same
  42 orders. Four item samples had no normalized item differences after the
  shipping-discount correction. For four stored-field comparisons, application
  of the missing-field preservation policy produced zero normalized header
  differences. Before preservation the only remaining 42-order header
  differences were omitted business/Prime flags; existing values are retained.
- Live six-case model evaluation against both models: all 12 decisions passed.
  Cases covered same-game matching, reprints, cross-platform rejection,
  different games/sequels, and sealed wording. The replacement accepted strict
  structured output and reasoning `none`; observed replacement latencies were
  approximately 1.9–2.6 seconds. These small fixtures do not prove universal
  semantic equivalence; keep existing conservative production decision gates.
- Five-order/one-page local dry run through the new Amazon API and real bounded
  database reads exited 0. All five had unchanged items, so no item rows were
  selected and no writes occurred. Item persistence was separately tested with
  the mocked apply-path regression test.
- No operational records were changed during these checks. Temporary parity
  fixtures and detailed model evaluation results are under ignored `tmp/`;
  no credentials or buyer/recipient datasets were stored in release evidence.

## Delivery plan and rollback

Commit and push only this migration's integration files, tests and review/release
documentation. Deploy from a clean detached worktree of that commit so unrelated
sourcing edits cannot enter the image. Use `mbop-scheduler-task:141` as the base
to preserve the configuration currently used by both affected workloads.

Batch 1 updates only `mbop-purchase-enrichment`; batch 2 updates only
`mbop-amazon-sales-recent-*`. The corrected Orders batch uses its own verified
image/revision as recorded below. Cadences,
networking, CPU/memory overrides, role permissions and secret references remain
unchanged. Do not retarget sourcing or other schedules. Verify bounded ECS
canaries and resulting schedule metadata/logs; no broad sync is needed as a
deployment check. Web revision 187 should remain healthy and unchanged.

Rollback consists of retargeting just these three schedules to their captured
prior revision 141 with `scripts/update-scheduler-schedules.ps1`, using exact
schedule prefixes. This restores the previous model/API behavior without a
schema rollback. Keep v0's retirement deadline in view; rollback is temporary.

## Canary correction before completing delivery

Revision 144 passed the AI and five-order dry-run ECS canaries. The subsequent
five-order apply canary exited 0 and retained all normalized order headers, but
the exact before/after check found four item shipping-tax fields changed from
null to zero when the provider supplied item tax without a shipping charge.
Amazon sales schedules were temporarily returned to revision 141; purchase
enrichment remained on the verified revision 144. The adapter now leaves
shipping tax unknown when shipping price is absent, with a dedicated regression
test. The four introduced zeroes were restored to null, conditional on their
unchanged canary timestamp/value. The baseline audit then returned zero
normalized differences. The corrected deployment/canary results follow.

## Deployment receipt

Application commits, both pushed to `origin/main`:

- `3a19e4855a7f`: active Orders/model migration, regression tests and review/release
  documentation.
- `cc030cf24bb2`: no-shipping-charge tax correction and regression/documentation.

Both images were built from a clean detached deployment worktree, without
dirty-build overrides or the unrelated sourcing changes.

| Workload | Final definition | Image digest |
| --- | --- | --- |
| `mbop-purchase-enrichment` | `mbop-scheduler-task:144` | `sha256:cd883f48a606be26676e6687c0ba435629113029c4bc5fbf5607fc0a7ce3a2c1` |
| `mbop-amazon-sales-recent-catchup`, `mbop-amazon-sales-recent-day` | `mbop-scheduler-task:145` | `sha256:e5aff39fb725af93b5d12f64d2be99bc91303001f7ae4dc08c94116e481c7ec5` |

Revision 144 was based on 141; task-definition comparison confirmed the image
was the only configuration difference. Revision 145 was based on 144. Live
schedule comparison confirmed existing timing, timezone, enabled state,
networking/launch overrides and scheduler role were preserved. All three
affected schedules remain ENABLED. Only their task-definition targets changed.

Production ECS canaries:

- `52d2eb627ecd41cba77d6a2b6ca9db4d` (revision 144): synthetic AI decision
  using the deployed `gpt-6-luna` default; expected match, exit 0. No purchase
  mutations.
- `58a50640f9cf48ca85e90256fcd34689` (revision 144): one-page/five-order dry
  run with unchanged-item skipping disabled to exercise item normalization;
  orders 5, items 5, failures 0, exit 0, no writes.
- Initial apply `85e8123f4f06420b899a0e2d261ed542` (144): the null/zero issue
  above was detected and corrected before completing delivery.
- Corrected apply `c3d556f73f194fe3ae1385045f08b2d0` (145): at 09:02 Pacific,
  orders 5, items 5, failures 0, exit 0. Logs explicitly show
  `/orders/2026-01-01/orders`. Fresh database capacity guard passed before launch.
  A bounded audit over 42 existing orders and 43 items found five headers and
  five items refreshed, with **zero normalized field differences** from the
  captured baseline. Sync timestamps/import batch IDs and sanitized raw payload
  projections are expected refreshes and are outside that equality check.

At final verification, web revision 187 was COMPLETED, desired/running 1/1,
pending 0, and its ALB target was healthy. Sourcing remains on revision 143.
No web deployment or broad orchestration run was performed. Normal scheduled
workloads will use the updated targets; canaries verify their migrated paths,
not completion of an entire future finance/enrichment schedule.

Documentation-only follow-up records this receipt; no image rebuild is needed
for that follow-up. The optional targeted v0 order path and manual draft-search
model remain unchanged as instructed.
