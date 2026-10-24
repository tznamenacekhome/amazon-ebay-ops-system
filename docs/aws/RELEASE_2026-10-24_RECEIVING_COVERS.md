# Receiving listing covers — October 24, 2026

Receiving Detail displays large eBay and Amazon listing images side by side
beneath the titles and package details. Images retain their full proportions,
fill the available left-column space, and link to their respective listings.
Missing or failed images display an explicit placeholder.

The detail-only GET /api/receiving/images endpoint uses the selected item's
stored import data or exact eBay legacy listing ID for eBay imagery. Amazon
imagery uses the item's saved ASIN and existing listing snapshots/sourcing seed
data, with the standard ASIN image URL as fallback. The queue does not hydrate
images. Lookups are bounded, read-only, and use the existing server-side
Supabase client. No provider jobs, migration, scheduler, or receiving-save
behavior changes are required.

## Validation

TypeScript, focused new-file ESLint, receivingDismiss.test.mjs,
trackingScan.test.mjs, and git diff --check passed. Image helper checks covered
nested eBay import pictures, exact listing ID extraction, Amazon snapshot
images, missing imagery, and unsafe URL rejection.

Deploy using scripts/deploy-web.ps1, confirm stable ECS service and build SHA
using scripts/aws-web-status.ps1, then inspect an existing Receiving detail in
the authenticated production browser without receiving or editing inventory.
Rollback uses the preceding web task revision; no database rollback is needed.
