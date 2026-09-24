# Sourcing dismissal and carrier tracking links

Deployment date: 2026-09-23

## Sourcing dismissal workflow

- Dismiss-reason buttons now show a persistent selected state before the operator confirms dismissal.
- Parser accuracy, seller-listing accuracy, and product-match review use optional Yes/No radio buttons with no default selection.
- The review copy now explains that parser accuracy, seller-listing accuracy, and product identity are separate decisions.
- The unused image-clue checklist was removed from the dismissal workflow.
- `Price Too Risky / Return Risk` records opportunities declined because the purchase price creates unacceptable customer-return exposure. It remains a business decision and does not mark a correct product match as incorrect.
- `Save feedback` was renamed to `Save review and keep opportunity` to describe its effect.
- Dismissed rows are removed from the current cached list immediately. The server mutation and background refresh still reconcile the authoritative result, and a failed mutation restores the row and reports the error.

## Tracking links

- Tracking numbers are links in Purchases, purchase details and event history, Order Problems, Receiving, and Amazon FBA shipment views.
- Stored EasyPost or carrier tracking URLs are preferred.
- When a stored URL is unavailable, MBOP builds the official UPS, USPS, FedEx, DHL, or OnTrac tracking URL from the carrier and tracking number. Unknown carriers use a tracking search fallback.
- The purchases API now includes the stored inbound-shipment tracking URL for each visible primary or replacement shipment.
- Receiving package rows now include their stored tracking URL.

## Data and deployment impact

- No database migration is required.
- No scheduler code or cadence changes are included.
- Existing sourcing feedback values remain accepted; the UI simply omits the uncertain choice when no selection is sufficient.

## Validation

- Sourcing review action tests
- Sourcing review component tests
- Sourcing opportunity cache and mutation tests
- Carrier tracking-link tests
- Next.js production build
- `git diff --check`
