-- 404 Dashboard defense-readiness migration.
-- Back up Supabase before running. This file is intentionally idempotent.

BEGIN;

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS profile_photo_data text,
    ADD COLUMN IF NOT EXISTS profile_photo_mime varchar(80),
    ADD COLUMN IF NOT EXISTS disabled_reason text;

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

ALTER TABLE public.session_records
    ADD COLUMN IF NOT EXISTS device_id varchar(80),
    ADD COLUMN IF NOT EXISTS device_label varchar(120),
    ADD COLUMN IF NOT EXISTS user_agent text,
    ADD COLUMN IF NOT EXISTS ip_address varchar(80),
    ADD COLUMN IF NOT EXISTS concurrent_note text;

CREATE TABLE IF NOT EXISTS public.sales_order_branches (
    id serial PRIMARY KEY,
    sales_order_id integer NOT NULL REFERENCES public.sales_orders(id) ON DELETE CASCADE,
    branch_name varchar(200) NOT NULL,
    normalized_branch_key varchar(200) NOT NULL,
    CONSTRAINT uq_sales_order_branch_key UNIQUE (sales_order_id, normalized_branch_key)
);

ALTER TABLE public.sales_order_items
    ADD COLUMN IF NOT EXISTS sales_order_branch_id integer
    REFERENCES public.sales_order_branches(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS public.system_settings (
    key varchar(100) PRIMARY KEY,
    value text NOT NULL,
    updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.collection_receipts (
    id serial PRIMARY KEY,
    invoice_id integer NOT NULL REFERENCES public.invoices(id) ON DELETE CASCADE,
    receipt_date date NOT NULL,
    cr_number varchar(50) NOT NULL,
    normalized_cr_number varchar(50) NOT NULL,
    payment_type varchar(20) NOT NULL
        CHECK (payment_type IN ('DOWNPAYMENT', 'FULL')),
    payment_amount double precision NOT NULL DEFAULT 0,
    tax_amount_paid double precision NOT NULL DEFAULT 0,
    is_2307_checked boolean NOT NULL DEFAULT false,
    collected_total double precision NOT NULL DEFAULT 0,
    created_by_user_id integer REFERENCES public.users(id),
    recorded_by varchar(80) NOT NULL DEFAULT 'system',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_collection_receipts_invoice_cr
        UNIQUE (invoice_id, normalized_cr_number)
);

-- CREATE TABLE IF NOT EXISTS does not add defaults when SQLAlchemy already
-- created the table, so repair the server-side defaults before backfilling.
ALTER TABLE public.collection_receipts
    ALTER COLUMN payment_amount SET DEFAULT 0,
    ALTER COLUMN tax_amount_paid SET DEFAULT 0,
    ALTER COLUMN is_2307_checked SET DEFAULT false,
    ALTER COLUMN collected_total SET DEFAULT 0,
    ALTER COLUMN recorded_by SET DEFAULT 'system',
    ALTER COLUMN created_at SET DEFAULT now();

UPDATE public.collection_receipts
SET created_at = now()
WHERE created_at IS NULL;

ALTER TABLE public.collection_receipts
    ALTER COLUMN created_at SET NOT NULL;

INSERT INTO public.collection_receipts (
    invoice_id, receipt_date, cr_number, normalized_cr_number,
    payment_type, payment_amount, tax_amount_paid,
    is_2307_checked, collected_total, recorded_by, created_at
)
SELECT
    invoices.id,
    invoices.invoice_date,
    COALESCE(NULLIF(btrim(invoices.cr_number), ''), 'LEGACY-' || invoices.id),
    upper(COALESCE(NULLIF(btrim(invoices.cr_number), ''), 'LEGACY-' || invoices.id)),
    CASE
        WHEN upper(COALESCE(invoices.payment_type, '')) = 'FULL' THEN 'FULL'
        WHEN invoices.balance IS NOT NULL AND invoices.balance <= 0.01 THEN 'FULL'
        ELSE 'DOWNPAYMENT'
    END,
    CASE
        WHEN COALESCE(invoices.payment_amount, 0) > 0
            THEN invoices.payment_amount
        ELSE invoices.amount_paid
    END,
    COALESCE(invoices.tax_amount_paid, 0),
    COALESCE(invoices.is_2307_checked, false),
    invoices.amount_paid,
    'legacy migration',
    now()
FROM public.invoices
WHERE COALESCE(invoices.amount_paid, 0) > 0
  AND NOT EXISTS (
      SELECT 1 FROM public.collection_receipts
      WHERE collection_receipts.invoice_id = invoices.id
  );

CREATE INDEX IF NOT EXISTS idx_users_status
    ON public.users (status);

CREATE INDEX IF NOT EXISTS idx_evaluation_sessions_user_id_created
    ON public.evaluation_sessions (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_session_records_user_status_device
    ON public.session_records (user_id, status, device_id);

CREATE INDEX IF NOT EXISTS idx_sales_orders_order_date_created
    ON public.sales_orders (order_date DESC, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_sales_orders_client_order_date
    ON public.sales_orders (client_id, order_date DESC);

CREATE INDEX IF NOT EXISTS idx_sales_order_items_sales_order_id
    ON public.sales_order_items (sales_order_id);

CREATE INDEX IF NOT EXISTS idx_sales_order_items_branch_id
    ON public.sales_order_items (sales_order_branch_id);

CREATE INDEX IF NOT EXISTS idx_sales_order_branches_order_id
    ON public.sales_order_branches (sales_order_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_order_branch_key
    ON public.sales_order_branches (sales_order_id, normalized_branch_key);

CREATE INDEX IF NOT EXISTS idx_sales_orders_number_staff
    ON public.sales_orders (so_number, sales_staff);

CREATE INDEX IF NOT EXISTS idx_invoices_sales_order_id
    ON public.invoices (sales_order_id);

CREATE INDEX IF NOT EXISTS idx_invoices_amount_paid_date
    ON public.invoices (amount_paid, invoice_date);

CREATE INDEX IF NOT EXISTS idx_invoices_balance_date
    ON public.invoices (balance, invoice_date);

CREATE INDEX IF NOT EXISTS idx_collection_receipts_invoice_date
    ON public.collection_receipts (invoice_id, receipt_date DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_collection_receipts_normalized_cr
    ON public.collection_receipts (normalized_cr_number);

COMMIT;
