-- Supabase/Postgres migration for account approval workflow.
-- Run this against the persistent Supabase database before deploying the code change.

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS approved_by integer REFERENCES public.users(id),
    ADD COLUMN IF NOT EXISTS approved_at timestamptz,
    ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();

UPDATE public.users
SET
    status = CASE
        WHEN upper(status) = 'ACTIVE' THEN 'approved'
        WHEN upper(status) = 'INACTIVE' THEN 'disabled'
        WHEN lower(status) IN ('pending', 'approved', 'rejected', 'disabled') THEN lower(status)
        ELSE 'pending'
    END,
    approved_at = CASE
        WHEN upper(status) = 'ACTIVE' OR lower(status) = 'approved' THEN COALESCE(approved_at, now())
        ELSE approved_at
    END,
    updated_at = COALESCE(updated_at, now());

ALTER TABLE public.users
    ALTER COLUMN status SET DEFAULT 'pending',
    ALTER COLUMN updated_at SET DEFAULT now();

ALTER TABLE public.users
    DROP CONSTRAINT IF EXISTS users_status_check;

ALTER TABLE public.users
    ADD CONSTRAINT users_status_check
    CHECK (status IN ('pending', 'approved', 'rejected', 'disabled'));

CREATE INDEX IF NOT EXISTS idx_users_status ON public.users(status);
CREATE INDEX IF NOT EXISTS idx_users_approved_by ON public.users(approved_by);
