# MBOP Web App

This is the Next.js frontend and API layer for Midnight Blue Operations Platform.

## Architecture

- React pages render operational workspaces.
- Next.js API routes are the only frontend path to backend data.
- API routes read/write Supabase; React components do not talk directly to Supabase.
- Backend/API responses own landed-cost values and workflow status values.

## Workspaces

- `/dashboard`: purchase completeness and cost reporting
- `/`: purchases review and ASIN/sell-price cleanup
- `/receiving`: delivered and shipped-without-tracking item receiving
- `/fba`: Amazon FBA shipment preparation and InventoryLab CSV export

## Local Development

From this folder:

```bash
npm run dev
```

The app normally runs at `http://localhost:3000`.

## Operational Notes

- Purchases list filtering, sorting, pagination, and counts are server-driven through `/api/purchases`.
- Receiving and FBA are separate workflows and should stay separate from the purchases review UI.
- Dashboard cost totals must use `vw_purchases_dashboard.unit_cost` through API-provided aggregates.
