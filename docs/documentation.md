# Syluxent ERP System - Complete Documentation

**Last Updated:** June 18, 2026  
**System Status:** Partially Ready — critical local fixes implemented and verified  
**Overall Compliance Estimate:** 90%

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Architecture](#system-architecture)
3. [Database Schema (ERD)](#database-schema-erd)
4. [Analytics System](#analytics-system)
5. [Deployment Guide](#deployment-guide)
6. [Testing & Verification](#testing--verification)
7. [Critical Issues & Recommendations](#critical-issues--recommendations)
8. [Demo Outline & Script](#demo-outline--script)
9. [Diagnostic & Validation Queries](#diagnostic--validation-queries)

---

## Executive Summary

**Syluxent** is a Flask-based ERP system designed to centralize sales orders, invoices, expenses, reports, user administration, and analytics in one workflow.

### Key Features
- **Authentication & Roles:** Admin, Manager, and Staff roles with server-side authorization
- **Sales Order Management:** Manual entry and spreadsheet (CSV/Excel) upload with client fuzzy matching
- **Invoice Processing:** Sales and service invoices with payment tracking and collection receipts
- **Expense Tracking:** Check/voucher tracking with debit categorization
- **Financial Reporting:** Summary reports, revenue leakage analysis, and accounts receivable
- **Advanced Analytics:** Descriptive analytics, Holt-Winters forecasting, client performance scoring, and recommendations
- **Admin Center:** User management, database inspection, audit logging, and theme settings
- **Evaluation Module:** Likert-scale evaluations with result aggregation

### Current Status
- Python syntax checks: ✅ Passed
- Flask routes: ✅ 76 registered routes
- System checks: ✅ Passed (auth, matching, analytics, uploads, evaluations)
- Authenticated pages/APIs: ✅ Verified
- Database migrations: ⚠️ SQLite auto-migration included; Supabase migration included
- CSRF protection: ❌ Not implemented
- Login throttling: ❌ Not implemented
- PostgreSQL compatibility: ⚠️ One legacy query uses SQLite-specific functions

---

## System Architecture

### Technology Stack

| Component | Technology |
|-----------|-----------|
| **Backend Framework** | Flask 2.3 with Flask-SQLAlchemy |
| **Database** | SQLite (development), Supabase PostgreSQL (production) |
| **Frontend** | HTML, CSS, JavaScript, Jinja templates |
| **Spreadsheet Support** | SheetJS (browser), pandas/openpyxl (Python backend) |
| **Data Visualization** | Chart.js (CDN) |
| **Deployment** | Render web service with Gunicorn |
| **Authentication** | Werkzeug password hashing, session-based |
| **Version Control** | GitHub |

### Architecture Layers

```
┌─────────────────────────────────────────────┐
│        Browser / Frontend Layer              │
│  (HTML, CSS, JavaScript, Jinja Templates)   │
└─────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────┐
│       Flask Web Application Layer            │
│  (app.py - 76 routes, session mgmt)         │
├─────────────────────────────────────────────┤
│  Service Layer (Business Logic)              │
│  - analytics_services.py                    │
│  - admin_services.py                        │
└─────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────┐
│    SQLAlchemy ORM Data Access Layer          │
│  (Maps Python classes to database tables)   │
└─────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────┐
│      Database Storage Layer                  │
│  Local: SQLite (database.db)                │
│  Production: Supabase PostgreSQL            │
└─────────────────────────────────────────────┘
```

### File Structure

```
root/
├── app.py                           # Main Flask application, 76 routes, SQLAlchemy models
├── analytics_services.py            # Analytics calculations and forecasting
├── admin_services.py                # Admin operations and database tools
├── defense_migrations.py            # SQLite-to-new-schema automatic migration
├── main.py                          # Application entry point
├── requirements.txt                 # Python dependencies
├── render.yaml                      # Render deployment configuration
├── database.db                      # SQLite database (local only)
├── templates/                       # Flask Jinja templates
│   ├── login.html, register.html, logout.html
│   ├── dashboard.html, analytics.html, reports.html
│   ├── admin.html, database_interface.html
│   ├── sales_order.html, invoices.html, purchase_orders.html
│   ├── evaluation.html, error_interface.html, landing.html
│   └── ...
├── static/
│   ├── css/                         # Styles
│   │   ├── styles.css
│   │   └── theme-overrides.css
│   ├── js/                          # JavaScript
│   │   └── system-states.js
│   ├── images/                      # Image assets
│   └── vendor/                      # Third-party libraries (Chart.js local copy)
├── instance/
│   ├── backups/                     # Database backups before migrations
│   └── ...
├── static/uploads/                  # User-uploaded files (temporary on Render)
├── tests/                           # 30+ automated test scripts
│   ├── accessibility_keyboard_check.py
│   ├── admin_client_list_check.py
│   ├── analytics_objectives_check.py
│   ├── defense_readiness_check.py
│   └── ...
└── docs/                            # Full documentation
    ├── README.md
    ├── analytics/                   # Analytics design
    ├── architecture/                # ERD and system design
    ├── audits/                      # Critical issue summaries and system reports
    ├── capstone-package/            # Capstone documentation package
    ├── database/                    # Diagnostic queries and migrations
    ├── deployment/                  # Deployment guides
    ├── design-reference/            # CSS, HTML, and design files
    └── testing/                     # Test analysis and test cases
```

### Core Modules

#### 1. Authentication & Authorization
- **File:** `app.py` (lines 1-200)
- **Features:**
  - Role-based access control (Admin, Manager, Staff)
  - Password hashing via Werkzeug
  - Session management with HttpOnly, SameSite cookies
  - Approval workflow for new registrations
  - Password reset request queue
  - Generic login error messages (no username disclosure)

#### 2. Sales Order Management
- **File:** `app.py` + `templates/sales_order.html`
- **Features:**
  - Manual sales order creation
  - Excel/CSV upload with auto-field detection
  - Client fuzzy matching (learns from aliases)
  - Store/branch tracking
  - Multiple line items with quantity and pricing
  - Terms (default 30 days) and notes

#### 3. Invoice Processing
- **File:** `app.py` + `templates/invoices.html`
- **Features:**
  - Sales and service invoice types
  - Payment tracking with collection receipts
  - Support for downpayment and full payment
  - 2307 tax form support
  - Invoice status derivation: UNPAID / PARTIAL / PAID (based on balance)
  - Confirmation modal with countdown

#### 4. Expense Tracking
- **File:** `app.py` + `templates/purchase_orders.html`
- **Features:**
  - Check/voucher number tracking
  - Multiple debit entries (16 debit types)
  - Cash amount and net balance calculation
  - Category tracking (Fixed/Variable expenses)
  - Legacy table name: `purchase_orders` (compatibility)

#### 5. Dashboard & Reporting
- **File:** `app.py` + `templates/dashboard.html`
- **Features:**
  - Financial summary cards (Revenue, Expenses, AR, Pondo, Sales Orders)
  - Client list with balances and client scores
  - Drill-through to unpaid sales orders
  - Date range filters (Year, Quarter, Month, All-time)
  - Real-time calculations from operational data

#### 6. Analytics System
- **See:** [Analytics System Section](#analytics-system)

#### 7. Admin Center
- **File:** `app.py` + `admin_services.py` + `templates/admin.html`
- **Features:**
  - User management (create, approve, disable, edit roles)
  - Database table views (Users, Roles, Clients, Sales Orders, Invoices, Expenses)
  - Session records viewer
  - Audit log viewer
  - Password reset request manager
  - Theme settings (persistent in `system_settings` table)
  - Safe SQL console (SELECT-only by default)
  - Database statistics and schema inspector
  - CSV export for admin tables
  - Bulk operations and maintenance commands

---

## Database Schema (ERD)

### Entity Relationship Diagram

```
roles 1 --< users
users 1 --< session_records
users 1 --< audit_logs
users 1 --< password_resets (user_id)
users 1 --< password_resets (resolved_by_user_id)
users 1 --< evaluation_sessions

clients 1 --< client_aliases
clients 1 --< sales_orders
sales_orders 1 --< sales_order_items
sales_orders 1 --< invoices
invoices 1 --< collection_receipts
users 1 --< collection_receipts (created_by_user_id)

purchase_orders 1 --< purchase_order_debits
evaluation_questions 1 --< evaluation_responses
evaluation_sessions 1 --< evaluation_responses

analytics_data (no declared foreign keys)
system_settings (key-value pairs)
```

### Table Reference

#### Authentication & Admin (7 tables)

**roles**
- `id` [PK, INTEGER]
- `role_name` [UNIQUE, VARCHAR(50)]
- `description` [TEXT]

**users**
- `id` [PK, INTEGER]
- `username` [UNIQUE, VARCHAR(80)]
- `email` [UNIQUE, VARCHAR(255)]
- `password_hash` [VARCHAR(120)]
- `role_id` [FK → roles.id]
- `status` [VARCHAR(20)]: pending, approved, rejected, disabled
- `approved_by` [FK → users.id, NULLABLE]
- `approved_at` [DATETIME]
- `profile_photo`, `profile_photo_data`, `profile_photo_mime` [Profile image storage]
- `created_at`, `updated_at` [DATETIME]

**session_records**
- `id` [PK, INTEGER]
- `user_id` [FK → users.id, NULLABLE]
- `username`, `role_name` [VARCHAR]
- `login_at`, `logout_at` [DATETIME]
- `status` [VARCHAR(20)]

**audit_logs**
- `id` [PK, INTEGER]
- `user_id` [FK → users.id, NULLABLE]
- `username` [VARCHAR(80)]
- `action` [VARCHAR(100)]
- `table_name` [VARCHAR(100)]
- `record_id`, `old_value`, `new_value` [TEXT]
- `created_at` [DATETIME]

**password_resets**
- `id` [PK, INTEGER]
- `user_id` [FK → users.id]
- `username` [VARCHAR(80)]
- `status` [VARCHAR(20)]
- `requested_at`, `resolved_at` [DATETIME]
- `resolved_by_user_id` [FK → users.id, NULLABLE]

**system_settings**
- `key` [PK, VARCHAR(100)]
- `value` [TEXT]
- `updated_at` [DATETIME]
- **Purpose:** Theme, runtime settings (persistent storage)

#### Client & Sales (6 tables)

**clients**
- `id` [PK, INTEGER]
- `client_name` [VARCHAR(200)]
- `contact_info` [VARCHAR(500)]
- `status`, `balance_status` [VARCHAR]
- `total_revenue`, `total_paid`, `total_balance` [FLOAT]
- `last_invoice_date`, `last_payment_date` [DATE]
- `financials_updated_at`, `created_at` [DATETIME]

**client_aliases**
- `id` [PK, INTEGER]
- `alias_name` [VARCHAR(200)]
- `normalized_alias` [UNIQUE, VARCHAR(200)]
- `client_id` [FK → clients.id]
- `status` [VARCHAR(20)]
- `created_at` [DATETIME]
- **Purpose:** Fuzzy client matching; learned from sales order entries

**sales_orders**
- `id` [PK, INTEGER]
- `so_number` [VARCHAR(50)]
- `client_id` [FK → clients.id]
- `company_name`, `official_client_name`, `original_entered_client_name` [VARCHAR(200)]
- `store_name`, `store_branch` [VARCHAR(200)]
- `order_date` [DATE] ⭐ Business date (used for analytics)
- `sales_staff` [VARCHAR(100)]
- `terms` [INTEGER]: default 30
- `notes` [TEXT]
- `total_amount` [FLOAT]
- `status` [VARCHAR(20)]
- `created_at` [DATETIME] ⭐ Entry timestamp (not used for analytics)

**sales_order_items**
- `id` [PK, INTEGER]
- `sales_order_id` [FK → sales_orders.id]
- `particular` [VARCHAR(500)]
- `quantity`, `unit_cost`, `selling_price`, `total` [FLOAT]

**sales_order_branches**
- `id` [PK, INTEGER]
- [Not detailed in current version]

#### Invoicing (3 tables)

**invoices**
- `id` [PK, INTEGER]
- `invoice_number` [UNIQUE, VARCHAR(50)]
- `sales_order_id` [FK → sales_orders.id, NULLABLE] ⭐ Can be NULL for admin uploads
- `invoice_type` [VARCHAR(20)]: Sales, Service
- `invoice_date`, `payment_date` [DATE]
- `summary` [TEXT]
- `payment_type`, `cr_number` [VARCHAR]
- `payment_amount`, `tax_amount_paid` [FLOAT]
- `is_2307_checked` [BOOLEAN]
- `total_amount`, `amount_paid`, `balance` [FLOAT]
- `status` [VARCHAR(20)]: derived from amount_paid and balance
  - UNPAID: `amount_paid == 0`
  - PARTIAL: `amount_paid > 0 AND balance > 0`
  - PAID: `balance <= 0` (within rounding tolerance)
- `uploaded_client_name` [VARCHAR(200)] ⭐ For admin invoice uploads
- `upload_source` [VARCHAR(50)]
- `admin_upload_note` [TEXT]
- `created_at` [DATETIME]

**collection_receipts**
- `id` [PK, INTEGER]
- `invoice_id` [FK → invoices.id]
- `receipt_date`, `cr_number` [DATE, VARCHAR]
- `normalized_cr_number` [VARCHAR(50)]
- `payment_type` [VARCHAR(20)]
- `payment_amount`, `tax_amount_paid` [FLOAT]
- `is_2307_checked` [BOOLEAN]
- `collected_total` [FLOAT]
- `created_by_user_id` [FK → users.id]
- `recorded_by` [VARCHAR(80)]
- `created_at` [DATETIME]

#### Expenses (2 tables)

**purchase_orders** (legacy name for expense records)
- `id` [PK, INTEGER]
- `check_voucher_number`, `check_number` [VARCHAR(50)]
- `check_date`, `date`, `or_date` [DATE]
- `ar_cr_or_number`, `po_number`, `lf_no` [VARCHAR(50)]
- `particulars` [VARCHAR(500)]
- `supplier_payee` [VARCHAR(200)]
- `tin_number` [VARCHAR(50)]
- `cash_amount` [FLOAT]
- `net_balance` [FLOAT]
- `status` [VARCHAR(20)]
- `category` [VARCHAR(20)]: FIXED, VARIABLE
- `created_at` [DATETIME]

**purchase_order_debits** (debit allocations)
- `id` [PK, INTEGER]
- `purchase_order_id` [FK → purchase_orders.id]
- `debit_type` [VARCHAR(100)]: 16 account types
- `amount` [FLOAT]

#### Analytics (1 table)

**analytics_data**
- `analytics_id` [PK, INTEGER]
- `source_type`, `source_id` [TEXT]
- `transaction_date` [DATE]
- `financial_stage` [TEXT]
- `flow_direction` [TEXT]: INFLOW, OUTFLOW
- `flow_status` [TEXT]: ACTUAL, PROJECTED
- `party_name`, `party_role` [TEXT]
- `amount`, `balance_amount` [FLOAT]
- `category` [TEXT]
- `status` [TEXT]
- `description` [TEXT]
- `upload_batch_id` [VARCHAR(80)]
- `source_filename` [VARCHAR(255)]
- `source_format` [VARCHAR(20)]
- `created_at` [DATETIME]
- **Purpose:** Historical ledger data from uploads; supports overview analytics

#### Evaluation (3 tables)

**evaluation_sessions**
- `id` [PK, INTEGER]
- `user_id` [FK → users.id, NULLABLE]
- `evaluator_name` [VARCHAR(120)]
- `evaluator_role` [VARCHAR(80)]
- `overall_comment` [TEXT]
- `overall_mean` [FLOAT]
- `interpretation` [VARCHAR(50)]
- `created_at` [DATETIME]

**evaluation_questions**
- `id` [PK, INTEGER]
- `category` [VARCHAR(80)]
- `question_text` [TEXT]
- `display_order` [INTEGER]
- `is_active` [BOOLEAN]

**evaluation_responses**
- `id` [PK, INTEGER]
- `session_id` [FK → evaluation_sessions.id]
- `question_id` [FK → evaluation_questions.id]
- `rating` [INTEGER]: 1-5 Likert scale
- `comment` [TEXT]
- `created_at` [DATETIME]

### Live Runtime Table Checklist

The system includes **19 runtime tables**:

1. `analytics_data`
2. `audit_logs`
3. `client_aliases`
4. `clients`
5. `collection_receipts`
6. `evaluation_questions`
7. `evaluation_responses`
8. `evaluation_sessions`
9. `invoices`
10. `password_resets`
11. `purchase_order_debits`
12. `purchase_orders`
13. `roles`
14. `sales_order_branches`
15. `sales_order_items`
16. `sales_orders`
17. `session_records`
18. `system_settings`
19. `users`

---

## Analytics System

### Overview

The analytics system provides three data paths:

1. **Overview Analytics** (Ledger-Based): Cash-flow analytics from `analytics_data`
2. **Revenue & Operational Analytics** (Sales-Order-Based): Operational metrics from live tables
3. **Historical Analytics** (Upload-Based): Imported historical data with validation

### Data Sources

**Live Operational Tables:**
- `sales_orders`, `sales_order_items`
- `invoices`, `collection_receipts`
- `purchase_orders`, `purchase_order_debits`
- `clients`, `client_aliases`
- `analytics_item_categories`
- `analytics_data`

**Supported Upload Schemas:**

*Sales Detail Schema:*
```
DATE, COMPANY NAME, STORE NAME, COST, QUANTITY, SELLING PRICE
Optional: STORE BRANCH, PARTICULAR
```

*Ledger Schema:*
```
SOURCE_TYPE, SOURCE_ID, TRANSACTION_DATE, FINANCIAL_STAGE,
FLOW_DIRECTION, FLOW_STATUS, PARTY_NAME, PARTY_ROLE, AMOUNT,
BALANCE_AMOUNT, CATEGORY, STATUS, DESCRIPTION
```

### Core Formulas

#### Overview Metrics

**Gross Revenue:**
```
SUM(amount WHERE flow_direction = 'INFLOW' AND flow_status = 'ACTUAL')
```

**Total Cost / Expense:**
```
SUM(amount WHERE flow_direction = 'OUTFLOW' AND flow_status = 'ACTUAL')
```

**Profit/Loss:**
```
gross_revenue - total_cost
```

**Percentage Change:**
```
((current - previous) / previous) * 100
(returns NULL if previous is zero)
```

#### Sales Order Metrics

**Item Revenue (Deduplicated):**
```
item_revenue = item.total OR (item.quantity * item.selling_price)
```

**Total Revenue:**
```
SUM(deduplicated item_revenue)
```

**Sales Count:**
```
COUNT(SalesOrder rows in selected date range)
```

**Top Items:**
```
GROUP BY item.particular
ORDER BY SUM(quantity) DESC
```

**Monthly Trend:**
```
monthly_revenue = SUM(item_revenue GROUP BY order_date month)
monthly_quantity = SUM(quantity GROUP BY order_date month)
average_quantity = monthly_quantity / active_sales_days
```

#### Client Analysis Metrics

**Client/Store Grouping (by Store Name):**
```
sales_order_value = SUM(order item totals)
order_count = COUNT(SalesOrder)
branches_count = COUNT(unique branches)
total_paid = SUM(Invoice.amount_paid for this client)
balance = sales_order_value - total_paid
profit_margin = (sales_order_value - total_cost) / sales_order_value * 100
```

**Recency Ratio:**
```
days_since_purchase = today - latest_order_date
recency_ratio = 1 - min(days_since_purchase, 365) / 365
(clamped between 0 and 1)
```

**Client Performance Score:**
```
amount_score = (store_sales_order_value / max_sales_order_value) * 50
frequency_score = (store_order_count / max_order_count) * 30
branch_score = (store_branch_count / max_branch_count) * 20

total_score = amount_score + frequency_score + branch_score (max 100)
normalized_score = total_score / 100
```

**ABC Client Classification:**
- A-Class: Cumulative revenue % < 80
- B-Class: Cumulative revenue % 80-95
- C-Class: Cumulative revenue % >= 95

#### Expense Metrics

**Fixed vs Variable:**
```
fixed_expenses = SUM(cash_amount WHERE category = 'FIXED')
variable_expenses = SUM(cash_amount WHERE category = 'VARIABLE')
total_expenses = fixed_expenses + variable_expenses

fixed_share = (fixed_expenses / total_expenses) * 100
variable_share = (variable_expenses / total_expenses) * 100
```

### Forecasting

**Algorithm:** Additive Holt-Winters with fallback averaging

**Components:**
- Level (baseline): baseline value for the time series
- Trend: direction and magnitude of change
- Seasonality: repeating patterns
- Damping: reduce trend over time

**Error Metric:** Mean Absolute Percentage Error (MAPE)

**Backtest:** Validated against historical months to measure forecast accuracy

**Acceptance Threshold:** Configurable MAPE limit (default ~20-30%)

**Output:**
- 3-month or 6-month forward forecast
- Confidence intervals
- MAPE status: Accepted / Rejected / Insufficient Data

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/analytics` | GET | Analytics page |
| `/api/analytics/generate` | POST | Rebuild analytics data |
| `/api/analytics/overview` | GET | Overview KPI dashboard |
| `/api/analytics/overview/upload` | POST | Upload historical data |
| `/api/analytics/sales` | GET | Sales trends and forecasts |
| `/api/analytics/clients` | GET | Client analysis and scores |
| `/api/analytics/expenses` | GET | Expense breakdown |
| `/api/analytics/item-categories` | GET | Product categorization |
| `/api/analytics/comparative` | GET | Year-over-year comparison |

### Key Functions (analytics_services.py)

- `build_analytics_payload()` - Assembles all analytics data
- `_revenue_by_client()` - Client revenue attribution
- `_client_balances()` - Outstanding client balances
- `_accounts_receivable()` - Total AR metrics
- `_revenue_leakage()` - High-impact client analysis
- `_sales_performance()` - Monthly sales trends
- `get_sales_analysis()` - Full sales analytics
- `get_clients_analysis()` - Client performance scoring
- `get_expenses_breakdown()` - Expense categorization
- `holt_winters_forecast()` - Predictive forecasting
- `backtest_holt_winters()` - Forecast validation

---

## Deployment Guide

### Local Development Setup

**Prerequisites:**
- Python 3.11+
- pip

**Steps:**

1. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\Activate.ps1  # Windows
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run application:
   ```bash
   python app.py
   ```

4. Access at `http://localhost:5000`

**Default Credentials:**
- Admin: `admin` / `admin123`
- Manager: `manager` / `manager123`
- Staff: `staff` / `staff123`

### Render Deployment

**Configuration:**

- **Runtime:** Python
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn app:app`

**Required Environment Variables:**

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Supabase PostgreSQL connection string | `postgresql+psycopg2://user:pass@host:5432/db` |
| `SECRET_KEY` | Session signing key (generate random) | (long random string) |
| `DEFAULT_ADMIN_PASSWORD` | Initial admin password | `secure_password_123` |

**Optional Environment Variables:**

| Variable | Description |
|----------|-------------|
| `DEFAULT_ADMIN_USERNAME` | Default admin username (default: `admin`) |
| `DEFAULT_MANAGER_USERNAME` | Manager seed account username |
| `DEFAULT_MANAGER_PASSWORD` | Manager seed account password |
| `DEFAULT_STAFF_USERNAME` | Staff seed account username |
| `DEFAULT_STAFF_PASSWORD` | Staff seed account password |
| `SESSION_COOKIE_SECURE` | Set to `true` on HTTPS-only deployment |

**Steps:**

1. Push code to GitHub
2. Connect GitHub repository to Render
3. Set environment variables in Render dashboard
4. Deploy manually or enable auto-deploy
5. Monitor deploy logs in Render dashboard

### Supabase PostgreSQL Setup

1. Create Supabase project
2. Get pooled connection string from Supabase dashboard
3. Set `DATABASE_URL` in Render
4. Run migrations from `docs/database/`:
   ```sql
   -- supabase_defense_readiness_migration.sql
   -- supabase_evaluation_user_id_migration.sql
   -- supabase_sales_order_query_indexes.sql
   -- supabase_user_approval_migration.sql
   -- supabase_render_multi_user_migration.sql
   ```

### Database Migrations

**Local SQLite:**
- `defense_migrations.py` runs automatically on startup
- Backs up database before schema changes
- Creates required columns and indexes

**Production PostgreSQL:**
- Manual SQL migrations from `docs/database/`
- Apply migrations in Supabase SQL Editor
- Test on staging before production

**Required Production Migrations:**

```sql
-- Add profile photo and evaluation user tracking
ALTER TABLE users ADD COLUMN profile_photo_data TEXT;
ALTER TABLE users ADD COLUMN profile_photo_mime VARCHAR(80);
ALTER TABLE evaluation_sessions ADD COLUMN user_id INTEGER REFERENCES users(id);

-- Create indexes for performance
CREATE INDEX idx_evaluation_sessions_user_id_created
ON evaluation_sessions (user_id, created_at DESC);
```

### Backup Recommendations

- **Daily:** Verify Supabase automatic backups
- **Weekly:** Test restore/export on non-production database
- **Before Updates:** Manual database backup
- **Post-Restore:** Verify at least one successful restoration

---

## Testing & Verification

### Test Coverage

**30+ Automated Test Scripts** in `tests/`:

| Category | Tests |
|----------|-------|
| **Authentication & Authorization** | `user_approval_check.py`, `admin_user_management_check.py` |
| **Dashboard** | `dashboard_home_check.py`, `smooth_transitions_check.py` |
| **Sales Orders** | `sales_order_manual_print_check.py`, `sales_order_query_check.py` |
| **Invoices** | `invoice_collection_csv_check.py`, `invoice_quantity_print_check.py` |
| **Analytics** | `analytics_objectives_check.py`, `analytics_chart_asset_check.py` |
| **Data Integrity** | `compiled_sales_import_check.py`, `historical_upload_schema_check.py` |
| **Client Management** | `client_matching_check.py`, `gongcha_branch_safeguard_check.py` |
| **Admin Functions** | `admin_data_grid_check.py`, `admin_client_list_check.py` |
| **Accessibility** | `accessibility_keyboard_check.py`, `interface_layout_check.py` |
| **Deployments** | `render_multi_user_check.py`, `defense_readiness_check.py` |

### Running Tests

```bash
# Individual test
python tests/test_name.py

# All tests
python -m pytest tests/

# Specific module
python -m pytest tests/analytics_*
```

### Test Preparation Checklist

Before manual testing:

1. Prepare test accounts (admin, manager, staff, accounting)
2. Create small valid upload files (CSV/Excel)
3. Prepare expected calculation totals
4. Set up screenshot folder
5. Document test records and IDs

### Verification Record

- ✅ Python syntax check: `app.py`, `analytics_services.py`, `admin_services.py`, `main.py`
- ✅ Flask routes: 76 registered
- ✅ 16 repository check scripts: passed
- ✅ Local server with fresh SQLite: started successfully
- ✅ Browser checks: login, navigation, redirects, empty states, responsive layouts
- ✅ Responsive viewport: 390 x 844

### Known Compliance Gaps

- ❌ CSRF protection not implemented
- ❌ Login rate limiting not implemented
- ❌ Maximum upload size limit not enforced
- ❌ Sales Order Excel processing still includes Python backend path
- ⚠️ One legacy analytics query uses SQLite `julianday()` (breaks on PostgreSQL)
- ⚠️ Partial payment status logic not fully tested across all paths

---

## Critical Issues & Recommendations

### CRITICAL Issues (Fix ASAP)

#### 1. Dual Company Matching Functions (Data Consistency Risk)

**Problem:** Two incompatible company matching implementations:
- `analytics_services.py`: Basic string normalization + SequenceMatcher
- `app.py`: Advanced fuzzy matching with Levenshtein distance, RapidFuzz, learned aliases

**Impact:** Same company "TEAMASTERS INC" vs "TEAMAKERS INC" matches in one system but not the other, causing revenue misattribution or duplication.

**Recommendation:** Unify matching logic—use `app.py`'s superior implementation in analytics, or create shared utility function.

#### 2. Missing Admin Invoices in Analytics Queries

**Problem:** Four analytics functions only join through `SalesOrder → Invoice`, excluding orphaned admin-uploaded invoices:
- `_revenue_by_client()` (line 162)
- `_client_balances()` (line 199)
- `_accounts_receivable()` (line 180)
- `_revenue_leakage()` (line 141)

**Impact:** Missing 20-50% of revenue if admin invoice volume is high. Client balance reports show wrong totals.

**Recommendation:** Update all four functions to use UNION pattern or LEFT JOIN to include invoices where `sales_order_id IS NULL AND uploaded_client_name IS NOT NULL`.

#### 3. Invoice Status Incorrectly Marked PAID (RESOLVED in June 18 revision)

**Issue:** Status becomes `PAID` whenever `cr_number` is present, even if `balance > 0`.

**Status:** ✅ Fixed in current revision—status now derives from `amount_paid` and `balance`

#### 4. Legacy Analytics Only Count "PAID" Invoices

**Problem:** Several calculations include only `status = 'PAID'`, missing partial payments.

**Recommendation:** Change filter from `status == "PAID"` to `amount_paid > 0` throughout analytics layer.

#### 5. Sales Trends Use Entry Date Instead of Order Date

**Problem:** `_sales_performance()` uses `created_at` instead of `order_date`, shifting back-entered records into wrong periods.

**Example:** Order business date Jan 5, entry date Feb 10 → assigned to February, not January.

**Impact:** Monthly/quarterly trends completely wrong.

**Recommendation:** Replace `SalesOrder.created_at` with `SalesOrder.order_date` in `_sales_performance()`.

#### 6. PostgreSQL Incompatible Query in Analytics

**Problem:** `_revenue_leakage()` uses SQLite `julianday()` function which doesn't exist in PostgreSQL.

**Impact:** `/api/analytics/overview` fails on Supabase PostgreSQL deployment.

**Recommendation:** Use dialect-aware date arithmetic or calculate difference in Python.

### HIGH Priority Issues

#### 1. Missing CSRF Protection

**Affected:** All POST/PUT/DELETE routes across app

**Risk:** Cross-site request forgery on forms, API uploads, user management, theme settings, SQL console

**Recommendation:** Add Flask-WTF CSRF tokens to all state-changing operations

#### 2. No Login Rate Limiting

**Affected:** `/login` route

**Risk:** Brute-force password attacks

**Recommendation:** Implement attempt counting + exponential backoff or account lockout after N failed attempts

#### 3. Legacy SQLite Compatibility Migration Issue

**Problem:** Existing `database.db` cannot start with current `users` model (missing `profile_photo_data`, `profile_photo_mime`)

**Status:** ✅ Fixed—`defense_migrations.py` auto-migrates on startup with timestamped backup

#### 4. No Upload Size Limit

**Affected:** File uploads for Sales Orders, Invoices, Analytics

**Risk:** Large workbooks exhaust server memory during pandas/openpyxl processing

**Recommendation:** Enforce max upload size (e.g., 10MB) at Flask middleware level

### MEDIUM Priority Issues

#### 1. Timezone Inconsistency

**Affected:** Date calculations in analytics and reporting

**Issue:** `datetime.now()` uses local system time; database may be UTC; `julianday()` assumes UTC

**Risk:** 1-14 hour offset in calculations

**Recommendation:** Use `datetime.now(UTC)` consistently throughout

#### 2. Payment Date vs Invoice Date Confusion

**Affected:** Days outstanding calculations in `_revenue_leakage()` and `_accounts_receivable()`

**Issue:** Uses `invoice_date` instead of actual `payment_date`

**Example:** Invoice issued Jan 1, paid Jan 15, but shows 160 days outstanding (from Jan 1 to Jun 9) instead of actual 14-day cycle

**Recommendation:** Add `payment_date` field to Invoice model; track actual payment date from collection receipts

#### 3. Admin SQL Console Security

**Risk:** Operator accidentally runs DML or DDL commands; limited audit trail

**Recommendation:** Require password re-authentication, explicit preview, SQL allowlisting, stronger audit controls

---

## Demo Outline & Script

### System Check Summary for Demo

- Python syntax check: ✅ Passed
- Flask app import: ✅ 76 registered routes
- System checks: ✅ Passed
- Database smoke test: ✅ Passed
- Browser checks: ✅ Passed

### Demo Preparation

1. **Start Application:**
   ```bash
   venv\Scripts\python.exe app.py
   # or
   python app.py
   ```

2. **Open Browser:**
   ```
   http://localhost:5000
   ```

3. **Prepare Test Accounts:**
   - Admin: `admin` / `admin123`
   - Manager: `manager` / `manager123`
   - Staff: `staff` / `staff123`

4. **Prepare Sample Data:**
   - Clean Excel file with sales order format
   - Expected calculation totals sheet

### Demo Flow (25 Minutes)

#### 1. Opening (2 minutes)
- Show landing page
- Explain role-based access
- Show login page

#### 2. Authentication & Navigation (3 minutes)
- Log in as Staff → show Staff nav (Home, Sales Order, Invoice, Expense)
- Log out
- Log in as Manager → show Manager nav (Home, Analytics)
- Log out
- Log in as Admin → show Admin nav (all modules)

#### 3. Dashboard (2 minutes)
- Financial cards: AR, Revenue, Expenses, Pondo, Sales Orders
- Clients tab with balance drill-through
- Show unpaid sales orders modal

#### 4. Sales Order Module (4 minutes)
- Upload sample Excel file
- Auto-identify fields
- Manual override example
- Confirm and save

#### 5. Invoice Module (3 minutes)
- Select pending sales order
- Enter invoice number, payment, tax
- Show 2307 checker
- Confirmation countdown
- Save to table

#### 6. Expense Module (3 minutes)
- Enter voucher, date, supplier, particulars
- Add debit entries
- Show balance calculation
- Save

#### 7. Reports & Admin (4 minutes)
- Open Reports → show sales/expense/revenue reports
- Open Admin Center → show Users, Clients, Sales Orders views
- Show database stats

#### 8. Analytics (3 minutes)
- Overview KPIs
- Revenue trends
- Client analysis
- Export CSV / Print preview

#### 9. Closing (1 minute)
- Summarize value proposition: centralized records, reduced manual tracking, clear visibility

### Recovery Lines

- **No data:** "This view updates automatically as records are added."
- **CDN assets fail:** "Full interface requires internet for frontend libraries."
- **Excel upload slow:** "System validates spreadsheet before committing."
- **Login fails:** "Using seeded default accounts: admin / admin123, manager / manager123, staff / staff123"
- **Analytics needs confirmation:** "System detected unusual values and asks for confirmation to protect data quality."

### Timing Breakdown

| Section | Time |
|---------|------|
| Opening | 2 min |
| Authentication | 3 min |
| Dashboard | 2 min |
| Sales Order | 4 min |
| Invoice | 3 min |
| Expense | 3 min |
| Reports/Admin | 4 min |
| Analytics | 3 min |
| Closing | 1 min |
| **Total** | **25 min** |

---

## Diagnostic & Validation Queries

### Check: Admin Invoice Volume

```sql
SELECT 
    'Total Invoices' as metric,
    COUNT(*) as count,
    COALESCE(SUM(amount_paid), 0) as total_paid
FROM invoices

UNION ALL

SELECT 
    'With Sales Order Link' as metric,
    COUNT(*) as count,
    COALESCE(SUM(amount_paid), 0) as total_paid
FROM invoices
WHERE sales_order_id IS NOT NULL

UNION ALL

SELECT 
    'Orphaned (Admin Upload)' as metric,
    COUNT(*) as count,
    COALESCE(SUM(amount_paid), 0) as total_paid
FROM invoices
WHERE sales_order_id IS NULL 
  AND uploaded_client_name IS NOT NULL;
```

**Interpretation:**
- If "Orphaned" > 20% of Total → Issue is CRITICAL
- If "Orphaned" < 5% of Total → Issue is low priority

### Check: Revenue Discrepancy

```sql
SELECT 
    'PAID status invoices' as source,
    COUNT(*) as invoice_count,
    COALESCE(SUM(amount_paid), 0) as revenue
FROM invoices
WHERE status = 'PAID'

UNION ALL

SELECT 
    'All invoices with amount_paid > 0' as source,
    COUNT(*) as invoice_count,
    COALESCE(SUM(amount_paid), 0) as revenue
FROM invoices
WHERE amount_paid > 0;
```

**Expected:** The second query should show more invoices/revenue (includes partial payments).

### Check: Date Field Issue (Order Date vs Entry Date)

```sql
SELECT 
    CASE 
        WHEN DATE(order_date) = DATE(created_at) THEN 'Same day'
        WHEN CAST((julianday(created_at) - julianday(order_date)) AS INTEGER) > 0 
             AND CAST((julianday(created_at) - julianday(order_date)) AS INTEGER) <= 1 
             THEN 'Entered next day'
        WHEN CAST((julianday(created_at) - julianday(order_date)) AS INTEGER) > 1 
             THEN 'Delayed entry (>1 day)'
        ELSE 'Before order date'
    END as entry_pattern,
    COUNT(*) as order_count
FROM sales_orders
WHERE order_date IS NOT NULL
GROUP BY entry_pattern
ORDER BY COUNT(*) DESC;
```

**Interpretation:**
- If "Delayed entry (>1 day)" has >30% volume → Trends will be inaccurate

### Check: Partial Payment Status

```sql
SELECT 
    status,
    COUNT(*) as invoice_count,
    COALESCE(SUM(amount_paid), 0) as total_paid
FROM invoices
GROUP BY status
ORDER BY COUNT(*) DESC;

-- Show invoices with amount_paid but not PAID status
SELECT 
    status,
    COUNT(*) as count,
    COALESCE(SUM(amount_paid), 0) as paid_amount
FROM invoices
WHERE amount_paid > 0 
  AND status != 'PAID'
GROUP BY status;
```

**Interpretation:** Should show PARTIAL invoices if partial payments exist.

### Check: Client Financial Accuracy

```sql
SELECT 
    c.id,
    c.client_name,
    c.total_revenue as stored_revenue,
    c.total_balance as stored_balance,
    (SELECT COALESCE(SUM(so.total_amount), 0)
     FROM sales_orders so
     WHERE so.client_id = c.id) as so_revenue
FROM clients c
WHERE c.total_revenue > 0
ORDER BY c.total_revenue DESC
LIMIT 20;
```

**Expected:** `stored_revenue` should ≈ `so_revenue` (within 2-5%). If difference > 10% → Data consistency issue.

### Check: Company Name Inconsistencies

```sql
SELECT 
    UPPER(TRIM(company_name)) as normalized_name,
    COUNT(DISTINCT company_name) as variant_count,
    COUNT(*) as total_orders,
    GROUP_CONCAT(DISTINCT company_name, ' | ') as variations
FROM sales_orders
WHERE company_name IS NOT NULL
GROUP BY UPPER(TRIM(company_name))
HAVING COUNT(DISTINCT company_name) > 1
ORDER BY total_orders DESC
LIMIT 20;
```

**Example Output:**
```
TEAMASTERS INC | 3 variants | 150 orders
  - TEAMASTERS INC
  - Teamasters Inc
  - TEAMASTERS INCORPORATED
```

### Quick Data Quality Score

```sql
SELECT 
    (SELECT COUNT(*) FROM invoices 
     WHERE sales_order_id IS NULL AND uploaded_client_name IS NOT NULL) 
        as orphaned_invoices,
    (SELECT COUNT(*) FROM invoices 
     WHERE status != 'PAID' AND amount_paid > 0) 
        as partial_payments,
    (SELECT COUNT(*) FROM sales_orders 
     WHERE DATE(order_date) != DATE(created_at)) 
        as delayed_entries,
    (SELECT COUNT(DISTINCT UPPER(TRIM(company_name))) FROM sales_orders) 
        as unique_company_names_exact,
    (SELECT COUNT(DISTINCT LOWER(TRIM(company_name))) FROM sales_orders) 
        as unique_company_names_normalized,
    (SELECT COUNT(*) FROM client_aliases WHERE status = 'ACTIVE') 
        as active_aliases;
```

**Result Interpretation:**
- `orphaned_invoices` > 100 → Issue #2 is CRITICAL
- `partial_payments` > 50 → Issue #3 is impacting data
- `delayed_entries` > 1000 → Issue #4 is widespread
- `unique_company_names_exact` >> `normalized` → Issue #1 scope is large

---

## Recommended Next Steps

### Immediate (This Week)

1. **Unify company matching** → Create `utils.py` with shared normalization function
2. **Fix admin invoice joins** → Add LEFT JOIN for orphaned invoices in 4 analytics functions
3. **Fix sales performance date field** → Use `order_date` not `created_at`
4. **Add CSRF protection** → Implement Flask-WTF on state-changing operations

### Short Term (Next Week)

5. **Add timezone handling** → Use UTC consistently
6. **Add login rate limiting** → Implement attempt throttling
7. **Add upload size limits** → Enforce maximum file size
8. **Consolidate analytics calculations** → Single authoritative ledger/service

### Medium Term (Sprint)

9. **Add database constraints** → Unique `so_number`, status check constraints
10. **Adopt Flask-Migrate/Alembic** → Versioned migration framework
11. **Add payment_date field** → Improve collection cycle analytics
12. **Complete stress/compatibility testing** → UAT evidence collection
13. **PostgreSQL integration tests** → Verify all queries work on Supabase

---

## Resources & References

### Documentation Files

- `docs/README.md` - Documentation index
- `docs/analytics/PYTHON_ANALYTICS_DOCUMENTATION.md` - Analytics design details
- `docs/architecture/SYSTEM_ERD.md` - Database entity relationships
- `docs/audits/CRITICAL_ISSUES_SUMMARY.md` - Critical issues from June 9 audit
- `docs/audits/SYSTEM_CHECK_REPORT_2026-06-09.md` - Historical audit report
- `docs/audits/SYSTEM_CHECK_REPORT_2026-06-18.md` - Latest audit with fixes
- `docs/capstone-package/DEMO_OUTLINE_AND_SCRIPT.md` - Demo script details
- `docs/capstone-package/System_Architecture_Text_Description.txt` - Architecture overview
- `docs/database/DIAGNOSTIC_QUERIES.md` - SQL diagnostic queries
- `docs/database/supabase_*_migration.sql` - Production migrations
- `docs/deployment/deployment.md` - Redeployment guide
- `docs/deployment/DEPLOYMENT_NOTES.md` - Render deployment notes
- `docs/deployment/DEPLOYMENT_SUGGESTIONS.md` - Deployment recommendations
- `docs/testing/SYSTEM_TEST_ANALYSIS.md` - Test coverage summary
- `docs/testing/Test_case.md` - Detailed test case specifications

### Configuration Files

- `requirements.txt` - Python dependencies
- `render.yaml` - Render service configuration
- `.env.example` - Local environment template
- `defense_migrations.py` - SQLite auto-migration on startup

### Source Code Entry Points

- `app.py` - Main Flask application (76 routes, SQLAlchemy models)
- `analytics_services.py` - Analytics calculations and forecasting
- `admin_services.py` - Admin operations and database tools
- `main.py` - Application entry point

---

## Summary

**Syluxent ERP** is a capable business management system with substantial functionality across sales, invoicing, expenses, reporting, and analytics. The codebase demonstrates advanced features like fuzzy client matching, Holt-Winters forecasting, and role-based access control.

**Current Status:**
- ✅ Core functionality: Implemented and tested
- ✅ Database migrations: Auto-managed locally, manual for production
- ✅ 90% compliance with documented requirements
- ⚠️ CSRF protection, login throttling, and PostgreSQL compatibility: Needed before production
- ⚠️ Some legacy analytics paths: Use basic filters or SQLite-specific functions

**Next Phase:**
Address critical analytics issues, implement CSRF and rate limiting, consolidate database logic, and add comprehensive PostgreSQL integration testing before production deployment.

**Estimated Timeline to Production Ready:** 1-2 weeks for critical fixes + 1 week testing = **2-3 weeks**

---

*Documentation compiled from system files dated through June 18, 2026*
*For updates, review individual docs/ files*
