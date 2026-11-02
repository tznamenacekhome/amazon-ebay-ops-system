-- Operator confirms both repeated Watch listings had declined buyer offers.
-- Amounts independently observed in live eBay BestOfferList on 2026-11-01;
-- eBay omitted status for these items, so this confirmation supplies that fact.
SELECT public.record_sourcing_declined_offers(
  '[{"ebay_legacy_item_id":"137887648197","declined_offer_amount":17.00},
    {"ebay_legacy_item_id":"403002608732","declined_offer_amount":19.00}]'::jsonb
);
