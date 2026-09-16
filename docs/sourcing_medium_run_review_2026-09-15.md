# Medium sourcing recovery run review

Scheduler run `33f583b3-41bf-4f26-bea5-0fc2b2e81877` completed with status `ok`, no error summary, from September 15 19:04:38 to 21:10:05 UTC (12:04 PM to 2:10 PM Pacific), duration 7,527 seconds. All five jobs report `ok`. The CloudWatch stream ends with `Sync group completed successfully`. ECS no longer returns this historical task; completion is verified through persisted scheduler telemetry and its exact CloudWatch stream, not the earlier cached RUNNING snapshot.

| Stage | Duration | Result |
| --- | ---: | --- |
| eBay buyer declined offers | 6 seconds | Success |
| Daily catalog sourcing | 113 minutes 35 seconds | 1,553 ASINs searched, 4,703 Browse calls; coverage cycle completed; discovery summary reports 22 opportunities |
| Browse listing availability | 58 seconds | 250 opportunities checked; 243 active, 7 unavailable, zero errors |
| Trading availability fallback | 86 seconds | 88 listings checked; 67 available, 21 unavailable, zero API errors |
| Matching intelligence refresh | 9 minutes 20 seconds | 19,690 examples prepared, deduplicated to 19,612; 900 candidates rescored, 236 updated, zero inserted; four duplicate opportunities dismissed |

The 22 opportunities are the discovery-stage summary, not a verified final Buy List count after availability checks and rescoring. Search batches reported 911 candidate observations; the final rescore processed 900 candidates. Generic scheduler rows-inserted/deleted totals combine multiple printed counters and should not be interpreted as final opportunities or physical deletions.

All 2,498 non-diagnostic log events were read, with no pagination truncation. No failed/timeout/retry warnings were found. A separate exact-stream diagnostic query returned 125 database-pressure samples and no `database_guard_wait`, `db_request_error`, or database-pressure-error events. Across those samples: minimum available RAM 1.459 GiB, minimum swap free 99.9977%, minimum available disk 24.548 GiB, PostgreSQL up in every sample, and OOM count zero. Samples do not prove the absence of sub-sample spikes, but the complete run remained successful. The capacity upgrade resolved the previous blockers for this workload.

Catalog discovery consumed about 91% of total runtime; increasing capacity did not eliminate the time required for thousands of provider calls and batch scoring. Matching intelligence reported 1,705 dismiss examples missing notes; these are an evidence-quality limitation, not a runtime failure.

Review was read-only: no rerun, deployment or configuration change. Evidence: `tmp/ops-20260915/sourcing-medium-review.json` and `sourcing-medium-pressure.json`. Runtime remained scheduler93.
