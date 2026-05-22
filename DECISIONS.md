# DECISIONS.md

# Core Architecture Decisions

## eBay Trading API Is Authoritative

Decision:
Use Trading API GetOrders for buyer purchases.

Reason:
Sell Fulfillment API unreliable/incomplete.

---

## Supabase Is Operational Source of Truth

Decision:
All operational workflows center around Supabase.

Pattern:
Python Integrations
-> Supabase
-> API Routes
-> Frontend

---

## Purchases Frontend Uses Component + Hook Boundaries

Decision:
Keep the purchases page as a composition layer and move reusable UI and derived logic into web/app/purchases.

Current structure:
- page.tsx composes the workspace
- usePurchases owns loading, API mutations, save state, and error state
- usePurchaseFilters owns filter state and filtered rows
- purchaseStats computes dashboard metrics
- PurchasesTable, PurchaseDetailDrawer, EditablePriceCell, PurchaseFilters, and PurchaseMetrics own focused UI sections

Reason:
The previous page.tsx monolith increased maintenance risk, truncation risk, and regression risk during AI-assisted edits.

Rule:
Do not place landed cost calculations, matching logic, or receiving workflow behavior in the purchases frontend.

---

## System Detection Is Backend-Owned

Decision:
Recognized video game system/platform values are populated by backend import/enrichment code, not inferred in the React frontend.

Reason:
System/platform is part of matching correctness. Frontend inference can hide missing backend data and risks incorrect ASIN review decisions.

Implementation:
- shared system detection lives in integrations/system_detection.py
- eBay buyer purchase sync populates purchase_items.system from eBay titles when a recognized system is present
- RevSeller enrichment requires title+system alignment before assigning ASIN and target price
