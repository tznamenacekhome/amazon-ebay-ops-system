# ZFI v3 production deployment — September 18, 2026

Deployment and production readback completed. The production payload is
`business_finance_replacement_v3`, schema `2026-09-17`.

## Runtime

- Approved implementation commit: `9e6d40d6bcf36212e158f6e89a0ed644a8bf50a1`.
- Final deployed commit: `0c94d3fb0b41` (adds only null-safe console formatting and
  its publisher-entrypoint regression test).
- Image: `297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler@sha256:b500966637beb7129b21f65e0cec24be09a2346a2a9e8fde3f8078379ac3b8ca`.
- Scheduler revision **97**: both `amazon-sales-recent` schedules,
  `fba-inventory-daily`, and `fba-shipments-active-window`.
- Scheduler revision **98**: all three `finance-refresh` schedules; preserves
  the existing finance payload archive setting.
- Scheduler revision **99**: latest family revision for existing manual web
  launches; preserves revision 93's configuration, including Phase 3.
- Web remains **159**, one running task, rollout `COMPLETED`. No web rebuild was
  needed: `_awsScheduler.ts` uses the unpinned scheduler family for these manual
  launches. The separate ZFI Buying purchase task pin remains revision 86.

All 20 schedule definitions were compared before and after deployment. Only
seven task-definition references changed. Expressions, timezones, state, retries,
commands, resource overrides, network settings and other configuration are
unchanged. The other 13 schedule targets are unchanged. Each registered task
configuration differs from its respective original (66, 88, 93) only by image.
No scheduler tasks remained active at final verification, so no earlier task was
pending a later v2 summary write.

## Production push

The normal integration ran directly in ECS, without running the surrounding
sync groups:

```text
python integrations/push_zfi_business_summary.py --generated-by aws-zfi-v3-release --apply
```

Task `3036de6343224634a32b4d0b864a54f9`, scheduler revision 99, exited **0**.
CloudWatch confirms the push completed at `2026-09-18 14:18:11.832 UTC`.
The latest MBOP row in ZFI `public.mbop_business_summaries` was read back from
project `rwlemrtlmtvljxtdhzcd` and verified:

- `generated_at`: **2026-09-18T14:18:10.960144Z**.
- `payload_version`: **business_finance_replacement_v3**.
- Row and payload `schema_version`: **2026-09-17**.

The first attempt on revision 96 exited 1 before any ZFI write because console
formatting did not support a null shipping cost. The fix preserves payload and
refund semantics. Initial revisions 94–96 are superseded by 97–99.

## Verified management values

| Field | `profitability_windows.current_month` | Top-level `management_pnl` |
| --- | --- | --- |
| Inclusive local period | 2026-09-01 through 2026-09-18 | 2026-08-19 through 2026-09-18 |
| Timezone / currency | America/Los_Angeles / USD | America/Los_Angeles / USD |
| `units_sold` | 145 | 233 |
| `gross_sales`, `revenue` | null | null |
| `cogs` | null | null |
| `marketplace_fees` | null | null |
| `fulfillment_costs` | null | null |
| `shipping_label_costs` | null | null |
| `gross_profit`, `net_profit` | null | null |
| `refunds_returns` | null | null |
| `refunds_returns_observed` | 103.25, diagnostic only | 163.18, diagnostic only |
| `refund_coverage` | unverified | unverified |

Current-month UTC bounds are `[2026-09-01T07:00:00Z, 2026-09-19T07:00:00Z)`.
The existing rolling 30d starts August 20, proving it was not repurposed as the
current month. The top-level requested period retains the CLI's existing
start-date convention; it is not the calendar-month object.

An independent bounded current-month read found 140 non-cancelled profitability
rows representing 145 units. Nineteen rows have no sale price and 84 have no
COGS. There is one merchant-fulfilled order without a verified label. Missing or
ambiguous FBA costs and missing/refunded fee rows also prevent complete cost
totals. The nulls are verified completeness behavior, not zero amounts or
successful full-period P&L totals. Source timestamps and all basis/warning fields
are present.

## Cost and refund checks

A complete current-month FBA sale sample has sale price **55.98**, acquisition
COGS **20.96**, marketplace fees **8.40**, FBA fulfillment **8.70** and shipping
labels **0.00**. Its stored financial events independently reproduce the 8.40
non-fulfillment fees and 8.70 FBA fees. Thus fulfillment is not copied into
shipping labels, and marketplace fees exclude fulfillment. Period shipping and
fulfillment totals are both null because source completeness is insufficient;
that does not mean two equal numeric costs were published. There was no verified
current-month Veeqo sample to assert a positive production label total.

Current-month observed seller refunds of 103.25 are explicitly diagnostic.
`refunds_returns` and management `net_profit` remain null. Warnings state that
order-scoped finance sync is not a complete posted-period ledger and that legacy
event IDs omit posting date and can collapse equal repeated refunds. No diagnostic
amount was promoted into authoritative contra-revenue.

## Compatibility and source preservation

All `30d`, `90d`, `ytd` keys and their gross sales, revenue, COGS, net profit,
ROI, units and added management objects are present. Verified legacy trend values:

| Window | Start | Gross sales | Legacy complete-row revenue | Legacy net profit |
| --- | --- | ---: | ---: | ---: |
| 30d | 2026-08-20 | 8463.17 | 2933.06 | 210.22 |
| 90d | 2026-06-21 | 25449.64 | 11784.85 | 494.69 |
| YTD | 2026-01-01 | 82061.47 | 64921.10 | 12379.40 |

These legacy trend values retain their existing semantics and must not replace
null management totals. YTD management begins January 1 in the business timezone.

The deployment and publisher run did not modify historical COGS, purchases or
other MBOP operational source data. The publisher's sole database mutation is
the outbound ZFI summary upsert. No source sync, profitability recalculation,
backfill, migration or refund-ingestion change was run. Ten-row before/after
samples each for historical purchase facts, COGS consumption and profitability
have identical hashes (30 sampled rows). This is bounded verification, not a
claim that unrelated normally scheduled activity was suspended.

Capacity preflight passed the existing pressure guard and a tiny MBOP read:
PostgreSQL up, 1.60 GiB available memory and 24.39 GiB available disk. The current
documented storage is gp3; capacity headroom does not guarantee sustained I/O.

Validation: **53 relevant Python tests passed**, including **21 publisher tests
inside the exact deployed image**. `git diff --check` passed.

Local evidence is under `tmp/zfi-v3-release/`: schedule snapshots, task mapping,
task exit/log evidence, ZFI readback, source hashes, independent sample checks,
capacity metrics and final runtime verification. No secret values are stored in
these evidence files.
