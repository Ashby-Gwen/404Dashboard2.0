-- Supabase/Postgres indexes for corrected Sales Order retrieval paths.
-- Run after existing migrations; these improve dashboard, invoice selection, reports, and analytics reads.

CREATE INDEX IF NOT EXISTS idx_sales_orders_order_date_created
    ON public.sales_orders (order_date DESC, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_sales_orders_status_order_date
    ON public.sales_orders (status, order_date DESC);

CREATE INDEX IF NOT EXISTS idx_sales_orders_client_order_date
    ON public.sales_orders (client_id, order_date DESC);

CREATE INDEX IF NOT EXISTS idx_sales_order_items_sales_order_id
    ON public.sales_order_items (sales_order_id);

CREATE INDEX IF NOT EXISTS idx_invoices_sales_order_id
    ON public.invoices (sales_order_id);

CREATE INDEX IF NOT EXISTS idx_invoices_sales_order_date
    ON public.invoices (sales_order_id, invoice_date DESC);
