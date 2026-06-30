# Syluxent / 404 Analytical Dashboard System Test Cases

## Purpose
Task ito para sa group member na gagawa at mag-eexecute ng test cases based sa current system features. Huwag generic na "check if working"; bawat test case dapat may exact steps, test data, and expected result para hindi sabog kapag actual testing na.

Use this document for manual QA, defense preparation, and future regression checks.

## Testing Notes
- Test on a local or staging database only. Huwag gumamit ng real production records for destructive tests.
- Use approved test accounts for each role: Admin, Manager, Sales Staff or Staff, and Accounting Staff if available.
- For uploads, prepare small safe CSV/XLSX files with known expected totals.
- For screenshots, use filenames like `TC-AUTH-001-login-success.png`.
- Keep `Actual Result`, `Status`, and `Remarks` blank until execution.
- Status values: `Pass`, `Fail`, or `Not Tested`.

## Required Test Preparation Files and Data

Create one testing folder before execution, for example:

```text
test-prep/
  accounts.md
  expected-totals.xlsx
  screenshots/
  uploads/
    sales_order_valid.xlsx
    sales_order_valid.csv
    sales_order_invalid.txt
    invoice_valid.csv
    invoice_bad_headers.csv
    analytics_historical_valid.csv
    analytics_historical_valid.xlsx
    analytics_missing_headers.csv
    unsupported_upload.txt
```

Prepare these files/data before running the cases:

- `accounts.md`: list the test usernames only, their roles, approval status, and purpose. Do not write real passwords in shared docs.
- `expected-totals.xlsx`: manual computation sheet for sales order totals, invoice paid/balance, expenses, pondo, revenue, and report totals.
- `screenshots/`: folder for proof screenshots using the test case ID in the filename.
- `sales_order_valid.xlsx` and `sales_order_valid.csv`: 1 valid sales order with company, store, branch, order date, terms, staff, notes, and at least 3 item lines.
- `sales_order_invalid.txt`: unsupported upload file for negative upload testing.
- `invoice_valid.csv`: valid invoice import file with at least 1 unpaid, 1 partial, and 1 fully paid scenario if the current import template supports it.
- `invoice_bad_headers.csv`: invoice import with wrong/missing headers.
- `analytics_historical_valid.csv` and `analytics_historical_valid.xlsx`: historical analytics file with headers `DATE`, `COMPANY NAME`, `STORE NAME`, `COST`, `QUANTITY`, and `SELLING PRICE`.
- `analytics_missing_headers.csv`: historical analytics file with one or more required headers removed.
- `unsupported_upload.txt`: generic unsupported file for upload error tests.

## Per-Test Preparation Matrix

Use this before conducting each test case. Kung wala ito prepared, wag muna i-run yung case kasi magiging hula-hula ang expected result.

| Test Case ID | Prepare Before Testing |
| --- | --- |
| TC-AUTH-001 | Approved admin account in `accounts.md`; browser ready at `/login`; screenshot target `screenshots/TC-AUTH-001-login-success.png`. |
| TC-AUTH-002 | Approved manager account in `accounts.md`; know which nav links manager should see; screenshot target `screenshots/TC-AUTH-002-manager-home.png`. |
| TC-AUTH-003 | Approved staff or sales staff account in `accounts.md`; list expected staff links in notes. |
| TC-AUTH-004 | Existing active username plus deliberately wrong password value; make sure no one locks a real account. |
| TC-AUTH-005 | New unused username/email for registration; note whether tester expects approval before login. |
| TC-AUTH-006 | Existing username/email from `accounts.md` for duplicate registration check. |
| TC-AUTH-007 | Logged-out browser session; direct URLs ready: `/dashboard`, `/analytics`, `/database-interface`. |
| TC-AUTH-008 | Any approved account; protected URL to revisit after logout, usually `/dashboard`. |
| TC-DASH-001 | Any approved account; screenshot target for loaded dashboard. |
| TC-DASH-002 | Staff account; expected allowed staff modules written in `accounts.md`. |
| TC-DASH-003 | Manager account; expected manager modules written in `accounts.md`. |
| TC-DASH-004 | Admin account; expected Admin Center deep links `/database-interface?tab=requests` and `/database-interface?tab=audit`. |
| TC-DASH-005 | Test records across at least two years; expected values listed in `expected-totals.xlsx`. |
| TC-DASH-006 | Multi-date records covering current and older periods; expected all-period totals in `expected-totals.xlsx`. |
| TC-DASH-007 | Known sales order, invoice, receipt, and expense records; computed dashboard totals in `expected-totals.xlsx`. |
| TC-DASH-008 | Logged-out browser session; direct `/dashboard` URL ready. |
| TC-SO-001 | Staff/sales account; manual sales order data sheet with company, store, branch, date, terms, staff, notes, and item line. |
| TC-SO-002 | Staff/sales account; list required fields to intentionally leave blank. |
| TC-SO-003 | Staff/sales account; 3-item sample order in `expected-totals.xlsx`. |
| TC-SO-004 | Calculator or `expected-totals.xlsx` entries for qty/selling combinations, e.g. 10 x 25 = 250. |
| TC-SO-005 | `uploads/sales_order_valid.xlsx` and `uploads/sales_order_valid.csv`. |
| TC-SO-006 | `uploads/sales_order_invalid.txt` or `uploads/unsupported_upload.txt`. |
| TC-SO-007 | `uploads/sales_order_valid.xlsx` with clearly identifiable company, store, branch, date, and order fields. |
| TC-SO-008 | Existing saved sales order ID; screenshot target for print preview. |
| TC-INV-001 | Pending sales order created from TC-SO-001 or fixture data; invoice test values in `expected-totals.xlsx`. |
| TC-INV-002 | Invoice page access; expected invoice prefix notes for Sales/Service invoice type. |
| TC-INV-003 | Pending sales order; invoice data with zero payment and expected full balance. |
| TC-INV-004 | Existing invoice; collection receipt amount lower than invoice total; expected partial balance. |
| TC-INV-005 | Existing invoice with remaining balance; payment amount equal to remaining balance. |
| TC-INV-006 | Existing invoice; overpayment amount greater than remaining balance. |
| TC-INV-007 | Existing invoice; CR amount, Form 2307 checkbox state, and tax amount examples in `expected-totals.xlsx`. |
| TC-INV-008 | Mixed invoice records: sales invoice, service invoice, unpaid, partial, and paid. |
| TC-INV-009 | Admin account; `uploads/invoice_valid.csv`; backup/test database confirmation before commit. |
| TC-INV-010 | Admin account; `uploads/invoice_bad_headers.csv` or malformed invoice file. |
| TC-EXP-001 | Expense-capable account; valid voucher/date/payee/particulars/cash/debit data in `expected-totals.xlsx`. |
| TC-EXP-002 | Expense-capable account; required expense fields list for intentional blank submission. |
| TC-EXP-003 | Multiple debit rows with debit type and amount values in `expected-totals.xlsx`. |
| TC-EXP-004 | Debit total and cash amount examples with expected net balance. |
| TC-EXP-005 | Existing test expense record ID; new payee/amount values to update. |
| TC-EXP-006 | Invalid amount examples: text value, blank value, and negative value if disallowed. |
| TC-EXP-007 | Known expense record and expected Analytics/Reports total after adding it. |
| TC-EXP-008 | Expense-capable account; compatibility route `/purchase-orders` ready. |
| TC-ANL-001 | Approved manager account; analytics test data available. |
| TC-ANL-002 | Approved admin account; analytics test data available. |
| TC-ANL-003 | Staff account with no analytics permission; direct `/analytics` URL ready. |
| TC-ANL-004 | Sales order, invoice, receipt, and expense data with expected overview values. |
| TC-ANL-005 | At least two clients with different sales order histories; expected high/low client comparison notes. |
| TC-ANL-006 | Manager/admin authenticated browser or API client session; endpoint `/api/analytics/overview`. |
| TC-ANL-007 | Manager/admin authenticated browser or API client session; endpoints `/api/analytics/sales`, `/api/analytics/expenses`, `/api/analytics/comparative`. |
| TC-ANL-008 | `uploads/analytics_historical_valid.csv` and `uploads/analytics_historical_valid.xlsx`. |
| TC-ANL-009 | `uploads/analytics_missing_headers.csv` and `uploads/unsupported_upload.txt`. |
| TC-ANL-010 | Historical analytics records covering enough periods, or note expected `insufficient_data` result. |
| TC-REP-001 | Manager/admin account with Reports access. |
| TC-REP-002 | Known sales order records with expected filtered values in `expected-totals.xlsx`. |
| TC-REP-003 | Known expense records with expected filtered values in `expected-totals.xlsx`. |
| TC-REP-004 | Paid, partial, and unpaid invoices with expected revenue/balance values. |
| TC-REP-005 | Historical transaction data from analytics upload or fixture records. |
| TC-REP-006 | Historical report rows available; folder ready for downloaded CSV. |
| TC-REP-007 | Staff account without Reports access; direct `/reports` URL ready. |
| TC-REP-008 | Filter values that intentionally return no report records, such as a future date range. |
| TC-ADM-001 | Approved admin account; screenshot target for Admin Center landing. |
| TC-ADM-002 | Staff or manager account; direct `/database-interface` URL ready. |
| TC-ADM-003 | Admin account; at least one known record or accepted empty state per Admin Center tab. |
| TC-ADM-004 | Admin table with enough rows for pagination; known search keyword. |
| TC-ADM-005 | Pending test user account awaiting approval. |
| TC-ADM-006 | Target test user account; allowed role/status changes; admin confirmation password available to tester only. |
| TC-ADM-007 | Target test user account safe to disable; disable reason text prepared. |
| TC-ADM-008 | Duplicate/unmatched test client records; backup/test database confirmation before applying cleanup. |
| TC-ADM-009 | Admin account; selected theme/appearance value and screenshot target before/after. |
| TC-ADM-010 | Test database only; safe `SELECT` query and blocked command example such as `DROP TABLE users` for rejection check. |
| TC-ADM-011 | Admin table with filtered rows; folder ready for downloaded CSV. |
| TC-ADM-012 | Test admin action to perform, such as edit test user or update test client; expected audit search keyword. |
| TC-EVAL-001 | App running; screenshot target for `/evaluation`. |
| TC-EVAL-002 | App running; expected current question count noted after first load. |
| TC-EVAL-003 | Complete set of 1-5 answers and optional feedback text. |
| TC-EVAL-004 | Evaluation form open; choose at least one required question to leave blank. |
| TC-EVAL-005 | API/client tool if available; invalid rating payload using 0 or 6. |
| TC-EVAL-006 | Admin account; at least one submitted evaluation response. |
| TC-EVAL-007 | Non-admin account; direct `/api/evaluation/results` URL ready. |
| TC-EVAL-008 | Admin account and existing evaluation results; screenshot target for print/preview. |
| TC-UI-001 | Desktop browser with responsive mode; screenshots folder; list of pages to check. |
| TC-UI-002 | Keyboard-only testing setup; pages with tabs/modals ready. |
| TC-UI-003 | Forms with required fields ready: login/register, sales order, invoice, expense, evaluation. |
| TC-UI-004 | Nonexistent URL ready, e.g. `/not-a-real-page`; screenshot target. |
| TC-UI-005 | Non-admin account; admin-only URL ready. |
| TC-UI-006 | Bad upload files: `sales_order_invalid.txt`, `invoice_bad_headers.csv`, `analytics_missing_headers.csv`, `unsupported_upload.txt`. |
| TC-UI-007 | Tables with many columns and rows: Admin Center, Reports, Invoices, Analytics tables. |
| TC-UI-008 | Session timeout route `/session-timeout`; optional idle-session test notes. |

## Test Case Format

| Field             | Content                                                                       |
| ---               | ---                                                                           |
| Test Case ID      | Example: TC-AUTH-001                                                          |
| Module            | Authentication                                                                |
| Test Scenario     | Login using valid admin account                                               |
| Preconditions     | Admin account exists and is approved                                          |
| Prepare Before Testing | Exact accounts, records, upload files, expected totals, and screenshot filename from the prep matrix |
| Test Steps        | 1. Open login page 2. Enter username/password 3. Click login                  |
| Test Data         | username, password, role                                                      |
| Expected Result   | User is redirected to Home dashboard and admin-accessible links are visible   |
| Actual Result     | Leave blank muna while hindi pa executed                                      |
| Status            | Pass / Fail / Not Tested                                                      |
| Remarks           | Notes, bug details, screenshot filename, etc.                                 |

## 1. Authentication and User Roles

| Test Case ID  | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Actual Result | Status | Remarks |
| ---           | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-AUTH-001   | Authentication | Login using valid admin account | Approved admin account exists | 1. Open `/login` 2. Enter valid admin username and password 3. Click login | Admin username/password | User is redirected to `/dashboard`; Admin Center, Analytics, and Reports links are available |  |  | Screenshot after login |
| TC-AUTH-002   | Authentication | Login using valid manager account | Approved manager account exists | 1. Open `/login` 2. Enter valid manager credentials 3. Click login | Manager username/password | User is redirected to `/dashboard`; Analytics and Reports are available; Admin Center is not visible |  |  | Role access dapat sakto |
| TC-AUTH-003   | Authentication | Login using valid staff account | Approved staff account exists | 1. Open `/login` 2. Enter valid staff credentials 3. Click login | Staff username/password | User is redirected to `/dashboard`; staff workflows like Sales Order, Invoice, and Expense are available based on role permissions |  |  | Check nav links |
| TC-AUTH-004   | Authentication | Reject invalid password | Any active account exists | 1. Open `/login` 2. Enter valid username with wrong password 3. Submit form | Existing username, wrong password | Login is rejected and user remains unauthenticated; no protected page is opened |  |  | Negative test, important ito |
| TC-AUTH-005   | Authentication | Register new account | Registration page is available | 1. Open `/register` 2. Enter required account details 3. Submit form | New username, email, password | Account registration is accepted or routed to approval flow; duplicate/invalid fields are not silently accepted |  |  | Note if approval is required |
| TC-AUTH-006   | Authentication | Block duplicate registration | Existing username or email is already used | 1. Open `/register` 2. Enter duplicate username/email 3. Submit | Existing username/email | System shows validation message and does not create a duplicate user |  |  | Negative test |
| TC-AUTH-007   | Authentication | Protected page redirects anonymous user | User is logged out | 1. Open `/logout` if needed 2. Browse directly to `/dashboard` or `/analytics` | No active session | User is redirected to `/login` or receives a proper authentication response |  |  | Good for access control |
| TC-AUTH-008   | Authentication | Logout clears session | User is logged in | 1. Click logout 2. Try opening previous protected page again | Active user session | User is logged out and protected pages are no longer accessible without login |  |  | Wag kalimutan back button check |

## 2. Dashboard / Home

| Test Case ID  | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Actual Result | Status | Remarks |
| ---           | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-DASH-001   | Dashboard | Load Home dashboard after login | User is logged in | 1. Login 2. Open `/dashboard` | Any approved role | Dashboard loads without server error; user name, role-aware content, and navigation are visible |  |  | Basic smoke test |
| TC-DASH-002   | Dashboard | Verify staff dashboard shortcuts | Staff user is logged in | 1. Open `/dashboard` 2. Review visible shortcuts/cards | Staff account | Staff sees allowed workflows only; Admin Center should not appear |  |  | Pag visible Admin Center sa staff, fail agad |
| TC-DASH-003   | Dashboard | Verify manager dashboard access | Manager user is logged in | 1. Open `/dashboard` 2. Check navigation and shortcut cards | Manager account | Manager can access Analytics and Reports; admin-only controls are hidden |  |  | Role-based UI check |
| TC-DASH-004   | Dashboard | Verify admin monitoring cards | Admin user is logged in | 1. Open `/dashboard` 2. Click requests/audit monitoring card links | Admin account | Cards open Admin Center target tabs such as requests or audit without broken links |  |  | Check query-param deep links |
| TC-DASH-005   | Dashboard | Test year filter | User has dashboard records across years | 1. Open `/dashboard` 2. Select/change year filter 3. Apply | Year with known records | Dashboard metrics and lists refresh according to selected year |  |  | Compare with known sample data |
| TC-DASH-006   | Dashboard | Test all-period filter | User has records across dates | 1. Open `/dashboard?period=all` or select All 2. Review cards | Multi-date records | Dashboard shows all-date totals, not only current year/month |  |  | Useful for demo data |
| TC-DASH-007   | Dashboard | Validate financial summary cards | Sales orders, invoices, and expenses exist | 1. Open `/dashboard` 2. Compare revenue, expenses, receivables, pondo, and sales order counts with source records | Known SO/invoice/expense records | Summary values match expected calculations from test records |  |  | Need manual computation sheet |
| TC-DASH-008   | Dashboard | Dashboard blocked for logged-out user | User is logged out | 1. Browse to `/dashboard` directly | No session | System redirects to login or denies access cleanly |  |  | Negative access test |

## 3. Sales Order

| Test Case ID  | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Actual Result | Status | Remarks |
| ---           | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-SO-001     | Sales Order | Create manual sales order | User with Sales Order access is logged in | 1. Open `/sales-order` 2. Fill company, store, branch, order date, terms, staff, notes 3. Add item line 4. Save | Valid sales order data | Sales order is saved successfully and appears in sales order list/admin records |  |  | Main happy path |
| TC-SO-002     | Sales Order | Validate required fields | User is on Sales Order page | 1. Leave required fields blank 2. Click save | Blank required fields | System blocks submission and shows validation; no incomplete sales order is saved |  |  | Negative validation |
| TC-SO-003     | Sales Order | Add multiple particulars | User is on manual entry form | 1. Add at least 3 item rows 2. Enter quantity, unit cost, selling price 3. Save | Multiple item lines | All item lines are saved with correct quantities and totals |  |  | Check Client Basket/admin too |
| TC-SO-004     | Sales Order | Verify total calculation | User is entering item line | 1. Enter qty 10 and selling price 25 2. Review total 3. Change qty/selling | Qty/selling combinations | Line total and order total update accurately based on entered values |  |  | Math check, wag hula |
| TC-SO-005     | Sales Order | Upload valid Excel or CSV | Upload tab is available | 1. Open Excel Upload tab 2. Select valid `.xlsx` or `.csv` 3. Preview file | Valid sales order upload file | Spreadsheet preview loads and fields can be mapped/identified |  |  | Test small file first |
| TC-SO-006     | Sales Order | Reject invalid upload file | Upload tab is available | 1. Select unsupported file type 2. Attempt upload/preview | `.txt` or invalid file | System shows friendly error and does not crash |  |  | Negative upload test |
| TC-SO-007     | Sales Order | Auto-identify fields and override | Valid spreadsheet is previewed | 1. Click auto-identify 2. Review mapped fields 3. Manually change one mapping/value 4. Save | Spreadsheet with company/store/date/order fields | Auto-detected fields populate the form, manual override is respected, saved record uses corrected values |  |  | Important for staff-specific formats |
| TC-SO-008     | Sales Order | Print sales order | Existing sales order exists | 1. Open saved sales order 2. Open print page `/sales-orders/<id>/print` 3. Use browser print preview | Existing sales order ID | Print page displays sales order details cleanly with item rows and totals |  |  | Screenshot print preview |

## 4. Invoice and Collection Receipts

| Test Case ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Actual Result | Status | Remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-INV-001 | Invoice | Create invoice from pending sales order | Pending sales order exists | 1. Open `/invoices` 2. Select pending sales order 3. Fill invoice form 4. Save | Pending SO, invoice type, amount | Invoice is created and linked to the selected sales order |  |  | Main invoice flow |
| TC-INV-002 | Invoice | Generate invoice number | User is on invoice page | 1. Click/generate invoice number 2. Review field | Sales or service invoice type | Invoice number is generated using the expected prefix/format |  |  | Check SI/SVI/SVL behavior if applicable |
| TC-INV-003 | Invoice | Create unpaid invoice | Pending SO exists | 1. Create invoice without full payment/receipt 2. Save 3. Check status | Invoice with zero payment | Invoice status becomes `UNPAID`; balance equals invoice total |  |  | Accounting check |
| TC-INV-004 | Invoice | Create partial payment | Invoice exists | 1. Add collection receipt with amount less than invoice total 2. Save 3. Refresh invoice list | Partial CR amount | Invoice status becomes `PARTIAL`; amount paid and balance are correct |  |  | Partial status dapat clear |
| TC-INV-005 | Invoice | Create fully paid invoice | Invoice exists | 1. Add payment equal to remaining balance 2. Save 3. Refresh invoice list | Full payment amount | Invoice status becomes `PAID`; balance is zero or expected rounded zero |  |  | Happy path |
| TC-INV-006 | Invoice | Block overpayment | Invoice exists | 1. Add collection receipt greater than remaining balance 2. Submit | Payment amount greater than balance | System rejects or warns according to validation; invalid overpayment is not silently saved |  |  | Negative money test |
| TC-INV-007 | Invoice | Test Form 2307 tax behavior | Invoice form has Form 2307 option | 1. Toggle Form 2307 2. Enter tax amount 3. Review total paid/balance | CR amount and tax amount | Tax amount affects paid total only according to the Form 2307 toggle behavior |  |  | Need exact expected math |
| TC-INV-008 | Invoice | Test invoice filters | Multiple invoice types/statuses exist | 1. Open invoice summary 2. Apply filters for all/sales/service/status if available | Mixed invoices | Table shows only matching invoices and keeps correct totals/details |  |  | UI table test |
| TC-INV-009 | Invoice | Admin invoice upload preview/commit | Admin is logged in and upload data is ready | 1. Open invoice admin upload area 2. Preview valid file 3. Review conflicts/errors 4. Commit clean rows | Valid invoice CSV/XLSX | Preview shows clean/conflict rows; commit creates/updates only accepted rows |  |  | Do in test DB lang |
| TC-INV-010 | Invoice | Invalid invoice upload response | Admin is logged in | 1. Upload malformed invoice file 2. Preview/commit | Bad headers or invalid values | System returns readable error and does not show raw HTML/JSON parse failure |  |  | Negative upload test |

## 5. Expense Module

| Test Case ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Actual Result | Status | Remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-EXP-001 | Expense | Create valid expense | User with Expense access is logged in | 1. Open `/expenses` 2. Fill voucher, dates, payee, particulars, cash amount 3. Add debit item 4. Save | Valid expense data | Expense is saved and appears in expense history/admin records |  |  | Main happy path |
| TC-EXP-002 | Expense | Validate required fields | User is on expense form | 1. Leave required fields blank 2. Submit | Blank required fields | System blocks submission and shows validation; no incomplete expense is saved |  |  | Negative validation |
| TC-EXP-003 | Expense | Add multiple debit entries | User is creating expense | 1. Add several debit rows 2. Choose debit types 3. Enter amounts 4. Save | Multiple debit types and amounts | All debit entries are saved and linked to the expense |  |  | Check legacy purchase_order storage if needed |
| TC-EXP-004 | Expense | Verify net balance calculation | User is entering expense amounts | 1. Enter total debit amount 2. Enter cash amount 3. Review net balance | Debit total and cash amount | Net balance equals total debit minus cash amount or the system's displayed formula |  |  | Exact math check |
| TC-EXP-005 | Expense | Edit existing expense | Existing expense exists | 1. Open expense edit action 2. Change amount or payee 3. Save | Existing expense record | Updated details are saved and shown after refresh |  |  | Check audit/admin too |
| TC-EXP-006 | Expense | Reject invalid amount | User is on expense form | 1. Enter non-numeric or negative amount where not allowed 2. Submit | Invalid cash/debit amount | System rejects invalid amount and keeps record unsaved |  |  | Negative amount test |
| TC-EXP-007 | Expense | Expense appears in analytics/reports | Expense record exists | 1. Create expense 2. Open Analytics/Reports 3. Compare expenses totals | Known expense amount | Expense total reflects the new record in relevant analytics/report views |  |  | Cross-module check |
| TC-EXP-008 | Expense | Compatibility expense route works | User has expense access | 1. Open `/purchase-orders` 2. Confirm page or compatibility path works | Compatibility route | Route loads the expense-compatible workflow without breaking current terminology |  |  | Current app keeps aliases |

## 6. Analytics

| Test Case ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Actual Result | Status | Remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-ANL-001 | Analytics | Open Analytics as manager | Approved manager account exists | 1. Login as manager 2. Open `/analytics` | Manager account | Analytics page loads and overview content is visible |  |  | Smoke test |
| TC-ANL-002 | Analytics | Open Analytics as admin | Approved admin account exists | 1. Login as admin 2. Open `/analytics` | Admin account | Analytics page loads with available tabs/cards/charts |  |  | Admin access |
| TC-ANL-003 | Analytics | Block Analytics for staff | Staff account exists | 1. Login as staff 2. Browse directly to `/analytics` | Staff account | System denies access or redirects; staff should not access manager/admin analytics |  |  | Negative role test |
| TC-ANL-004 | Analytics | Verify overview cards and charts | Analytics data exists | 1. Open Overview tab 2. Review cards and chart areas | Sales, invoice, expense data | Cards show values and charts render or show readable fallback if chart runtime fails |  |  | No blank broken chart |
| TC-ANL-005 | Analytics | Test client analysis/client value | Client sales order history exists | 1. Open Clients Analysis 2. Review client scores/cohorts/breakdowns | Client with known SO history | Client value results use sales order behavior and show score details/recommendations |  |  | Compare high/low clients |
| TC-ANL-006 | Analytics | Test analytics API overview | Manager/admin session exists | 1. Open browser/dev tool or API client 2. Request `/api/analytics/overview` | Authenticated session | JSON response returns overview metrics without server error |  |  | API smoke |
| TC-ANL-007 | Analytics | Test sales/expenses/comparative APIs | Manager/admin session exists | 1. Request `/api/analytics/sales` 2. Request `/api/analytics/expenses` 3. Request `/api/analytics/comparative` | Authenticated session | Endpoints return valid JSON and expected metric sections |  |  | API coverage |
| TC-ANL-008 | Analytics | Upload valid historical data | Manager/admin is on Analytics upload area | 1. Upload valid `.csv` or `.xlsx` with required headers 2. Review output | Headers: DATE, COMPANY NAME, STORE NAME, COST, QUANTITY, SELLING PRICE | Upload is accepted; EDA/summary/forecast-related outputs appear as designed |  |  | Use small fixture |
| TC-ANL-009 | Analytics | Reject invalid analytics upload | Manager/admin is on Analytics upload area | 1. Upload unsupported file or missing-header file 2. Submit | Bad file or missing headers | System shows friendly validation error and does not crash |  |  | Negative upload |
| TC-ANL-010 | Analytics | Verify forecast and MAPE output | Enough historical records exist | 1. Open Revenue/forecast section 2. Set/observe MAPE threshold if available 3. Generate analytics | Historical data | Forecast output includes MAPE status or `insufficient_data`; recommendations are readable |  |  | Predictive check |

## 7. Reports

| Test Case ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Actual Result | Status | Remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-REP-001 | Reports | Open Reports page | User with Reports access is logged in | 1. Login as manager/admin 2. Open `/reports` | Manager/admin account | Reports page loads without server error |  |  | Smoke test |
| TC-REP-002 | Reports | Sales order report filter | Sales orders exist | 1. Open Sales Orders report 2. Apply date/client/status filter 3. Review results | Known sales order records | Report returns only matching sales orders and keeps correct values |  |  | Compare source data |
| TC-REP-003 | Reports | Expense report filter | Expenses exist | 1. Open Expenses report 2. Apply date/payee/category filter if available 3. Review results | Known expense records | Report returns matching expenses and totals are accurate |  |  | Expense term, not PO in UI |
| TC-REP-004 | Reports | Revenue report | Paid/partial/unpaid invoices exist | 1. Open Revenue report 2. Apply date filter 3. Review paid revenue/receivable values | Known invoice/payment records | Revenue report uses expected paid revenue and balance values |  |  | Important financial check |
| TC-REP-005 | Reports | Historical transactions report | Historical upload or transaction data exists | 1. Open historical transactions report 2. Apply filter 3. Review table | Historical transaction data | Report displays expected historical rows and summary values |  |  | Depends on data availability |
| TC-REP-006 | Reports | Export historical transactions CSV | Historical report has rows | 1. Apply report filter 2. Click/export CSV 3. Open downloaded file | Filtered historical data | CSV downloads and row set matches active filter |  |  | Verify file content |
| TC-REP-007 | Reports | Block Reports for unauthorized role | Staff account has no Reports access | 1. Login as staff 2. Browse to `/reports` | Staff account | System denies access or hides restricted report controls |  |  | Negative role test |
| TC-REP-008 | Reports | Empty report state | No records match selected filter | 1. Apply future date or unmatched filter 2. Review report | Filter with no matches | Page/API shows clean empty state, not broken table/server error |  |  | Edge case |

## 8. Admin Center

| Test Case ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Actual Result | Status | Remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-ADM-001 | Admin Center | Open Admin Center as admin | Approved admin account exists | 1. Login as admin 2. Open `/database-interface` | Admin account | Admin Center loads with admin tabs and records controls |  |  | Smoke test |
| TC-ADM-002 | Admin Center | Block non-admin from Admin Center | Staff or manager account exists | 1. Login as non-admin 2. Browse to `/database-interface` | Staff/manager account | Access is denied or redirected; admin-only data is not shown |  |  | Negative role test |
| TC-ADM-003 | Admin Center | View main admin record tabs | Admin is logged in | 1. Open Admin Center 2. Switch through Users, Roles, Clients, Sales Orders, Invoices, Expenses, Session Records, Audit Logs | Existing records | Each tab loads its table or empty state without JavaScript/server error |  |  | Tab coverage |
| TC-ADM-004 | Admin Center | Search and pagination | Admin table has enough rows | 1. Open a populated admin table 2. Search keyword 3. Change page | Known search term | Results filter correctly and pagination updates without losing table state |  |  | Server-side table check |
| TC-ADM-005 | Admin Center | User approval flow | Pending user exists | 1. Open requests/users area 2. Approve pending user 3. Try login as approved user | Pending test user | User status updates and account can log in according to approved role |  |  | Use test account only |
| TC-ADM-006 | Admin Center | Edit user role/status | Admin is logged in; target user exists | 1. Open Edit User 2. Change allowed role/status field 3. Confirm with required password if prompted | Test user | User update is saved and protected mutation requires confirmation as designed |  |  | Wag gamitin own main account |
| TC-ADM-007 | Admin Center | Disable user with reason | Target test user exists | 1. Open Edit User/action flow 2. Disable user 3. Enter reason 4. Save | Test user and reason | User is disabled, reason is stored/shown, and disabled user cannot access system |  |  | Security-related |
| TC-ADM-008 | Admin Center | Client cleanup/client match | Duplicate or unmatched client data exists | 1. Open client cleanup/match tools 2. Preview match 3. Apply safe test merge/update | Test client records | Preview is understandable; accepted cleanup updates only intended test clients |  |  | Backup muna if real DB |
| TC-ADM-009 | Admin Center | Theme/appearance settings | Admin is logged in | 1. Open Appearance tab 2. Change theme setting 3. Save 4. Refresh page | Test theme choice | Theme updates persist and page remains readable |  |  | UI setting |
| TC-ADM-010 | Admin Center | Advanced SQL dry-run safety | Admin is logged in; use test data only | 1. Open Advanced technical tools 2. Run safe `SELECT` 3. Try blocked destructive command in dry-run | Safe SQL and blocked SQL | SELECT returns rows; destructive/schema command is blocked or forced safe according to production/test rules |  |  | Ingat dito, test DB only |
| TC-ADM-011 | Admin Center | Admin CSV export | Admin table has filtered rows | 1. Apply filter/search 2. Click export CSV 3. Open file | Filtered records | CSV contains records matching active filter, not unrelated rows |  |  | File check |
| TC-ADM-012 | Admin Center | Audit log records actions | Admin action is performed | 1. Create/edit/disable a test record 2. Open audit logs 3. Search action | Test admin action | Audit log includes user, action, table/context, timestamp, and old/new value when applicable |  |  | Traceability |

## 9. Evaluation Page

| Test Case ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Actual Result | Status | Remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-EVAL-001 | Evaluation | Open evaluation page | App is running | 1. Browse to `/evaluation` | None | Evaluation page loads with questionnaire interface |  |  | Standalone page |
| TC-EVAL-002 | Evaluation | Load evaluation questions | Evaluation page is open | 1. Open page 2. Trigger/load questions if needed 3. Count visible questions | Current question set | Questions load from `/api/evaluation/questions` and are grouped/readable |  |  | Current system has ISO-style evaluation |
| TC-EVAL-003 | Evaluation | Submit complete response | Evaluation questions are loaded | 1. Answer every required 1-5 scale item 2. Add feedback if available 3. Submit | Valid ratings 1-5 | Response is saved and success message appears |  |  | Happy path |
| TC-EVAL-004 | Evaluation | Block missing required answers | Evaluation form is open | 1. Leave at least one required question unanswered 2. Submit | Incomplete ratings | System blocks submission and tells user what needs to be completed |  |  | Negative validation |
| TC-EVAL-005 | Evaluation | Reject invalid scale value | API/client test setup available | 1. Submit response with rating outside 1-5 through client/API if possible | Rating 0 or 6 | System rejects invalid scale value and does not save bad response |  |  | Negative API/data test |
| TC-EVAL-006 | Evaluation | Admin can view results | Admin is logged in and responses exist | 1. Login as admin 2. Open `/api/evaluation/results` or results UI | Admin session | Results show question averages, category averages, overall mean, interpretation, and recent feedback |  |  | Admin-only result |
| TC-EVAL-007 | Evaluation | Non-admin cannot view results | Staff/manager is logged in | 1. Login as non-admin 2. Request `/api/evaluation/results` | Staff/manager session | Results are denied or hidden according to access rules |  |  | Negative role test |
| TC-EVAL-008 | Evaluation | Print/preview evaluation results if available | Admin is viewing results | 1. Open results 2. Use print preview if supported | Existing results | Result layout remains readable in print/preview |  |  | For defense evidence |

## 10. UI, Accessibility, and Error Handling

| Test Case ID | Module | Test Scenario | Preconditions | Test Steps | Test Data | Expected Result | Actual Result | Status | Remarks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-UI-001 | UI/Accessibility | Mobile responsiveness on major pages | User is logged in | 1. Open Dashboard, Sales Order, Invoices, Expenses, Analytics, Reports, Admin Center, Evaluation 2. Resize to mobile width | Mobile viewport | Content fits screen; tables scroll inside wrappers; no major horizontal page drift |  |  | Screenshot key pages |
| TC-UI-002 | UI/Accessibility | Keyboard navigation on tabs/modals | User is logged in | 1. Use Tab/Shift+Tab/Enter/Escape on menus, tabs, modals 2. Observe focus | Keyboard only | Focus is visible and controls can be opened/closed without mouse where expected |  |  | Accessibility check |
| TC-UI-003 | UI/Accessibility | Form validation messages are readable | User is on any required form | 1. Submit incomplete form 2. Review validation message | Missing required fields | Validation messages are clear, visible, and do not overlap form controls |  |  | UX polish |
| TC-UI-004 | UI/Accessibility | Friendly 404 page | App is running | 1. Browse to a nonexistent route | `/not-a-real-page` | System shows friendly 404/empty error page, not raw stack trace |  |  | Error page check |
| TC-UI-005 | UI/Accessibility | Permission error page | Non-admin user exists | 1. Login as non-admin 2. Open admin-only URL | Staff/manager session | System shows redirect or friendly permission error, not raw server error |  |  | 403 behavior |
| TC-UI-006 | UI/Accessibility | Upload error messaging | Upload feature is available | 1. Upload malformed/unsupported file in Sales Order, Invoice, or Analytics upload 2. Observe message | Bad file | User sees actionable error message; page remains usable |  |  | Negative UX test |
| TC-UI-007 | UI/Accessibility | Tables do not overlap on desktop/mobile | Tables have enough columns | 1. Open admin/data/report tables 2. Test desktop and mobile widths | Populated tables | Headers, rows, filters, and action buttons stay readable without incoherent overlap |  |  | Very important for defense demo |
| TC-UI-008 | UI/Accessibility | Session timeout page | Session timeout route exists | 1. Open `/session-timeout` or trigger idle timeout if possible | Expired/timeout session | Timeout page/message appears and user can return to login safely |  |  | Session behavior |

## Execution Summary Template

Use this after running the cases:

| Module | Total Cases | Passed | Failed | Not Tested | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| Authentication and User Roles | 8 |  |  |  |  |
| Dashboard / Home | 8 |  |  |  |  |
| Sales Order | 8 |  |  |  |  |
| Invoice and Collection Receipts | 10 |  |  |  |  |
| Expense Module | 8 |  |  |  |  |
| Analytics | 10 |  |  |  |  |
| Reports | 8 |  |  |  |  |
| Admin Center | 12 |  |  |  |  |
| Evaluation Page | 8 |  |  |  |  |
| UI, Accessibility, and Error Handling | 8 |  |  |  |  |

## Suggested Automated Regression Checks

Run these after manual edits or before final defense testing:

```powershell
python -m py_compile app.py analytics_services.py admin_services.py
python tests\defense_readiness_check.py
python tests\interface_layout_check.py
python tests\accessibility_keyboard_check.py
python tests\dashboard_home_check.py
python tests\sales_order_manual_print_check.py
python tests\invoice_collection_csv_check.py
python tests\invoice_quantity_print_check.py
python tests\expense_module_terminology_check.py
python tests\analytics_objectives_check.py
python tests\evaluation_interface_check.py
```

## Final Reminder sa Assigned Tester

Pre, wag basta check-check lang. Every test case should answer: ano ginawa mo, anong data ginamit mo, anong dapat mangyari, at ano talaga nangyari. Kapag may fail, ilagay agad sa Remarks yung exact page, screenshot name, role/account used, and steps to reproduce para madali ayusin.
