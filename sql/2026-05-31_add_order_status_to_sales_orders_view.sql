-- Add Amazon order status to the Sales Orders frontend view so the API can
-- distinguish fulfilled missing-fee rows from not-yet-fulfilled pending-fee rows.

create or replace view public.vw_amazon_sales_orders_recent as
select
  orders.purchase_date,
  orders.amazon_order_id,
  profitability.amazon_order_item_id,
  profitability.asin,
  profitability.seller_sku,
  profitability.title,
  profitability.quantity,
  profitability.sale_price,
  orders.fulfillment_channel,
  profitability.amazon_fees_excluding_fulfillment,
  profitability.fulfillment_cost,
  profitability.fulfillment_cost_source,
  profitability.cogs,
  profitability.cogs_source,
  profitability.net_profit,
  profitability.roi,
  profitability.data_status,
  orders.order_status
from public.amazon_sales_profitability profitability
join public.amazon_sales_orders orders
  on orders.amazon_order_id = profitability.amazon_order_id
where coalesce(lower(orders.order_status), '') <> 'canceled'
  and profitability.data_status not in ('cancelled', 'refunded');

grant select on public.vw_amazon_sales_orders_recent to service_role;
