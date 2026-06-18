# Syluxent ERP Demo Outline and Script

Date checked: June 9, 2026

## System Check Summary

Use this opening summary if asked whether the system is ready for demonstration.

- Python syntax check passed for `app.py`, `admin_services.py`, `analytics_services.py`, and `tests/`.
- App import check passed with 76 registered Flask routes.
- Existing system checks passed:
  - Client matching and client alias learning.
  - Expense upload normalization and admin upload commit.
  - Analytics upload, outlier confirmation, analytics APIs, and evaluation flow.
- Authenticated page/API smoke check passed:
  - Public: `/`, `/login`, `/register`.
  - Staff: `/dashboard`, `/sales-order`, `/invoices`, `/purchase-orders`.
  - Manager: `/analytics`, `/api/analytics/overview`.
  - Admin: `/database-interface`, `/reports`, `/get-database-stats`.
- Dashboard KPI layout now combines Actual and Expected values into two cards: Revenue and Profit.
- Dashboard Clients and Client Balances now use the same client financial/scoring data flow used by Client Analysis, with client score and cohort shown alongside balance data.
- Analytics tabs now share one date range filter for year, quarter, and month.
- Analytics reports can now be exported as CSV or previewed for print/save-to-PDF from the active tab.
- Local static references are present for `styles.css`, `theme-overrides.css`, and `system-states.js`.
- Internet access is recommended during the demo because several frontend libraries load from CDNs: Bootstrap, Chart.js, SheetJS, Lucide, and jQuery.

Known note:

- The Sales Order module has browser-side SheetJS support, but the documented system test analysis still notes that some Excel processing paths use backend Python parsing. Present this as an implementation detail or future refinement if asked.

## Demo Preparation

1. Start the application.

   ```bash
   venv\Scripts\python.exe app.py
   ```

2. Open the app.

   ```text
   http://localhost:5000
   ```

3. Prepare these default accounts.

   ```text
   Admin:   admin / admin123
   Manager: manager / manager123
   Staff:   staff / staff123
   ```

4. Prepare one clean Excel file for Sales Order upload if you want to demonstrate import. Include columns similar to company name, store name, order date, particulars, quantity, unit cost, and selling price.

## Demo Flow

### 1. Opening

Goal: Explain the problem and position the system.

Say:

"Good day. This is Syluxent ERP, a Flask and database-backed business management system designed to centralize sales orders, invoices, expenses, reports, administration, and analytics in one workflow. The goal is to reduce manual tracking across spreadsheets while preserving the familiar business data format the company already uses."

Show:

- Landing page.
- Login page.
- Mention role-based access.

### 2. Authentication and Role-Based Navigation

Goal: Prove that users see different modules depending on role.

Steps:

1. Log in as `staff`.
2. Show Staff navigation: Home, Sales Order, Invoice, Expense.
3. Log out.
4. Log in as `manager`.
5. Show Manager navigation: Home and Analytics.
6. Log out.
7. Log in as `admin`.
8. Show Admin access to the Admin Center and Reports.

Say:

"The system uses role-based access. Staff users focus on daily encoding, managers focus on dashboard and analytics review, and administrators manage records, users, and database-level tools."

### 3. Dashboard

Goal: Show the main operational overview.

Steps:

1. Log in as Admin or Staff.
2. Open Home/Dashboard.
3. Point out financial cards: Accounts Receivable, Revenue, Expenses, Pondo Remaining, and Sales Orders.
4. Show the Revenue card with Actual and Expected values together.
5. Show the Profit card with Actual and Expected values together.
6. Open the Clients tab and point out client score, cohort, revenue, paid amount, and balance.
7. Click a client with a balance to show unpaid sales orders.

Say:

"The dashboard gives a quick financial snapshot. Revenue and Profit each show actual results beside expected values, so users can compare what was billed or paid against sales order projections. The Clients tab uses the same client analysis data flow for score, cohort, revenue, payments, and balances."

If the dashboard has little data:

"This demo database may have limited records, but these cards update from the underlying sales, invoice, and expense records as data is encoded."

### 4. Sales Order Module

Goal: Demonstrate data entry and spreadsheet-assisted sales order creation.

Steps:

1. Open Sales Order.
2. Show the upload area and spreadsheet viewer.
3. Upload a sample Excel file if prepared.
4. Use auto-identify fields.
5. Show manual override or editable fields.
6. Confirm company, store, branch, order date, sales staff, terms, notes, and line items.
7. Submit the sales order.

Say:

"The Sales Order module supports spreadsheet upload and automatic field identification. This helps convert existing business documents into structured records while still allowing manual correction before saving."

Highlight:

- Company/client matching helps avoid duplicate clients.
- Store and branch stay separate from the official client name.
- Line items include particulars, quantity, unit cost, selling price, and total.

### 5. Invoice Module

Goal: Show how sales orders move into billing and payment tracking.

Steps:

1. Open Invoices.
2. Show pending sales order selector.
3. Select a sales order if available.
4. Show read-only sales order details.
5. Choose Sales Invoice or Service Invoice.
6. Enter invoice number, summary, payment type, payment amount, and tax amount.
7. Toggle the 2307 checker and explain the calculation.
8. Show confirmation modal/countdown.
9. Save and show invoice table/filtering.

Say:

"After a sales order is created, it can be converted into an invoice. The invoice module supports sales and service invoices, downpayment or full payment tracking, tax handling, and a confirmation buffer for critical actions."

### 6. Expense Module

Goal: Show expense tracking and debit categorization.

Steps:

1. Open Expenses.
2. Show required voucher/check/date/supplier fields.
3. Add one or more debit entries.
4. Show cash amount, total debit amount, and net balance calculation.
5. Save the expense.
6. Show expense history table.

Say:

"Expenses capture company costs and categorize them across debit accounts. The system automatically compares total debits against cash amount, then marks the balance and status accordingly."

### 7. Reports

Goal: Show consolidated business records.

Steps:

1. Log in as Admin.
2. Open Reports.
3. Show sales order, expense, revenue, and historical transaction reports.
4. Mention CSV export where available.

Say:

"The Reports page gives structured views of operational and financial records. This supports review, audit preparation, and management reporting without manually rebuilding summaries from raw spreadsheets."

### 8. Admin Center

Goal: Show administrative control and data governance.

Steps:

1. Open Admin Center.
2. Show Users as the default view.
3. Show Roles, Clients, Sales Orders, Invoices, Expenses, Sessions, and Client Basket views.
4. Show database stats.
5. Mention upload preview/commit, export, health, maintenance, safe SQL console, theme settings, audit logs, and notifications if visible.

Say:

"The Admin Center provides business-friendly user, record, client, request, audit, and appearance management. Database maintenance, schema inspection, and SQL tools remain available under the collapsed Advanced technical tools section for trained administrators."

### 9. Analytics

Goal: Show management insights and research objective support.

Steps:

1. Log in as Manager or Admin.
2. Open Analytics.
3. Use the shared date range filter to switch between Full Year, Quarter, and Month.
4. Show overview KPIs.
5. Use Show Analytics Tools only if you need to generate analytics data or upload historical records.
6. Show weekly cashflow for the selected period if available.
7. Show monthly cashflow for the selected year if available.
8. Show revenue leakage or bad debt/high-impact client insight.
9. Open Clients Analysis, Revenue, Recommendations, and Evaluation to show that each tab follows the same date range filter.
10. Use Export CSV or Preview PDF to demonstrate analytics reporting.
11. If using upload, demonstrate analytics upload and outlier confirmation.
12. Show evaluation questions/results if part of your defense.

Say:

"The Analytics module turns encoded records into business insights. Every analytics tab uses the same date range filter, so managers can review a full year, quarter, or month. It supports descriptive analysis, sales forecasting support, client performance scoring, recommendations, evaluation metrics, and export or print-ready reporting."

### 10. Closing

Goal: Tie the demo back to the capstone value.

Say:

"To summarize, Syluxent ERP centralizes the company's sales orders, invoices, expenses, reports, user administration, and analytics. The system reduces scattered manual tracking, improves record consistency, and gives managers clearer visibility into revenue, expenses, balances, and client behavior."

"The system check completed successfully for core routes, page rendering, upload logic, client matching, expense processing, dashboard client balances, analytics filters, and analytics workflows. The remaining improvement noted in testing is to fully align Sales Order Excel processing with a purely browser-side workflow if that requirement is enforced."

## Quick Recovery Lines

Use these if something unexpected happens during the live demo.

- If a page has no data: "This view is data-driven. Once records are added through the modules, the table and summaries populate automatically."
- If CDN assets fail: "Some visual and spreadsheet libraries are loaded from online CDNs, so the full interface requires internet access during demonstration."
- If Excel upload is slow: "The upload process validates and maps spreadsheet fields before saving, so the system is checking the file before committing records."
- If login fails: "I will use the seeded default accounts created by the application: admin, manager, and staff."
- If analytics requires confirmation: "The system detected unusual values and asks for confirmation before accepting outlier data, which protects the analytics dataset."

## Suggested Timing

- Opening and login: 2 minutes.
- Dashboard: 2 minutes.
- Sales Order: 4 minutes.
- Invoice: 3 minutes.
- Expense: 3 minutes.
- Reports and Admin: 4 minutes.
- Analytics: 4 minutes.
- Closing: 1 minute.

Total target time: 21 to 25 minutes.
