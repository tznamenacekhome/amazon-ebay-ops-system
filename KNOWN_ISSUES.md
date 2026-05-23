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
