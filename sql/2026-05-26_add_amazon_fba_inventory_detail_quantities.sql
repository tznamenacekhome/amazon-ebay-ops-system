-- Normalize detailed Amazon FBA inventory quantities from raw SP-API payloads.
--
-- These fields distinguish normal reserved/in-transit inventory from true
-- operator-action issues. FC transfer is Amazon moving inventory between
-- fulfillment centers; it should not be treated as an MBOP action issue by
-- itself.

alter table public.amazon_fba_inventory_snapshots
  add column if not exists reserved_customer_order_quantity integer,
  add column if not exists reserved_fc_transfer_quantity integer,
  add column if not exists reserved_fc_processing_quantity integer,
  add column if not exists future_supply_buyable_quantity integer,
  add column if not exists reserved_future_supply_quantity integer,
  add column if not exists researching_short_term_quantity integer,
  add column if not exists researching_mid_term_quantity integer,
  add column if not exists researching_long_term_quantity integer,
  add column if not exists unfulfillable_customer_damaged_quantity integer,
  add column if not exists unfulfillable_warehouse_damaged_quantity integer,
  add column if not exists unfulfillable_distributor_damaged_quantity integer,
  add column if not exists unfulfillable_carrier_damaged_quantity integer,
  add column if not exists unfulfillable_defective_quantity integer,
  add column if not exists unfulfillable_expired_quantity integer;

comment on column public.amazon_fba_inventory_snapshots.reserved_customer_order_quantity is
'FBA reserved units tied to pending customer orders from inventoryDetails.reservedQuantity.pendingCustomerOrderQuantity.';

comment on column public.amazon_fba_inventory_snapshots.reserved_fc_transfer_quantity is
'FBA reserved units being transferred between fulfillment centers from inventoryDetails.reservedQuantity.pendingTransshipmentQuantity.';

comment on column public.amazon_fba_inventory_snapshots.reserved_fc_processing_quantity is
'FBA reserved units sidelined for additional fulfillment-center processing from inventoryDetails.reservedQuantity.fcProcessingQuantity.';

comment on column public.amazon_fba_inventory_snapshots.future_supply_buyable_quantity is
'Future supply units Amazon says are buyable from inventoryDetails.futureSupplyQuantity.futureSupplyBuyableQuantity.';

comment on column public.amazon_fba_inventory_snapshots.reserved_future_supply_quantity is
'Reserved future supply units from inventoryDetails.futureSupplyQuantity.reservedFutureSupplyQuantity.';

update public.amazon_fba_inventory_snapshots
set
  reserved_customer_order_quantity = nullif(raw_inventory_json #>> '{inventoryDetails,reservedQuantity,pendingCustomerOrderQuantity}', '')::integer,
  reserved_fc_transfer_quantity = nullif(raw_inventory_json #>> '{inventoryDetails,reservedQuantity,pendingTransshipmentQuantity}', '')::integer,
  reserved_fc_processing_quantity = nullif(raw_inventory_json #>> '{inventoryDetails,reservedQuantity,fcProcessingQuantity}', '')::integer,
  future_supply_buyable_quantity = nullif(raw_inventory_json #>> '{inventoryDetails,futureSupplyQuantity,futureSupplyBuyableQuantity}', '')::integer,
  reserved_future_supply_quantity = nullif(raw_inventory_json #>> '{inventoryDetails,futureSupplyQuantity,reservedFutureSupplyQuantity}', '')::integer,
  unfulfillable_customer_damaged_quantity = nullif(raw_inventory_json #>> '{inventoryDetails,unfulfillableQuantity,customerDamagedQuantity}', '')::integer,
  unfulfillable_warehouse_damaged_quantity = nullif(raw_inventory_json #>> '{inventoryDetails,unfulfillableQuantity,warehouseDamagedQuantity}', '')::integer,
  unfulfillable_distributor_damaged_quantity = nullif(raw_inventory_json #>> '{inventoryDetails,unfulfillableQuantity,distributorDamagedQuantity}', '')::integer,
  unfulfillable_carrier_damaged_quantity = nullif(raw_inventory_json #>> '{inventoryDetails,unfulfillableQuantity,carrierDamagedQuantity}', '')::integer,
  unfulfillable_defective_quantity = nullif(raw_inventory_json #>> '{inventoryDetails,unfulfillableQuantity,defectiveQuantity}', '')::integer,
  unfulfillable_expired_quantity = nullif(raw_inventory_json #>> '{inventoryDetails,unfulfillableQuantity,expiredQuantity}', '')::integer
where raw_inventory_json ? 'inventoryDetails';

with researching_breakdown as (
  select
    snapshot.amazon_fba_inventory_snapshot_id,
    max(case when breakdown.value ->> 'name' = 'researchingQuantityInShortTerm'
      then nullif(breakdown.value ->> 'quantity', '')::integer end) as short_term,
    max(case when breakdown.value ->> 'name' = 'researchingQuantityInMidTerm'
      then nullif(breakdown.value ->> 'quantity', '')::integer end) as mid_term,
    max(case when breakdown.value ->> 'name' = 'researchingQuantityInLongTerm'
      then nullif(breakdown.value ->> 'quantity', '')::integer end) as long_term
  from public.amazon_fba_inventory_snapshots snapshot
  cross join lateral jsonb_array_elements(
    coalesce(
      snapshot.raw_inventory_json #> '{inventoryDetails,researchingQuantity,researchingQuantityBreakdown}',
      '[]'::jsonb
    )
  ) as breakdown(value)
  group by snapshot.amazon_fba_inventory_snapshot_id
)
update public.amazon_fba_inventory_snapshots snapshot
set
  researching_short_term_quantity = researching_breakdown.short_term,
  researching_mid_term_quantity = researching_breakdown.mid_term,
  researching_long_term_quantity = researching_breakdown.long_term
from researching_breakdown
where researching_breakdown.amazon_fba_inventory_snapshot_id = snapshot.amazon_fba_inventory_snapshot_id;

create index if not exists amazon_fba_inventory_snapshots_reserved_detail_idx
  on public.amazon_fba_inventory_snapshots (
    reserved_customer_order_quantity,
    reserved_fc_transfer_quantity,
    reserved_fc_processing_quantity,
    future_supply_buyable_quantity,
    reserved_future_supply_quantity
  );
