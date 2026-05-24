alter table purchase_items
  add column if not exists marketplace text,
  add column if not exists received_date date;

alter table purchase_items
  drop constraint if exists purchase_items_marketplace_check;

alter table purchase_items
  add constraint purchase_items_marketplace_check
  check (marketplace is null or marketplace in ('Amazon', 'eBay'));

create index if not exists idx_purchase_items_marketplace
  on purchase_items(marketplace);

create index if not exists idx_purchase_items_received_date
  on purchase_items(received_date);
