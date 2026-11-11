# MBOP eBay Drafts

The eBay Drafts workspace is a seller-listing workflow, separate from purchases,
receiving, Amazon listing batches, and sales orders. It stores photo imports and
editable listing drafts in `ebay_draft_imports`, `ebay_listing_drafts`, and
`ebay_listing_draft_photos`. Photos are private in the
`mbop-ebay-draft-photos` Supabase Storage bucket. Browser code calls authenticated
Next.js API routes; only the server uses the Supabase service role.

## Current behavior

- Folder subdirectories are suggested as photo groups. A flat folder is treated
  as an uncertain loose group, and the seller must confirm or split it.
- Original images are retained. Intake makes an orientation-corrected review
  copy; later rotations create another corrected copy and preserve the original.
- A repeated import with the same relative paths and source image hashes reuses
  the existing batch instead of creating duplicate drafts.
- AI image analysis is optional and requires server-side `OPENAI_API_KEY`.
  `MBOP_EBAY_DRAFT_VISION_MODEL` can select a configured compatible vision
  model; the default is `gpt-4.1-mini`. AI output is stored as suggestions and
  does not replace seller edits.
- Sold-search URLs follow the query pattern from
  `integrations/price_ebay_draft_listings.py` (`LH_Sold=1`, `LH_Complete=1`,
  `rt=nc`). MBOP has no verified sold-comp price feed or automated price
  recommendation in this phase.
- “Ready in MBOP” is an internal review state only. No eBay API is called and
  no Seller Hub draft is created. eBay category metadata, allowed specifics,
  and condition values are not live-validated.

## Handoff boundary

The eBay handoff remains disconnected by operator instruction. A future
integration should use the supported Seller Hub Feed API `FX_LISTING` draft
action and verify the saved draft in Seller Hub. Do not report an Inventory API
unpublished offer as a Seller Hub draft; those are distinct outcomes.

## Existing source data

The current purchase schema has no eBay seller item-number field or existing
photo-group table. Draft intake therefore does not infer a purchase link from
photo names. `source_item_number` remains a review hint only, and
`source_item_id` should be populated only after a reliable explicit mapping is
added.
