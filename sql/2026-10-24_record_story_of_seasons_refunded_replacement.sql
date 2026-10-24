-- Target: MBOP production froeucjkcepuhgwisped. Apply after migration 20261024204208.
-- Operator confirmed possession; leave warehouse receipt/date to Receiving.
select public.mbop_record_refunded_inventory_recovery(
  '95f098c4-66b6-45dc-9cef-e5622f328819'::uuid,
  '2dbea060-0255-46d9-9fbb-7d2a465d37a1'::uuid,
  26.07,
  'refunded_replacement_received',
  'Order 23-15229-99266: seller sent an empty/wrong game case, issued a full $26.07 refund, and also supplied the correct Story of Seasons: Pioneers of Olive Town for Nintendo Switch. Operator confirmed possession on October 24, 2026. One usable copy; net acquisition cost $0. Warehouse Receiving verification remains pending.'
);
