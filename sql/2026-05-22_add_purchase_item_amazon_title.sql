alter table public.purchase_items
add column if not exists amazon_title text;

comment on column public.purchase_items.amazon_title is
'Matched Amazon/RevSeller title used for purchase review display. eBay supplier title remains purchase_items.title.';
