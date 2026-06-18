# 404 Analytical Dashboard System Check

**Audit date:** June 18, 2026  
**Documentation checked:** `GROUP 404 DOCUMENTATION (JUNE 1)`  
**Repository branch:** `main`  
**Audit method:** documentation comparison, static code/schema review, automated checks, isolated browser testing, and responsive viewport testing

## A. Overall System Status

**Status: Partially Ready — critical local fixes implemented and verified**

The main documented modules are present and the repository's automated check scripts pass. Authentication, role navigation, Excel/CSV validation, client matching, descriptive analytics, Holt-Winters forecasting, MAPE validation, recommendations, reports, evaluation, and responsive page behavior are substantially implemented.

The defense-readiness revision completed the two original high-impact local fixes:

1. Existing SQLite databases are backed up and migrated for the required profile/evaluation columns during startup.
2. Invoice status now derives from paid amount and remaining balance, with overpayment validation and shared analytics totals.

The system is suitable for controlled defense/UAT use after applying the matching Supabase migration in production. CSRF protection, login throttling, PostgreSQL integration coverage, and formal stress/UAT evidence remain release-hardening work.

## Revision Update — June 18, 2026

Implemented after the original audit:

- Safe SQLite compatibility migration with timestamped backup.
- Idempotent Supabase defense-readiness migration.
- Balance-based `UNPAID`, `PARTIAL`, and `PAID` invoice status.
- Canonical collected-revenue and receivable ledger including standalone uploaded invoices.
- Business-date Sales Order trends and PostgreSQL-safe leakage calculations.
- Production secret, upload-size, debug, SQL-console, and public-error safeguards.
- Simplified Admin Center with business-friendly default columns and collapsed technical tools.
- Canonical user-facing Expense terminology while retaining legacy physical table/route aliases.
- Automated accessibility and keyboard-navigation checks.
- Updated README, ERD, and historical audit notes.

## B. Documentation Alignment Summary

### Fully aligned items

- Flask web application with SQLAlchemy data access.
- Supabase PostgreSQL production configuration and SQLite local-development fallback.
- Admin, Manager, and Staff roles with server-side route authorization.
- Registration defaults to Staff and requires administrator approval.
- Generic login error does not disclose whether the username or password was incorrect.
- Sales Order, Invoice, Expense, Dashboard, Reports, Analytics, and Admin Center modules.
- Excel/CSV historical-data upload with schema checks, row validation, duplicate indicators, EDA distributions, and outlier confirmation.
- Fuzzy client matching that can present multiple possible resolutions.
- Client value scoring based on Sales Order history.
- Descriptive analytics for sales trends, products, clients, peak periods, expenses, and comparative performance.
- Predictive analytics using an additive Holt-Winters implementation with backtesting and MAPE threshold status.
- Prescriptive rule-based recommendations with displayed trigger, source data, calculation, interpretation, and suggested action.
- Integrated Likert evaluation workflow and stored evaluation results.
- Future dates generate warnings rather than unnecessarily blocking data entry.
- Render service definition uses Gunicorn and requires `DATABASE_URL`.
- Responsive page behavior at a 390 x 844 viewport; no page-level horizontal overflow was observed on Sales Order, Invoice, Expense, or Analytics pages.

### Partially aligned items

- **Invoice/payment workflow:** screens and calculations exist, but partial-payment status is incorrect.
- **Analytics consistency:** newer analytics endpoints implement the documented framework, while legacy payload functions still use paid-only filters, linked-invoice-only joins, entry dates, and SQLite-specific date functions.
- **Database management:** schema and migration notes exist, but migrations are manual and the current local database is already behind the models.
- **Security:** password hashing, secure cookie settings, role checks, and secret environment variables are implemented; CSRF protection, login throttling, and upload-size limits are not.
- **Testing:** automated functional scripts and browser checks exist, but there is no demonstrated stress/load result, multi-browser compatibility result, formal coverage measurement, or completed UAT evidence.
- **Duplicate handling:** upload duplicates are reported for review, but key business identifiers such as `sales_orders.so_number` are not protected by database uniqueness constraints.

### Missing items

- A versioned migration framework such as Alembic/Flask-Migrate.
- A SQLite migration equivalent for the recent profile and evaluation schema changes.
- A reliable payment date field for collection-cycle and days-outstanding analysis.
- CSRF tokens/protection on state-changing form and JSON requests.
- Login attempt throttling or account lockout controls.
- Maximum upload request size and stronger file-content validation.
- Demonstrated performance/stress-test evidence required by the manuscript.

### Extra or undocumented items

- Theme editor and persistent system theme settings.
- Administrator SQL console, schema browser, maintenance commands, audit log viewer, and bulk data operations.
- Password-reset request queue managed by administrators.
- Generic JSON developer viewer.
- Gospel display widget.

The theme editor and audit/evaluation capabilities support the manuscript. The SQL console, developer viewer, and Gospel widget should be explicitly documented or removed from the production-facing scope.

## C. Critical Issues

### 1. Existing local database cannot start with the current models — Resolved in working revision

- **Affected module:** `database.db`, `app.py` model initialization
- **Requirement:** Local execution and deployment readiness
- **Problem:** `db.create_all()` does not alter existing tables. The current `users` table lacks `profile_photo_data` and `profile_photo_mime`; `evaluation_sessions` lacks `user_id`. Importing `app.py` fails with `sqlite3.OperationalError: no such column: users.profile_photo_data`.
- **Risk:** Critical
- **Recommended fix:** Back up the database, apply a versioned local migration, verify every model column against the live schema, and add a startup migration/version check. Do not delete a business database merely to recreate it.

### 2. Partial invoice payments are marked as fully paid — Resolved in working revision

- **Affected module:** `app.py` — `create_invoice()` and `update_invoice_payment()`
- **Requirement:** Correct invoice status, balances, revenue, and accounts receivable
- **Problem:** Status becomes `PAID` whenever `cr_number` is present, even if `balance > 0`. The Sales Order may correctly become `PARTIAL`, while the related invoice is incorrectly `PAID`.
- **Risk:** Critical
- **Recommended fix:** Derive invoice status from amount and balance:
  - `UNPAID` when paid amount is zero
  - `PARTIAL` when paid amount is positive and balance remains
  - `PAID` when balance is within the rounding tolerance

### 3. Legacy analytics can omit valid balances and payments — Resolved in active payload path

- **Affected module:** `analytics_services.py` — `build_analytics_payload()`, `_invoice_revenue()`, `_revenue_by_client()`, `_accounts_receivable()`, `_client_balances()`, `_revenue_leakage()`
- **Requirement:** Correct and consistent revenue, client balance, and receivable analytics
- **Problem:** Several calculations include only invoices with `status == "PAID"` or only invoices linked through Sales Orders. Partial payments and administrator-uploaded invoices can be excluded.
- **Risk:** High
- **Recommended fix:** Use `amount_paid > 0` for collected revenue, use `balance > 0` for receivables, include standalone uploaded invoices through the shared client-resolution logic, and retire duplicate legacy calculation paths.

### 4. Legacy revenue-leakage query is not PostgreSQL portable — Resolved

- **Affected module:** `analytics_services.py` — `_revenue_leakage()`
- **Requirement:** Supabase PostgreSQL production deployment
- **Problem:** The query calls SQLite `julianday()`. PostgreSQL does not provide this function, so `/get-analytics` can fail on Supabase.
- **Risk:** High
- **Recommended fix:** Use dialect-aware date arithmetic or calculate the date difference in Python from retrieved dates.

### 5. Business-date analytics still use entry timestamps in one path — Resolved

- **Affected module:** `analytics_services.py` — `_sales_performance()`
- **Requirement:** Sales trends based on actual transaction dates
- **Problem:** It groups Sales Orders using `created_at` instead of `order_date`, shifting back-entered records into the wrong period.
- **Risk:** High
- **Recommended fix:** Use calendar month boundaries and `SalesOrder.order_date`.

### 6. State-changing requests lack CSRF protection

- **Affected module:** application-wide POST/PUT/DELETE routes
- **Requirement:** Data security, confidentiality, integrity, and controlled access
- **Problem:** No Flask-WTF/CSRF mechanism or equivalent request token validation was found. SameSite cookies reduce some exposure but do not replace CSRF protection.
- **Risk:** High
- **Recommended fix:** Add CSRF protection to HTML forms and JSON requests, including admin, upload, user-management, invoice, expense, theme, and SQL-console actions.

## D. Database and Migration Issues

### Current schema findings

- The models define 17 runtime tables, including `system_settings`.
- `SYSTEM_ERD.md` states there are 16 tables but also describes `system_settings`; its table count is outdated.
- Older local databases may be missing `users.profile_photo_data`, `users.profile_photo_mime`, and `evaluation_sessions.user_id`; `defense_migrations.py` now backs up and migrates SQLite automatically.
- `docs/supabase_defense_readiness_migration.sql` supplies the equivalent idempotent production migration.
- `sales_orders.so_number` is not unique at database level.
- Client names are not unique; application-level matching reduces duplicates but cannot guarantee integrity under concurrent writes.
- Most status fields have no database check constraints.
- `Invoice` has no actual `payment_date`; `last_payment_date` is inferred from invoice dates.

### Required migrations

Apply only after backing up and confirming the target schema:

```sql
ALTER TABLE users ADD COLUMN profile_photo_data TEXT;
ALTER TABLE users ADD COLUMN profile_photo_mime VARCHAR(80);
ALTER TABLE evaluation_sessions ADD COLUMN user_id INTEGER REFERENCES users(id);

CREATE INDEX IF NOT EXISTS idx_evaluation_sessions_user_id_created
ON evaluation_sessions (user_id, created_at DESC);
```

Also add a migration for invoice payment dates if payment-cycle analytics remain in scope:

```sql
ALTER TABLE invoices ADD COLUMN payment_date DATE;
CREATE INDEX IF NOT EXISTS idx_invoices_payment_date
ON invoices (payment_date);
```

Before adding a unique Sales Order constraint, resolve existing duplicates:

```sql
SELECT so_number, COUNT(*)
FROM sales_orders
GROUP BY so_number
HAVING COUNT(*) > 1;
```

Then consider:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_orders_so_number
ON sales_orders (so_number);
```

### Migration recommendation

Adopt Flask-Migrate/Alembic and run migrations as an explicit Render release step. Add a read-only schema compatibility check to startup so missing columns produce a clear migration message rather than a query crash.

## E. Security Issues

### Implemented safeguards

- Werkzeug password hashing.
- Generic invalid-login response.
- Generic forgot-password response.
- Server-side role decorators on protected pages and APIs.
- Approval checks invalidate sessions for disabled or unapproved users.
- HttpOnly and SameSite session cookies; Secure cookies on Render/when configured.
- Production requires `DATABASE_URL`.
- `.env`, database files, caches, and upload folders are ignored by Git.
- Admin table output masks password hashes.

### Issues

1. **No CSRF protection — High**
2. **No login rate limiting or lockout — Medium**
3. **Fallback `dev-secret-key` — Medium:** safe only for development; fail closed when production mode is intended and `SECRET_KEY` is missing.
4. **No request upload-size limit — Medium:** large workbooks can exhaust memory during pandas/openpyxl processing.
5. **Extension-focused upload validation — Medium:** validate file signatures/content, not only filename suffixes.
6. **Admin SQL console permits arbitrary DML when dry-run is disabled — High operational risk:** administrator-only access helps, but require password re-authentication, explicit transaction preview, statement allowlisting, and stronger audit controls.
7. **Raw exception text returned by several APIs — Medium:** database and parser errors can disclose implementation details.
8. **Debug mode in direct execution — Low/Medium:** `app.run(debug=True)` is local-only but should be controlled by an environment flag.

## F. UI/UX Issues

### Browser-verified strengths

- Role-specific navigation is correct:
  - Manager: Home, Analytics, Reports
  - Staff: Home, Sales Order, Invoice, Expense
  - Admin: all operational, analytics, reporting, and database pages
- Direct unauthorized navigation redirects to the Dashboard.
- Empty states are present for invoices, sales orders, and analytics.
- Analytics upload requirements and date format are visible.
- Long tables use scroll containers.
- At mobile width, tested pages did not create document-level horizontal scrolling.
- No browser console warnings or errors were observed on the empty Analytics page.

### Issues and improvements

- The Admin Center now removes the developer note, uses task-oriented labels, defaults to curated business columns, and offers an optional technical-column view.
- Bulk actions, maintenance, schema inspection, and SQL tools are collapsed and clearly labeled as advanced.
- Expense is now the canonical interface/API/documentation term. Legacy `purchase_orders` storage and compatibility routes remain documented implementation details.
- Analytics contains a future-work comment for a client distribution chart. Either implement it or remove the placeholder comment.
- Narrow-screen select controls in the Expense debit row need additional width/ellipsis testing with long account names.
- The mobile check covered responsive Chrome-like rendering only; Safari, Firefox, and Edge compatibility remains unverified.

## G. Analytics Issues

### Implemented analytics

- KPI dashboard and date filters.
- Sales trends and product distribution.
- Client value scoring and cohorts.
- Peak month and weekday analysis.
- Historical upload EDA, validation, duplicate review, and outlier confirmation.
- Holt-Winters forecasts with fallback averaging.
- MAPE backtesting and configurable acceptance threshold.
- Rule-based recommendations.
- Comparative year analysis.
- Evaluation result aggregation.

### Calculation risks

- Partial payments are excluded when incorrectly marked `PAID` with a remaining balance.
- Legacy collected-revenue calculations count only `PAID` invoices rather than all positive payments.
- Standalone/admin-uploaded invoices are omitted from several client joins.
- One trend function uses `created_at` rather than `order_date`.
- Days outstanding is based on invoice date and lacks a true payment date.
- SQLite `julianday()` breaks the legacy leakage query on PostgreSQL.
- Client matching is duplicated: legacy analytics uses a simpler `SequenceMatcher`, while transaction handling uses the richer resolver and alias registry.
- `calculate_customer_behavior_score()` has weak normalization because two components become effectively constant for any client with orders; the newer client score path should be the single authoritative implementation.
- Multiple analytics endpoints calculate similar KPIs differently. This can make Dashboard, Analytics, Reports, and `/get-analytics` disagree.

### Recommended fixes

Create one analytics ledger/service contract and require all UI pages and exports to use it. Add benchmark integration tests with known expected totals for:

- linked and standalone invoices
- unpaid, partial, and paid invoices
- back-entered Sales Orders
- fuzzy client aliases
- SQLite and PostgreSQL
- MAPE accepted, rejected, and insufficient-data cases

## H. Final Recommendations

### Fix immediately

1. Migrate `database.db` so the application starts.
2. Correct invoice `UNPAID` / `PARTIAL` / `PAID` status derivation.
3. Correct analytics revenue and receivable filters.
4. Remove PostgreSQL-incompatible `julianday()` usage.
5. Consolidate client matching and analytics calculation paths.
6. Add CSRF protection.

### Fix next

1. Adopt Alembic/Flask-Migrate.
2. Add payment dates and update collection metrics.
3. Add upload-size and file-content validation.
4. Add login throttling and production secret enforcement.
5. Add database constraints after cleaning existing data.
6. Add PostgreSQL integration tests and known-value analytics fixtures.
7. Complete stress, compatibility, and formal UAT evidence.

### Optional improvements

1. Continue usability testing of the simplified Admin Center with non-developer administrators.
2. Decide whether the Gospel widget remains an approved themed feature.
3. Add a versioned Alembic/Flask-Migrate workflow.
4. Add full CSRF protection and login throttling.
5. Add PostgreSQL integration, browser compatibility, stress, and formal UAT evidence.

## Verification Record

- `python -m py_compile app.py analytics_services.py admin_services.py defense_migrations.py main.py`: passed.
- `python -m pip check`: passed.
- 16 repository check scripts under `tests/`: passed after the accessibility and defense-readiness checks were added.
- Isolated local server using a fresh temporary SQLite database: started successfully.
- Existing repository `database.db`: startup failed because the schema is behind the models.
- Browser checks: generic login error, Admin/Manager/Staff navigation, unauthorized route redirects, Analytics empty state, Admin data grid, Invoice empty state, and responsive layouts.
- Responsive viewport tested: 390 x 844.
- No production Supabase database was modified.
- The audit itself was read-only. The subsequent defense-readiness revision changed application, template, documentation, migration, and test files; those changes are recorded in the Revision Update above.
