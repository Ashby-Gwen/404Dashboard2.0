# Syluxent System Test Cases - May 15, 2026 Revision

## Scope
Validate invoice handling, analytics modularization, manager analytics workflows, admin database tools, audit logging, and core staff workflows.

## 1. Authentication and Roles
- Register a staff account and verify required fields, duplicate email handling, and login.
- Login as staff and confirm only Home, Sales Order, Invoice, and Purchase Order workflows are available.
- Login as manager and confirm Analytics is available.
- Login as admin and confirm Database Interface is available.
- Logout and verify protected pages redirect to login.

## 2. Invoice Workflow
- Create an invoice without a CR number and verify status is `UNPAID`.
- Create an invoice with CR number `CR-0001` and verify status is `PAID`.
- Toggle payment type between Downpayment and Full Payment; verify both remain `PAID` when CR number exists.
- Check Form 2307 and enter tax amount; verify paid total includes CR amount plus tax amount.
- Leave Form 2307 unchecked; verify tax is excluded from paid total.
- Enter CR amount plus tax amount that does not equal invoice total; verify warning appears but saving is allowed.
- Edit an unpaid invoice later, add CR number, CR amount, and Form 2307 state; verify status changes to `PAID`.
- Verify invoice summary table displays CR number, paid amount, balance, status, and edit action.

## 3. Accounts Receivable
- Create a sales order and an invoice with no CR number.
- Verify unpaid invoices are listed as accounts receivable in dashboard/analytics.
- Verify paid invoices are excluded from accounts receivable.
- Confirm sales orders with unpaid invoices remain visible as receivable exposure.

## 4. Sales Order and Client Basket
- Create a sales order with multiple item lines.
- Verify items appear in Client Basket/admin data grid.
- Verify item quantities and totals are reflected in analytics top sold items.
- Confirm sales order status updates when invoice payments are added.

## 5. Purchase Orders and Pondo
- Create purchase orders with cash amounts.
- Verify analytics expenses include purchase order cash amounts.
- Verify remaining pondo equals paid revenue minus expenses.
- Verify recommended next-month purchases do not exceed available pondo.

## 6. Manager Analytics
- Open Analytics as manager/admin and verify the Overview tab loads.
- Verify summary cards show Paid Revenue, Accounts Receivable, Expenses, and Pondo.
- Verify Monthly Cashflow and Revenue by Client charts render.
- Verify Historical Analytics tables show top items, client balances, weekly cashflow, and sales performance.
- Verify Predictions tab shows future item demand and recommended items to buy.
- Upload an Excel workbook with multiple sheets and verify each sheet is previewed as a table.
- Upload an invalid/non-Excel file and verify a friendly error appears.

## 7. Analytics Module Maintainability
- Confirm analytics calculations are located in `analytics_services.py`.
- Add a temporary test report function to the module and expose it through `build_analytics_payload()`.
- Confirm the manager UI can consume the new JSON key without changing unrelated routes.
- Review module comments and verify future development instructions are clear.

## 8. Admin Data Grid
- Open Database Interface as admin.
- Switch between Users, Roles, Clients, Sales Orders, Invoices, Purchase Orders, and Session Records.
- Verify server-side pagination changes pages correctly.
- Search by keyword and verify filtered results are returned from the server.
- Filter by status for tables that have a status field.
- Export filtered results to CSV and verify exported rows match the active filter.

## 9. Admin Bulk Operations
- Select multiple sales orders/invoices/purchase orders.
- Batch-update status and verify selected rows changed.
- Attempt status update on unsupported tables such as roles; verify safe error.
- Batch-delete allowed records and verify deletion.
- Attempt bulk-delete users or roles; verify operation is blocked.

## 10. Database Health Suite
- Open System Maintenance tab and verify database size displays.
- Verify last backup date displays or shows no backup detected.
- Run `ANALYZE` and verify success message.
- Run `VACUUM` and verify success message.
- Confirm maintenance actions are written to audit logs.

## 11. Schema Browser and SQL Console
- Open Schema Browser and verify tables, columns, and indexes display.
- Run `SELECT * FROM invoices LIMIT 10` with Dry Run enabled and verify rows display.
- Run an UPDATE with Dry Run enabled and verify changes are rolled back.
- Run a blocked schema command such as `DROP TABLE users` and verify it is rejected.
- Run approved non-dry-run SQL only on test data and verify audit log records the action.

## 12. Audit Logging
- Create, update, and delete admin-managed records.
- Verify audit log records User, Action, Table, Record ID, Timestamp, Old Value, and New Value.
- Verify bulk operations and SQL console actions create audit entries.
- Confirm audit log is visible only to admin users.

## 13. Regression Checks
- Run `python -m py_compile app.py analytics_services.py admin_services.py`.
- Start Flask and verify `/login` returns HTTP 200.
- Verify existing staff pages still load: dashboard, sales order, invoice, purchase order.
- Verify manager/admin pages load without JavaScript console errors.

## 14. Objective-Based Analytics Completion Checks
- Upload a historical sales `.csv` and `.xlsx` file with required headers: `DATE`, `COMPANY NAME`, `STORE NAME`, `COST`, `QUANTITY`, and `SELLING PRICE`.
- Verify the upload response shows EDA summary values: missing counts, duplicates, invalid row count, outlier count, and distributions for cost, quantity, selling price, and total sales.
- Upload a file with an outlier and confirm the first upload is blocked until the user confirms outlier review.
- Verify `/api/analytics/clients` returns `client_performance_score`, `score_breakdown`, `cohort`, and recommendations for each client.
- Verify the Clients Analysis dashboard displays CPS, cohort, score breakdown, and cohort visualization.
- Open the Revenue tab, set MAPE threshold to 20, and verify sales analytics returns descriptive, predictive, and prescriptive sections.
- Verify forecast output includes MAPE status or `insufficient_data` when historical periods are not enough.
- Verify the Revenue tab displays sales trend, product distribution, peak sales periods, forecast-vs-actual validation, and rule-based recommendations.
- Submit the Likert evaluation form as manager/admin.
- Verify `/api/evaluation/results` displays question averages, category averages, overall mean, interpretation, and recent feedback.
- Run `python tests\analytics_objectives_check.py`.
