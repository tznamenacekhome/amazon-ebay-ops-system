-- Remove Amazon sales orders outside MBOP's 2025-forward operating window.
--
-- These two orders were imported because Amazon updated old orders in 2026 and
-- the scheduled order sync uses LastUpdatedAfter. The code now prevents
-- pre-2025 purchase dates from being imported again.
--
-- Deleting from amazon_sales_orders cascades to order items, financial events,
-- profitability, and COGS consumption through the existing foreign keys.

delete from public.amazon_sales_orders
where amazon_order_id in (
  '112-7815330-1795416',
  '113-6358461-6273015'
)
and purchase_date < '2025-01-01T00:00:00Z';
