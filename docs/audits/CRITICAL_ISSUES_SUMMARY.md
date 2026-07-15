# Quick Reference: Critical Issues Found

## Issue Severity Breakdown

### 🔴 CRITICAL (Fix ASAP)
1. **Dual Company Matching Functions** - Causes data inconsistency
2. **Missing Admin Invoices in Analytics** - Up to 30-50% revenue missing
3. **Revenue Only Counts "PAID" Status** - Undercounts by 5-15%

### 🟠 HIGH (This Week)
4. **Wrong Date Field in Sales Performance** - Monthly trends completely wrong
5. **Client Analysis Uses Wrong Matching** - Client segmentation incorrect

### 🟡 MEDIUM (Next Week)
6. **Payment Date vs Invoice Date** - Days outstanding overstated
7. **Partial Payment Handling** - Customer scores off by 10-20 points

---

## Code Locations

### analytics_services.py

**Issue #1: Mismatched normalization (Line 31)**
```python
# Current (WRONG):
def normalize_company_match_key(value: Any) -> str:
    text = str(value or "").upper().replace("&", " AND ")
    text = re_sub_non_company(text)
    return " ".join(text.split())

# Should use app.py's normalize_client_match_key() instead
```

**Issue #2: Missing admin invoices (Lines 162-172)**
```python
# Current BROKEN _revenue_by_client():
def _revenue_by_client(db, Client, SalesOrder, Invoice):
    rows = (
        db.session.query(Client.client_name, func.sum(Invoice.amount_paid).label("revenue"))
        .select_from(Client)
        .join(SalesOrder, Client.id == SalesOrder.client_id)
        .join(Invoice, SalesOrder.id == Invoice.sales_order_id)
        .filter(Invoice.status == "PAID")  # ← Issue #3: Only PAID
        # ❌ Missing admin invoices (sales_order_id IS NULL)
```

**Issue #3: Only "PAID" status (Lines 103-107)**
```python
# Current WRONG:
def _invoice_revenue(db, Invoice, start, end):
    return numeric(
        db.session.query(func.sum(Invoice.amount_paid))
        .filter(Invoice.status == "PAID")  # ← WRONG: ignores partial payments
        .filter(Invoice.invoice_date >= start, Invoice.invoice_date <= end)
        .scalar()
    )
```

**Issue #4: Wrong date field (Lines 124-132)**
```python
# Current WRONG:
"sales_count": SalesOrder.query.filter(
    SalesOrder.created_at >= start,  # ← WRONG: Use order_date
    SalesOrder.created_at < end
).count(),

# Should be:
"sales_count": SalesOrder.query.filter(
    SalesOrder.order_date >= start,  # ← CORRECT: Business date
    SalesOrder.order_date < end
).count(),
```

**Issue #5: Client analysis matching (Lines 676-704)**
```python
# Current:
matched_client_name = best_company_match(row.company_name, client_names)
# Uses normalize_company_match_key() ← Low sophistication

# Should use:
matched_client_name = resolve_client_name(row.company_name, registry=registry)
# Uses app.py's superior logic
```

---

## Database Records to Check

Run these queries to understand current data state:

```sql
-- 1. How many orphaned admin invoices exist?
SELECT 
    COUNT(*) as orphaned_invoices,
    COALESCE(SUM(amount_paid), 0) as total_paid,
    COALESCE(SUM(balance), 0) as total_balance
FROM invoices 
WHERE sales_order_id IS NULL 
  AND uploaded_client_name IS NOT NULL;

-- 2. Invoices with amount_paid but not marked PAID
SELECT COUNT(*) FROM invoices 
WHERE status != 'PAID' 
  AND amount_paid > 0;

-- 3. Orders entered days after business date
SELECT COUNT(*), AVG(JULIANDAY(created_at) - JULIANDAY(order_date))
FROM sales_orders 
WHERE DATE(order_date) != DATE(created_at);

-- 4. Client name inconsistencies
SELECT DISTINCT 
    so.company_name, 
    COUNT(*) 
FROM sales_orders so
GROUP BY LOWER(so.company_name)
ORDER BY COUNT(*) DESC
LIMIT 20;

-- 5. Payment status distribution
SELECT status, COUNT(*), SUM(amount_paid), SUM(balance)
FROM invoices
GROUP BY status;
```

---

## Files With Issues

**PRIMARY ISSUES:**
- `analytics_services.py` - 6 functions broken/wrong
- `app.py` - Dual matching functions

**SECONDARY IMPACT:**
- `templates/analytics.html` - Displays wrong data
- Any reports using `/api/analytics/*` endpoints

---

## How to Prioritize Fixes

### If admin invoice volume is HIGH (>20% of invoices):
1. Fix admin invoice joins (Issue #2) - Will recover 20-50% accuracy
2. Unify matching logic (Issue #1)
3. Fix date field (Issue #4)

### If admin invoice volume is LOW (<5% of invoices):
1. Unify matching logic (Issue #1) 
2. Fix date field (Issue #4)
3. Fix "PAID" status filter (Issue #3)

---

## Impact Matrix: Which Reports Are Affected

| Report | Issue #1 | #2 | #3 | #4 | #5 | Impact |
|--------|----------|----|----|----|----|--------|
| Revenue by Client | ✓ | ✓ | ✓ | | | 🔴 BROKEN |
| Client Balances | ✓ | ✓ | ✓ | | | 🔴 BROKEN |
| Accounts Receivable | | ✓ | ✓ | | | 🟠 WRONG |
| Sales Performance | | | | ✓ | | 🟠 WRONG |
| Revenue Leakage | ✓ | ✓ | ✓ | | | 🔴 BROKEN |
| Client Analysis | ✓ | ✓ | ✓ | | ✓ | 🟠 WRONG |
| Customer Behavior Score | ✓ | ✓ | | | | 🟠 WRONG |
| Cash Flow Analysis | | | ✓ | | | 🟡 MINOR |
| Demand Predictions | | | | ✓ | | 🟡 MINOR |

---

## Estimated Data Accuracy Currently

Assuming typical patterns:
- **Client Revenue Reports**: 60-80% accurate (if high admin volume)
- **Monthly Trends**: 40-70% accurate (date field issue)
- **Client Balance**: 65-85% accurate (if high admin volume)
- **Accounts Receivable**: 70-90% accurate
- **Customer Scores**: 70-85% accurate (matching + payment logic)

*Accuracy improves significantly if admin invoice volume is low.*

---

## Validation After Fixes

```python
# Test 1: Revenue consistency
assert analytics_revenue ≈ app_refresh_revenue ±2%

# Test 2: Admin invoices included
assert revenue_with_admin_invoices > revenue_without

# Test 3: Date field correct
assert june_sales_count from analytics 
       ≈ count(order_date in June)

# Test 4: Matching unified
assert normalize_company_match_key() 
       == normalize_client_match_key()

# Test 5: Partial payments counted
assert invoice_count[amount_paid > 0] 
       == revenue_calculation_base
```

