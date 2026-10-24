# Original eBay photo retention — October 24, 2026

The Tiger Woods PC purchase (order 18-15291-47640, eBay listing 327405342969)
had no stored photo in its transaction import, sourcing candidate, or sourcing
snapshots. The original closed listing was retrievable through authenticated
Trading GetItem. A targeted preview returned seven seller photos; applying the
repair saved only normalized photo metadata in purchase_items.raw_import_json.
The production Receiving image endpoint then returned the restored seller photo,
and the image loaded successfully in the authenticated browser.

Buyer ingestion now captures original listing photos through Trading GetItem,
bounded to 25 unique attempts per process and cached per listing ID. Responses
must match the requested listing ID. Existing normalized photo metadata is
preserved across imports. API timeouts/failures do not prevent purchase import.
The web task receives no additional credentials or privileges and its existing
detail image endpoint requires no deployment. No schema change is involved.

The repair CLI requires explicit item IDs (maximum 25), defaults to preview,
requires --apply to write, and re-reads metadata immediately before the write.
It verifies saved photos after applying. Quantity, receiving status, titles,
ASIN, price, and cost are never changed by the repair.

Validation: five image-retention tests and twelve buyer-ingestion tests passed;
the latter mocked image provider calls. Live validation used one exact listing
and one exact purchase item. No full sync, broad backfill, or schema SQL ran.

Deploy the scheduler image using scripts/deploy-scheduler.ps1 with
ScheduleNamePrefix mbop-purchase-ingestion and the current ingestion task as
BaseTaskDefinition. This updates only the hourly and catchup ingestion schedules.
Do not run orchestration to smoke-test this image-only change. Roll back those
two schedules to their previous immutable task revision if necessary.

## Deployment receipt

- Commit `986e148204fa` pushed to origin/main.
- Scheduler image digest:
  `sha256:54d1c1786611bf0be8360d7a35ae4a1200c99df4b679b91e966735d8125dedc7`.
- Deployed scheduler task `mbop-scheduler-task:148`, based on ingestion revision
  `141`, preserving its task configuration and credentials.
- Only `mbop-purchase-ingestion-hourly` and `mbop-purchase-ingestion-catchup`
  were updated; both remain enabled. No immediate sync was launched.
- All 17 image/buyer-ingestion tests passed inside the built Linux scheduler
  image with networking disabled and fake credentials.
- The repaired Tiger Woods item's production image endpoint returns both
  marketplace images; its original eBay seller photograph loaded successfully
  in the browser. Close and reopen an already-open Receiving detail to fetch
  the repaired URL.
