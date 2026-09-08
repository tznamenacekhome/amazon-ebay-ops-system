# Sourcing log review — September 8, 2026

Read-only review; no code, schedules, telemetry statuses or production data changed.

## Latest scheduled run

Scheduler run `74bb5762-5031-4914-80cd-aeb6d8f1ffc4` ran September 8,
00:10:55–02:02:00 Pacific. All four jobs reported success: discovery,
Browse availability, Trading availability fallback, and matching refresh.

Discovery `e1d3412b-5bbb-4952-9469-e00dd1eed9b0` searched 1,581 ASINs,
recorded 2,872 candidate/opportunity rows (not all actionable buying leads),
and ended `cycle_completed`, 100% reported coverage, zero remaining ASINs.
Matching prepared 18,917 examples and rescored 2,872 candidates.

Complete CloudWatch stream review found 7,920 completed database HTTP requests
with zero HTTP error responses. Peak sampled task cgroup memory was 835.2 MiB;
peak Python RSS 803.2 MiB. There was one database-guard wait for low disk
headroom between discovery and availability; it recovered on the next attempt.
Minimum sampled database free data disk was about 1.16 GiB. Periodic
`database_pressure` events are measurements, not 111 separate failures.

PostgreSQL start time remains `2026-09-07T08:31:21.844266Z` as verified on
September 8 at 16:35 UTC: no subsequent restart. This supports the reduced
write/scoring amplification and memory fixes under a real overnight workload.
It does not establish a conclusive kernel-level cause for the original restart.

## Previous manual quota-consuming run

Run `aff5d5c4-5d6b-400b-ace9-5da15f7467b9` ended degraded September 7 at
19:51 Pacific. Discovery searched 558 ASINs, depleted its starting 1,950-call
quota to zero, and received eBay HTTP 429 after six attempts. Stop reason was
`ebay_rate_limited`, not a database crash. Its 3,224 completed database requests
had zero HTTP error responses. Browse availability then reported 250 row-level
errors despite job status `ok`; Trading fallback and matching succeeded.

## Assessment / remaining issues

The latest OK is supported by actual completed work. Treat the prior crash
mitigation as validated for one full scheduled run, but retain monitoring.
Database disk headroom is still tight enough to activate the guard.

Quota handling/status accounting remains separate outstanding work:
- Exhausting requested daily credit produces a failed/degraded discovery run.
- Availability can report job success despite all checked rows failing.
- Latest discovery's local counter says 5,371 Browse calls, while eBay's saved
  ending quota says 500 remained out of 5,000. The stream also includes a local
  detail-budget pause before eventual cycle completion. These counters should
  not be represented as an independently verified number of billed calls.

Next operational check: monitor subsequent nightly runs for database guard
waits, restarts, HTTP errors and completed queue coverage. Review quota/error
classification separately; do not weaken database guards to hide warnings.
Raw evidence: `logs/diagnostics/sourcing-status-20260908/` (Git-ignored).
