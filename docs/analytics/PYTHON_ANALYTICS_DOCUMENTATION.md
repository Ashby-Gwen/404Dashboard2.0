# Python Analytics Documentation

This document explains where the analytics design lives, how data flows through the analytics process, what formulas are used, and which Python/frontend libraries support the feature.

## Where the Analytics Design Lives

The analytics feature is implemented across these files:

- `app.py`
  - Defines the `AnalyticsData` model.
  - Defines `/analytics`.
  - Defines `/api/analytics/generate`.
  - Defines `/api/analytics/overview`.
  - Defines `/api/analytics/overview/upload`.
  - Defines `/api/analytics/clients`.
  - Defines `/api/analytics/expenses`.
  - Defines `/api/analytics/item-categories`.
  - Defines `/api/analytics/sales`.
  - Defines `/api/analytics/comparative`.
- `analytics_services.py`
  - Contains most analytics calculations.
  - Builds client analysis, expense analysis, sales analysis, forecasting, recommendations, and comparative analytics.
- `templates/analytics.html`
  - Contains the Analytics UI.
  - Calls the analytics API endpoints.
  - Renders charts, tables, filters, recommendation views, and export behavior.
- `static/vendor/chartjs/chart.umd.min.js`
  - Local Chart.js runtime used by the Analytics page.
- `tests/analytics_objectives_check.py`
  - Main regression test for analytics objectives, payloads, forecasting, client analysis, and upload behavior.
- `tests/historical_upload_schema_check.py`
  - Focused test for historical analytics upload schemas.
- `tests/analytics_chart_asset_check.py`
  - Verifies the local chart asset contract.

## High-Level Analytics Design

The system has two main analytics data paths.

### 1. Overview Analytics: Ledger-Based

The Overview tab reads from `analytics_data` through the `AnalyticsData` model.

This path is used for cash-flow style analytics:

- Gross revenue
- Expense or cost outflow
- Profit/Loss
- Current period versus previous year comparison
- Monthly Revenue vs Expense trend
- Historical upload data

The key endpoint is:

```text
GET /api/analytics/overview
```

Historical upload endpoint:

```text
POST /api/analytics/overview/upload
```

Generate/rebuild endpoint:

```text
POST /api/analytics/generate
```

### 2. Revenue and Operational Analytics: Sales-Order-Based

The Revenue tab reads live operational tables, mainly Sales Orders and Sales Order Items, through `analytics_services.py`.

This path is used for sales-planning analytics:

- Sales Order revenue
- Product/item performance
- Sales trend
- Peak sales periods
- Forecasting
- Store/client forecasting
- Rule-based recommendations

The key endpoint is:

```text
GET /api/analytics/sales
```

This design means Overview and Revenue can show different numbers. Overview uses the financial ledger and cash-flow direction. Revenue uses Sales Order item value.

## Analytics Data Sources

### Live Operational Tables

Analytics reads these operational tables:

- `sales_orders`
- `sales_order_items`
- `sales_order_branches`
- `invoices`
- `collection_receipts`
- `purchase_orders`
- `clients`
- `client_aliases`
- `analytics_item_categories`
- `analytics_data`

### Historical Upload Files

The upload endpoint accepts CSV and Excel files.

Supported sales-detail schema:

```text
DATE
COMPANY NAME
STORE NAME
COST
QUANTITY
SELLING PRICE
```

Optional sales-detail columns include:

```text
STORE BRANCH
PARTICULAR
```

Supported ledger schema:

```text
SOURCE_TYPE
SOURCE_ID
TRANSACTION_DATE
FINANCIAL_STAGE
FLOW_DIRECTION
FLOW_STATUS
PARTY_NAME
PARTY_ROLE
AMOUNT
BALANCE_AMOUNT
CATEGORY
STATUS
DESCRIPTION
```

Historical upload rows are validated, checked for duplicates, checked for outliers, and inserted into `analytics_data`.

## Analytics Process Flow

### Overview Flow

1. User opens `/analytics`.
2. Frontend calls `/api/analytics/overview`.
3. Backend checks `AnalyticsData`.
4. Backend applies selected date filters.
5. Backend groups rows by transaction month.
6. Backend computes revenue, expense, profit, and comparison values.
7. Frontend renders KPI cards and charts in `templates/analytics.html`.

### Historical Upload Flow

1. User uploads CSV or Excel file.
2. Backend reads the file with pandas.
3. Backend normalizes headers.
4. Backend checks if the file matches the sales-detail schema or ledger schema.
5. Backend validates dates, required values, numeric fields, duplicates, and outliers.
6. If client names need resolution, backend returns a resolution response.
7. Confirmed rows are inserted into `AnalyticsData`.
8. Client financials are refreshed.
9. Audit log is written.

### Sales/Revenue Flow

1. Frontend calls `/api/analytics/sales`.
2. Backend parses date and forecast filter settings.
3. `get_sales_analysis()` builds the response.
4. The response combines:
   - `get_sales_kpis()`
   - `get_sales_order_history()`
   - `get_sales_descriptive()`
   - `get_sales_forecast()`
   - `get_clients_analysis()`
   - `build_client_forecasting()`
   - `build_rule_based_recommendations()`
5. Frontend renders Revenue tab charts, forecast controls, client forecasts, product distribution, and recommendations.

### Client Analysis Flow

1. Frontend calls `/api/analytics/clients`.
2. Backend calls `get_clients_analysis()`.
3. Sales Orders are grouped by Store Name.
4. Store-level totals, order count, branch count, cost, paid amount, balance, recency, and item metrics are calculated.
5. A weighted score is computed.
6. Clients are ranked and assigned A-Class, B-Class, or C-Class.

### Expense Analysis Flow

1. Frontend calls `/api/analytics/expenses`.
2. Backend calls `get_expenses_breakdown()`.
3. Purchase Orders are grouped by category, particulars, and supplier/payee.
4. Fixed and variable expense totals are calculated.
5. Ranked expense contributors and pie data are returned.

## Core Formulas

### Overview Gross Revenue

Source: `AnalyticsData`

```text
gross_revenue = SUM(amount WHERE flow_direction = 'INFLOW' AND flow_status = 'ACTUAL')
```

### Overview Total Cost / Expense

Source: `AnalyticsData`

```text
total_cost_of_goods = SUM(amount WHERE flow_direction = 'OUTFLOW' AND flow_status = 'ACTUAL')
```

### Overview Profit/Loss

```text
profit = gross_revenue - total_cost_of_goods
```

### Percentage Change

Used for current period versus comparison period.

```text
percentage_change = ((current - previous) / previous) * 100
```

If previous is zero, the value is returned as `None` because the percentage change is not safely comparable.

### Historical Upload Sales Amount

For sales-detail uploads:

```text
total_sales = quantity * selling_price
```

The inserted analytics amount is:

```text
amount = selling_price * quantity
```

### Historical Upload Outlier Detection

For each numeric upload field:

```text
mean = average(values)
std = standard_deviation(values)
z_score = (value - mean) / std
```

IQR bounds:

```text
q1 = 25th percentile
q3 = 75th percentile
iqr = q3 - q1
lower_bound = q1 - (1.5 * iqr)
upper_bound = q3 + (1.5 * iqr)
```

A value is flagged when:

```text
abs(z_score) >= 2.5
OR value < lower_bound
OR value > upper_bound
```

### Sales Order Item Revenue

The Revenue tab uses a deduplicated item revenue subquery.

```text
item_revenue = item.total OR (item.quantity * item.selling_price)
```

Rows are grouped by Sales Order date, Sales Order number, staff, company, store, branch, item, quantity, cost, selling price, and revenue to collapse exact duplicate item rows for analytics.

### Sales Total Revenue

```text
total_revenue = SUM(deduplicated item_revenue)
```

### Sales Count

```text
total_sales = COUNT(SalesOrder rows in selected date range)
```

### Top Items

```text
top_items = GROUP BY item.particular
            ORDER BY SUM(quantity) DESC
```

### Monthly Sales Trend

```text
monthly_revenue = SUM(deduplicated item_revenue GROUP BY SalesOrder.order_date month)
monthly_quantity = SUM(quantity GROUP BY SalesOrder.order_date month)
active_sales_days = COUNT(DISTINCT SalesOrder.order_date)
average_quantity = monthly_quantity / active_sales_days
```

### Product Distribution

```text
product_quantity = SUM(quantity GROUP BY normalized item name)
product_revenue = SUM(revenue GROUP BY normalized item name)
```

If item category mappings exist in `analytics_item_categories`, each product is assigned to the saved category. Otherwise it uses the uncategorized label.

### Peak Month and Weekday

For month or weekday groups:

```text
quantity = SUM(quantity)
revenue = SUM(revenue)
active_sales_days = COUNT(DISTINCT SalesOrder.order_date)
average_quantity = quantity / active_sales_days
```

The UI sorts by strongest quantity/average activity to show peak periods.

### Expense Totals

Source: `PurchaseOrder`

```text
fixed_expenses = SUM(cash_amount WHERE category = 'FIXED')
variable_expenses = SUM(cash_amount WHERE category = 'VARIABLE')
total_expenses = fixed_expenses + variable_expenses
```

### Expense Share

```text
fixed_share_percent = fixed_expenses / total_expenses * 100
variable_share_percent = variable_expenses / total_expenses * 100
```

If total expenses is zero, shares are returned as zero.

### Ranked Expense Contributors

```text
ranked_particular_amount = SUM(cash_amount GROUP BY PurchaseOrder.particulars)
ranked_supplier_amount = SUM(cash_amount GROUP BY PurchaseOrder.supplier_payee)
share_percent = amount / total_expenses * 100
```

### Client / Store Grouping

Client Analysis groups Sales Orders by Store Name.

```text
store_key = normalized Store Name
```

For each store group:

```text
sales_order_value = SUM(order item totals OR SalesOrder.total_amount)
order_count = COUNT(SalesOrder)
branches_count = COUNT(unique branch names)
total_paid = SUM(Invoice.amount_paid linked to store orders)
balance = sales_order_value - total_paid
average_order_value = sales_order_value / order_count
repeat_order_frequency = max(order_count - 1, 0)
```

### Item-Level Client Metrics

For each store and item:

```text
item_sales = item.total OR (quantity * selling_price)
item_cost = quantity * unit_cost
item_gross_profit = item_sales - item_cost
item_profit_margin = item_gross_profit / item_sales * 100
```

### Store Gross Profit and Margin

```text
gross_profit = sales_order_value - total_cost
profit_margin = gross_profit / sales_order_value * 100
```

### Recency Ratio

```text
days_since_purchase = today - latest_order_date
recency_ratio = 1 - min(days_since_purchase, 365) / 365
```

The ratio is clamped between 0 and 1.

### Client Performance Score

The score is Sales Order based and uses three weighted components.

```text
amount_score = (store_sales_order_value / max_sales_order_value) * 50
order_frequency_score = (store_order_count / max_order_count) * 30
branch_count_score = (store_branch_count / max_branch_count) * 20
```

Final score:

```text
client_performance_score = amount_score + order_frequency_score + branch_count_score
```

Maximum score is 100.

Normalized score:

```text
score = client_performance_score / 100
```

### ABC Client Classification

Stores are sorted by:

```text
client_performance_score DESC
sales_order_value DESC
store_name ASC
```

Cumulative revenue is calculated:

```text
cumulative_revenue_percent = cumulative_sales_order_value / total_client_revenue * 100
```

Classification:

```text
A-Class Clients: previous cumulative percent < 80
B-Class Clients: previous cumulative percent >= 80 and < 95
C-Class Clients: previous cumulative percent >= 95
```

### Trend Status for Clients

Uses complete months only. The current month is excluded.

```text
trend_change_percent = (current_complete_month - previous_complete_month) / previous_complete_month * 100
```

Status:

```text
declining if trend_change_percent <= -10
stable_or_growing otherwise
insufficient_history if fewer than 3 complete months
not_comparable if previous month value is zero
```

## Forecasting Design

Forecasting is implemented in `analytics_services.py`.

Important functions:

- `holt_winters_forecast()`
- `backtest_holt_winters()`
- `mean_absolute_percentage_error()`
- `build_monthly_revenue_forecast()`
- `get_sales_forecast()`
- `build_client_forecasting()`

### Additive Holt-Winters Formula

The system uses a small additive Holt-Winters implementation.

Configuration:

```text
season_length = 12
alpha = 0.35
beta = 0.15
gamma = 0.25
```

Initial level:

```text
level = average(first season_length values)
```

Initial trend:

```text
trend = (average(second season_length values) - level) / season_length
```

Initial seasonal values:

```text
seasonal[i] = value[i] - level
```

For each value:

```text
season = seasonal[index % season_length]
last_level = level
level = alpha * (value - season) + (1 - alpha) * (level + trend)
trend = beta * (level - last_level) + (1 - beta) * trend
seasonal[index % season_length] = gamma * (value - level) + (1 - gamma) * season
```

One-step forecast:

```text
forecast = level + trend + seasonal[next_index % season_length]
```

The output is clamped to zero:

```text
forecast = max(forecast, 0)
```

### Fallback Forecast

If there are fewer than 24 values for seasonal Holt-Winters:

```text
forecast = average(last 3 values)
```

If fewer than three values exist for monthly revenue forecast, the response status becomes:

```text
insufficient_data
```

### MAPE Formula

MAPE means Mean Absolute Percentage Error.

```text
MAPE = average(abs((actual - predicted) / actual)) * 100
```

Rows with actual value equal to zero are excluded to avoid division by zero.

### Forecast Backtesting

Backtesting uses the latest validation periods.

```text
validation_count = min(validation_periods, max(1, len(values) // 4))
```

Default validation periods:

```text
validation_periods = 3
```

For each validation point:

1. Train on older values.
2. Predict the next value.
3. Compare prediction against actual.
4. Compute MAPE.

If fewer than six values exist:

```text
status = insufficient_data
```

### Forecast Acceptance

Default MAPE threshold:

```text
MAPE_DEFAULT_THRESHOLD = 20.0
```

The `/api/analytics/sales` endpoint accepts:

```text
mape_threshold
```

Forecast status:

```text
accepted if MAPE <= threshold
above_threshold if MAPE > threshold
insufficient_data if backtest cannot run
```

### Predicted Revenue and Profit by Item

For each forecasted item:

```text
average_price = average(selling_price)
average_cost = average(unit_cost)
predicted_qty = forecasted quantity
predicted_revenue = predicted_qty * average_price
predicted_profit = predicted_qty * (average_price - average_cost)
```

### Monthly Revenue Forecast

The system creates 12 forecast points by default.

```text
historical_points = actual monthly Sales Order revenue
forecast_points = future months generated recursively
```

Recursive forecasting:

```text
forecast_revenue = holt_winters_forecast(working_values)
append forecast_revenue to working_values
repeat until horizon is reached
```

Available UI horizons:

```text
3 months
6 months
12 months
```

## Rule-Based Recommendations

Recommendations are generated in `build_rule_based_recommendations()`.

Inputs:

- Forecast data
- Descriptive sales data
- Client/store performance data
- Pondo value

Pondo:

```text
pondo = max(paid_revenue - total_expenses, 0)
```

Thresholds:

```text
high_sales_threshold = 75th percentile of store sales values
low_activity_threshold = 25th percentile of store order counts
```

Rules include:

- Strong sales but weak margin
- Healthy profit margin
- Low ordering activity
- Recent sales decline
- Not enough trend history
- Clear lead item
- High-cost items need review
- Incomplete cost data
- Continue monitoring

Each recommendation includes:

- Title
- Severity
- Why it appeared
- Business interpretation
- Recommended action
- Calculation process
- Evidence values
- Rule labels
- Store metrics

## Comparative Analytics

Comparative analytics is exposed through:

```text
GET /api/analytics/comparative
```

The function is:

```text
get_comparative_analysis()
```

It supports comparison views for analytics reporting and UI charts.

## Libraries Used

### Python Libraries

From `requirements.txt` and imports:

- Flask
  - Web framework.
  - Defines routes, sessions, request handling, and JSON responses.
- Flask-SQLAlchemy
  - ORM integration for Flask.
  - Used for model queries and database writes.
- SQLAlchemy
  - Query building, grouping, aggregation, `func`, and `extract`.
- pandas
  - Reads CSV/Excel uploads.
  - Builds upload EDA statistics.
  - Handles numeric distributions and outlier calculations.
- openpyxl
  - Excel engine used by pandas for `.xlsx` files.
- numpy
  - Installed dependency, but the current analytics code is primarily pandas/SQLAlchemy based.
- python-Levenshtein
  - Installed string matching support dependency.
- rapidfuzz
  - Installed fuzzy matching support dependency.
- psycopg2-binary
  - PostgreSQL driver for Supabase.
- python-dotenv
  - Environment variable loading.
- Werkzeug
  - Flask dependency used for web utilities and security helpers.

### Python Standard Library

Used in analytics-related code:

- `collections.defaultdict`
- `datetime.date`
- `datetime.datetime`
- `datetime.timedelta`
- `difflib.SequenceMatcher`
- `typing.Any`
- `csv`
- `re`
- `decimal.Decimal`
- `io.TextIOWrapper`
- `io.BytesIO`

### Frontend Libraries

Used by Analytics UI:

- Chart.js
  - Local file: `static/vendor/chartjs/chart.umd.min.js`
  - Renders charts in `templates/analytics.html`.
- SheetJS
  - Used by the frontend for workbook-related behavior.
- Bootstrap
  - UI layout and components.

## Analytics UI Design

The UI design is in:

```text
templates/analytics.html
```

Important frontend functions include:

- `loadSection(section)`
- `activateAnalyticsSection(section)`
- `cachedAnalyticsJson(...)`
- `createAnalyticsChart(...)`
- `replaceChartForCanvas(...)`
- `renderChartUnavailableState(...)`
- `initOverviewCharts(...)`
- `initClientsCharts(...)`
- `initExpensesCharts(...)`
- `initSalesCharts(...)`
- `renderRevenueForecastChart(...)`
- `renderClientForecastCharts(...)`

The Analytics UI uses AJAX to fetch JSON and Chart.js to render:

- Overview Revenue vs Expense chart
- Client Pareto chart
- Expense composition chart
- Expense particulars chart
- Revenue forecast chart
- Product distribution chart
- Peak sales period chart
- Peak weekday chart
- Client category trend and forecast charts
- Recommendation cards and modals

## API Endpoint Summary

| Endpoint | Purpose | Main backend function |
|---|---|---|
| `GET /analytics` | Analytics page | `analytics()` |
| `POST /api/analytics/generate` | Rebuild analytics ledger from live records | `generate_analytics_report()` |
| `GET /api/analytics/overview` | Overview KPIs and trend | `get_overview()` |
| `POST /api/analytics/overview/upload` | Historical CSV/Excel upload | `upload_csv()` |
| `GET /api/analytics/clients` | Client/store analysis | `get_clients_analysis()` |
| `GET /api/analytics/expenses` | Expense breakdown | `get_expenses_breakdown()` |
| `GET /api/analytics/item-categories` | Detected item categories | `analytics_detected_item_categories()` |
| `POST /api/analytics/item-categories` | Save item category assignments | `api_analytics_item_categories_save()` |
| `GET /api/analytics/sales` | Revenue, forecasting, recommendations | `get_sales_analysis()` |
| `GET /api/analytics/comparative` | Comparative analytics | `get_comparative_analysis()` |
| `GET /get-analytics` | Legacy/shared payload endpoint | `build_analytics_payload()` |
| `POST /analytics/excel-preview` | Excel preview helper | `preview_excel_sheets()` |

## Important Design Notes

- Overview and Revenue are intentionally different.
  - Overview is ledger/cash-flow based.
  - Revenue is Sales Order/item based.
- Client Value is Sales Order based.
  - It uses Sales Order value, order count, and branch count.
  - Invoice payment behavior contributes to paid/balance status, but not the main 100-point performance score.
- Forecasting uses additive Holt-Winters when enough history exists.
  - Otherwise it falls back to an average of recent values.
- MAPE validates forecast accuracy.
  - Default threshold is 20%.
- Historical upload supports both sales-detail files and ledger-style files.
- Chart.js is local, not CDN-only, so the Analytics page can render charts without relying on an external Chart.js network request.

## Main Verification Files

Use these checks after changing analytics behavior:

```powershell
python tests\analytics_objectives_check.py
python tests\historical_upload_schema_check.py
python tests\analytics_chart_asset_check.py
python tests\interface_layout_check.py
python tests\accessibility_keyboard_check.py
```

For upload schema work, start with:

```powershell
python tests\historical_upload_schema_check.py
```

For forecasting, client value, recommendations, and payload contracts, start with:

```powershell
python tests\analytics_objectives_check.py
```
