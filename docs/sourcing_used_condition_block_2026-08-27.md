# Sourcing Used-Condition Block

Date: 2026-08-27

## Trigger

eBay listing `147512155227` was presented as an open sourcing opportunity even
though the listing-facing evidence showed it was used-condition inventory.

Stored details:

- eBay Browse item ID: `v1|147512155227|0`
- ASIN: `B000NSH4YY`
- Opportunity ID: `c7c566cb-9e08-4bbc-aff9-ab8647bb8cf9`
- Candidate ID: `fd821c0a-7c71-4eb9-af6f-3614ced14b56`
- Stored eBay structured condition: `Brand New`, condition ID `1000`
- Listing title: `Command and Conquer 3 - Tiberium Wars [XBOX360][USED]`
- Seller description: `Disc is in great shape, and plays great too!`

## Fix

Sourcing now hard-blocks explicit used-condition signals from eBay
listing-facing fields even when eBay also reports structured condition ID
`1000`. Signals include `Used`, `Pre-owned`, `Like New`, and disc condition
language such as `disc is in` or `great shape`. `Very Good` is intentionally
not blocked by itself because sellers may use it to describe new-item packaging.

Changed files:

- `integrations/sourcing_match_rules.py`
- `integrations/score_sourcing_opportunities.py`
- `tests/test_sourcing_match_rules.py`
- `docs/business_rules.md`

## Production Data Correction

The existing opportunity was rescored and updated in Supabase:

- status: `rejected`
- opportunity type: `no_profitable_source_found`
- diagnostic: `condition_mismatch`
- flags: `Blocked: not new condition signal: disc is in, great shape, used`

## Verification

Local verification:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_sourcing_match_rules
.\.venv\Scripts\python.exe -m py_compile integrations\sourcing_match_rules.py integrations\score_sourcing_opportunities.py integrations\ebay_sourcing_search.py
```

Results:

- `53` sourcing match tests passed.
- Python compile check passed.

## Deployment

Commit:

- `02a3300` - `Block used-condition sourcing candidates`

Scheduler deployment:

- image tag: `scheduler-02a33007ce7c`
- image digest:
  `sha256:c48e3946633c0ee99e8ac09e26bbc46476fe041fd1c0f7aabb67894628dceacd`
- task definition:
  `arn:aws:ecs:us-west-2:297464765814:task-definition/mbop-scheduler-task:68`

EventBridge schedule update:

- schedule: `mbop-sourcing-catalog`
- task definition:
  `arn:aws:ecs:us-west-2:297464765814:task-definition/mbop-scheduler-task:68`
- schedule expression preserved: `cron(10 0 ? * * *)`
- timezone preserved: `America/Los_Angeles`
- command preserved: `python run_all_syncs.py --group sourcing-catalog`
- CPU/memory override preserved: `1024` / `2048`
