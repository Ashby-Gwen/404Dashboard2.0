# 404 Analytical Dashboard System

A Flask and SQLAlchemy business analytics system for Sales Orders, invoices, expenses, reporting, client analysis, forecasting, recommendations, evaluation, and role-based administration.

## Current Architecture

- Flask application served by Gunicorn in production
- SQLAlchemy ORM
- Supabase PostgreSQL for production
- SQLite fallback for local development and automated checks
- Server-rendered HTML with Bootstrap, Chart.js, SheetJS, and shared theme styles
- Admin, Manager, Sales Staff, Accounting Staff, and compatibility Staff roles

The runtime path is:

`User -> Front End -> Flask Back End -> SQLAlchemy -> Database -> Flask Back End -> Front End -> User`

GitHub and Render belong to the deployment flow. They are not part of the live user-to-database request path.

## Main Modules

- Authentication, registration approval, profile, and password-reset requests
- Sales Order entry, Excel processing, client resolution, store/branch grouping, and printable forms
- Invoice entry with `UNPAID`, `PARTIAL`, and `PAID` balance-based status
- Expense entry, debit allocation, import preview, editing, and reporting
- Dashboard KPIs and client balances
- Descriptive, predictive, comparative, and prescriptive analytics
- Reports and evaluation results
- Admin Center for users, records, client cleanup, requests, audit history, and appearance

Advanced database maintenance, schema inspection, and SQL tools are collapsed under **Advanced technical tools** in the Admin Center. Production SQL execution is forced into read-only/dry-run behavior. The generic developer JSON viewer is unavailable in production.

## Expense Terminology

**Expense** is the canonical user-facing module name.

The physical database tables remain named `purchase_orders` and `purchase_order_debits` for backward compatibility. The Flask routes `/purchase-orders`, `/get-purchase-orders`, and `/create-purchase-order` are compatibility aliases; new integrations should use:

- `GET /expenses`
- `GET /get-expenses`
- `POST /create-expense`
- `PUT /expenses/<expense_id>`

## Database and Migrations

The SQLAlchemy models define 17 runtime tables, including `system_settings`. Local SQLite startup runs the defense-readiness compatibility migration in `defense_migrations.py`, creates a timestamped backup before altering an existing database, and adds required indexes.

For Supabase, review and apply:

- `docs/supabase_defense_readiness_migration.sql`
- Other dated migration files under `docs/` when upgrading an older deployment

Always back up the target database before applying a migration.

## Local Setup

Requirements:

- Python 3.10 or newer
- Packages from `requirements.txt`

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

The local application defaults to `http://localhost:5000`.

Default demo accounts are not created unless the corresponding password environment variables are supplied. For local-only insecure demo seeding, `SYLUXENT_ALLOW_INSECURE_DEMO_PASSWORDS=true` must be explicitly enabled.

## Environment Variables

- `SECRET_KEY`: required in production
- `DATABASE_URL`: required on Render/production; use the Supabase PostgreSQL URL
- `MAX_UPLOAD_BYTES`: optional upload limit; defaults to 10 MB
- `SESSION_COOKIE_SECURE=true`: optional local override; enabled automatically in production
- `FLASK_DEBUG=true`: optional local debugging only
- `DEFAULT_ADMIN_PASSWORD`, `DEFAULT_MANAGER_PASSWORD`, `DEFAULT_STAFF_PASSWORD`: optional initial account seeding

## Production Deployment

`render.yaml` defines the Render service and Gunicorn start command. Follow [docs/deployment.md](docs/deployment.md) for GitHub, Render, Supabase, rollback, and post-deployment checks.

Do not deploy production with SQLite. Render local files are not durable business storage.

## Verification

Run all repository checks:

```powershell
Get-ChildItem tests -Filter '*_check.py' | Sort-Object Name | ForEach-Object { python $_.FullName }
```

Important focused checks include:

- `tests/defense_readiness_check.py`
- `tests/expense_module_terminology_check.py`
- `tests/accessibility_keyboard_check.py`
- `tests/render_multi_user_check.py`
- `tests/analytics_objectives_check.py`

See [SYSTEM_CHECK_REPORT_2026-06-18.md](SYSTEM_CHECK_REPORT_2026-06-18.md) for the latest audit and revision status.

## Security and Remaining Work

Implemented safeguards include password hashing, server-side role checks, approval-state enforcement, secure production cookies, production secret/database requirements, upload-size limits, masked password hashes, safer production error messages, and read-only production SQL behavior.

CSRF protection and login throttling remain release-hardening work. Database-level uniqueness/check constraints and a versioned Alembic/Flask-Migrate workflow are also recommended after existing data is reviewed.

## Documentation

- [System ERD](SYSTEM_ERD.md)
- [Latest System Check](SYSTEM_CHECK_REPORT_2026-06-18.md)
- [System Test Analysis](docs/SYSTEM_TEST_ANALYSIS.md)
- [Demo Outline and Script](docs/DEMO_OUTLINE_AND_SCRIPT.md)
- [Deployment Guide](docs/deployment.md)
