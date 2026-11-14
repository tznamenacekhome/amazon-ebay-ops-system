# MF returns order failure recovery

The MF returns finance worker previously stopped at the first unavailable order lookup, preventing subsequent transactions and return-carrier tracking from running. Recent Amazon Sales repeatedly encountered order `114-8866055-7493009`, whose Orders API lookup returned HTTP 404.

Order verification errors are now collected per order and cached for the current run. Other transactions continue. Individual finance import failures are also collected while remaining transactions continue. Carrier tracking runs after transaction processing. Collected errors remain visible in the final failure summary, preserving degraded scheduler status while unresolved coverage exists. Later scheduled runs retry the unresolved data through the existing overlapping window.

The regression check covers a repeated unavailable order, a rejected finance import, a subsequent successful transaction, and carrier tracking. All 11 MF returns source tests passed.

Deployment uses the existing scheduler workflow scoped to `mbop-amazon-sales-recent-`. No schema migration is required.

Application commit `89b8ed9bb032` was pushed and deployed as scheduler task revision 166, image digest `sha256:37b091acd4997cf5eb5c7a1b737a5f9a589466a836ee2f9b1d21c4b5f43bcad6`. Both Recent Amazon Sales schedules reference revision 166.

Production verification used the bounded `mf-returns` group on task `bb6d852d7e504501b81c361bdf1609da`, run `41967217-3834-4ca1-bb58-c488b235710f`. The database capacity gate passed. The worker logged the same order's HTTP 404 as a warning, continued to the next finance page, and reached the collected-error check after carrier synchronization. The run finished at 1:09 PM Pacific on November 14. Its degraded status retains the unresolved order warning, while other processing now completes. The orchestration exits zero for a degraded group under its existing nonblocking-job rules.
