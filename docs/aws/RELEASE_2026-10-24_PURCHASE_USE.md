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

## Deployment receipt

- Application commit: `ed6302777356`, pushed to `origin/main`.
- Deployed task: `mbop-web-task:190`; preceding revision: `189`.
- ECR digest: `sha256:f2bedfbd0bb74cb24e3af6914ca3b16c45bc47fa36441e5e6edad311b71964e3`.
- Production Docker build and TypeScript passed; focused page/drawer lint passed.
- ECS services-stable waiter exited successfully on October 24, 2026.
- Authenticated browser showed build `ed63027`, loaded Purchases rows, and
  displayed all three Purchase use options. Selecting Personal purchase enabled
  Save Purchase Use; Supply was selectable. Closing without saving and reopening
  restored Resale with the save button disabled. No production item was changed.
- A transient chunk-load error occurred during traffic transition and cleared
  after reloading once the new task served traffic.
