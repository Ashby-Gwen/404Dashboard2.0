# Syluxent System Check Report
**Date:** 2026-06-09  
**Focus:** Data Retrieval, Company Matching, Analytics Issues

---

> **Historical report:** This document preserves findings from June 9, 2026. The June 18 defense-readiness revision introduced a shared financial ledger, included standalone uploaded invoices, changed collected-revenue filters to `amount_paid > 0`, switched Sales Order trends to `order_date`, and removed SQLite-only `julianday()` from the active leakage path. See `SYSTEM_CHECK_REPORT_2026-06-18.md` and `tests/defense_readiness_check.py` for current status and verification.

## Executive Summary
At the time of this audit, **6 data integrity issues** could cause significant inaccuracies in financial reporting and analytics. They primarily affected:
- Revenue attribution (up to 30-50% missing if admin invoices exist)
- Client balance calculations
- Analytics trend analysis
- Company/client matching consistency

---

## 1. 🔴 CRITICAL: Dual Company Matching Functions (Data Consistency Risk)

### Problem
Two incompatible company matching implementations exist:

**Location A: `analytics_services.py`** (Lines 31-35)
```python
def normalize_company_match_key(value: Any) -> str:
    # Uses basic string normalization + SequenceMatcher ratio
    # Low sophistication - only 100% match or basic similarity
```

**Location B: `app.py`** (Lines 880-901)
```python
def normalize_client_match_key(value):
    # Uses advanced fuzzy matching with:
    # - Levenshtein distance
    # - RapidFuzz token_sort_ratio & token_set_ratio
    # - Custom CLIENT_FUZZY_MATCH_EXCEPTIONS
    # - Learned aliases from ClientAlias table
```

### Why This Matters
- `analytics_services.py` is used in `build_analytics_payload()` and all revenue/client analysis
- `app.py` is used for transaction data entry and client resolution
- Same company "TEAMASTERS INC" vs "TEAMAKERS INC" will match at app.py level but NOT at analytics level
- Results: **Revenue attributed to wrong clients or duplicated**

### Impact
- Client revenue reports don't match transaction history
- Revenue by client analytics unreliable
- Client behavior scoring (line 363-409) uses wrong matching

### Recommendation
**Unify matching logic** - Use app.py's superior logic in analytics_services.py, or create shared utility function.

---

## 2. 🔴 CRITICAL: Missing Admin Invoices in Analytics Queries

### Problem
Four key analytics functions only join through `SalesOrder -> Invoice` chain, which **excludes orphaned admin-uploaded invoices**:

| Function | File | Issue |
|----------|------|-------|
| `_revenue_by_client()` | analytics_services.py:162-172 | Missing admin invoice revenue |
| `_client_balances()` | analytics_services.py:199-208 | Missing outstanding balances |
| `_accounts_receivable()` | analytics_services.py:180-196 | Missing unpaid invoices |
| `_revenue_leakage()` | analytics_services.py:141-160 | Missing at-risk balances |

### Current Query Pattern (WRONG)
```python
.select_from(Client)
.join(SalesOrder, Client.id == SalesOrder.client_id)
.join(Invoice, SalesOrder.id == Invoice.sales_order_id)
# ❌ Ignores: Invoice.sales_order_id IS NULL + Invoice.uploaded_client_name NOT NULL
```

### What's Missing
- Admin payment uploads (historical payment records)
- Direct invoice uploads without sales orders
- External account imports

### Impact Estimate
- If 20% of invoices are admin-uploaded: **-20% revenue on reports**
- If 30% are admin-uploaded: **-30% accounts receivable accuracy**
- Client balance reports show wrong totals

### Comparison: Correct Implementation (app.py)
The `refresh_client_financials()` function (Lines 1125-1165) handles this correctly:
```python
# Step 1: Process linked invoices
linked_invoices = Invoice.query.join(SalesOrder, ...).all()

# Step 2: ALSO process admin invoices
admin_invoices = Invoice.query.filter(
    Invoice.sales_order_id.is_(None)
).filter(
    Invoice.uploaded_client_name.isnot(None)
).all()
```

### Recommendation
**Update all four functions** to use UNION pattern or LEFT JOIN to include admin invoices.

---

## 3. 🟠 HIGH: Revenue Calculation Only Counts "PAID" Status

### Problem
Location: `analytics_services.py` Lines 103-107, 120-123

```python
def _invoice_revenue(db, Invoice, start, end):
    return numeric(
        db.session.query(func.sum(Invoice.amount_paid))
        .filter(Invoice.status == "PAID")  # ❌ Only PAID invoices
        .filter(Invoice.invoice_date >= start, Invoice.invoice_date <= end)
        .scalar()
    )
```

### Why This Is Wrong
Invoice lifecycle: `UNPAID` → `PARTIAL` → `PAID`
- Invoice with `status="UNPAID"` but `amount_paid=500` is ignored
- Invoice with `status="PENDING"` but `amount_paid=300` is ignored
- Partial payments not counted in revenue

### Correct Approach
```python
# Count what was actually paid, regardless of status
.filter(Invoice.amount_paid > 0)
```

### Impact
- Gross revenue understated
- Accounts receivable overstated (logic: AR = Total - Paid, so if Paid is low, AR looks high)
- Pondo (remaining cash) calculation affected

### Recommendation
Change filter from `status == "PAID"` to `amount_paid > 0` OR manage status lifecycle better.

---

## 4. 🟠 HIGH: Wrong Date Field in Sales Performance Analysis

### Problem
Location: `analytics_services.py` Lines 124-132

```python
def _sales_performance(SalesOrder, Invoice) -> list[dict]:
    for i in range(6):
        start = now - timedelta(days=i * 30)
        end = start + timedelta(days=30)
        rows.append({
            "period": start.strftime("%b %Y"),
            "sales_count": SalesOrder.query.filter(
                SalesOrder.created_at >= start,  # ❌ WRONG FIELD
                SalesOrder.created_at < end
            ).count(),
```

### The Issue
- `created_at`: When user entered order into system (could be batch import weeks later)
- `order_date`: Actual business date of the transaction (what you want)

### Example Scenario
- Business date: January 5, 2026
- Data entry date: February 10, 2026 (backlog processing)
- `created_at` filter assigns it to February, not January
- **January sales report shows 0 sales, February shows spike**

### Impact
- Monthly/quarterly trends completely wrong
- Seasonal analysis meaningless
- Forecasting unreliable

### Recommendation
Replace `SalesOrder.created_at` with `SalesOrder.order_date`.

---

## 5. 🟠 HIGH: Client Matching in Analytics Uses Wrong Normalization

### Problem
Location: `analytics_services.py` Lines 676-704 (`get_clients_analysis()`)

```python
def get_clients_analysis(...):
    # This function uses best_company_match() which uses:
    matched_client_name = best_company_match(row.company_name, client_names)
    
    # best_company_match() uses normalize_company_match_key()
    # NOT the sophisticated app.py normalize_client_match_key()
```

### Consequence
- Client analysis doesn't benefit from learned aliases
- Won't recognize "TEAMMAKERS INC" as "TEAMASTERS INC" even after admin training
- Client cohort calculations (Core Partners, At-Risk, etc.) use wrong company groupings

### Impact
- Client segmentation incorrect
- Core Partners misidentified
- At-Risk Whales not flagged

### Recommendation
Pass `app.py`'s `normalize_client_match_key()` or unified resolver to this function.

---

## 6. 🟡 MEDIUM: Payment Date vs Invoice Date Confusion

### Problem
Location: `analytics_services.py` Lines 156, 183

Used in `_revenue_leakage()` and `_accounts_receivable()`:
```python
# Days outstanding calculated from invoice_date (when issued)
# But payment_date (when money arrived) would be more accurate
func.avg(
    func.julianday(func.current_date()) 
    - func.julianday(Invoice.invoice_date)  # ❌ Issue date, not payment date
).label("days_outstanding")
```

### Why It Matters
- Invoice issued: Jan 1, 2026
- Payment received: Jan 15, 2026
- Days outstanding today (Jun 9): 160 days
- But actual payment cycle was only 14 days
- Report says client is slow, but they're actually fast

### Workaround Note
App doesn't track `payment_date` field in Invoice model. Would need schema change.

### Impact (Current)
- Days outstanding overstated (less impact since it's only used in UI analysis)
- Collections prioritization might be off

---

## 7. 🟡 MEDIUM: No Timezone Handling

### Problem
- `datetime.now()` uses local system time
- Database might be UTC
- `julianday()` in SQLite assumes UTC
- Could cause 1-14 hour offset in calculations

### Locations Affected
- `_weekly_cashflow()`: Line 95
- `_sales_performance()`: Line 124
- Analytics date comparisons throughout

### Current Status in Code
App imports `from datetime import UTC` but uses `datetime.now()` (local) instead of `datetime.now(UTC)`. Inconsistent.

### Impact
Minor (1-2 day variance in trending), but compounds over time.

---

## 8. 🟡 MEDIUM: Payment Consistency Calculation Issue

### Problem
Location: `analytics_services.py` Lines 372-383

```python
on_time_count = sum(
    1 for inv in invoices
    if inv.status == "PAID" 
    and (datetime.now().date() - inv.invoice_date).days <= terms_default
)
```

### Issue
- Only looks at invoices marked `PAID`
- Invoices with partial payments (status = "PARTIAL") ignored
- If invoice issued 60 days ago and half-paid today, marked as "late" (not "PAID")
- Clients with partial payment patterns score low

### Impact
- Customer behavior scores inaccurate
- Core Partners misidentified

---

## Summary Table: Data Retrieval Issues

| Issue | Severity | Affected Reports | Estimated Error |
|-------|----------|------------------|-----------------|
| Dual matching functions | 🔴 Critical | All client reports | Possible duplicates/mismatches |
| Missing admin invoices | 🔴 Critical | Revenue, AR, Client balances | ±30% if high admin upload volume |
| Only "PAID" status revenue | 🟠 High | Gross revenue, Pondo | ±5-15% understatement |
| Wrong date field (`created_at`) | 🟠 High | Sales trends, Monthly analysis | Weeks/months offset |
| Analytics uses basic matching | 🟠 High | Client analysis, Cohorts | Grouping errors |
| Payment date vs invoice date | 🟡 Medium | Days outstanding report | ±15-30 day offset |
| Timezone inconsistency | 🟡 Medium | Date boundaries | ±12 hour variance |
| Partial payment handling | 🟡 Medium | Customer scores | 10-20 point variance |

---

## Analytics Functions Health Scorecard

| Function | Status | Issues |
|----------|--------|--------|
| `build_analytics_payload()` | ⚠️ Risky | Calls broken sub-functions |
| `_revenue_by_client()` | ❌ Broken | Missing admin invoices |
| `_client_balances()` | ❌ Broken | Missing admin invoices |
| `_accounts_receivable()` | ❌ Broken | Missing admin invoices |
| `_revenue_leakage()` | ❌ Broken | Missing admin invoices |
| `_sales_performance()` | ⚠️ Wrong | Uses created_at instead of order_date |
| `get_clients_analysis()` | ⚠️ Risky | Uses inferior matching logic |
| `calculate_customer_behavior_score()` | ⚠️ Risky | Payment consistency logic flawed |
| `_weekly_cashflow()` | ⚠️ Minor | OK structure, needs timezone check |
| `_monthly_cashflow()` | ⚠️ Minor | OK structure, needs timezone check |

---

## Recommended Quick Fixes (In Priority Order)

### Immediate (This Week)
1. **Unify company matching** → Create `utils.py` with shared normalization
2. **Fix admin invoice joins** → Add LEFT JOIN for orphaned invoices in 4 functions
3. **Fix date field** → Use `order_date` not `created_at` in `_sales_performance()`

### Short Term (Next Week)
4. **Add timezone handling** → Use `UTC` consistently
5. **Review payment status logic** → Handle partial payments correctly
6. **Add validation tests** → Test analytics against known data

### Medium Term (Sprint)
7. **Schema enhancement** → Add `payment_date` field to Invoice for accuracy
8. **Client alias sync** → Ensure analytics uses alias registry

---

## Testing Recommendations

### Unit Tests to Add
- Match company names across both functions (should be identical)
- Revenue calc: Should include admin invoices + partial payments
- Date filtering: Should use business dates not entry dates
- Client analysis: Should use learned aliases

### Sample Test Data Needed
```
Scenario: Admin Invoice Handling
- Create client "TEST CO"
- Create sale order + invoice (linked) = $1000
- Upload payment invoice directly (orphaned) = $500
- Revenue report should show $1500, not $1000
```

### Validation Query
```sql
-- Check for orphaned admin invoices
SELECT COUNT(*) FROM invoices 
WHERE sales_order_id IS NULL 
  AND uploaded_client_name IS NOT NULL;

-- Check for partial payments
SELECT COUNT(*) FROM invoices 
WHERE status != 'PAID' 
  AND amount_paid > 0;

-- Check date discrepancy
SELECT so_number, DATE(order_date) AS biz_date, DATE(created_at) AS entry_date
FROM sales_orders 
WHERE DATE(order_date) != DATE(created_at) 
LIMIT 10;
```

---

## Files Requiring Changes

| File | Functions to Fix | Priority |
|------|-----------------|----------|
| `analytics_services.py` | `_revenue_by_client`, `_client_balances`, `_accounts_receivable`, `_revenue_leakage`, `_sales_performance`, `get_clients_analysis` | 🔴 Critical |
| `app.py` | Create shared matching utility | 🔴 Critical |
| `utils.py` (new) | Centralized company matching | 🔴 Critical |

---

## Next Steps
1. Review findings with team
2. Prioritize fix order based on data volume (check admin invoice count)
3. Create integration tests before fixing
4. Implement fixes systematically
5. Validate against known benchmark data

---

*Report generated by System Audit*
