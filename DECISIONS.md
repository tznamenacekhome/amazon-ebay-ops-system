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
→ Supabase
→ API Routes
→ Frontend
