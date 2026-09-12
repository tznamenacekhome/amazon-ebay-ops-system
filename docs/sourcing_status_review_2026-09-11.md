# Sourcing failure review — September 11, 2026

Read-only production investigation. No schedules, telemetry, or production data changed; no discovery retry launched.

The 00:10–00:32 Pacific catalog run `3bb1ceaa-6bcb-4d33-90eb-67147a934877` finished degraded. Discovery searched its first 50 ASINs, then stopped with `scoring_chunk_failed`; matching refresh subsequently exhausted the database capacity wait. Buyer declined offers and both listing availability jobs reported OK.

The complete CloudWatch stream for task `44dd804cc75844adbe422fd611019856` contains 19 `low_available_memory` and five `low_swap_headroom` guard waits. Periodic samples recorded available database RAM as low as 186.3 MiB and free swap as low as 11.3 MiB out of approximately 1 GiB. The captured database HTTP responses contain no errors. Sampled `pg_up` remained 1 and host OOM counters were zero. This supports a protective capacity stop; it does not prove a database crash or identify which shared-database workload caused the pressure.

The preceding manual run `3649751b-d825-4254-a323-374a553691a2` completed all five jobs successfully September 10, 19:42–21:30 Pacific. The September 10 nightly run had also stopped on a capacity guard; September 8 and 9 nightly runs were OK.

At September 11 10:20 Pacific, a fresh metrics request passed the existing capacity thresholds: approximately 730 MiB available RAM, 513 MiB free swap, and 1.39 GiB free data disk. A bounded scheduler telemetry read also succeeded. Current recovery does not establish that a complete sourcing rerun will stay within capacity; disk space remains tight. Disk IO Budget was not measured in this investigation.

Next remediation should examine concurrent overnight workloads and database memory consumption before another full catalog run or any capacity change. Retain the current guard thresholds. Do not mark catalog coverage current based on the successful availability jobs or the present health probe.

Raw evidence is retained in the ignored `logs/diagnostics/sourcing-status-20260911/` directory (`logs.json` and `current-health.json`).
