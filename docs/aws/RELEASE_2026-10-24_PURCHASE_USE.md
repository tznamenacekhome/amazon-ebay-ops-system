# Purchase use classification — October 24, 2026

The Purchases detail drawer now offers Resale, Personal purchase, and Supply
in a Purchase use selector with a separate Save Purchase Use button. Unsaved
selection changes are discarded when the drawer closes. ASIN and price
validation do not block classification or dismissal.

The existing authenticated PATCH /api/purchases endpoint validates and saves
purchase_items.exclude_from_purchase_reporting and exclusion_reason together.
Personal purchase uses the existing `Personal purchase` reason; Supply uses
`Business supply / non-resale`; Resale clears the exclusion and reason.
Classification applies only to the selected item and never propagates by title
or system. No schema migration, provider sync, or scheduler change is required.

After saving, the list reloads from the backend so existing exclusion rules
remove personal purchases and supplies from resale reports and Purchases,
Receiving, and FBA queues. The drawer remains open so the operator can correct
the choice before closing; excluded rows cannot be reopened from those queues.

## Validation and delivery

TypeScript and diff whitespace checks pass. Full touched-file lint reports
pre-existing no-explicit-any errors at purchases/route.ts lines 343 and 546.
Deploy from a clean committed checkout using scripts/deploy-web.ps1, confirm
the stable ECS task and build SHA using scripts/aws-web-status.ps1, then inspect
the selector and dismissal in the authenticated production browser. Avoid
changing a real purchase merely to smoke-test the controls.

Rollback uses the preceding web task revision; no database rollback is needed.
