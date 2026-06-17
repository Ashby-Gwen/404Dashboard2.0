# Syluxent Redeployment Guide

This guide covers the normal GitHub, Render, and Supabase redeployment flow for this Flask application.

## GitHub Steps

1. Run the local checks before pushing:
   ```powershell
   python -m py_compile app.py
   python tests\render_multi_user_check.py
   python tests\sales_order_query_check.py
   ```
2. Review changed files and make sure no `.env`, local database, uploads, or generated cache files are committed.
3. Commit the changes with a short message that names the fix.
4. Push the branch to GitHub.
5. If using pull requests, review the diff before merging to the Render deploy branch.

## Render Steps

1. Open the Render service connected to this repository.
2. Confirm the service uses the pushed branch.
3. Confirm the build command installs `requirements.txt`.
4. Confirm the start command matches `render.yaml`.
5. Trigger a manual deploy or wait for the automatic deploy.
6. Watch the deploy logs until the app starts without import, database, or migration errors.

## Supabase Steps

1. Open the Supabase project used by `DATABASE_URL`.
2. Run any new migration SQL from the `docs/` folder before testing features that depend on it.
3. Confirm required tables exist, especially users, roles, sales orders, invoices, expenses, audit logs, and evaluation tables.
4. Confirm Row Level Security or storage policies do not block the server-side connection used by Render.

## Environment Variables

Required for production:

- `DATABASE_URL`: Supabase Postgres connection string.
- `SECRET_KEY`: Flask session signing key.

Optional setup variables:

- `DEFAULT_ADMIN_USERNAME`
- `DEFAULT_ADMIN_PASSWORD`
- `DEFAULT_MANAGER_USERNAME`
- `DEFAULT_MANAGER_PASSWORD`
- `DEFAULT_STAFF_USERNAME`
- `DEFAULT_STAFF_PASSWORD`
- `SESSION_COOKIE_SECURE=true`

Do not expose Supabase service role keys or database passwords in frontend JavaScript.

## Database Migration Notes

Apply migrations manually in Supabase SQL Editor when a fix adds fields or indexes. Current migration files include:

- `docs/supabase_user_approval_migration.sql`
- `docs/supabase_render_multi_user_migration.sql`
- `docs/supabase_sales_order_query_indexes.sql`
- `docs/supabase_evaluation_user_id_migration.sql`

After a migration, redeploy Render and test the affected page.

## Storage Policy Notes

Render local storage is temporary. Do not rely on files written inside the app container for permanent records. Permanent business data should live in Supabase Postgres. Uploaded files should be processed immediately or moved to persistent storage if long-term access is required.

## User Testing Checklist

1. Register a new account and verify it waits for admin approval.
2. Log in as admin and approve or reject the pending account.
3. Log in as sales staff and create a manual Sales Order.
4. Log in as accounting staff and create an invoice using Sales Order search.
5. Add or edit an expense and verify history updates.
6. Open dashboard, analytics, reports, and database interface as allowed roles.
7. Submit the evaluation modal from at least one non-admin approved account.
8. Log out and confirm temporary browser cache is cleared.

## Common Deployment Errors

- Missing `DATABASE_URL`: Render cannot connect to Supabase.
- Missing `SECRET_KEY`: sessions are insecure or unstable.
- Tables missing columns: run the matching SQL migration.
- Default admin does not exist: set `DEFAULT_ADMIN_PASSWORD` before first deploy or create an admin in the database.
- Static/theme mismatch: clear browser cache and confirm `/theme-overrides.css` loads.

## Rollback Plan

1. In Render, redeploy the last known good deploy.
2. If the issue is database-related, restore from a Supabase backup or apply a corrective SQL migration.
3. Re-test login, dashboard, Sales Order, invoices, expenses, reports, and evaluation.
4. Document what changed before attempting another deploy.
