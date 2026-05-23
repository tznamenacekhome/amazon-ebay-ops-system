# KNOWN_ISSUES.md

# High Priority

## page.tsx Monolith

Status: RESOLVED / MONITOR

File:
web/app/page.tsx

Resolution:
- extracted purchases table
- extracted detail drawer
- extracted editable price cell
- extracted filter bar
- extracted metrics
- moved purchase API state into usePurchases
- moved filtering into usePurchaseFilters
- moved metric calculation into purchaseStats

Remaining risk:
Future UI work could reintroduce large JSX blocks or mixed responsibilities.

Recommended guardrail:
Keep page.tsx focused on composition and UI-local workflow state.

---

## RevSeller Matching Ambiguity

Status: ACTIVE

Problem:
same game titles exist across multiple systems.

Risks:
- incorrect ASIN assignment
- incorrect sell price enrichment

Recommended next mitigation:
- build an explicit ASIN review workflow in the purchases UI
- surface system/platform prominently
- rely on backend-provided matching diagnostics and confidence
- never infer matching confidence in the frontend

Current mitigation:
- backend system detection has been centralized
- eBay import/sync populates purchase_items.system from recognized title terms
- RevSeller enrichment requires system-aware matching before ASIN assignment
- matched Amazon/RevSeller title is stored separately from the eBay supplier title for review clarity
- shared marketplace-title cleaning now runs before RevSeller normalized matching

---

## EasyPost FedEx Tracking Credentials

Status: ACTIVE

Problem:
Two FedEx tracking numbers from the 2026-05-01+ backfill failed in EasyPost with "Credentials not found for the specified carrier", even when retried without passing carrier.

Affected orders:
- 06-14656-35281, tracking 381367337613, order date 2026-05-17
- 27-14629-25992, tracking 381418656302, order date 2026-05-18

Risk:
FedEx shipments may remain at unknown or awaiting-carrier status unless EasyPost FedEx credentials are configured or a separate FedEx/direct-carrier path is added.

Recommended next mitigation:
- verify FedEx tracking support/credentials in the EasyPost account
- decide whether to configure FedEx credentials in EasyPost or add a carrier-direct fallback later

---

## EasyPost Webhook Requires Public HTTPS Hosting

Status: ACTIVE

Problem:
The webhook route exists locally, but EasyPost cannot deliver production webhooks to localhost.

Risk:
Until the app is deployed publicly and registered with EasyPost, tracking updates still require running the sync script manually or on a scheduler.

Recommended next mitigation:
- deploy the Next.js app to a public HTTPS server
- configure EASYPOST_WEBHOOK_SECRET
- register /api/easypost/webhook in EasyPost
- test webhook HMAC validation with a real EasyPost event
