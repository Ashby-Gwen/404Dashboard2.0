# Validation & Diagnostic Queries

## Run These Queries to Verify Issues

---

## 1. CHECK: Admin Invoice Volume (Issue #2)

```sql
-- See if there are significant orphaned admin invoices
SELECT 
    'Total Invoices' as metric,
    COUNT(*) as count,
    COALESCE(SUM(amount_paid), 0) as total_paid,
    COALESCE(SUM(balance), 0) as total_unpaid

FROM invoices

UNION ALL

SELECT 
    'With Sales Order Link' as metric,
    COUNT(*) as count,
    COALESCE(SUM(i.amount_paid), 0) as total_paid,
    COALESCE(SUM(i.balance), 0) as total_unpaid

FROM invoices i
WHERE i.sales_order_id IS NOT NULL

UNION ALL

SELECT 
    'Orphaned (Admin Upload)' as metric,
    COUNT(*) as count,
    COALESCE(SUM(amount_paid), 0) as total_paid,
    COALESCE(SUM(balance), 0) as total_unpaid

FROM invoices
WHERE sales_order_id IS NULL 
  AND uploaded_client_name IS NOT NULL;
```

**What to look for:**
- If "Orphaned" count > 20% of "Total Invoices" → Issue is CRITICAL
- If "Orphaned" count < 5% of "Total Invoices" → Issue is low priority

---

## 2. CHECK: Revenue Discrepancy (Issues #2 + #3)

```sql
-- Compare actual payments vs reported revenue
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

-- Difference = potential undercount from Issue #3
```

**Expected result:**
```
PAID status invoices          X invoices,  $A revenue
All with amount_paid > 0      Y invoices,  $B revenue
Difference = Y-X invoices, $(B-A) revenue missing
```

---

## 3. CHECK: Date Field Issue (Issue #4)

```sql
-- See how many orders have business date != entry date
SELECT 
    CASE 
        WHEN DATE(order_date) = DATE(created_at) THEN 'Same day'
        WHEN JULIANDAY(created_at) - JULIANDAY(order_date) > 0 
             AND JULIANDAY(created_at) - JULIANDAY(order_date) <= 1 
             THEN 'Entered next day'
        WHEN JULIANDAY(created_at) - JULIANDAY(order_date) > 1 
             THEN 'Delayed entry (>1 day)'
        ELSE 'Before order date (data error)'
    END as entry_pattern,
    COUNT(*) as order_count,
    AVG(JULIANDAY(created_at) - JULIANDAY(order_date)) as avg_days_delayed
FROM sales_orders
WHERE order_date IS NOT NULL
GROUP BY 
    CASE 
        WHEN DATE(order_date) = DATE(created_at) THEN 'Same day'
        WHEN JULIANDAY(created_at) - JULIANDAY(order_date) > 0 
             AND JULIANDAY(created_at) - JULIANDAY(order_date) <= 1 
             THEN 'Entered next day'
        WHEN JULIANDAY(created_at) - JULIANDAY(order_date) > 1 
             THEN 'Delayed entry (>1 day)'
        ELSE 'Before order date (data error)'
    END
ORDER BY avg_days_delayed DESC;
```

**What to look for:**
- If "Delayed entry (>1 day)" has significant volume → Trends will be wrong
- If average delay > 3 days → Sales performance reports are very inaccurate

---

## 4. CHECK: Partial Payment Status (Issue #3)

```sql
-- Show payment status distribution
SELECT 
    status,
    COUNT(*) as invoice_count,
    COALESCE(SUM(amount_paid), 0) as total_paid,
    COALESCE(SUM(balance), 0) as total_balance,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM invoices), 2) as pct_of_total
FROM invoices
GROUP BY status
ORDER BY COUNT(*) DESC;

-- Show invoices where amount_paid > 0 but not PAID status
SELECT 
    status,
    COUNT(*) as count,
    COALESCE(SUM(amount_paid), 0) as paid_amount,
    COALESCE(SUM(total_amount), 0) as total_amount
FROM invoices
WHERE amount_paid > 0 
  AND status != 'PAID'
GROUP BY status;
```

**What to look for:**
- "PARTIAL" status with significant volume → Issue #3 is active
- Second query with rows → Revenue is being undercounted

---

## 5. CHECK: Company Name Inconsistencies (Issue #1 & #5)

```sql
-- Find similar company names that should probably match
SELECT 
    UPPER(TRIM(company_name)) as normalized_name,
    COUNT(DISTINCT UPPER(TRIM(company_name))) as variant_count,
    COUNT(*) as total_orders,
    GROUP_CONCAT(DISTINCT company_name, ' | ') as variations
FROM sales_orders
WHERE company_name IS NOT NULL
GROUP BY UPPER(TRIM(company_name))
HAVING COUNT(DISTINCT company_name) > 1
ORDER BY total_orders DESC
LIMIT 20;
```

**Example output:**
```
TEAMASTERS INC     | 3 variants | 150 orders
  - TEAMASTERS INC
  - Teamasters Inc  
  - TEAMASTERS INCORPORATED
```

---

## 6. CHECK: Client Financial Accuracy (Issue #2)

```sql
-- Compare built-in client totals vs calculated from invoices
SELECT 
    c.id,
    c.client_name,
    c.total_revenue as stored_revenue,
    c.total_balance as stored_balance,
    
    -- Calculate from linked sales orders + invoices
    COALESCE((
        SELECT SUM(so.total_amount)
        FROM sales_orders so
        WHERE so.client_id = c.id
    ), 0) as calculated_so_revenue,
    
    -- Calculate from linked invoices only
    COALESCE((
        SELECT COALESCE(SUM(i.amount_paid), 0)
        FROM invoices i
        JOIN sales_orders so ON i.sales_order_id = so.id
        WHERE so.client_id = c.id
    ), 0) as calculated_linked_revenue,
    
    -- Calculate from BOTH linked + admin invoices
    COALESCE((
        SELECT COALESCE(SUM(i.amount_paid), 0)
        FROM invoices i
        WHERE i.sales_order_id IS NULL 
          AND i.uploaded_client_name IS NOT NULL
          AND c.client_name LIKE i.uploaded_client_name
    ), 0) as admin_invoice_revenue,
    
    -- Total including admin
    COALESCE((
        SELECT COALESCE(SUM(i.amount_paid), 0)
        FROM invoices i
        JOIN sales_orders so ON i.sales_order_id = so.id
        WHERE so.client_id = c.id
    ), 0) + COALESCE((
        SELECT COALESCE(SUM(i.amount_paid), 0)
        FROM invoices i
        WHERE i.sales_order_id IS NULL 
          AND i.uploaded_client_name IS NOT NULL
          AND c.client_name LIKE i.uploaded_client_name
    ), 0) as calculated_total_revenue
    
FROM clients c
WHERE c.total_revenue > 0
ORDER BY c.total_revenue DESC
LIMIT 20;
```

**Analysis:**
- `stored_revenue` should ≈ `calculated_total_revenue` (within 2-5%)
- If difference > 10% → Issue #2 is affecting that client
- If admin_invoice_revenue > 0 → That data exists but might be lost

---

## 7. CHECK: Analytics vs Raw Data (Issue #2)

```sql
-- Monthly revenue from analytics query vs correct query
WITH monthly_correct AS (
    SELECT 
        strftime('%Y-%m', COALESCE(so.order_date, i.invoice_date)) as month,
        COALESCE(SUM(i.amount_paid), 0) as revenue
    FROM invoices i
    LEFT JOIN sales_orders so ON i.sales_order_id = so.id
    WHERE i.amount_paid > 0
    GROUP BY strftime('%Y-%m', COALESCE(so.order_date, i.invoice_date))
),
monthly_analytics_pattern AS (
    SELECT 
        strftime('%Y-%m', i.invoice_date) as month,
        COALESCE(SUM(i.amount_paid), 0) as revenue
    FROM invoices i
    JOIN sales_orders so ON i.sales_order_id = so.id
    WHERE so.client_id IS NOT NULL  -- Missing admin invoices
      AND i.status = 'PAID'  -- Missing partial payments
    GROUP BY strftime('%Y-%m', i.invoice_date)
)
SELECT 
    COALESCE(mc.month, map.month) as month,
    mc.revenue as correct_revenue,
    map.revenue as analytics_revenue,
    CASE 
        WHEN mc.revenue > 0 
        THEN ROUND(100.0 * (mc.revenue - map.revenue) / mc.revenue, 2)
        ELSE 0
    END as error_pct
FROM monthly_correct mc
FULL OUTER JOIN monthly_analytics_pattern map ON mc.month = map.month
ORDER BY month DESC;
```

**Look for:**
- `error_pct` > 5% → Issues are impacting monthly reports
- If error_pct negative → Analytics counts MORE than should be possible

---

## 8. CHECK: ClientAlias Usage (Issue #1)

```sql
-- How many aliases exist and are being used?
SELECT 
    'Total Clients' as metric,
    COUNT(*) as count
FROM clients

UNION ALL

SELECT 
    'Active Aliases' as metric,
    COUNT(*) as count
FROM client_aliases
WHERE status = 'ACTIVE'

UNION ALL

SELECT 
    'Learned Aliases (sample)' as metric,
    COUNT(DISTINCT client_id) as count
FROM client_aliases
WHERE status = 'ACTIVE'
  AND normalized_alias NOT LIKE client_aliases.alias_name;

-- Show what aliases exist
SELECT 
    c.client_name,
    ca.alias_name,
    ca.normalized_alias,
    COUNT(so.id) as sales_orders_with_alias
FROM client_aliases ca
JOIN clients c ON ca.client_id = c.id
LEFT JOIN sales_orders so ON so.client_id = c.id 
  AND UPPER(so.company_name) = ca.alias_name
WHERE ca.status = 'ACTIVE'
GROUP BY ca.id
ORDER BY COUNT(so.id) DESC
LIMIT 20;
```

**Look for:**
- If there are many aliases → Issue #1 is definitely affecting data
- `normalized_alias` should differ from `alias_name` if learning is working

---

## Quick Diagnostic Command

Run this to get a score of data quality issues:

```sql
SELECT 
    (SELECT COUNT(*) FROM invoices WHERE sales_order_id IS NULL AND uploaded_client_name IS NOT NULL) 
        as orphaned_invoices,
    (SELECT COUNT(*) FROM invoices WHERE status != 'PAID' AND amount_paid > 0) 
        as partial_payments,
    (SELECT COUNT(*) FROM sales_orders WHERE DATE(order_date) != DATE(created_at)) 
        as delayed_entries,
    (SELECT COUNT(DISTINCT UPPER(TRIM(company_name))) FROM sales_orders) 
        as unique_company_names_exact,
    (SELECT COUNT(DISTINCT LOWER(TRIM(company_name))) FROM sales_orders) 
        as unique_company_names_normalized,
    (SELECT COUNT(*) FROM client_aliases WHERE status = 'ACTIVE') 
        as active_aliases;
```

**Result interpretation:**
- `orphaned_invoices` > 100 → Issue #2 is CRITICAL  
- `partial_payments` > 50 → Issue #3 is impacting data
- `delayed_entries` > 1000 → Issue #4 is widespread
- `company_names_exact` >> `normalized` → Issue #1 scope

