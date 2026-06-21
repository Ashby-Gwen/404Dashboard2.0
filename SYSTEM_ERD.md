# Syluxent System ERD Structure

Text-based entity relationship documentation for the live Syluxent runtime schema.

Verified against:

- `app.py` SQLAlchemy models
- Defense-readiness migration requirements in `defense_migrations.py`
- Supabase migration in `docs/supabase_defense_readiness_migration.sql`

Scope:

- Includes the live runtime tables only.
- Excludes demo and working-module databases under `analytics/for demo` and `analytics/working modules`.

## Relationship Map

```text
roles 1 --< users
users 1 --< session_records
users 1 --< audit_logs
users 1 --< password_resets.user_id
users 1 --< password_resets.resolved_by_user_id
users 1 --< evaluation_sessions

clients 1 --< client_aliases
clients 1 --< sales_orders
sales_orders 1 --< sales_order_items
sales_orders 1 --< invoices
invoices 1 --< collection_receipts
users 1 --< collection_receipts.created_by_user_id

purchase_orders 1 --< purchase_order_debits

evaluation_sessions 1 --< evaluation_responses
evaluation_questions 1 --< evaluation_responses

analytics_data has no declared foreign keys.
```

## Authentication and Admin

### roles

- id INTEGER [PK, NOT NULL]
- role_name VARCHAR(50) [UNIQUE, NOT NULL]
- description TEXT

### users

- id INTEGER [PK, NOT NULL]
- username VARCHAR(80) [UNIQUE, NOT NULL]
- email VARCHAR(255) [UNIQUE]
- password_hash VARCHAR(120) [NOT NULL]
- role_id INTEGER [FK -> roles.id, NOT NULL]
- status VARCHAR(20) [NOT NULL]
- approved_by INTEGER [FK -> users.id]
- approved_at DATETIME
- profile_photo VARCHAR(255)
- profile_photo_data TEXT
- profile_photo_mime VARCHAR(80)
- created_at DATETIME
- updated_at DATETIME

Relationship:

- One `roles` record can be assigned to many `users`.
- User status is one of `pending`, `approved`, `rejected`, or `disabled`.
- New profile photo uploads are stored in persistent Supabase Postgres fields; `profile_photo` remains only for legacy static paths.

### system_settings

- key VARCHAR(100) [PK, NOT NULL]
- value TEXT [NOT NULL]
- updated_at DATETIME

Purpose:

- Stores shared runtime settings, including the selected theme, in Supabase Postgres instead of Render local files.

### session_records

- id INTEGER [PK, NOT NULL]
- user_id INTEGER [FK -> users.id, NULLABLE FK]
- username VARCHAR(80) [NOT NULL]
- role_name VARCHAR(50) [NOT NULL]
- login_at DATETIME
- logout_at DATETIME
- status VARCHAR(20)

Relationship:

- One `users` record can have many `session_records`.
- `user_id` is nullable, so a session record can retain username/role text even without a linked user row.

### audit_logs

- id INTEGER [PK, NOT NULL]
- user_id INTEGER [FK -> users.id, NULLABLE FK]
- username VARCHAR(80) [NOT NULL]
- action VARCHAR(100) [NOT NULL]
- table_name VARCHAR(100) [NOT NULL]
- record_id VARCHAR(100)
- old_value TEXT
- new_value TEXT
- created_at DATETIME

Relationship:

- One `users` record can have many `audit_logs`.
- `user_id` is nullable, so audit history can preserve username text even without a linked user row.

### password_resets

- id INTEGER [PK, NOT NULL]
- user_id INTEGER [FK -> users.id, NOT NULL]
- username VARCHAR(80) [NOT NULL]
- status VARCHAR(20) [NOT NULL]
- requested_at DATETIME [NOT NULL]
- resolved_at DATETIME
- resolved_by_user_id INTEGER [FK -> users.id, NULLABLE FK]

Relationships:

- One `users` record can have many password reset requests through `user_id`.
- One `users` record can resolve many password reset requests through `resolved_by_user_id`.
- `resolved_by_user_id` is nullable while the request is unresolved.

## Client, Sales, and Invoicing

### clients

- id INTEGER [PK, NOT NULL]
- client_name VARCHAR(200) [NOT NULL]
- contact_info VARCHAR(500)
- status VARCHAR(20)
- total_revenue FLOAT
- total_paid FLOAT
- total_balance FLOAT
- balance_status VARCHAR(30)
- last_invoice_date DATE
- last_payment_date DATE
- financials_updated_at DATETIME
- created_at DATETIME

### client_aliases

- id INTEGER [PK, NOT NULL]
- alias_name VARCHAR(200) [NOT NULL]
- normalized_alias VARCHAR(200) [UNIQUE, NOT NULL]
- client_id INTEGER [FK -> clients.id, NOT NULL]
- status VARCHAR(20)
- created_at DATETIME

Relationship:

- One `clients` record can have many `client_aliases`.

### sales_orders

- id INTEGER [PK, NOT NULL]
- so_number VARCHAR(50) [NOT NULL]
- client_id INTEGER [FK -> clients.id, NOT NULL]
- company_name VARCHAR(200)
- official_client_name VARCHAR(200)
- original_entered_client_name VARCHAR(200)
- store_name VARCHAR(200)
- store_branch VARCHAR(200)
- order_date DATE [NOT NULL]
- sales_staff VARCHAR(100)
- terms INTEGER
- notes TEXT
- total_amount FLOAT
- status VARCHAR(20)
- created_at DATETIME

Relationship:

- One `clients` record can have many `sales_orders`.

### sales_order_items    

- id INTEGER [PK, NOT NULL]
- sales_order_id INTEGER [FK -> sales_orders.id, NOT NULL]
- particular VARCHAR(500) [NOT NULL]
- quantity FLOAT [NOT NULL]
- unit_cost FLOAT [NOT NULL]
- selling_price FLOAT [NOT NULL]
- total FLOAT [NOT NULL]

Relationship:

- One `sales_orders` record can have many `sales_order_items`.

### invoices

- id INTEGER [PK, NOT NULL]
- invoice_number VARCHAR(50) [UNIQUE, NOT NULL]
- sales_order_id INTEGER [FK -> sales_orders.id, NULLABLE FK]
- invoice_type VARCHAR(20) [NOT NULL]
- invoice_date DATE [NOT NULL]
- summary TEXT
- payment_type VARCHAR(20)
- cr_number VARCHAR(50)
- payment_amount FLOAT
- tax_amount_paid FLOAT
- is_2307_checked BOOLEAN
- total_amount FLOAT
- amount_paid FLOAT
- balance FLOAT
- status VARCHAR(20)
- uploaded_client_name VARCHAR(200)
- upload_source VARCHAR(50)
- admin_upload_note TEXT
- created_at DATETIME

Relationship:

- One `sales_orders` record can have many `invoices`.
- `sales_order_id` is nullable, so uploaded or service invoices can exist without a linked sales order.
- Legacy Invoice payment fields preserve the original payment snapshot; aggregate payment state is synchronized from Collection Receipts.

### collection_receipts

- id INTEGER [PK, NOT NULL]
- invoice_id INTEGER [FK -> invoices.id, NOT NULL]
- receipt_date DATE [NOT NULL]
- cr_number VARCHAR(50) [NOT NULL]
- normalized_cr_number VARCHAR(50) [NOT NULL]
- payment_type VARCHAR(20) [NOT NULL]
- payment_amount FLOAT [NOT NULL]
- tax_amount_paid FLOAT [NOT NULL]
- is_2307_checked BOOLEAN [NOT NULL]
- collected_total FLOAT [NOT NULL]
- created_by_user_id INTEGER [FK -> users.id]
- recorded_by VARCHAR(80) [NOT NULL]
- created_at DATETIME [NOT NULL]

Relationship:

- One `invoices` record can have many append-only `collection_receipts`.
- CR numbers are case-insensitively unique within each invoice.

## Expenses

Expense is the canonical module and API terminology. The physical table names below are retained from an older purchase-order implementation for database and route compatibility.

### purchase_orders (legacy physical name for expense records)

- id INTEGER [PK, NOT NULL]
- check_voucher_number VARCHAR(50) [NOT NULL]
- check_number VARCHAR(50) [NOT NULL]
- check_date DATE [NOT NULL]
- date DATE [NOT NULL]
- or_date DATE
- ar_cr_or_number VARCHAR(50)
- po_number VARCHAR(50)
- lf_no VARCHAR(50)
- particulars VARCHAR(500) [NOT NULL]
- supplier_payee VARCHAR(200) [NOT NULL]
- tin_number VARCHAR(50)
- cash_amount FLOAT [NOT NULL]
- net_balance FLOAT
- status VARCHAR(20)
- category VARCHAR(20)
- created_at DATETIME

### purchase_order_debits (legacy physical name for expense debit allocations)

- id INTEGER [PK, NOT NULL]
- purchase_order_id INTEGER [FK -> purchase_orders.id, NOT NULL]
- debit_type VARCHAR(100) [NOT NULL]
- amount FLOAT [NOT NULL]

Relationship:

- One expense record in `purchase_orders` can have many debit allocations in `purchase_order_debits`.

## Analytics Ledger

### analytics_data

- analytics_id INTEGER [PK, NOT NULL]
- source_type TEXT [NOT NULL]
- source_id TEXT [NOT NULL]
- transaction_date DATE [NOT NULL]
- financial_stage TEXT [NOT NULL]
- flow_direction TEXT [NOT NULL]
- flow_status TEXT [NOT NULL]
- party_name TEXT [NOT NULL]
- party_role TEXT [NOT NULL]
- amount FLOAT [NOT NULL]
- balance_amount FLOAT
- category TEXT [NOT NULL]
- status TEXT
- description TEXT
- upload_batch_id VARCHAR(80)
- source_filename VARCHAR(255)
- source_format VARCHAR(20)
- created_at DATETIME

Notes:

- `analytics_id` is the real database primary key.
- Application code exposes `id` as a synonym for `analytics_id`.
- `source_type` and `source_id` are logical references to source records, not database-enforced foreign keys.
- This table has no declared foreign keys in the live schema.

## Evaluation Module

### evaluation_sessions

- id INTEGER [PK, NOT NULL]
- user_id INTEGER [FK -> users.id, NULLABLE FK]
- evaluator_name VARCHAR(120) [NOT NULL]
- evaluator_role VARCHAR(80)
- overall_comment TEXT
- overall_mean FLOAT
- interpretation VARCHAR(50)
- created_at DATETIME

### evaluation_questions

- id INTEGER [PK, NOT NULL]
- category VARCHAR(80) [NOT NULL]
- question_text TEXT [NOT NULL]
- display_order INTEGER
- is_active BOOLEAN

### evaluation_responses

- id INTEGER [PK, NOT NULL]
- session_id INTEGER [FK -> evaluation_sessions.id, NOT NULL]
- question_id INTEGER [FK -> evaluation_questions.id, NOT NULL]
- rating INTEGER [NOT NULL]
- comment TEXT
- created_at DATETIME

Relationships:

- One `users` record can have many `evaluation_sessions`; `user_id` remains nullable for compatibility with earlier anonymous or imported evaluations.
- One `evaluation_sessions` record can have many `evaluation_responses`.
- One `evaluation_questions` record can have many `evaluation_responses`.

## Live Runtime Table Checklist

The ERD includes all 19 runtime tables defined by the current models:

1. `analytics_data`
2. `audit_logs`
3. `client_aliases`
4. `clients`
5. `evaluation_questions`
6. `evaluation_responses`
7. `evaluation_sessions`
8. `invoices`
9. `collection_receipts`
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

`system_settings` stores shared theme/runtime configuration. Older databases may require the defense-readiness migration before all listed columns and indexes are available.
