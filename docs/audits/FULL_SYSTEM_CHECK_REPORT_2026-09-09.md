# System check and documentation alignment — September 9, 2026

## Verdict

**The README matches the main business modules, but not all implementation and setup details. The application is broadly functional locally, with confirmed defects that prevent a clean readiness verdict.**

`app.py` is the actual Flask application used by local startup and the configured production command (`gunicorn app:app`). It works with `analytics_services.py`, `admin_services.py`, `defense_migrations.py`, templates, and browser scripts; it is not the entire system by itself. The local database contains every model table and column, but its invoice/receipt relationships are currently broken.

Application source, README, and existing business records were not edited by this check. Audit scripts, logs, and this report were added.

## Verification results

| Check | Result |
|---|---|
| Existing regression checks | 31/31 passed |
| Main Python module compilation | Passed for app, analytics services, admin services, migrations, and main |
| Installed dependency consistency | `pip check`: no broken requirements |
| Runtime | Local virtual environment: Python 3.12.10; deployment version file: 3.11.9 |
| Registered routes | 109 rules, including the static rule |
| GET access probes | 434 requests across anonymous access and six roles; no HTTP 5xx responses |
| Template compilation | No errors |
| Model schema | 20 application tables |
| Existing local database schema | All expected model tables and columns present; additional SQLite statistics table `sqlite_stat1` |
| Existing local database file integrity | SQLite `quick_check`: OK |
| Existing local database relationships | FAILED: 836 foreign-key violations |
| Isolated invoice reset reproduction | FAILED: invoice deleted, associated receipt retained |
| Invalid request handling | FAILED on several routes; details below |
| Browser smoke check | Login, Home, Sales Order, Invoice, Expense, Analytics, Reports, and Admin Center loaded |

The GET probes cover parameter-free routes with GET support, excluding logout and session-timeout. These probes establish response behavior, not correctness of every payload or permission decision. Existing regression scripts provide additional role and workflow assertions. Passing them does not override the failures found by the additional checks.

## README compared with implementation

| README claim | Assessment | Evidence / correction |
|---|---|---|
| Flask, SQLAlchemy, SQLite locally, PostgreSQL for production | Matches configured architecture | `app.py:88-126`, `render.yaml`; live production was not contacted |
| Sales Orders, invoices, expenses, analytics, reports, evaluation, administration | Matches | Routes, templates, regression checks, and browser screens support these modules |
| Expense is canonical; purchase-order routes are compatibility aliases | Matches | `/expenses`, `/get-expenses`, `/create-expense`, and edit routes coexist with legacy aliases |
| Invoice status is balance-based | Matches | Payment-state and receipt workflows exist and their regression checks pass |
| Advanced technical tools are collapsed | Matches | Confirmed in Admin Center browser view |
| Production developer viewer is unavailable | Matches source | `dev_json_viewer()` checks production mode and returns 404 |
| Production SQL is read-only/dry-run | Wording needs precision | Production forces `dry_run=True`; statements execute and are rolled back. This is not a database-enforced read-only connection or a SELECT-only validator |
| 17 runtime tables | Incorrect | Current SQLAlchemy metadata defines 20 |
| Python 3.10 or newer | Incorrect | `app.py:31` imports `datetime.UTC`, requiring Python 3.11+; `.python-version` specifies 3.11.9 |
| Admin, Manager, Sales Staff, Accounting Staff, compatibility Staff | Incomplete setup description | These roles have access rules, but a fresh database seeds only admin, manager, staff, and IT Evaluator. Sales/accounting roles require explicit creation; IT Evaluator is omitted from README |
| June 18 report is the latest audit | Outdated | September 8 audit reports already exist, and this September 9 check adds fresh evidence |
| CSRF protection and login throttling remain outstanding | Matches source review | Neither protection was found in application code or templates |

Useful additions to README: collection receipt history, historical transaction imports, item category management, the five-minute idle timeout, and the single-active-device login behavior. These are implemented behaviors that the current summary does not explain.

The broader `docs/documentation.md` is also stale: it repeatedly says 76 routes, and describes `main.py` as the application entry point. Current runtime has 109 registered rules; `main.py` is a database connection diagnostic, as also noted in `.env.example`.

## Confirmed defects

### 1. Critical: invoice reset leaves orphaned receipts on SQLite

At `app.py:7690`, the reset endpoint bulk-deletes invoices without explicitly deleting related collection receipts. In the isolated database, a valid invoice and receipt were created, and resetting invoices returned HTTP 200. The invoice count became zero, the receipt count remained one, and `PRAGMA foreign_key_check` reported the broken reference. SQLite foreign-key enforcement does not make the declared cascade effective in this tested configuration.

The existing local `database.db`, inspected with a read-only connection, contains:

- 548 Sales Orders
- 0 invoices
- 836 collection receipts
- 0 expense records
- 1,708 analytics rows
- 836 foreign-key violations

The reset defect can produce this type of corruption; this check does not establish the history of how the existing records reached their present state. Passing SQLite file integrity checks does not mean business relationships are valid. Collections and invoice-based reporting cannot be treated as reconciled while these references remain broken.

Fix the reset transaction and add a regression assertion for receipt cleanup. Reconcile existing receipts against a trusted source or backup. Do not discard the receipts merely to eliminate the integrity errors.

### 2. High: missing login password causes HTTP 500

Posting an existing username without a password field causes HTTP 500. `app.py:4726` passes the missing value into password verification. Normalize missing credentials and return a controlled invalid-credentials response.

### 3. Medium: invalid JSON shapes cause server errors

Nonempty JSON arrays and JSON strings cause HTTP 500 at:

- `/create-sales-order` (`app.py:5993`)
- `/create-invoice` (`app.py:6517`)
- `/admin/transaction-reset` (`app.py:7671` onward)

The handlers assume an object and call `.get()` before validating the JSON shape. Empty objects on these routes correctly returned HTTP 400. Add object validation before reading fields.

### 4. Medium: inconsistent validation responses

`/create-expense` and `/create-client` return HTTP 200 with `success:false` and raw Python attribute errors for invalid JSON shapes. This makes HTTP-level error monitoring unreliable. An empty object submitted to `/create-client` also created `UNMAPPED CLIENT`; confirm whether that placeholder is an intended manual-entry rule or should be rejected.

### 5. Medium: mobile navigation clips destinations

At a 390 × 844 viewport, the Sales Order page shows Home, Sales Order, Invoice, Expense, and only the start of the next destination. Later destinations are offscreen with no visible menu button. The form content itself reflows. A visible mobile menu or clear scrolling affordance is needed.

### 6. Medium: Sales Order inputs lack associated labels

Browser DOM inspection confirmed zero associated labels and no `aria-label` for order date, quantity, unit cost, and selling price. The accessibility tree exposes IDs in place of useful field names. Source examples: `templates/sales_order.html:768`, `:827`, `:831`, and `:835`. Associate visible labels with their inputs and verify accessible names.

### 7. Low: corrupted Analytics text

The Analytics empty state visibly renders `ðŸ“Š`; the same invalid text is present at `templates/analytics.html:2959`. Other table/card controls also contain corrupted symbols. Replace these with valid UTF-8 characters or accessible icons.

### 8. Release hardening: acknowledged protections remain absent

CSRF protection and login throttling remain absent, consistent with README. Existing role checks, password hashing, and production configuration guards are present. This was a targeted source review, not a penetration test or dependency vulnerability scan.

## Suggested repair order

1. Fix invoice reset integrity and reconcile the existing orphaned receipts.
2. Normalize login input and validate JSON request shapes; return appropriate error status codes.
3. Correct README table count, Python requirement, role setup, audit links, and SQL wording; update the broader documentation's route count and entry point.
4. Repair mobile navigation, form labels, and corrupted Analytics text.
5. Complete the acknowledged security hardening and verify the deployed PostgreSQL environment separately.

## Scope and evidence

Business-data mutations ran only against in-memory SQLite. The real database was inspected using SQLite `mode=ro`. Browser checks used a separate in-memory instance on localhost port 5099 with an audit-only account. Browser inspection covered empty-state navigation and selected desktop/mobile presentation; it was not a complete browser execution of every transaction.

Live Render availability, deployed code parity, Supabase schema/data integrity, real concurrent load, comprehensive screen-reader behavior, dependency vulnerabilities, and forecast accuracy against real outcomes were not verified. No production-ready certification is implied.

Evidence in `full-check-2026-09-09/`:

- `regression-results.json`: exit status of all 31 repository checks
- Per-check `.log` files: detailed regression output
- `runtime_check.py`: repeatable isolated probes and read-only local database inspection
- `runtime-results.json`: route statuses, schema results, malformed inputs, reset reproduction, and database counts
- `runtime.log`: runtime output and error traces

Browser findings were observed in the current audit session; no new screenshot files were saved. September 8 screenshots are historical evidence, not substitutes for this run.
