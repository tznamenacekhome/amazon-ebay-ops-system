# MF returns order failure recovery

The MF returns finance worker previously stopped at the first unavailable order lookup, preventing subsequent transactions and return-carrier tracking from running. Recent Amazon Sales repeatedly encountered order `114-8866055-7493009`, whose Orders API lookup returned HTTP 404.

Order verification errors are now collected per order and cached for the current run. Other transactions continue. Individual finance import failures are also collected while remaining transactions continue. Carrier tracking runs after transaction processing. Collected errors remain visible in the final failure summary, preserving degraded scheduler status while unresolved coverage exists. Later scheduled runs retry the unresolved data through the existing overlapping window.

The regression check covers a repeated unavailable order, a rejected finance import, a subsequent successful transaction, and carrier tracking. All 11 MF returns source tests passed.

Deployment uses the existing scheduler workflow scoped to `mbop-amazon-sales-recent-`. No schema migration is required.
