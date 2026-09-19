# Web161 and ZFI Management P&L Deployment — September 19, 2026

Production deployment completed from commit
`36a248a1e5f1819a9a5ecb7e5f6e1a878769b454`.

## Web runtime

- ECS task definition: `mbop-web-task:161`.
- Image: `297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-web@sha256:e6462bfc4f41cb89f8b6a157f1884bacdf00534ef1a6212101a90692de0cb53d`.
- Build SHA variables: `36a248a1e5f1`.
- Service rollout: `COMPLETED`, desired/running/pending `1/1/0`.
- The sole ALB target is healthy.

This deploy activates the Purchases **Due by Saturday** metric. The production
RPC returned:

| As-of date | Through date | Units | Purchase dollars | Unpriced units |
| --- | --- | ---: | ---: | ---: |
| 2026-09-19 | 2026-09-19 | 13 | $273.07 | 0 |
| 2026-09-20 | 2026-09-26 | 18 | $400.17 | 0 |

The ECS image compiled successfully and is serving production. An authenticated
browser session was not available for an interactive UI check; ECS rollout,
target health, exact build SHA, and the production backing RPC were verified.

## Scheduler runtime

- Image: `297464765814.dkr.ecr.us-west-2.amazonaws.com/mbop-scheduler@sha256:a47b11f4d67f689341794bed56074e22d9f2907798061d7dd37516d6e58ee91c`.
- Scheduler100: sales/FBA configuration inherited from scheduler97.
- Scheduler101: finance-refresh configuration inherited from scheduler98,
  including `MBOP_FINANCE_PAYLOAD_ARCHIVE=1`.
- Scheduler102: latest manual-launch configuration inherited from scheduler99,
  including `MBOP_SOURCING_PHASE3=1`.
- All revisions preserve `CLOUD_DEPLOYMENT=true` and
  `LOCAL_SYNC_ENABLED=false`.

All 20 EventBridge schedules were compared before and after. Exactly seven task
references changed:

- `mbop-amazon-sales-recent-day` and `-catchup` -> scheduler100;
- `mbop-fba-inventory-daily` and `mbop-fba-shipments-active-window` ->
  scheduler100;
- all three `mbop-finance-refresh-*` schedules -> scheduler101.

Expressions, time zones, enabled state, commands, retries, networking, resource
overrides, and cadence are unchanged. The other 13 schedules are unchanged.

## Bounded production refresh

The normal ECS runtime ran these steps serially for September 1-18:

1. Finance task `1fabf5a5b2e24666a59c979c702b3877`: exit 0, 562 normalized
   financial rows, 190 transaction rows, zero order-finance failures.
2. Profitability task `627a5ef9f2eb4117a4fde6e411453f2d`: exit 0, 162 rows.
3. ZFI push task `c2abc5a67e31445eb78f4a7bc8088ca8`: exit 0.

Every task ran image digest `sha256:a47b11f...` from commit `36a248a`.

## ZFI production readback

- Generated at: `2026-09-19T19:12:16.650797Z`.
- Payload version: `business_finance_replacement_v3`.
- Row and payload schema version: `2026-09-17`.
- Current-month period: September 1-18, 2026, America/Los_Angeles.
- Top-level management period: September 1-18, matching the explicit push.

Verified current-month and top-level management values:

| Field | Value |
| --- | ---: |
| Units sold | 134 |
| Gross sales / revenue | $5,681.38 |
| Acquisition COGS | null |
| Marketplace fees excluding fulfillment | $1,089.50 |
| FBA fulfillment | $548.27 |
| Verified MFN shipping labels | null |
| Refunds / returns | null |
| Refunds / returns observed | $103.25 diagnostic only |
| Gross profit | null |
| Net profit | null |

The source cohort independently contains 129 shipped, non-replacement rows and
134 units with the same $5,681.38 gross sales, $1,089.50 marketplace fees, and
$548.27 FBA fulfillment. The single MFN row lacks a verified Veeqo label, so
shipping-label cost remains null rather than being copied from fulfillment.
Warnings explicitly describe the missing label, incomplete acquisition COGS,
and uncertified refund ledger. Refund semantics were not changed.

The existing trend windows remain present with management objects:

| Window | Start | Gross sales | Legacy units |
| --- | --- | ---: | ---: |
| 30d | 2026-08-20 | $8,775.27 | 87 |
| 90d | 2026-06-21 | $25,761.74 | 316 |
| YTD | 2026-01-01 | $82,373.57 | 1,688 |

The current month starts September 1 while 30d starts August 20, confirming the
calendar month was not implemented as a rolling window.

## Source preservation

Before/after hashes for ten-row purchase, purchase-item, and pre-September
profitability samples are identical. The recalculation refreshed 57 derived COGS
consumption rows for orders purchased between September 1 and September 18; zero
refreshed rows belong to orders before the bounded September start. Acquisition
cost values were preserved. No historical purchases, purchase items, COGS, or
profitability rows were modified, and no FIFO allocator ran.

No migration was required for the ZFI repair. The previously applied additive
Saturday-stat RPC migration was not reapplied.
