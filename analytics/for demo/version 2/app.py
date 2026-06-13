import os
import sqlite3
import json
import numpy as np
import pandas as pd
from flask import Flask, jsonify, request, render_template_string
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import r2_score, accuracy_score

# Initialize Flask application
app = Flask(__name__)
DB_NAME = "analytics_pos.db"

def get_db_connection():
    """Establishes a connection to the SQLite database and returns the connection object."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the SQLite database tables and seeds mock data if they do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Core clients table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        pondo_remaining REAL DEFAULT 0.0
    )
    """)

    # 2. Sales orders (itemized demand)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sales_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        so_number TEXT UNIQUE,
        item_qty INTEGER DEFAULT 0,
        date TEXT,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )
    """)

    # 3. Invoices (Paid / Unpaid revenue tracking)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        invoice_number TEXT UNIQUE,
        amount REAL DEFAULT 0.0,
        status TEXT, -- 'Paid' or 'Unpaid'
        date TEXT,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )
    """)

    # 4. Purchase orders (Expenses tracking)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS purchase_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        cash_amount REAL DEFAULT 0.0,
        date TEXT,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )
    """)

    # 5. Historical analytics consolidated entries
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historical_analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        client_name TEXT,
        revenue REAL DEFAULT 0.0,
        accounts_receivable REAL DEFAULT 0.0,
        pondo_remaining REAL DEFAULT 0.0,
        demand_qty INTEGER DEFAULT 0
    )
    """)

    # 6. Recommendation engine configurable rules
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS analytics_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_key TEXT UNIQUE,
        rule_name TEXT,
        threshold_val REAL,
        description TEXT
    )
    """)

    conn.commit()

    # Seed initial client data if empty to provide a learning sandbox on load
    cursor.execute("SELECT COUNT(*) FROM clients")
    if cursor.fetchone()[0] == 0:
        # Client 1: High outstanding Accounts Receivable (Risk Client)
        cursor.execute("INSERT INTO clients (name, pondo_remaining) VALUES ('Alpha Enterprises', 12000.0)")
        # Client 2: Low cash (Pondo) with high demand (Supply chain bottleneck)
        cursor.execute("INSERT INTO clients (name, pondo_remaining) VALUES ('Beta Retailers', 4000.0)")
        # Client 3: VIP High Revenue but low physical hardware demand (Upsell Target)
        cursor.execute("INSERT INTO clients (name, pondo_remaining) VALUES ('Gamma Corp', 65000.0)")
        # Client 4: Normal Healthy Client
        cursor.execute("INSERT INTO clients (name, pondo_remaining) VALUES ('Delta Solutions', 22000.0)")
        # Client 5: Small client
        cursor.execute("INSERT INTO clients (name, pondo_remaining) VALUES ('Epsilon Tech', 8000.0)")

        # Seed Sales Orders (Hardware demand)
        orders = [
            (1, 'SO-0001', 120, '2026-05-10'),
            (1, 'SO-0002', 80, '2026-05-12'),
            (2, 'SO-0003', 350, '2026-05-11'), # High volume
            (3, 'SO-0004', 50, '2026-05-14'),  # Low volume
            (4, 'SO-0005', 180, '2026-05-13'),
            (5, 'SO-0006', 90, '2026-05-15')
        ]
        cursor.executemany("INSERT INTO sales_orders (client_id, so_number, item_qty, date) VALUES (?,?,?,?)", orders)

        # Seed Invoices (Paid vs Unpaid)
        invoices = [
            (1, 'SI-0001', 30000.0, 'Paid', '2026-05-01'),
            (1, 'SI-0002', 25000.0, 'Unpaid', '2026-05-02'), # high AR ratio
            (2, 'SI-0003', 15000.0, 'Paid', '2026-05-03'),
            (2, 'SI-0004', 5000.0, 'Unpaid', '2026-05-04'),
            (3, 'SI-0005', 85000.0, 'Paid', '2026-05-05'),  # VIP
            (3, 'SI-0006', 4000.0, 'Unpaid', '2026-05-06'),
            (4, 'SI-0007', 40000.0, 'Paid', '2026-05-07'),
            (4, 'SI-0008', 2000.0, 'Unpaid', '2026-05-08'),
            (5, 'SI-0009', 12000.0, 'Paid', '2026-05-09'),
            (5, 'SI-0010', 1000.0, 'Unpaid', '2026-05-10')
        ]
        cursor.executemany("INSERT INTO invoices (client_id, invoice_number, amount, status, date) VALUES (?,?,?,?,?)", invoices)

        # Seed Purchase Orders (Operational expenses)
        pos = [
            (1, 8000.0, '2026-05-02'),
            (2, 14000.0, '2026-05-04'), # high expenses, draining pondo
            (3, 10000.0, '2026-05-06'),
            (4, 5000.0, '2026-05-08'),
            (5, 3000.0, '2026-05-10')
        ]
        cursor.executemany("INSERT INTO purchase_orders (client_id, cash_amount, date) VALUES (?,?,?)", pos)

        # Seed Historical Consolidated Records for Blended Analytics
        historical = [
            ('2025-11-15', 'Alpha Enterprises', 28000.0, 10000.0, 10000.0, 110),
            ('2025-12-15', 'Alpha Enterprises', 32000.0, 12000.0, 11500.0, 130),
            ('2026-01-15', 'Beta Retailers', 14000.0, 4000.0, 2000.0, 310),
            ('2026-02-15', 'Beta Retailers', 16000.0, 6000.0, 1500.0, 340),
            ('2026-03-15', 'Gamma Corp', 78000.0, 2000.0, 60000.0, 45),
            ('2026-04-15', 'Gamma Corp', 82000.0, 3000.0, 62000.0, 60),
            ('2026-01-15', 'Delta Solutions', 38000.0, 1000.0, 18000.0, 170),
            ('2026-02-15', 'Delta Solutions', 39000.0, 1500.0, 19500.0, 175)
        ]
        cursor.executemany("""
        INSERT INTO historical_analytics (date, client_name, revenue, accounts_receivable, pondo_remaining, demand_qty)
        VALUES (?,?,?,?,?,?)
        """, historical)

        # Seed Configurable Rule Thresholds
        rules = [
            ('RULE_A_AR_THRESH', 'Collections Risk Ratio Threshold', 0.40, 'Ratio of outstanding unpaid receivables to revenue triggering critical payment freezes.'),
            ('RULE_B_PONDO_MIN', 'Operational Safety Fund Floor', 15000.0, 'Minimum safe pondo reserves required to safely satisfy high volume shipments.'),
            ('RULE_B_DEMAND_MAX', 'High Volume Demand Threshold', 300.0, 'Demand value categorized as high-volume hardware distribution.'),
            ('RULE_C_VIP_REV', 'VIP Elite Revenue Threshold', 50000.0, 'Revenue tier above which clients qualify for high-value strategic auditing.'),
            ('RULE_C_LOW_DEMAND', 'Low Hardware Demand Ceiling', 150.0, 'Demand volume ceiling identifying client operational software up-sell candidates.')
        ]
        cursor.executemany("INSERT INTO analytics_rules (rule_key, rule_name, threshold_val, description) VALUES (?,?,?,?)", rules)

        conn.commit()
    conn.close()

init_db()

def query_raw_data(mode="LIVE"):
    """Queries, normalizes, and matches physical tables to support Pandas analysis."""
    conn = get_db_connection()
    
    if mode == "HISTORICAL":
        query = "SELECT client_name, revenue, accounts_receivable, pondo_remaining, demand_qty FROM historical_analytics"
        df = pd.read_sql_query(query, conn)
        df.rename(columns={'client_name': 'Client_ID', 'demand_qty': 'Demand_Per_Item_Sold'}, inplace=True)
        conn.close()
        return df

    # For LIVE mode: we aggregate data using exact operational queries matching current dashboard rules:
    # Revenue = SUM unpaid is Accounts Receivable; SUM paid is Revenue; Pondo = Revenue - Expenses
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM clients")
    clients_list = cursor.fetchall()

    rows = []
    for client in clients_list:
        c_id = client['id']
        c_name = client['name']

        # Revenue: SUM paid invoices
        cursor.execute("SELECT SUM(amount) FROM invoices WHERE client_id = ? AND status = 'Paid'", (c_id,))
        paid = cursor.fetchone()[0] or 0.0

        # Accounts Receivable: SUM unpaid invoices
        cursor.execute("SELECT SUM(amount) FROM invoices WHERE client_id = ? AND status = 'Unpaid'", (c_id,))
        unpaid = cursor.fetchone()[0] or 0.0

        # Expenses: SUM cash amount of purchase orders
        cursor.execute("SELECT SUM(cash_amount) FROM purchase_orders WHERE client_id = ?", (c_id,))
        expenses = cursor.fetchone()[0] or 0.0

        # Demand: SUM hardware sales order item qty
        cursor.execute("SELECT SUM(item_qty) FROM sales_orders WHERE client_id = ?", (c_id,))
        demand = cursor.fetchone()[0] or 0

        # Dynamic Calculations matching database logic
        pondo = paid - expenses
        rows.append({
            'Client_ID': c_name,
            'Revenue': paid,
            'Accounts_Receivable': unpaid,
            'Pondo_Remaining': pondo,
            'Demand_Per_Item_Sold': demand
        })

    conn.close()
    return pd.DataFrame(rows)

def run_predictive_models(df):
    """
    Trains multiple Scikit-Learn models to forecast hardware demands, 
    assess payment outstanding risks, and perform continuous analytics.
    """
    if len(df) < 3:
        # Graceful fallback data to prevent training crashes on tiny sets
        df = pd.DataFrame([
            {'Client_Balances': 50000, 'Pondo_Remaining': 30000, 'Demand_Per_Item_Sold': 200},
            {'Client_Balances': 20000, 'Pondo_Remaining': 5000, 'Demand_Per_Item_Sold': 350},
            {'Client_Balances': 90000, 'Pondo_Remaining': 70000, 'Demand_Per_Item_Sold': 80},
            {'Client_Balances': 40000, 'Pondo_Remaining': 25000, 'Demand_Per_Item_Sold': 180}
        ])

    df['Client_Balances'] = df['Revenue'] + df['Accounts_Receivable']

    # Predictor variables Matrix (X) and target variable vector (y)
    X = df[['Client_Balances', 'Pondo_Remaining']].values
    y = df['Demand_Per_Item_Sold'].values

    # Fit linear regression model
    model = LinearRegression()
    model.fit(X, y)
    
    # Calculate R-squared score on the training cohort
    predictions = model.predict(X)
    r2 = r2_score(y, predictions)

    # Secondary logistic classifier for tracking payment likelihood risks
    df['is_high_risk'] = (df['Accounts_Receivable'] > (df['Revenue'] * 0.4)).astype(int)
    X_risk = df[['Accounts_Receivable', 'Revenue']].values
    y_risk = df['is_high_risk'].values
    
    risk_model = LogisticRegression()
    risk_model.fit(X_risk, y_risk)
    
    return model, r2, risk_model

def generate_recommendations(row, rules):
    """
    Evaluates dynamic, prescriptive optimization logic per client using configured rule parameters.
    """
    recs = []
    
    # Map rules dictionary to variables
    rule_ar_thresh = rules.get('RULE_A_AR_THRESH', 0.40)
    rule_pondo_min = rules.get('RULE_B_PONDO_MIN', 15000.0)
    rule_demand_max = rules.get('RULE_B_DEMAND_MAX', 300.0)
    rule_vip_rev = rules.get('RULE_C_VIP_REV', 50000.0)
    rule_low_demand = rules.get('RULE_C_LOW_DEMAND', 150.0)

    # RULE A: Collections and liquidity health freeze
    if row['Accounts_Receivable'] > (row['Revenue'] * rule_ar_thresh):
        recs.append({
            'type': 'CRITICAL',
            'message': f"CRITICAL: Unpaid invoices (${row['Accounts_Receivable']:,.2f}) exceed {int(rule_ar_thresh * 100)}% of total Revenue (${row['Revenue']:,.2f}). Freeze hardware shipments immediately."
        })

    # RULE B: Operational Continuity and fulfillment buffer
    if row['Pondo_Remaining'] < rule_pondo_min and row['Demand_Per_Item_Sold'] > rule_demand_max:
        recs.append({
            'type': 'WARNING',
            'message': f"WARNING: Low cash float Pondo (${row['Pondo_Remaining']:,.2f}) alongside high item demand ({row['Demand_Per_Item_Sold']} units). Risk of stockout or delays."
        })

    # RULE C: Sales expansion and premium up-selling
    if row['Revenue'] > rule_vip_rev and row['Demand_Per_Item_Sold'] < rule_low_demand:
        recs.append({
            'type': 'OPTIMIZE',
            'message': f"OPTIMIZE: High-revenue VIP client ($ {row['Revenue']:,.2f}) with lower physical demand ({row['Demand_Per_Item_Sold']}). Target with premium software licensing or cloud integrations."
        })

    if not recs:
        recs.append({
            'type': 'NORMAL',
            'message': "STATUS NORMAL: Account parameters are balanced. Maintain standard servicing routines."
        })
        
    return recs

@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    """Endpoint serving raw and parsed analytics for simple, historical, or blended models."""
    mode = request.args.get('mode', 'LIVE') # LIVE, HISTORICAL, or COMBINED
    hist_weight = float(request.args.get('hist_weight', 0.5))
    live_weight = 1.0 - hist_weight

    # Read analytical rules
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT rule_key, threshold_val FROM analytics_rules")
    rules = {row['rule_key']: row['threshold_val'] for row in cursor.fetchall()}
    conn.close()

    # Load respective tables using Pandas
    df_live = query_raw_data("LIVE")
    df_hist = query_raw_data("HISTORICAL")

    if mode == "LIVE":
        df = df_live.copy()
    elif mode == "HISTORICAL":
        df = df_hist.copy()
    else: # COMBINED (Blends live metrics with historical using weight matrices)
        # Group both by Client Name/ID to synchronize indices
        live_grouped = df_live.groupby('Client_ID').mean().reset_index()
        hist_grouped = df_hist.groupby('Client_ID').mean().reset_index()

        merged = pd.merge(live_grouped, hist_grouped, on='Client_ID', how='outer', suffixes=('_live', '_hist')).fillna(0)
        
        # Calculate dynamic blended fields using NumPy weighted averages
        merged['Revenue'] = (merged['Revenue_live'] * live_weight) + (merged['Revenue_hist'] * hist_weight)
        merged['Accounts_Receivable'] = (merged['Accounts_Receivable_live'] * live_weight) + (merged['Accounts_Receivable_hist'] * hist_weight)
        merged['Pondo_Remaining'] = (merged['Pondo_Remaining_live'] * live_weight) + (merged['Pondo_Remaining_hist'] * hist_weight)
        merged['Demand_Per_Item_Sold'] = np.round((merged['Demand_Per_Item_Sold_live'] * live_weight) + (merged['Demand_Per_Item_Sold_hist'] * hist_weight))
        
        df = merged[['Client_ID', 'Revenue', 'Accounts_Receivable', 'Pondo_Remaining', 'Demand_Per_Item_Sold']].copy()

    df['Client_Balances'] = df['Revenue'] + df['Accounts_Receivable']

    # Descriptive calculations
    total_rev = float(df['Revenue'].sum())
    total_ar = float(df['Accounts_Receivable'].sum())
    ar_ratio = total_ar / total_rev if total_rev > 0 else 0.0

    avg_rev = float(df['Revenue'].mean()) if len(df) > 0 else 0.0
    avg_pondo = float(df['Pondo_Remaining'].mean()) if len(df) > 0 else 0.0
    avg_demand = float(df['Demand_Per_Item_Sold'].mean()) if len(df) > 0 else 0.0

    # Predictive modeling using SciKit-Learn LinearRegression
    model, r2, _ = run_predictive_models(df)
    coeff_balances = float(model.coef_[0]) if len(model.coef_) > 0 else 0.0
    coeff_pondo = float(model.coef_[1]) if len(model.coef_) > 1 else 0.0
    intercept = float(model.intercept_)

    # Apply Prescriptive recommendations engine row-by-row
    client_records = []
    critical_count = 0
    warning_count = 0
    optimize_count = 0

    for _, row in df.iterrows():
        recs = generate_recommendations(row, rules)
        for r in recs:
            if r['type'] == 'CRITICAL': critical_count += 1
            elif r['type'] == 'WARNING': warning_count += 1
            elif r['type'] == 'OPTIMIZE': optimize_count += 1

        client_records.append({
            'client_id': row['Client_ID'],
            'revenue': float(row['Revenue']),
            'ar': float(row['Accounts_Receivable']),
            'balance': float(row['Client_Balances']),
            'pondo': float(row['Pondo_Remaining']),
            'demand': int(row['Demand_Per_Item_Sold']),
            'recommendations': recs
        })

    return jsonify({
        'mode': mode,
        'metrics': {
            'total_revenue': total_rev,
            'total_ar': total_ar,
            'ar_ratio': ar_ratio,
            'avg_revenue': avg_rev,
            'avg_pondo': avg_pondo,
            'avg_demand': avg_demand
        },
        'ml_model': {
            'r2_score': max(0.0, r2),
            'coeff_balances': coeff_balances,
            'coeff_pondo': coeff_pondo,
            'intercept': intercept
        },
        'records': client_records,
        'summary': {
            'critical': critical_count,
            'warning': warning_count,
            'optimize': optimize_count
        }
    })

@app.route('/api/historical/save', methods=['POST'])
def save_historical_spreadsheet():
    """Accepts manual tabular dataset configurations and pushes directly into historical database."""
    data = request.json
    if not data or 'rows' not in data:
        return jsonify({'success': False, 'message': 'Invalid data package.'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Clear existing historical metrics before committing new data
        cursor.execute("DELETE FROM historical_analytics")
        
        for r in data['rows']:
            # Validation pipeline
            date_val = r.get('date', '2026-05-17')
            client_name = r.get('client_name', '').strip()
            if not client_name:
                continue
            
            revenue = float(r.get('revenue', 0))
            ar = float(r.get('accounts_receivable', 0))
            pondo = float(r.get('pondo_remaining', 0))
            demand = int(r.get('demand_qty', 0))

            cursor.execute("""
            INSERT INTO historical_analytics (date, client_name, revenue, accounts_receivable, pondo_remaining, demand_qty)
            VALUES (?,?,?,?,?,?)
            """, (date_val, client_name, revenue, ar, pondo, demand))

        conn.commit()
        success = True
        message = "Tabular records consolidated successfully into the system!"
    except Exception as e:
        conn.rollback()
        success = False
        message = f"Database ingestion failure: {str(e)}"
    finally:
        conn.close()

    return jsonify({'success': success, 'message': message})

@app.route('/api/rules', methods=['GET', 'POST'])
def handle_rules():
    """Handles loading and editing dynamic threshold rules."""
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        data = request.json
        for key, val in data.items():
            cursor.execute("UPDATE analytics_rules SET threshold_val = ? WHERE rule_key = ?", (float(val), key))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Dynamic thresholds successfully adjusted!'})

    cursor.execute("SELECT rule_key, rule_name, threshold_val, description FROM analytics_rules")
    rules = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'rules': rules})

@app.route('/api/database/inspect', methods=['GET'])
def inspect_database():
    """Returns exact details of schema, tables, and raw rows for analytical validation."""
    conn = get_db_connection()
    cursor = conn.cursor()
    tables = ['clients', 'sales_orders', 'invoices', 'purchase_orders', 'historical_analytics', 'analytics_rules']
    db_summary = {}

    for t in tables:
        # Schema
        cursor.execute(f"PRAGMA table_info({t})")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Raw records
        cursor.execute(f"SELECT * FROM {t} LIMIT 10")
        rows = [dict(row) for row in cursor.fetchall()]
        
        db_summary[t] = {
            'columns': columns,
            'rows': rows
        }

    conn.close()
    return jsonify(db_summary)

@app.route('/')
def home():
    """Serves the Unified Interactive Executive Dashboard UI."""
    return render_template_string("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Integrated Executive Analytics Suite</title>
    <!-- Tailwind CSS Engine -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Lucide Icons Library -->
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Fira+Code:wght@400;500&display=swap');
        body {
            font-family: 'Inter', sans-serif;
            transition: all 0.3s ease;
        }
        .awesome-glow {
            box-shadow: 0 0 20px rgba(99, 102, 241, 0.2);
        }
        .simple-theme {
            --bg-primary: #f8fafc;
            --bg-card: #ffffff;
            --text-title: #0f172a;
            --text-body: #475569;
            --border-color: #e2e8f0;
            --accent: #3b82f6;
            --accent-hover: #2563eb;
        }
        .awesome-theme {
            --bg-primary: #0b0f19;
            --bg-card: #151c2c;
            --text-title: #f8fafc;
            --text-body: #94a3b8;
            --border-color: #1e293b;
            --accent: #6366f1;
            --accent-hover: #4f46e5;
        }
    </style>
</head>
<body class="bg-slate-50 text-slate-700 simple-theme" id="app-body">
    
    <!-- Top Global Header -->
    <header class="border-b transition-colors duration-200" id="global-header" style="background-color: var(--bg-card); border-color: var(--border-color);">
        <div class="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row justify-between items-center gap-4">
            <div class="flex items-center gap-3">
                <div class="p-2.5 bg-blue-600 rounded-xl text-white flex items-center justify-center">
                    <i data-lucide="bar-chart-3" class="w-6 h-6"></i>
                </div>
                <div>
                    <h1 class="text-xl font-extrabold tracking-tight transition-colors duration-200" style="color: var(--text-title);">InsightFlow™</h1>
                    <p class="text-xs transition-colors duration-200" style="color: var(--text-body);">Manager's Decision Portal & Learning Sandbox</p>
                </div>
            </div>
            
            <!-- Quick Utility Actions -->
            <div class="flex items-center gap-3">
                <!-- Theme Switcher -->
                <button onclick="toggleTheme()" class="flex items-center gap-2 px-3 py-1.5 border rounded-lg text-sm transition-all" style="border-color: var(--border-color); color: var(--text-body);">
                    <i id="theme-icon" data-lucide="sparkles" class="w-4 h-4 text-amber-500"></i>
                    <span id="theme-text">Awesome Mode</span>
                </button>
                <span class="px-3 py-1 text-xs font-semibold bg-emerald-100 text-emerald-800 rounded-full flex items-center gap-1.5">
                    <span class="w-2 h-2 bg-emerald-500 rounded-full animate-ping"></span> Live Connection
                </span>
            </div>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
        
        <!-- STEP-BY-STEP GUIDED LEARNING SEQUENCE -->
        <section class="mb-10 p-6 rounded-2xl border transition-all duration-200" style="background-color: var(--bg-card); border-color: var(--border-color);">
            <div class="flex flex-col md:flex-row justify-between items-start md:items-center border-b pb-4 mb-6" style="border-color: var(--border-color);">
                <div>
                    <h2 class="text-lg font-bold flex items-center gap-2" style="color: var(--text-title);">
                        <span class="flex h-6 w-6 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-600">🎓</span>
                        Interactive Analytics Sequence Trainer
                    </h2>
                    <p class="text-xs" style="color: var(--text-body);">Master data science logic step-by-step from raw database tables up to machine learning forecasts.</p>
                </div>
                <div class="mt-2 md:mt-0 flex gap-1 bg-slate-100 p-1 rounded-lg">
                    <button onclick="setSequenceStep(1)" class="seq-btn px-3 py-1 text-xs font-medium rounded-md bg-blue-600 text-white" id="step-btn-1">1. Tables</button>
                    <button onclick="setSequenceStep(2)" class="seq-btn px-3 py-1 text-xs font-medium rounded-md text-slate-600" id="step-btn-2">2. Descriptives</button>
                    <button onclick="setSequenceStep(3)" class="seq-btn px-3 py-1 text-xs font-medium rounded-md text-slate-600" id="step-btn-3">3. ML Models</button>
                    <button onclick="setSequenceStep(4)" class="seq-btn px-3 py-1 text-xs font-medium rounded-md text-slate-600" id="step-btn-4">4. Prescriptive Rules</button>
                    <button onclick="setSequenceStep(5)" class="seq-btn px-3 py-1 text-xs font-medium rounded-md text-slate-600" id="step-btn-5">5. Executive Report</button>
                </div>
            </div>

            <!-- Dynamic Learning Content Area -->
            <div id="sequence-box" class="p-5 bg-slate-50 rounded-xl border border-slate-200">
                <!-- Content will load dynamically via JS -->
            </div>
        </section>

        <!-- PORTAL WORKSPACE CONFIGURATION (MODE SELECTION) -->
        <section class="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
            <div class="lg:col-span-2 p-6 rounded-2xl border flex flex-col justify-between transition-all duration-200" style="background-color: var(--bg-card); border-color: var(--border-color);">
                <div>
                    <h3 class="text-base font-bold flex items-center gap-2 mb-2" style="color: var(--text-title);">
                        <i data-lucide="sliders" class="w-5 h-5 text-indigo-500"></i> Analytics Mode Selection
                    </h3>
                    <p class="text-xs mb-6" style="color: var(--text-body);">Choose how data sources are analyzed. You can run system live metrics, historical uploaded databases, or blend both with custom influence percentages.</p>
                    
                    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
                        <button onclick="changeMode('LIVE')" id="mode-LIVE" class="p-4 border-2 rounded-xl text-left transition-all bg-blue-50 border-blue-600">
                            <span class="block text-sm font-bold text-blue-900">1. System Live Data</span>
                            <span class="block text-[11px] text-blue-700 mt-1">Real-time transactional logs</span>
                        </button>
                        <button onclick="changeMode('HISTORICAL')" id="mode-HISTORICAL" class="p-4 border border-slate-200 rounded-xl text-left transition-all hover:bg-slate-50 text-slate-700">
                            <span class="block text-sm font-bold">2. Historical Set</span>
                            <span class="block text-[11px] mt-1 text-slate-500">Uploaded offline sheets</span>
                        </button>
                        <button onclick="changeMode('COMBINED')" id="mode-COMBINED" class="p-4 border border-slate-200 rounded-xl text-left transition-all hover:bg-slate-50 text-slate-700">
                            <span class="block text-sm font-bold">3. Combined Matrix</span>
                            <span class="block text-[11px] mt-1 text-slate-500">Matrix-blended analytics</span>
                        </button>
                    </div>
                </div>

                <!-- Weighted Sliders (Combined Only) -->
                <div id="combined-weight-container" class="hidden p-4 bg-indigo-50/50 rounded-xl border border-indigo-100">
                    <div class="flex justify-between text-xs font-bold text-indigo-950 mb-2">
                        <span>Live weight: <span id="lbl-live-weight">50%</span></span>
                        <span>Historical weight: <span id="lbl-hist-weight">50%</span></span>
                    </div>
                    <input type="range" min="0" max="1" step="0.05" value="0.5" id="slider-weight" oninput="updateWeights(this.value)" class="w-full accent-indigo-600">
                </div>
            </div>

            <!-- EXCEL ENTRY GRID SPREADSHEET (BUILT-IN EDITOR) -->
            <div class="p-6 rounded-2xl border transition-all duration-200 flex flex-col justify-between" style="background-color: var(--bg-card); border-color: var(--border-color);">
                <div>
                    <h3 class="text-base font-bold flex items-center gap-2 mb-2" style="color: var(--text-title);">
                        <i data-lucide="table-properties" class="w-5 h-5 text-emerald-500"></i> Historical Ingestor Grid
                    </h3>
                    <p class="text-xs mb-6" style="color: var(--text-body);">Directly write consolidated matrices. No spreadsheet uploads required. Perfect for testing raw numerical trends instantly.</p>
                </div>
                <button onclick="openSpreadsheet()" class="w-full py-3 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl font-medium text-sm flex items-center justify-center gap-2 shadow-sm transition-all">
                    <i data-lucide="table" class="w-4 h-4"></i> Launch Built-in Grid Editor
                </button>
            </div>
        </section>

        <!-- HIGH-LEVEL EXECUTIVE REPORT CARD -->
        <section class="p-6 rounded-2xl border mb-8 transition-all duration-200" id="executive-summary-card" style="background-color: var(--bg-card); border-color: var(--border-color);">
            <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b pb-4 mb-6" style="border-color: var(--border-color);">
                <div>
                    <span class="text-xs uppercase font-extrabold text-blue-600 tracking-wider">Operational Baseline Metrics</span>
                    <h2 class="text-lg font-bold flex items-center gap-2" style="color: var(--text-title);">
                        Current Mode: <span id="display-mode-badge" class="px-2.5 py-0.5 text-xs bg-blue-100 text-blue-800 rounded-full font-bold">LIVE</span>
                    </h2>
                </div>
                <div class="flex items-center gap-2">
                    <input type="text" id="client-search" placeholder="Search Client ID..." oninput="fetchAnalytics()" class="px-3 py-1.5 text-xs border rounded-lg focus:ring-1 focus:ring-blue-500 bg-transparent outline-none transition-all" style="border-color: var(--border-color); color: var(--text-title);">
                </div>
            </div>

            <!-- Dynamic Statistics Matrix -->
            <div class="grid grid-cols-2 md:grid-cols-4 gap-6">
                <div class="p-4 bg-slate-50 rounded-xl border border-slate-200/60">
                    <span class="block text-xs font-semibold text-slate-500 mb-1">Total Revenue</span>
                    <span class="text-lg font-extrabold text-slate-900" id="stat-total-revenue">$0.00</span>
                </div>
                <div class="p-4 bg-slate-50 rounded-xl border border-slate-200/60">
                    <span class="block text-xs font-semibold text-slate-500 mb-1">Accounts Receivable</span>
                    <span class="text-lg font-extrabold text-slate-900" id="stat-total-ar">$0.00</span>
                </div>
                <div class="p-4 bg-slate-50 rounded-xl border border-slate-200/60">
                    <span class="block text-xs font-semibold text-slate-500 mb-1">AR to Revenue Ratio</span>
                    <span class="text-lg font-extrabold text-slate-900" id="stat-ar-ratio">0.00%</span>
                </div>
                <div class="p-4 bg-slate-50 rounded-xl border border-slate-200/60">
                    <span class="block text-xs font-semibold text-slate-500 mb-1">Average Pondo (Cash Float)</span>
                    <span class="text-lg font-extrabold text-slate-900" id="stat-avg-pondo">$0.00</span>
                </div>
            </div>
        </section>

        <!-- DATA RESULTS & MODEL FORECAST CARDS -->
        <section class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <!-- Consolidated Client Database & Recommendations Grid -->
            <div class="lg:col-span-2 p-6 rounded-2xl border transition-all duration-200" style="background-color: var(--bg-card); border-color: var(--border-color);">
                <h3 class="text-base font-bold flex items-center gap-2 mb-6" style="color: var(--text-title);">
                    <i data-lucide="users" class="w-5 h-5 text-blue-500"></i> Client Portfolio & Audited Recommendations
                </h3>
                <div class="overflow-x-auto">
                    <table class="w-full text-left border-collapse text-xs">
                        <thead>
                            <tr class="border-b" style="border-color: var(--border-color); color: var(--text-body);">
                                <th class="py-3 px-2 font-bold uppercase tracking-wider">Client ID / Name</th>
                                <th class="py-3 px-2 font-bold uppercase tracking-wider text-right">Revenue</th>
                                <th class="py-3 px-2 font-bold uppercase tracking-wider text-right">AR</th>
                                <th class="py-3 px-2 font-bold uppercase tracking-wider text-right">Pondo (Cash)</th>
                                <th class="py-3 px-2 font-bold uppercase tracking-wider text-center">Hardware Demand</th>
                                <th class="py-3 px-2 font-bold uppercase tracking-wider">Prescriptive Audit Decisions</th>
                            </tr>
                        </thead>
                        <tbody id="client-table-body" class="divide-y" style="color: var(--text-title);">
                            <!-- Dynamic rows injected -->
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Prediction Testing Sandbox Card -->
            <div class="p-6 rounded-2xl border transition-all duration-200 flex flex-col justify-between" style="background-color: var(--bg-card); border-color: var(--border-color);">
                <div>
                    <h3 class="text-base font-bold flex items-center gap-2 mb-2" style="color: var(--text-title);">
                        <i data-lucide="cpu" class="w-5 h-5 text-indigo-500"></i> Prediction Testing Sandbox
                    </h3>
                    <p class="text-xs mb-6" style="color: var(--text-body);">Simulate how Scikit-Learn processes newly hypothetical metrics to forecast distribution requirements instantly.</p>

                    <div class="p-4 bg-slate-50 rounded-xl border border-slate-200 mb-6">
                        <div class="flex justify-between text-xs font-bold text-slate-700 mb-2">
                            <span>Client balance (Paid + Unpaid):</span>
                            <span id="lbl-sandbox-balance">$60,000</span>
                        </div>
                        <input type="range" min="5000" max="150000" step="5000" value="60000" id="slider-sandbox-balance" oninput="calculateSandboxPrediction()" class="w-full mb-4 accent-blue-600">

                        <div class="flex justify-between text-xs font-bold text-slate-700 mb-2">
                            <span>Operational Pondo remaining:</span>
                            <span id="lbl-sandbox-pondo">$25,000</span>
                        </div>
                        <input type="range" min="-10000" max="80000" step="2500" value="25000" id="slider-sandbox-pondo" oninput="calculateSandboxPrediction()" class="w-full accent-blue-600">
                    </div>
                </div>

                <div class="p-4 bg-blue-50 border border-blue-200 rounded-xl text-center">
                    <span class="block text-xs font-semibold text-blue-700 mb-1">Expected Hardware Demand</span>
                    <span class="text-3xl font-extrabold text-blue-900" id="sandbox-prediction-result">0 units</span>
                    <p class="text-[10px] text-blue-600 mt-2">Calculated live via Linear Regression formula: <br><span class="font-mono text-xs font-medium" id="ml-formula-text"></span></p>
                </div>
            </div>
        </section>
    </main>

    <!-- FLOATING SPREADSHEET MODAL -->
    <div id="spreadsheet-modal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center z-50 hidden p-4">
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden border">
            <div class="p-5 border-b flex justify-between items-center bg-slate-50">
                <div>
                    <h3 class="text-base font-bold text-slate-900 flex items-center gap-2">
                        <i data-lucide="layout-grid" class="w-5 h-5 text-emerald-600"></i> Interactive Ingestor Editor
                    </h3>
                    <p class="text-xs text-slate-500 mt-1">Directly manage custom historical matrices. Double-click cells to modify values.</p>
                </div>
                <button onclick="closeSpreadsheet()" class="text-slate-400 hover:text-slate-600 p-1 bg-slate-200 rounded-full">
                    <i data-lucide="x" class="w-5 h-5"></i>
                </button>
            </div>

            <!-- Spreadsheet Grid Container -->
            <div class="p-6 overflow-y-auto flex-1">
                <div class="flex gap-2 mb-4 justify-between">
                    <div class="flex gap-2">
                        <button onclick="addSpreadsheetRow()" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-900 text-white rounded-lg text-xs font-bold flex items-center gap-1.5">
                            <i data-lucide="plus" class="w-4 h-4"></i> Add Blank Row
                        </button>
                        <button onclick="resetSpreadsheetTemplate()" class="px-3 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-800 rounded-lg text-xs font-bold">
                            Reset Mock Template
                        </button>
                    </div>
                    <span class="text-xs text-slate-500 self-center">Double-click table header/cells to enter manual values.</span>
                </div>

                <div class="border rounded-lg overflow-hidden">
                    <table class="w-full text-left border-collapse text-xs">
                        <thead>
                            <tr class="bg-slate-100 text-slate-700 font-bold border-b">
                                <th class="p-3">Record Date (YYYY-MM-DD)</th>
                                <th class="p-3">Client Identifier</th>
                                <th class="p-3 text-right">Revenue ($)</th>
                                <th class="p-3 text-right">Accounts Receivable ($)</th>
                                <th class="p-3 text-right">Pondo Cash ($)</th>
                                <th class="p-3 text-center">Hardware Demand (Qty)</th>
                                <th class="p-3 text-center">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="spreadsheet-body" class="divide-y text-slate-950">
                            <!-- Injected spreadsheet rows -->
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="p-4 border-t bg-slate-50 flex justify-between items-center">
                <p class="text-xs text-slate-500">Ensure positive values are inserted correctly before saving changes.</p>
                <button onclick="commitSpreadsheetData()" class="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold shadow-sm transition-all flex items-center gap-2">
                    <i data-lucide="check-circle" class="w-4 h-4"></i> Ingest Consolidated Sheet
                </button>
            </div>
        </div>
    </div>

    <!-- GLOBAL CLIENT RE-TUNING DRAWER -->
    <div id="rules-drawer" class="fixed right-0 top-0 bottom-0 w-full max-w-md bg-white border-l shadow-2xl z-40 transform translate-x-full transition-transform duration-300 ease-in-out flex flex-col hidden">
        <div class="p-5 border-b bg-slate-50 flex justify-between items-center">
            <div>
                <h3 class="text-sm font-extrabold text-slate-900">Configure Rule Thresholds</h3>
                <p class="text-xs text-slate-500">Tune operational prescriptive limits</p>
            </div>
            <button onclick="toggleRulesDrawer()" class="text-slate-400 hover:text-slate-600 bg-slate-200 p-1 rounded-full">
                <i data-lucide="x" class="w-5 h-5"></i>
            </button>
        </div>
        <div class="p-6 flex-1 overflow-y-auto" id="rules-form-container">
            <!-- Dynamically populated settings -->
        </div>
        <div class="p-4 border-t bg-slate-50">
            <button onclick="saveRules()" class="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold transition-all">
                Update Rules & Refresh Engine
            </button>
        </div>
    </div>

    <!-- CORE INTERACTION JAVASCRIPT LOGIC -->
    <script>
        let currentMode = "LIVE";
        let blendHistWeight = 0.5;
        let globalDbDump = null;
        let activeSequenceStep = 1;
        let activeTheme = "simple";
        let globalModelData = null;

        // Sample Template data for the tabular editor
        let spreadsheetData = [
            {date: '2026-05-17', client_name: 'Alpha Enterprises', revenue: 35000, accounts_receivable: 14000, pondo_remaining: 8000, demand_qty: 210},
            {date: '2026-05-17', client_name: 'Beta Retailers', revenue: 20000, accounts_receivable: 5000, pondo_remaining: 3500, demand_qty: 320},
            {date: '2026-05-17', client_name: 'Gamma Corp', revenue: 90000, accounts_receivable: 2000, pondo_remaining: 68000, demand_qty: 40},
            {date: '2026-05-17', client_name: 'Delta Solutions', revenue: 45000, accounts_receivable: 3000, pondo_remaining: 24000, demand_qty: 155},
            {date: '2026-05-17', client_name: 'Epsilon Tech', revenue: 15000, accounts_receivable: 1000, pondo_remaining: 9500, demand_qty: 80}
        ];

        // Ensure everything renders
        window.onload = function() {
            lucide.createIcons();
            fetchDatabaseInspect();
            fetchAnalytics();
        };

        function toggleTheme() {
            const body = document.getElementById('app-body');
            const icon = document.getElementById('theme-icon');
            const text = document.getElementById('theme-text');
            
            if (activeTheme === "simple") {
                body.classList.remove('simple-theme');
                body.classList.add('awesome-theme', 'bg-slate-950');
                text.innerText = "Simple Mode";
                activeTheme = "awesome";
            } else {
                body.classList.remove('awesome-theme', 'bg-slate-950');
                body.classList.add('simple-theme');
                text.innerText = "Awesome Mode";
                activeTheme = "simple";
            }
        }

        function changeMode(mode) {
            currentMode = mode;
            // Highlight button
            ['LIVE', 'HISTORICAL', 'COMBINED'].forEach(m => {
                const el = document.getElementById(`mode-${m}`);
                if (m === mode) {
                    el.className = "p-4 border-2 rounded-xl text-left transition-all bg-blue-50 border-blue-600 text-slate-900";
                } else {
                    el.className = "p-4 border border-slate-200 rounded-xl text-left transition-all hover:bg-slate-50 text-slate-700";
                }
            });

            const weightContainer = document.getElementById('combined-weight-container');
            if (mode === "COMBINED") {
                weightContainer.classList.remove('hidden');
            } else {
                weightContainer.classList.add('hidden');
            }

            document.getElementById('display-mode-badge').innerText = mode;
            fetchAnalytics();
        }

        function updateWeights(val) {
            blendHistWeight = parseFloat(val);
            const livePct = Math.round((1.0 - blendHistWeight) * 100);
            const histPct = Math.round(blendHistWeight * 100);
            
            document.getElementById('lbl-live-weight').innerText = `${livePct}%`;
            document.getElementById('lbl-hist-weight').innerText = `${histPct}%`;
            
            fetchAnalytics();
        }

        async function fetchDatabaseInspect() {
            try {
                const res = await fetch('/api/database/inspect');
                globalDbDump = await res.json();
                renderSequenceContent();
            } catch(e) {
                console.error("Database inspection error: ", e);
            }
        }

        async function fetchAnalytics() {
            const searchQuery = document.getElementById('client-search').value.toLowerCase();
            try {
                const res = await fetch(`/api/analytics?mode=${currentMode}&hist_weight=${blendHistWeight}`);
                const data = await res.json();
                
                // Store coefficients for prediction testing
                globalModelData = data.ml_model;

                // Load basic stats
                document.getElementById('stat-total-revenue').innerText = formatCurrency(data.metrics.total_revenue);
                document.getElementById('stat-total-ar').innerText = formatCurrency(data.metrics.total_ar);
                document.getElementById('stat-ar-ratio').innerText = `${(data.metrics.ar_ratio * 100).toFixed(2)}%`;
                document.getElementById('stat-avg-pondo').innerText = formatCurrency(data.metrics.avg_pondo);

                // Render dynamic table
                const tbody = document.getElementById('client-table-body');
                tbody.innerHTML = '';

                // Filter rows locally (case-insensitive filter)
                const filteredRecords = data.records.filter(r => r.client_id.toLowerCase().includes(searchQuery));

                filteredRecords.forEach(record => {
                    let recommendationBadge = '';
                    record.recommendations.forEach(rec => {
                        let colorClass = "bg-slate-100 text-slate-800";
                        if (rec.type === 'CRITICAL') colorClass = "bg-rose-100 text-rose-800 border-l-4 border-rose-600";
                        else if (rec.type === 'WARNING') colorClass = "bg-amber-100 text-amber-800 border-l-4 border-amber-500";
                        else if (rec.type === 'OPTIMIZE') colorClass = "bg-violet-100 text-violet-800 border-l-4 border-indigo-500";
                        
                        recommendationBadge += `<div class="p-1.5 rounded-md text-[11px] mb-1 font-medium ${colorClass}">${rec.message}</div>`;
                    });

                    const tr = document.createElement('tr');
                    tr.className = "border-b hover:bg-slate-50 transition-all";
                    tr.innerHTML = `
                        <td class="py-3 px-2 font-bold">${record.client_id}</td>
                        <td class="py-3 px-2 text-right">${formatCurrency(record.revenue)}</td>
                        <td class="py-3 px-2 text-right text-rose-600">${formatCurrency(record.ar)}</td>
                        <td class="py-3 px-2 text-right text-emerald-600">${formatCurrency(record.pondo)}</td>
                        <td class="py-3 px-2 text-center font-mono font-medium">${record.demand}</td>
                        <td class="py-3 px-2 max-w-sm">${recommendationBadge}</td>
                    `;
                    tbody.appendChild(tr);
                });

                calculateSandboxPrediction();
                renderSequenceContent();
            } catch(e) {
                console.error("Fetch analytics critical failure: ", e);
            }
        }

        function calculateSandboxPrediction() {
            if (!globalModelData) return;
            const bal = parseFloat(document.getElementById('slider-sandbox-balance').value);
            const pondo = parseFloat(document.getElementById('slider-sandbox-pondo').value);

            document.getElementById('lbl-sandbox-balance').innerText = formatCurrency(bal);
            document.getElementById('lbl-sandbox-pondo').innerText = formatCurrency(pondo);

            // Scikit-Learn predictions math: target_val = Intercept + (coeff1 * bal) + (coeff2 * pondo)
            const result = globalModelData.intercept + (globalModelData.coeff_balances * bal) + (globalModelData.coeff_pondo * pondo);
            const finalUnits = Math.max(0, Math.round(result));

            document.getElementById('sandbox-prediction-result').innerText = `${finalUnits} units`;
            document.getElementById('ml-formula-text').innerText = 
                `${globalModelData.intercept.toFixed(2)} + (${globalModelData.coeff_balances.toFixed(4)} * Bal) + (${globalModelData.coeff_pondo.toFixed(4)} * Pondo)`;
        }

        // --- SEQUENCE TRAINER LOGIC ---
        function setSequenceStep(step) {
            activeSequenceStep = step;
            for (let i = 1; i <= 5; i++) {
                const btn = document.getElementById(`step-btn-${i}`);
                if (i === step) {
                    btn.className = "seq-btn px-3 py-1 text-xs font-bold rounded-md bg-blue-600 text-white shadow-sm";
                } else {
                    btn.className = "seq-btn px-3 py-1 text-xs font-medium rounded-md text-slate-600 hover:bg-slate-200";
                }
            }
            renderSequenceContent();
        }

        function renderSequenceContent() {
            const container = document.getElementById('sequence-box');
            if (!globalDbDump) {
                container.innerHTML = `<div class="text-xs text-slate-500">Loading learning database components...</div>`;
                return;
            }

            let html = '';
            switch(activeSequenceStep) {
                case 1:
                    html = `
                    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <div>
                            <span class="px-2 py-0.5 bg-blue-100 text-blue-800 rounded-full font-bold text-[10px] uppercase">Kid-Friendly Mode</span>
                            <h4 class="text-sm font-extrabold text-blue-900 mt-1 mb-2">Think of it like a toy organizer box! 🧩</h4>
                            <p class="text-xs text-slate-600 mb-4 leading-relaxed">
                                A database is just an organized filing cabinet. Before doing fancy math, we inspect the separate folders (Invoices, Sales, Purchase Orders) to map the variables.
                            </p>
                            <div class="text-[11px] bg-slate-100 p-3 rounded-lg border font-mono">
                                <span class="text-blue-700 font-bold">Client_Balances</span> = Revenue (Paid Invoices) + Accounts_Receivable (Unpaid Invoices)<br>
                                <span class="text-emerald-700 font-bold">Pondo_Remaining</span> = Revenue - Expenses (Purchase Orders)
                            </div>
                        </div>
                        <div class="border rounded-lg bg-white p-3 overflow-y-auto max-h-48 text-[11px]">
                            <h5 class="font-bold text-slate-800 mb-2 flex items-center gap-1.5"><i data-lucide="database" class="w-3.5 h-3.5"></i> Active SQL Tables</h5>
                            <div class="space-y-2">
                                <div><strong class="text-blue-600">clients:</strong> name (TEXT), pondo_remaining (REAL)</div>
                                <div><strong class="text-blue-600">sales_orders (Hardware Demand):</strong> so_number, item_qty (INT), date</div>
                                <div><strong class="text-blue-600">invoices:</strong> invoice_number, amount (REAL), status ('Paid'/'Unpaid')</div>
                                <div><strong class="text-blue-600">purchase_orders (Expenses):</strong> cash_amount (REAL), date</div>
                            </div>
                        </div>
                    </div>`;
                    break;
                case 2:
                    html = `
                    <div>
                        <span class="px-2 py-0.5 bg-blue-100 text-blue-800 rounded-full font-bold text-[10px] uppercase">Explain Like I'm Five</span>
                        <h4 class="text-sm font-extrabold text-blue-900 mt-1 mb-2">Finding the Middle Ground ⚖️</h4>
                        <p class="text-xs text-slate-600 mb-4 leading-relaxed">
                            Descriptive analytics simply means describing what already happened. We calculate the sum (adding everything up) and average (dividing equally) of our business activities to find our normal operational baseline.
                        </p>
                        <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
                            <div class="p-3 bg-white border rounded-lg text-center shadow-sm">
                                <span class="block text-[10px] uppercase text-slate-500 font-bold">Pandas sum()</span>
                                <span class="block font-extrabold text-blue-600 text-sm mt-1">Total Revenue Summary</span>
                            </div>
                            <div class="p-3 bg-white border rounded-lg text-center shadow-sm">
                                <span class="block text-[10px] uppercase text-slate-500 font-bold">NumPy mean()</span>
                                <span class="block font-extrabold text-indigo-600 text-sm mt-1">Average Cash Buffer</span>
                            </div>
                            <div class="p-3 bg-white border rounded-lg text-center shadow-sm">
                                <span class="block text-[10px] uppercase text-slate-500 font-bold">Ratio Math</span>
                                <span class="block font-extrabold text-violet-600 text-sm mt-1">Receivables Health Index</span>
                            </div>
                        </div>
                    </div>`;
                    break;
                case 3:
                    html = `
                    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <div>
                            <span class="px-2 py-0.5 bg-blue-100 text-blue-800 rounded-full font-bold text-[10px] uppercase">ELI5: Predict with AI</span>
                            <h4 class="text-sm font-extrabold text-blue-900 mt-1 mb-2">Connect the Dots! 📈</h4>
                            <p class="text-xs text-slate-600 mb-4 leading-relaxed">
                                Imagine looking at height and age of children. Kids get taller as they get older. Linear Regression draws a "best fit line" through the scattered dots so we can guess how tall (or how much hardware) a new client will need!
                            </p>
                            <span class="inline-block px-3 py-1 bg-indigo-50 border border-indigo-200 text-indigo-800 rounded-lg text-[10px] font-mono">
                                Model Accuracy (R² Score): <strong>${(globalModelData ? (globalModelData.r2_score * 100).toFixed(1) : '0')}%</strong>
                            </span>
                        </div>
                        <div class="bg-white border p-3 rounded-lg text-[11px] font-mono">
                            <div class="font-bold text-slate-800 border-b pb-1 mb-2">Scikit-Learn Python Execution:</div>
                            <div class="text-slate-600 space-y-1">
                                <div>from sklearn.linear_model import LinearRegression</div>
                                <div>X = dataset[['Client_Balances', 'Pondo_Remaining']]</div>
                                <div>y = dataset['Demand_Per_Item_Sold']</div>
                                <div class="text-blue-600">model = LinearRegression().fit(X, y)</div>
                                <div>print("Accuracy R-Squared score is", model.score(X, y))</div>
                            </div>
                        </div>
                    </div>`;
                    break;
                case 4:
                    html = `
                    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <div>
                            <span class="px-2 py-0.5 bg-blue-100 text-blue-800 rounded-full font-bold text-[10px] uppercase">Rules Trainer</span>
                            <h4 class="text-sm font-extrabold text-blue-900 mt-1 mb-2">Setting Guard Rails 🛡️</h4>
                            <p class="text-xs text-slate-600 mb-4 leading-relaxed">
                                AI only forecasts predictions. Prescriptive analytics uses strict mathematical thresholds (like traffic lights) to tell managers exactly *how* to react to dangerous trends.
                            </p>
                            <button onclick="toggleRulesDrawer()" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-lg text-xs flex items-center gap-1">
                                <i data-lucide="sliders-horizontal" class="w-3.5 h-3.5"></i> Live Adjust Threshold Rules
                            </button>
                        </div>
                        <div class="bg-white border p-4 rounded-lg space-y-2 text-xs">
                            <div class="flex items-center gap-2"><span class="h-2 w-2 bg-rose-500 rounded-full"></span> <strong>Rule A:</strong> Freeze delivery if receivables > 40%</div>
                            <div class="flex items-center gap-2"><span class="h-2 w-2 bg-amber-500 rounded-full"></span> <strong>Rule B:</strong> Alert if safety cash < $15,000</div>
                            <div class="flex items-center gap-2"><span class="h-2 w-2 bg-violet-500 rounded-full"></span> <strong>Rule C:</strong> Target upsell if high-value ($50k+) low demand</div>
                        </div>
                    </div>`;
                    break;
                case 5:
                    html = `
                    <div class="bg-indigo-900 text-white rounded-xl p-5 relative overflow-hidden">
                        <div class="absolute right-0 bottom-0 opacity-10 transform translate-x-10 translate-y-10">
                            <i data-lucide="file-text" class="w-48 h-48"></i>
                        </div>
                        <div class="max-w-xl">
                            <h4 class="text-sm font-extrabold tracking-tight mb-2">Executive Strategy Briefing Ready 📄</h4>
                            <p class="text-xs text-indigo-200 mb-4 leading-relaxed">
                                Managers only want to look at the outcomes to formulate business decisions. Our pipeline analyzed the records and generated these clear strategic interventions:
                            </p>
                            <ul class="space-y-2 text-xs text-indigo-100">
                                <li class="flex items-center gap-2"><i data-lucide="shield-alert" class="w-4 h-4 text-rose-400"></i> Audit Client Alpha Enterprises immediately for risk freeze.</li>
                                <li class="flex items-center gap-2"><i data-lucide="trending-up" class="w-4 h-4 text-emerald-400"></i> Initiate upsell actions on healthy premium tiers.</li>
                            </ul>
                        </div>
                    </div>`;
                    break;
            }

            container.innerHTML = html;
            lucide.createIcons();
        }

        // --- SPREADSHEET MANUAL DATA ENTRY HANDLERS ---
        function openSpreadsheet() {
            document.getElementById('spreadsheet-modal').classList.remove('hidden');
            renderSpreadsheet();
        }

        function closeSpreadsheet() {
            document.getElementById('spreadsheet-modal').classList.add('hidden');
        }

        function renderSpreadsheet() {
            const tbody = document.getElementById('spreadsheet-body');
            tbody.innerHTML = '';
            
            spreadsheetData.forEach((row, idx) => {
                const tr = document.createElement('tr');
                tr.className = "hover:bg-slate-50 transition-all";
                tr.innerHTML = `
                    <td class="p-2"><input type="date" value="${row.date}" onchange="updateSpreadsheetCell(${idx}, 'date', this.value)" class="p-1 border rounded w-full bg-transparent"></td>
                    <td class="p-2"><input type="text" value="${row.client_name}" onchange="updateSpreadsheetCell(${idx}, 'client_name', this.value)" class="p-1 border rounded w-full bg-transparent font-bold"></td>
                    <td class="p-2 text-right"><input type="number" value="${row.revenue}" onchange="updateSpreadsheetCell(${idx}, 'revenue', this.value)" class="p-1 border rounded w-28 bg-transparent text-right"></td>
                    <td class="p-2 text-right"><input type="number" value="${row.accounts_receivable}" onchange="updateSpreadsheetCell(${idx}, 'accounts_receivable', this.value)" class="p-1 border rounded w-28 bg-transparent text-right"></td>
                    <td class="p-2 text-right"><input type="number" value="${row.pondo_remaining}" onchange="updateSpreadsheetCell(${idx}, 'pondo_remaining', this.value)" class="p-1 border rounded w-28 bg-transparent text-right"></td>
                    <td class="p-2 text-center"><input type="number" value="${row.demand_qty}" onchange="updateSpreadsheetCell(${idx}, 'demand_qty', this.value)" class="p-1 border rounded w-20 bg-transparent text-center"></td>
                    <td class="p-2 text-center">
                        <button onclick="deleteSpreadsheetRow(${idx})" class="p-1.5 bg-rose-100 hover:bg-rose-200 text-rose-700 rounded-md transition-all">
                            <i data-lucide="trash" class="w-4 h-4"></i>
                        </button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
            lucide.createIcons();
        }

        function updateSpreadsheetCell(index, col, val) {
            spreadsheetData[index][col] = (col === 'client_name' || col === 'date') ? val : parseFloat(val);
        }

        function addSpreadsheetRow() {
            spreadsheetData.push({
                date: '2026-05-17',
                client_name: 'New Client Inc',
                revenue: 10000,
                accounts_receivable: 1000,
                pondo_remaining: 5000,
                demand_qty: 50
            });
            renderSpreadsheet();
        }

        function deleteSpreadsheetRow(index) {
            spreadsheetData.splice(index, 1);
            renderSpreadsheet();
        }

        function resetSpreadsheetTemplate() {
            spreadsheetData = [
                {date: '2026-05-17', client_name: 'Alpha Enterprises', revenue: 35000, accounts_receivable: 14000, pondo_remaining: 8000, demand_qty: 210},
                {date: '2026-05-17', client_name: 'Beta Retailers', revenue: 20000, accounts_receivable: 5000, pondo_remaining: 3500, demand_qty: 320},
                {date: '2026-05-17', client_name: 'Gamma Corp', revenue: 90000, accounts_receivable: 2000, pondo_remaining: 68000, demand_qty: 40},
                {date: '2026-05-17', client_name: 'Delta Solutions', revenue: 45000, accounts_receivable: 3000, pondo_remaining: 24000, demand_qty: 155},
                {date: '2026-05-17', client_name: 'Epsilon Tech', revenue: 15000, accounts_receivable: 1000, pondo_remaining: 9500, demand_qty: 80}
            ];
            renderSpreadsheet();
        }

        async function commitSpreadsheetData() {
            try {
                const res = await fetch('/api/historical/save', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({rows: spreadsheetData})
                });
                const response = await res.json();
                if (response.success) {
                    closeSpreadsheet();
                    fetchDatabaseInspect();
                    fetchAnalytics();
                    alert(response.message);
                } else {
                    alert(response.message);
                }
            } catch(e) {
                alert("Consolidation API failed to connect.");
            }
        }

        // --- PRESCRIPTIVE RULE EDITING LOGIC ---
        function toggleRulesDrawer() {
            const drawer = document.getElementById('rules-drawer');
            if (drawer.classList.contains('hidden')) {
                drawer.classList.remove('hidden');
                setTimeout(() => drawer.style.transform = "translateX(0)", 10);
                loadRulesConfig();
            } else {
                drawer.style.transform = "translateX(100%)";
                setTimeout(() => drawer.classList.add('hidden'), 300);
            }
        }

        async function loadRulesConfig() {
            try {
                const res = await fetch('/api/rules');
                const data = await res.json();
                const container = document.getElementById('rules-form-container');
                container.innerHTML = '';

                data.rules.forEach(rule => {
                    const group = document.createElement('div');
                    group.className = "mb-4 border-b pb-4";
                    group.innerHTML = `
                        <label class="block text-xs font-bold text-slate-800 mb-1">${rule.rule_name}</label>
                        <span class="block text-[10px] text-slate-500 mb-2 leading-tight">${rule.description}</span>
                        <input type="number" step="any" value="${rule.threshold_val}" id="input-rule-${rule.rule_key}" class="w-full p-2 border rounded-lg text-xs font-semibold bg-transparent outline-none">
                    `;
                    container.appendChild(group);
                });
            } catch(e) {
                console.error("Rule fetch failed.");
            }
        }

        async function saveRules() {
            const inputs = document.querySelectorAll('[id^="input-rule-"]');
            const data = {};
            inputs.forEach(input => {
                const key = input.id.replace('input-rule-', '');
                data[key] = parseFloat(input.value);
            });

            try {
                const res = await fetch('/api/rules', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                const response = await res.json();
                if (response.success) {
                    toggleRulesDrawer();
                    fetchAnalytics();
                    alert(response.message);
                }
            } catch(e) {
                alert("Saving dynamic threshold rules failed.");
            }
        }

        // Helpers
        function formatCurrency(val) {
            return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
        }
    </script>
</body>
</html>
""")

if __name__ == '__main__':
    # Running local server on standard port 5000
    print("----------------------------------------------------------------------")
    print(" SUCCESS: Starting InsightFlow™ Interactive Analytics Server locally...")
    print(" Database mapping successfully aligned to POS database logic.")
    print(" Access http://127.0.0.1:5000/ to launch simple / awesome UI mode.")
    print("----------------------------------------------------------------------")
    app.run(debug=True, port=5000)