# Purchases due by Saturday metric

The Purchases summary now includes **Due by Saturday M/D** beside the existing
delivery totals. The date is the end of the current calendar week's Saturday in
the `America/Los_Angeles` business timezone. For example, Friday 2026-09-18 uses
Saturday 2026-09-19, while Sunday 2026-09-20 uses Saturday 2026-09-26.

The metric counts active, undelivered resale units whose best available ETA is
on or before that Saturday. Overdue units remain included because they have not
arrived and their expected date is already inside the window. Units without an
ETA are excluded. The dollar amount is calculated in the backend from
`vw_purchases_dashboard.unit_cost * quantity`; the frontend only displays the
authoritative aggregate.

The additive `purchase_saturday_delivery_stats(date)` RPC is security-invoker
and executable only by `service_role`. It reads purchases, purchase items, and
the dashboard view and does not update operational or historical data.
