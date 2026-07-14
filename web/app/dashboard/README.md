# MBOP Dashboard

The MBOP dashboard is now operational-only. Financial planning, YNAB cash,
business value history, Schedule C planning, and long-range growth views belong
in ZFI.

Active dashboard views:

- Overview
- Operations
- Inventory
- Amazon
- Sourcing
- Loss Prevention
- System Health

Removed dashboard views:

- Financial
- Growth

Removed active API routes:

- `/api/dashboard/financial`
- `/api/dashboard/growth`

The Amazon dashboard preserves operational seller-account, listing-health, FBA
inventory, and repricing signals. High-level Amazon revenue/profit summary
sections were removed from this dashboard; detailed sales and profitability data
remain in the Sales Orders workflow and backend source tables.

The Overview dashboard no longer reads `business_value_snapshots` or YNAB
snapshot tables. Inventory and cash facts that MBOP still owns operationally are
served from purchase, inventory, Amazon Finance, and workflow tables.
