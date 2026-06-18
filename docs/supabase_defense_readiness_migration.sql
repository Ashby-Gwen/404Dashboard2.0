-- 404 Dashboard defense-readiness migration.
-- Back up Supabase before running. This file is intentionally idempotent.

BEGIN;

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS profile_photo_data text,
    ADD COLUMN IF NOT EXISTS profile_photo_mime varchar(80);

UPDATE public.users
SET status = CASE
    WHEN upper(status) = 'ACTIVE' THEN 'approved'
    WHEN upper(status) = 'INACTIVE' THEN 'disabled'
    WHEN lower(status) IN ('pending', 'approved', 'rejected', 'disabled') THEN lower(status)
    ELSE 'pending'
END;

ALTER TABLE public.users
    ALTER COLUMN status SET DEFAULT 'pending';

ALTER TABLE public.users
    DROP CONSTRAINT IF EXISTS users_status_check;

ALTER TABLE public.users
    ADD CONSTRAINT users_status_check
    CHECK (status IN ('pending', 'approved', 'rejected', 'disabled'));

ALTER TABLE public.evaluation_sessions
    ADD COLUMN IF NOT EXISTS user_id integer REFERENCES public.users(id);

CREATE TABLE IF NOT EXISTS public.system_settings (
    key varchar(100) PRIMARY KEY,
    value text NOT NULL,
    updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_status
    ON public.users (status);

CREATE INDEX IF NOT EXISTS idx_evaluation_sessions_user_id_created
    ON public.evaluation_sessions (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sales_orders_order_date_created
    ON public.sales_orders (order_date DESC, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_sales_orders_client_order_date
    ON public.sales_orders (client_id, order_date DESC);

CREATE INDEX IF NOT EXISTS idx_sales_order_items_sales_order_id
    ON public.sales_order_items (sales_order_id);

CREATE INDEX IF NOT EXISTS idx_invoices_sales_order_id
    ON public.invoices (sales_order_id);

CREATE INDEX IF NOT EXISTS idx_invoices_amount_paid_date
    ON public.invoices (amount_paid, invoice_date);

CREATE INDEX IF NOT EXISTS idx_invoices_balance_date
    ON public.invoices (balance, invoice_date);

COMMIT;
