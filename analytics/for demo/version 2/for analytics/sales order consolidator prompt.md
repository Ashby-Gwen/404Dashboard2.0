use html java script css
create sales order consolidator

1. Upload excel file containing data.
2. map the data
3. create db if nonexistent
4. create table for sales order if non existent.
5. save the data mapped
6. allow export of database as excel file


Read [](file:///c%3A/Users/Ruelo/Desktop/Syluxent-Working%20Copy/templates/sales_order.html)

## Sales Order Data Mapper - Detailed Summary

This is a **three-pass visual mapper** that automatically identifies and extracts sales order data from Excel files. It's staff-specific with customized keyword recognition for each of three staff members.

---

### **Overall Architecture**

**Three-Pass System with Visual Feedback:**
- **Pass 1 (Blue):** Locate PARTICULARS header
- **Pass 2 (Purple):** Scan right to find quantity, cost, and price columns  
- **Pass 3 (Orange):** Extract and count data rows

---

### **Keywords by Data Field & Staff**

#### **1. ORDER NUMBER**
| Staff | Keywords |
|-------|----------|
| MARITESS, JOANNE, RUDELYN | `S.O NO:` or `SO NO:` |
| Processing | Strips label, removes spaces, prefixes with `SO-` |

**Example:** `S.O NO: 12345` → `SO-12345`

---

#### **2. COMPANY NAME**
| Staff | Keywords |
|-------|----------|
| MARITESS | `COMPANY:` or `COMPANY: CHICKEN DELI` |
| JOANNE | `COMPANY:` |
| RUDELYN | `COMPANY:` |
| Processing | Reads next cell value, strips special characters, uppercased |

---

#### **3. STORE NAME**
| Staff | Keywords |
|-------|----------|
| MARITESS | `STORE:` |
| JOANNE | `STORE:` (excludes `STORE ADDRESS:`) |
| RUDELYN | `STORE:` (excludes `STORE ADDRESS:`) |
| Processing | Extracts text after label, preserved as-is |

---

#### **4. STORE BRANCH / ADDRESS**
| Staff | Keywords |
|-------|----------|
| MARITESS | `BRANCH` |
| JOANNE | `STORE ADDRESS:` |
| RUDELYN | `STORE ADDRESS:` |
| Processing | Reads next cell for MARITESS; extracts after label for JOANNE/RUDELYN |

---

#### **5. ORDER DATE**
| All Staff | Keyword | Processing |
|-----------|---------|-----------|
| Searches all | `DATE OF PO:` | 1. Remove label `DATE OF PO:` <br> 2. Replace special chars with spaces <br> 3. Collapse double spaces <br> 4. Trim whitespace <br> 5. Parse: Month Day Year <br> 6. Convert to SQL format (YYYY-MM-DD) |

**Month parsing:** Supports abbreviated (JAN, FEB, etc.) and full names (JANUARY, FEBRUARY, etc.)

---

### **Particulars (Line Items) - Multi-Step Process**

#### **Step 1: Find PARTICULARS Header (Pass 1 - Blue)**
- **Search scope:** First 30 rows across columns A-K
- **Keyword:** Text containing `"PARTICULAR"`
- **Output:** Row index & column index stored for reference

#### **Step 2: Scan Right for Column Headers (Pass 2 - Purple)**
From the PARTICULARS column, scan right to column K looking for:

| Column Purpose | Keywords |
|---|---|
| **Quantity** | `QTY` or `QUANTITY` |
| **Unit Cost** | `UNIT COST` or `COST` |
| **Selling Price** | `SELLING PRICE` or `SELLING` |
| **Total Price** | `TOTAL PRICE` or `TOTAL` |

---

#### **Step 3: Extract Data Rows (Pass 3 - Orange)**

**Two different strategies depending on staff:**

##### **MARITESS BALANQUIT:**
- Counts rows with **numeric values in TOTAL PRICE column**
- Stops when hitting first non-numeric value
- Extracts exactly that count of rows
- **Requirement:** Row must have a description AND total value

##### **JOANNE ZAPANTA & RUDELYN MACAYAN:**
- Identifies **all rows with non-empty PARTICULARS**
- Stops when hitting first empty particulars cell
- **Connected Row Logic:** If QTY, UNIT COST, SELLING, TOTAL are **ALL blank**, that row connects to previous (concatenates description with space)
- **Example:** Multi-line descriptions get merged as single item

---

### **Field Population Logic**

```
Order Information (Metadata):
├─ SO Number → field-orderNumber
├─ Company Name → field-companyName  
├─ Store Name → field-storeName
├─ Store Branch → field-storeBranch
└─ Order Date → field-orderDate

Particulars (Line Items):
├─ Description → particulars[].particulars
├─ Qty → particulars[].qty
├─ Unit Cost → particulars[].cost
├─ Selling Price → particulars[].price
└─ Total → particulars[].total
```

---

### **Visual Feedback During Processing**

| Stage | Color | Action |
|-------|-------|--------|
| **Searching** | Blue/Purple/Orange (pass-specific) | Cell highlights as being checked |
| **Found** | Brighter version (blue/purple/orange) | Cell stays highlighted after match |
| **Toast Notifications** | Pass 1/2/3 colors | Progress messages appear (top-right) |

---

### **Data Validation & Storage**

✅ **Validation before saving:**
- All metadata fields required (company, store, branch, date)
- At least 1 particular required
- Each item must have: description, item_price > 0, quantity > 0

✅ **Processing before DB:**
- All text uppercased
- Numbers formatted to 2 decimals
- Total calculated from price × quantity
- Client auto-created if doesn't exist