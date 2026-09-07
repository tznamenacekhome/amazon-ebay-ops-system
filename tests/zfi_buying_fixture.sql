do $$ begin create role anon; exception when duplicate_object then null; end $$;
do $$ begin create role authenticated; exception when duplicate_object then null; end $$;
do $$ begin create role service_role; exception when duplicate_object then null; end $$;
create table public.purchases (
 purchase_id uuid primary key, supplier text, supplier_order_id text, order_date date,
 total_order_cost numeric, order_status text, created_at timestamptz default now()
);
create table public.purchase_items (
 item_id uuid primary key, purchase_id uuid references purchases, quantity int,
 unit_cost numeric, current_status text, exclude_from_purchase_reporting boolean default false,
 manual_split_child boolean default false, created_at timestamptz default now()
);
create table public.scheduler_runs (
 run_id uuid primary key, group_name text, status text, started_at timestamptz default now(),
 ecs_task_arn text
);
insert into purchases(purchase_id,supplier,supplier_order_id,order_date,total_order_cost) values
 ('00000000-0000-0000-0000-000000000001','eBay','ORDER-A','2024-09-10',50),
 ('00000000-0000-0000-0000-000000000002','eBay','ORDER-A','2024-09-10',50),
 ('00000000-0000-0000-0000-000000000003','eBay','ORDER-B','2024-09-11',40),
 ('00000000-0000-0000-0000-000000000004','eBay','CANCELLED','2024-09-11',30),
 ('00000000-0000-0000-0000-000000000005','eBay','UNKNOWN-COST','2024-09-11',null),
 ('00000000-0000-0000-0000-000000000006','Other','OTHER','2024-09-11',10);
insert into purchase_items(item_id,purchase_id,quantity,unit_cost,current_status,exclude_from_purchase_reporting,manual_split_child) values
 ('10000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001',1,18,'listed',false,false),
 ('10000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000002',1,27,'received',false,false),
 ('10000000-0000-0000-0000-000000000003','00000000-0000-0000-0000-000000000003',2,10,'delivered',false,false),
 ('10000000-0000-0000-0000-000000000004','00000000-0000-0000-0000-000000000003',1,5,'delivered',false,true),
 ('10000000-0000-0000-0000-000000000005','00000000-0000-0000-0000-000000000003',1,15,'received',true,false),
 ('10000000-0000-0000-0000-000000000006','00000000-0000-0000-0000-000000000004',1,30,'cancelled',false,false),
 ('10000000-0000-0000-0000-000000000007','00000000-0000-0000-0000-000000000005',1,null,'received',false,false);
