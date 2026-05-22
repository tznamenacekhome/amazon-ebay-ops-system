# Purchases Frontend

This folder contains the purchases workflow UI.

## Boundaries

- `page.tsx` composes the workspace and owns UI-local workflow state.
- `usePurchases` owns purchase loading, save status, errors, and API mutations.
- `usePurchaseFilters` owns filter state and filtered row derivation.
- Table, filter, metric, price-cell, and drawer components stay presentation-focused.

## Operational Rules

- The frontend must never recalculate landed cost.
- Display `unit_cost` from `vw_purchases_dashboard`; backend logic is authoritative.
- Purchases and receiving are separate workflows. Do not merge receiving verification into this UI.
- ASIN/manual review can live here, but matching confidence and ambiguity status must come from backend data.
- Video-game matching is platform-specific. Do not introduce frontend matching shortcuts across systems.
