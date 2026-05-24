alter table purchase_items
  add column if not exists manual_title_override boolean not null default false,
  add column if not exists manual_unit_cost_override boolean not null default false,
  add column if not exists manual_split_child boolean not null default false,
  add column if not exists manual_split_parent_item_id uuid references purchase_items(item_id) on delete set null;

create index if not exists idx_purchase_items_manual_split_parent
  on purchase_items(manual_split_parent_item_id);
