-- An omitted eBay offer status is unknown, never evidence of a decline.
-- Retain the offered amount separately so unknown history cannot reappear as new.
BEGIN;
CREATE TABLE public.sourcing_unresolved_ebay_offers (
  ebay_legacy_item_id text PRIMARY KEY CHECK (ebay_legacy_item_id ~ '^[0-9]+$'),
  offer_amount numeric(12,2) NOT NULL CHECK (offer_amount > 0),
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.sourcing_unresolved_ebay_offers ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sourcing_unresolved_ebay_offers FROM public, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.sourcing_unresolved_ebay_offers TO service_role;
CREATE FUNCTION public.record_sourcing_unresolved_offers(offers jsonb) RETURNS void
LANGUAGE sql SECURITY INVOKER SET search_path = pg_catalog, public AS $$
  INSERT INTO public.sourcing_unresolved_ebay_offers (ebay_legacy_item_id,offer_amount)
  SELECT ebay_legacy_item_id,max(offer_amount)
  FROM jsonb_to_recordset(offers) AS x(ebay_legacy_item_id text,offer_amount numeric)
  GROUP BY ebay_legacy_item_id
  ON CONFLICT (ebay_legacy_item_id) DO UPDATE SET
    offer_amount=greatest(sourcing_unresolved_ebay_offers.offer_amount,excluded.offer_amount),
    last_seen_at=now();
$$;
REVOKE ALL ON FUNCTION public.record_sourcing_unresolved_offers(jsonb) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_sourcing_unresolved_offers(jsonb) TO service_role;
CREATE VIEW public.vw_sourcing_offer_limits WITH (security_invoker=true) AS
  SELECT ebay_legacy_item_id,max(amount) AS declined_offer_amount
  FROM (
    SELECT ebay_legacy_item_id,declined_offer_amount AS amount FROM public.sourcing_declined_ebay_offers
    UNION ALL
    SELECT ebay_legacy_item_id,offer_amount FROM public.sourcing_unresolved_ebay_offers
  ) evidence GROUP BY ebay_legacy_item_id;
REVOKE ALL ON public.vw_sourcing_offer_limits FROM public, anon, authenticated;
GRANT SELECT ON public.vw_sourcing_offer_limits TO service_role;
COMMENT ON VIEW public.vw_sourcing_offer_limits IS
  'Conservative sourcing presentation/scoring floor from declined or status-omitted USD item offers. Alias declined_offer_amount preserves existing scorer contract; unresolved evidence is not a confirmed decline.';
COMMIT;
