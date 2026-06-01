-- Merchant Fulfilled inventory COGS states.
--
-- Adds explicit states for Merchant Fulfilled inventory that is still physically
-- in stock but split between Seller Central available quantity and units
-- allocated to open/unshipped orders.

alter table public.amazon_inventory_cogs_layers
  drop constraint if exists amazon_inventory_cogs_layers_inventory_state_check;

alter table public.amazon_inventory_cogs_layers
  add constraint amazon_inventory_cogs_layers_inventory_state_check
    check (inventory_state in (
      'fulfillable',
      'reserved',
      'inbound_working',
      'inbound_shipped',
      'inbound_receiving',
      'unfulfillable',
      'merchant_available',
      'merchant_allocated',
      'other'
    ));
