# Keepa Weekend Token Reserve - 2026-09-19

## Behavior

The scheduled `keepa-catalog-priority` cycle protects 150 Keepa tokens on
Saturday and Sunday in `America/Los_Angeles`. This is enough for a lightweight
Send to Amazon pricing refresh of 150 ASINs at one token per ASIN. On Monday
through Friday the reserve is zero, so the catalog cycle can use the full token
pool.

The scheduled offer-enriched catalog cycle subtracts the active reserve before
checking its minimum balance or calculating its adaptive ASIN limit. Its token
estimate was raised from four to twelve tokens per ASIN based on production
usage, preventing a selected offer batch from consuming the protected balance.

## Deployment

- Source commit: `14c0f42d00639d1a7c01f539133c1a1b731f42f9`
- Scheduler task definition: `mbop-scheduler-task:104`
- Image digest: `sha256:0fab2a5297ff548e994c743965bf9c1d4248bab49a3dbab78559612a63926c83`
- Schedule: `mbop-keepa-catalog-priority`
- Cadence: `rate(30 minutes)` unchanged
- Command: `python run_all_syncs.py --group keepa-catalog-priority`

Only the Keepa schedule target moved from scheduler revision 76 to revision
104. No web deployment or schema migration was required.

## Verification

Five focused unit tests passed, including Pacific-time Friday/Saturday and
Sunday/Monday boundaries. Python compilation, scheduler group listing, and
`git diff --check` also passed.

Production verification run `fa4506d6-ed6a-4b6b-b35d-b94f4bd2dd1c` ran on
Saturday, September 19, 2026. Its live token balance was 62. The job reported:

```text
tokens_left=62 reserve=150 spendable=0 timezone=America/Los_Angeles
```

It correctly skipped the product request, used zero Keepa tokens, preserved the
catalog cycle at 2,439 covered and 2,184 remaining ASINs, and exited `ok` in
33.863 seconds. Because the earlier pricing incident had already depleted the
pool before this deployment, the balance was initially below the reserve. The
scheduled catalog job now spends nothing until the pool replenishes above the
protected balance.
