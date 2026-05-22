# KNOWN_ISSUES.md

# High Priority

## page.tsx Monolith

Status: ACTIVE

File:
web/app/page.tsx

Issues:
- large JSX blocks
- difficult maintenance
- truncation corruption risk
- alignment regressions

Recommended fix:
component extraction

---

## RevSeller Matching Ambiguity

Status: ACTIVE

Problem:
same game titles exist across multiple systems.

Risks:
- incorrect ASIN assignment
- incorrect sell price enrichment
