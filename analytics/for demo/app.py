import os
import sqlite3
import json
from flask import Flask, jsonify, request, render_template_string

# Try to import numpy and scipy, fall back if necessary
try:
    import numpy as np
    import scipy.stats as stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

app = Flask(__name__)
DATABASE = 'analytics.db'

def get_db_connection():
    """Establishes and returns a database connection with Row factory."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(force_reset=False):
    """Initializes the database schema and seeds sample data if empty or forced."""
    db_exists = os.path.exists(DATABASE)
    
    if force_reset and db_exists:
        try:
            os.remove(DATABASE)
        except OSError:
            pass
            
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            csat REAL NOT NULL CHECK(csat >= 0.0 AND csat <= 10.0)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0.0),
            order_date TEXT NOT NULL,
            description TEXT NOT NULL,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
        )
    """)
    
    # Check if we need to seed the database
    cursor.execute("SELECT COUNT(*) FROM clients")
    client_count = cursor.fetchone()[0]
    
    if client_count == 0:
        # Seed 10 distinct Clients with varying CSAT scores
        clients_data = [
            ("Apex Solutions", 8.5),
            ("Blue Horizon Tech", 7.2),
            ("Summit Enterprises", 9.0),
            ("Vanguard Group", 6.5),
            ("Quantum Labs", 9.5),
            ("Nexus Global", 4.5),
            ("Horizon Media", 8.0),
            ("Nova Trading", 7.8),
            ("Zenith Consultancy", 9.2),
            ("Prime Logistics", 5.8)
        ]
        
        cursor.executemany("INSERT INTO clients (name, csat) VALUES (?, ?)", clients_data)
        conn.commit()
        
        # Get client IDs mapping
        cursor.execute("SELECT id, name FROM clients")
        client_map = {row["name"]: row["id"] for row in cursor.fetchall()}
        
        # Seed exactly 30 sales orders distributed among the 10 clients
        # We model a clean correlation scenario: clients with higher CSAT spend more and order more frequently.
        orders_data = [
            # Quantum Labs (CSAT: 9.5) - 4 large orders
            (client_map["Quantum Labs"], 14500.00, "2026-01-10", "Enterprise SaaS License Renewal"),
            (client_map["Quantum Labs"], 16200.00, "2026-02-14", "Cloud Infrastructure Migration"),
            (client_map["Quantum Labs"], 18500.00, "2026-03-20", "AI Integration Consulting"),
            (client_map["Quantum Labs"], 15000.00, "2026-04-12", "Managed Operations Support"),
            
            # Zenith Consultancy (CSAT: 9.2) - 4 large/medium orders
            (client_map["Zenith Consultancy"], 11200.00, "2026-01-15", "Cybersecurity Audit - Phase 1"),
            (client_map["Zenith Consultancy"], 13400.00, "2026-02-18", "Network Hardware Refresh"),
            (client_map["Zenith Consultancy"], 12000.00, "2026-03-25", "Systems Integration SLA"),
            (client_map["Zenith Consultancy"], 14100.00, "2026-05-02", "DevOps Pipeline Implementation"),
            
            # Summit Enterprises (CSAT: 9.0) - 3 large orders
            (client_map["Summit Enterprises"], 10500.00, "2026-01-12", "Database Cluster Virtualization"),
            (client_map["Summit Enterprises"], 13800.00, "2026-03-05", "Core ERP License Expansion"),
            (client_map["Summit Enterprises"], 11000.00, "2026-04-22", "Staff Augmentation Services"),
            
            # Apex Solutions (CSAT: 8.5) - 3 medium orders
            (client_map["Apex Solutions"], 8200.00, "2026-01-05", "Custom API Webhooks Development"),
            (client_map["Apex Solutions"], 9500.00, "2026-02-10", "E-Commerce Integration Sprint"),
            (client_map["Apex Solutions"], 7800.00, "2026-04-01", "Post-Deployment Maintenance"),
            
            # Horizon Media (CSAT: 8.0) - 3 medium orders
            (client_map["Horizon Media"], 6800.00, "2026-01-20", "Brand Engagement Audit"),
            (client_map["Horizon Media"], 8500.00, "2026-03-12", "Interactive Media Framework"),
            (client_map["Horizon Media"], 7400.00, "2026-05-10", "Ad Campaign Retainer"),
            
            # Nova Trading (CSAT: 7.8) - 3 orders
            (client_map["Nova Trading"], 5200.00, "2026-02-22", "Inventory Management Setup"),
            (client_map["Nova Trading"], 6900.00, "2026-04-05", "Automated Ledger Sync Tool"),
            (client_map["Nova Trading"], 6100.00, "2026-05-14", "Market Data Analytics Feed"),
            
            # Blue Horizon Tech (CSAT: 7.2) - 3 smaller orders
            (client_map["Blue Horizon Tech"], 4200.00, "2026-01-18", "Customer Portal UX Audit"),
            (client_map["Blue Horizon Tech"], 5100.00, "2026-03-01", "Mobile App Patch deployment"),
            (client_map["Blue Horizon Tech"], 4700.00, "2026-04-18", "API Standard Suite Integration"),
            
            # Vanguard Group (CSAT: 6.5) - 3 smaller orders
            (client_map["Vanguard Group"], 3100.00, "2026-02-05", "Regulatory Compliance Report"),
            (client_map["Vanguard Group"], 4200.00, "2026-03-15", "Risk Analysis Reporting"),
            (client_map["Vanguard Group"], 3600.00, "2026-05-01", "System Patch Validation"),
            
            # Prime Logistics (CSAT: 5.8) - 2 small orders
            (client_map["Prime Logistics"], 2800.00, "2026-01-30", "Routing Protocol Optimization"),
            (client_map["Prime Logistics"], 3200.00, "2026-04-10", "Vehicle Dispatch UI Mod"),
            
            # Nexus Global (CSAT: 4.5) - 2 minimal orders
            (client_map["Nexus Global"], 1800.00, "2026-02-28", "Legacy Server Diagnostics"),
            (client_map["Nexus Global"], 2100.00, "2026-05-05", "Emergency Patch Deployment")
        ]
        
        cursor.executemany("INSERT INTO orders (client_id, amount, order_date, description) VALUES (?, ?, ?, ?)", orders_data)
        conn.commit()
        
    conn.close()

# Initialize DB on start
init_db()

def perform_correlation_analysis(clients, total_spends, avg_spends, order_counts):
    """
    Computes Pearson Correlation and simple linear regression using SciPy.
    Ensures safe calculations even with low variance or static numbers.
    """
    if not HAS_SCIPY:
        return {
            "pearson_r": 0.0,
            "p_value": 1.0,
            "slope": 0.0,
            "intercept": 0.0,
            "trendline": [],
            "status": "SciPy/NumPy not loaded properly on host system."
        }
        
    # Convert lists to numpy arrays
    x = np.array(clients, dtype=float)
    y = np.array(total_spends, dtype=float)
    
    # Check if we have sufficient variance to calculate correlation
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return {
            "pearson_r": 0.0,
            "p_value": 1.0,
            "slope": 0.0,
            "intercept": sum(y)/len(y) if len(y) > 0 else 0,
            "trendline": [],
            "status": "Insufficient variation in data to compute meaningful correlation"
        }
    
    # Pearson Correlation Coefficient (r) and two-tailed p-value
    r_coeff, p_val = stats.pearsonr(x, y)
    
    # Linear regression to compute the trend line coordinates
    slope, intercept, r_value_reg, p_value_reg, std_err = stats.linregress(x, y)
    
    # Calculate trendline boundaries
    min_x, max_x = float(np.min(x)), float(np.max(x))
    trendline_coords = [
        {"x": min_x, "y": float(slope * min_x + intercept)},
        {"x": max_x, "y": float(slope * max_x + intercept)}
    ]
    
    # CSAT vs Order Frequency correlation
    freq_r, freq_p = stats.pearsonr(x, np.array(order_counts, dtype=float))
    
    # CSAT vs Avg Order Value correlation
    avg_r, avg_p = stats.pearsonr(x, np.array(avg_spends, dtype=float))

    return {
        "pearson_r": float(r_coeff) if not np.isnan(r_coeff) else 0.0,
        "p_value": float(p_val) if not np.isnan(p_val) else 1.0,
        "slope": float(slope),
        "intercept": float(intercept),
        "trendline_coords": trendline_coords,
        "frequency_r": float(freq_r) if not np.isnan(freq_r) else 0.0,
        "frequency_p": float(freq_p) if not np.isnan(freq_p) else 1.0,
        "avg_value_r": float(avg_r) if not np.isnan(avg_r) else 0.0,
        "avg_value_p": float(avg_p) if not np.isnan(avg_p) else 1.0,
        "status": "Success"
    }

@app.route('/api/dashboard_data', methods=['GET'])
def get_dashboard_data():
    """Retrieves all dashboard statistics, client data, order details, and correlation indicators."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Retrieve all client data
    cursor.execute("SELECT * FROM clients ORDER BY csat DESC")
    clients_rows = cursor.fetchall()
    clients_list = [dict(row) for row in clients_rows]
    
    # Retrieve all orders with Client names joined
    cursor.execute("""
        SELECT o.id, o.client_id, c.name as client_name, o.amount, o.order_date, o.description 
        FROM orders o
        JOIN clients c ON o.client_id = c.id
        ORDER BY o.order_date DESC
    """)
    orders_rows = cursor.fetchall()
    orders_list = [dict(row) for row in orders_rows]
    
    # Gather aggregated data per client for correlation
    cursor.execute("""
        SELECT c.id, c.name, c.csat,
               COALESCE(SUM(o.amount), 0) as total_spend,
               COALESCE(AVG(o.amount), 0) as avg_spend,
               COUNT(o.id) as order_count
        FROM clients c
        LEFT JOIN orders o ON c.id = o.client_id
        GROUP BY c.id
    """)
    aggregates_rows = cursor.fetchall()
    
    # Format data vectors for SciPy
    csat_vec = []
    total_spend_vec = []
    avg_spend_vec = []
    order_count_vec = []
    agg_list = []
    
    for row in aggregates_rows:
        csat_vec.append(row["csat"])
        total_spend_vec.append(row["total_spend"])
        avg_spend_vec.append(row["avg_spend"])
        order_count_vec.append(row["order_count"])
        agg_list.append(dict(row))
        
    # Perform SciPy statistical correlation
    stats_result = perform_correlation_analysis(csat_vec, total_spend_vec, avg_spend_vec, order_count_vec)
    
    # Calculate some helper metrics
    total_revenue = sum(total_spend_vec)
    avg_csat = sum(csat_vec) / len(csat_vec) if csat_vec else 0
    total_orders_count = len(orders_list)
    
    conn.close()
    
    return jsonify({
        "clients": clients_list,
        "orders": orders_list,
        "aggregates": agg_list,
        "correlation": stats_result,
        "summary": {
            "total_revenue": total_revenue,
            "avg_csat": round(avg_csat, 2),
            "total_orders": total_orders_count,
            "client_count": len(clients_list)
        }
    })

@app.route('/api/update_csat', methods=['POST'])
def update_csat():
    """Updates the customer satisfaction score for a client."""
    data = request.json
    client_id = data.get('client_id')
    new_csat = data.get('csat')
    
    if client_id is None or new_csat is None:
        return jsonify({"error": "Missing client_id or csat value"}), 400
        
    try:
        new_csat = float(new_csat)
        if new_csat < 0.0 or new_csat > 10.0:
            raise ValueError
    except ValueError:
        return jsonify({"error": "CSAT must be a float between 0.0 and 10.0"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE clients SET csat = ? WHERE id = ?", (new_csat, client_id))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "CSAT updated successfully"})

@app.route('/api/add_order', methods=['POST'])
def add_order():
    """Adds a new sales order to the database."""
    data = request.json
    client_id = data.get('client_id')
    amount = data.get('amount')
    order_date = data.get('order_date')
    description = data.get('description', '')
    
    if not all([client_id, amount, order_date, description]):
        return jsonify({"error": "All fields are required"}), 400
        
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError
    except ValueError:
        return jsonify({"error": "Amount must be a positive decimal number"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO orders (client_id, amount, order_date, description) VALUES (?, ?, ?, ?)",
        (client_id, amount, order_date, description)
    )
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Order added successfully"})

@app.route('/api/delete_order', methods=['POST'])
def delete_order():
    """Deletes an existing sales order."""
    data = request.json
    order_id = data.get('order_id')
    
    if order_id is None:
        return jsonify({"error": "Missing order_id"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Order deleted successfully"})

@app.route('/api/reset_data', methods=['POST'])
def reset_data():
    """Resets client and order statistics to standard seed values."""
    init_db(force_reset=True)
    return jsonify({"success": True, "message": "Database successfully reset to initial seed values."})


@app.route('/', methods=['GET'])
def index():
    """Renders the comprehensive dashboard interface."""
    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Customer Satisfaction & Sales Correlation Dashboard</title>
        <!-- Tailwind CSS CDN -->
        <script src="https://cdn.tailwindcss.com"></script>
        <!-- Chart.js CDN -->
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <!-- FontAwesome Icons -->
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <!-- Google Font -->
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
        <style>
            body {
                font-family: 'Inter', sans-serif;
            }
            .glass-effect {
                background: rgba(255, 255, 255, 0.85);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
            }
        </style>
    </head>
    <body class="bg-slate-50 text-slate-800 min-h-screen">
        
        <!-- Header -->
        <header class="bg-indigo-900 text-white shadow-lg sticky top-0 z-40 transition-all">
            <div class="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row justify-between items-center gap-4">
                <div class="flex items-center gap-3">
                    <div class="p-2 bg-indigo-500 rounded-lg text-white">
                        <i class="fa-solid fa-chart-line text-2xl"></i>
                    </div>
                    <div>
                        <h1 class="text-xl font-extrabold tracking-tight">CSAT vs. Revenue Analytics</h1>
                        <p class="text-xs text-indigo-200">SciPy-Powered Correlation Engine</p>
                    </div>
                </div>
                <div class="flex items-center gap-3">
                    <button onclick="resetData()" class="flex items-center gap-2 px-4 py-2 bg-indigo-800 hover:bg-indigo-700 active:bg-indigo-900 border border-indigo-600 rounded-lg text-sm font-semibold transition shadow-sm">
                        <i class="fa-solid fa-rotate-left"></i> Reset Seed Data
                    </button>
                    <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                        <span class="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                        Live Dashboard
                    </span>
                </div>
            </div>
        </header>

        <!-- Main Workspace Grid -->
        <main class="max-w-7xl mx-auto px-4 py-6 sm:px-6 lg:px-8 space-y-6">
            
            <!-- Global Metric Summary Grid -->
            <div class="grid grid-cols-1 md:grid-cols-4 gap-5">
                <!-- Total revenue -->
                <div class="bg-white rounded-2xl p-5 shadow-sm border border-slate-100 flex items-center justify-between">
                    <div>
                        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400">Total Portfolio Value</p>
                        <h3 id="stat-total-revenue" class="text-2xl font-bold text-slate-900 mt-1">$0.00</h3>
                        <p class="text-xs text-slate-500 mt-1">Across all clients & segments</p>
                    </div>
                    <div class="h-12 w-12 rounded-xl bg-indigo-50 flex items-center justify-center text-indigo-600">
                        <i class="fa-solid fa-wallet text-xl"></i>
                    </div>
                </div>

                <!-- Avg CSAT -->
                <div class="bg-white rounded-2xl p-5 shadow-sm border border-slate-100 flex items-center justify-between">
                    <div>
                        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400">Average Client CSAT</p>
                        <h3 id="stat-avg-csat" class="text-2xl font-bold text-slate-900 mt-1">0.0 / 10</h3>
                        <p class="text-xs text-slate-500 mt-1">Weighted customer feedback</p>
                    </div>
                    <div class="h-12 w-12 rounded-xl bg-amber-50 flex items-center justify-center text-amber-500">
                        <i class="fa-solid fa-star text-xl"></i>
                    </div>
                </div>

                <!-- Pearson R -->
                <div class="bg-white rounded-2xl p-5 shadow-sm border border-slate-100 flex items-center justify-between">
                    <div>
                        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400">Pearson Correlation (r)</p>
                        <h3 id="stat-pearson" class="text-2xl font-bold text-slate-900 mt-1">0.00</h3>
                        <span id="stat-pearson-badge" class="inline-block mt-1 text-xs px-2 py-0.5 rounded font-medium">Loading...</span>
                    </div>
                    <div class="h-12 w-12 rounded-xl bg-teal-50 flex items-center justify-center text-teal-600">
                        <i class="fa-solid fa-code-merge text-xl"></i>
                    </div>
                </div>

                <!-- Significance P-value -->
                <div class="bg-white rounded-2xl p-5 shadow-sm border border-slate-100 flex items-center justify-between">
                    <div>
                        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400">Statistical Significance</p>
                        <h3 id="stat-p-value" class="text-2xl font-bold text-slate-900 mt-1">p = 1.000</h3>
                        <span id="stat-p-badge" class="inline-block mt-1 text-xs px-2 py-0.5 rounded font-medium">Loading...</span>
                    </div>
                    <div class="h-12 w-12 rounded-xl bg-rose-50 flex items-center justify-center text-rose-500">
                        <i class="fa-solid fa-scale-balanced text-xl"></i>
                    </div>
                </div>
            </div>

            <!-- Analytics Visualisation Row -->
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                
                <!-- Chart 1: Scatter plot & Regression line -->
                <div class="lg:col-span-2 bg-white rounded-2xl p-6 shadow-sm border border-slate-100 flex flex-col justify-between">
                    <div>
                        <div class="flex justify-between items-start mb-4">
                            <div>
                                <h2 class="text-lg font-bold text-slate-900">Scatter Plot & Linear Regression Line</h2>
                                <p class="text-xs text-slate-500">CSAT Score (X-axis) vs. Total Client Revenue (Y-axis)</p>
                            </div>
                            <span class="text-xs font-medium text-indigo-600 bg-indigo-50 px-2.5 py-1 rounded-full"><i class="fa-solid fa-cube mr-1"></i>SciPy stats.linregress</span>
                        </div>
                        <div class="relative w-full h-[360px]">
                            <canvas id="scatterChart"></canvas>
                        </div>
                    </div>
                    <div class="mt-4 pt-4 border-t border-slate-100 flex flex-wrap justify-between items-center text-xs text-slate-500 gap-2">
                        <span><i class="fa-solid fa-info-circle mr-1 text-indigo-500"></i><strong>Trendline equation:</strong> <span id="regression-formula" class="font-mono bg-slate-100 px-1.5 py-0.5 rounded">y = mx + c</span></span>
                        <span>Click dataset dots to highlight custom client stats below.</span>
                    </div>
                </div>

                <!-- Chart 2: Statistical Insights Panel -->
                <div class="bg-white rounded-2xl p-6 shadow-sm border border-slate-100 flex flex-col justify-between">
                    <div>
                        <h2 class="text-lg font-bold text-slate-900 mb-2">SciPy Analysis Report</h2>
                        <p class="text-xs text-slate-500 mb-4">Mathematical verification of customer sentiments vs. spending habits.</p>
                        
                        <!-- Correlation Strength Indicator -->
                        <div class="space-y-4">
                            <div class="p-4 bg-slate-50 rounded-xl border border-slate-100">
                                <h4 class="text-xs font-semibold text-slate-400 uppercase tracking-wide">Primary Verdict</h4>
                                <p id="scipy-verdict" class="text-sm font-bold text-slate-800 mt-1">Analyzing client-spend distribution...</p>
                                <p id="scipy-verdict-desc" class="text-xs text-slate-500 mt-1">SciPy computes a Pearson's r calculation over your active data array dynamically.</p>
                            </div>

                            <div>
                                <h4 class="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Detailed Correlation Vectors</h4>
                                <div class="space-y-2.5">
                                    <div class="flex justify-between items-center text-sm p-2 bg-slate-50 rounded-lg">
                                        <span class="text-slate-600">CSAT vs. Overall Portfolio Value:</span>
                                        <span id="csat-revenue-r" class="font-bold text-indigo-600">--</span>
                                    </div>
                                    <div class="flex justify-between items-center text-sm p-2 bg-slate-50 rounded-lg">
                                        <span class="text-slate-600">CSAT vs. Order Frequency (Count):</span>
                                        <span id="csat-frequency-r" class="font-bold text-teal-600">--</span>
                                    </div>
                                    <div class="flex justify-between items-center text-sm p-2 bg-slate-50 rounded-lg">
                                        <span class="text-slate-600">CSAT vs. Average Basket Size ($):</span>
                                        <span id="csat-avgvalue-r" class="font-bold text-emerald-600">--</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Informational Note -->
                    <div class="mt-6 p-3 bg-indigo-50 rounded-xl border border-indigo-100/30 text-xs text-indigo-900/80">
                        <h5 class="font-semibold flex items-center gap-1"><i class="fa-solid fa-graduation-cap"></i> Dynamic Stats Note</h5>
                        <p class="mt-1 leading-relaxed">Adjust client CSAT scores or add new sales orders using the tables below. SciPy will recalculate these indicators dynamically in real-time!</p>
                    </div>
                </div>
            </div>

            <!-- Double-Axis Client Performance Chart -->
            <div class="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
                <div class="flex justify-between items-center mb-4">
                    <div>
                        <h2 class="text-lg font-bold text-slate-900">Client CSAT vs. Overall Spends Comparative Analysis</h2>
                        <p class="text-xs text-slate-500">Evaluating client satisfaction (left bar) with total sales receipts (right line)</p>
                    </div>
                </div>
                <div class="relative w-full h-[280px]">
                    <canvas id="barLineChart"></canvas>
                </div>
            </div>

            <!-- Action Panels: Edit CSAT / Manage Orders -->
            <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
                
                <!-- Client CSAT Editor Tab -->
                <div class="lg:col-span-5 bg-white rounded-2xl p-6 shadow-sm border border-slate-100 flex flex-col justify-between">
                    <div>
                        <div class="flex justify-between items-center mb-4">
                            <div>
                                <h3 class="text-lg font-bold text-slate-900">Client Satisfaction (CSAT)</h3>
                                <p class="text-xs text-slate-500">Configure satisfaction scores (Scale: 0.0 - 10.0)</p>
                            </div>
                            <span class="text-xs font-semibold bg-indigo-50 text-indigo-600 px-2 py-1 rounded">10 Clients</span>
                        </div>
                        
                        <div class="overflow-y-auto max-h-[380px] pr-2 space-y-3" id="clients-list-container">
                            <!-- Populated by JS -->
                        </div>
                    </div>
                    
                    <div class="mt-4 pt-3 border-t border-slate-100 text-[11px] text-slate-400">
                        <i class="fa-solid fa-bolt mr-1 text-amber-500"></i> Updates trigger direct SQLite updates and compute real-time statistical changes instantly.
                    </div>
                </div>

                <!-- Sales Order Management -->
                <div class="lg:col-span-7 bg-white rounded-2xl p-6 shadow-sm border border-slate-100 flex flex-col justify-between">
                    <div>
                        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 mb-4">
                            <div>
                                <h3 class="text-lg font-bold text-slate-900">Sales Orders Registry</h3>
                                <p class="text-xs text-slate-500">Showing active sales metrics used in correlation calculation</p>
                            </div>
                            <button onclick="toggleOrderModal(true)" class="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 transition">
                                <i class="fa-solid fa-plus"></i> Add Sales Order
                            </button>
                        </div>
                        
                        <div class="overflow-x-auto rounded-lg border border-slate-100">
                            <table class="min-w-full divide-y divide-slate-100 text-left text-sm">
                                <thead class="bg-slate-50 text-slate-500 font-semibold text-xs uppercase">
                                    <tr>
                                        <th class="px-4 py-3">Client</th>
                                        <th class="px-4 py-3">Date</th>
                                        <th class="px-4 py-3">Description</th>
                                        <th class="px-4 py-3 text-right">Amount</th>
                                        <th class="px-4 py-3 text-center">Action</th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y divide-slate-100 font-medium text-slate-700" id="orders-table-body">
                                    <!-- Populated by JS -->
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

            </div>

        </main>

        <!-- New Sales Order Slide-Over Modal -->
        <div id="add-order-modal" class="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center hidden opacity-0 transition-opacity duration-300">
            <div class="bg-white rounded-2xl max-w-md w-full p-6 shadow-xl transform scale-95 transition-transform duration-300">
                <div class="flex justify-between items-center pb-4 border-b border-slate-100">
                    <h3 class="text-lg font-extrabold text-slate-900"><i class="fa-solid fa-cart-plus text-indigo-600 mr-1.5"></i> Register New Sales Order</h3>
                    <button onclick="toggleOrderModal(false)" class="text-slate-400 hover:text-slate-600 transition"><i class="fa-solid fa-xmark text-lg"></i></button>
                </div>
                
                <form id="add-order-form" onsubmit="submitNewOrder(event)" class="mt-4 space-y-4">
                    <div>
                        <label class="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Select Client</label>
                        <select id="form-client-id" class="w-full border border-slate-200 rounded-lg p-2.5 text-sm bg-slate-50 focus:bg-white focus:outline-indigo-500" required>
                            <!-- Populated by JS -->
                        </select>
                    </div>

                    <div>
                        <label class="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Order Amount ($)</label>
                        <input type="number" id="form-amount" step="0.01" min="0.01" class="w-full border border-slate-200 rounded-lg p-2.5 text-sm bg-slate-50 focus:bg-white focus:outline-indigo-500" placeholder="e.g. 12500.00" required>
                    </div>

                    <div>
                        <label class="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Order Date</label>
                        <input type="date" id="form-date" class="w-full border border-slate-200 rounded-lg p-2.5 text-sm bg-slate-50 focus:bg-white focus:outline-indigo-500" required>
                    </div>

                    <div>
                        <label class="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Order Specifications / Description</label>
                        <input type="text" id="form-desc" class="w-full border border-slate-200 rounded-lg p-2.5 text-sm bg-slate-50 focus:bg-white focus:outline-indigo-500" placeholder="e.g. SaaS Subscription Upgrade" required>
                    </div>

                    <div class="pt-2 flex justify-end gap-3">
                        <button type="button" onclick="toggleOrderModal(false)" class="px-4 py-2 text-sm font-semibold border border-slate-200 rounded-lg hover:bg-slate-50 transition">Cancel</button>
                        <button type="submit" class="px-4 py-2 text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition shadow-sm">Save Order</button>
                    </div>
                </form>
            </div>
        </div>

        <!-- Custom Notification Slide-Out Toast -->
        <div id="toast" class="fixed bottom-5 right-5 bg-slate-900 text-white px-5 py-3 rounded-xl shadow-lg flex items-center gap-3 transform translate-y-20 opacity-0 transition-all duration-300 z-50">
            <span id="toast-icon" class="text-teal-400"><i class="fa-solid fa-circle-check"></i></span>
            <span id="toast-message" class="text-xs font-medium">Notification message.</span>
        </div>

        <script>
            // Global chart reference storage to reuse canvas objects gracefully
            let scatterChartInstance = null;
            let barLineChartInstance = null;
            let loadedClientData = [];

            // Initialize on window loading sequence
            window.onload = function() {
                // Set default order date to today
                const today = new Date().toISOString().split('T')[0];
                document.getElementById('form-date').value = today;

                fetchAndRenderDashboard();
            };

            // Custom non-blocking Toast notification helper
            function showToast(message, type = 'success') {
                const toast = document.getElementById('toast');
                const icon = document.getElementById('toast-icon');
                const text = document.getElementById('toast-message');

                text.innerText = message;
                if (type === 'success') {
                    icon.innerHTML = '<i class="fa-solid fa-circle-check text-teal-400"></i>';
                } else {
                    icon.innerHTML = '<i class="fa-solid fa-circle-exclamation text-rose-400"></i>';
                }

                toast.classList.remove('translate-y-20', 'opacity-0');
                toast.classList.add('translate-y-0', 'opacity-100');

                setTimeout(() => {
                    toast.classList.add('translate-y-20', 'opacity-0');
                    toast.classList.remove('translate-y-0', 'opacity-100');
                }, 3500);
            }

            // Slide order registration modal
            function toggleOrderModal(open) {
                const modal = document.getElementById('add-order-modal');
                if (open) {
                    modal.classList.remove('hidden');
                    setTimeout(() => {
                        modal.classList.remove('opacity-0');
                        modal.querySelector('.transform').classList.remove('scale-95');
                        modal.querySelector('.transform').classList.add('scale-100');
                    }, 50);
                } else {
                    modal.classList.add('opacity-0');
                    modal.querySelector('.transform').classList.add('scale-95');
                    modal.querySelector('.transform').classList.remove('scale-100');
                    setTimeout(() => {
                        modal.classList.add('hidden');
                    }, 300);
                }
            }

            // Reset Data handler
            function resetData() {
                fetch('/api/reset_data', { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        showToast(data.message, 'success');
                        fetchAndRenderDashboard();
                    }
                })
                .catch(err => showToast("Error resetting data", "error"));
            }

            // Submit newly input sales orders via POST APIs
            function submitNewOrder(event) {
                event.preventDefault();
                const payload = {
                    client_id: parseInt(document.getElementById('form-client-id').value),
                    amount: parseFloat(document.getElementById('form-amount').value),
                    order_date: document.getElementById('form-date').value,
                    description: document.getElementById('form-desc').value
                };

                fetch('/api/add_order', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        showToast("Sales order registered successfully", "success");
                        toggleOrderModal(false);
                        document.getElementById('add-order-form').reset();
                        // Reset date to default today
                        document.getElementById('form-date').value = new Date().toISOString().split('T')[0];
                        fetchAndRenderDashboard();
                    } else {
                        showToast(data.error || "Failed to save order", "error");
                    }
                })
                .catch(err => showToast("Network request error saving order", "error"));
            }

            // Handler for deleting orders dynamically
            function deleteOrder(orderId) {
                if (!confirm("Are you sure you want to remove this sales order? This will immediately affect core SciPy correlation outputs.")) return;

                fetch('/api/delete_order', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ order_id: orderId })
                })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        showToast("Order entry deleted successfully", "success");
                        fetchAndRenderDashboard();
                    }
                })
                .catch(err => showToast("Error deleting order entry", "error"));
            }

            // Real-time CSAT Slider change controller
            function handleCSATChange(clientId, newCsatVal) {
                // Update slider text instantly
                document.getElementById(`csat-display-${clientId}`).innerText = parseFloat(newCsatVal).toFixed(1);

                // Send update request to SQLite
                fetch('/api/update_csat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ client_id: clientId, csat: parseFloat(newCsatVal) })
                })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        // Refresh chart and metrics but preserve table layout stability
                        silentUpdateDashboard();
                    }
                })
                .catch(err => showToast("Error updating customer satisfaction score", "error"));
            }

            // Core fetch and layout compilation loop
            function fetchAndRenderDashboard() {
                fetch('/api/dashboard_data')
                .then(res => res.json())
                .then(data => {
                    loadedClientData = data.clients;
                    
                    // Render Metrics cards
                    updateMetricCards(data);
                    
                    // Populate Charts
                    renderCharts(data);
                    
                    // Compile Client CSAT sliders list
                    renderClientCSATSliders(data.clients);
                    
                    // Compile dynamic client options in selector forms
                    renderClientOptions(data.clients);
                    
                    // Compile active sales orders list table
                    renderOrdersTable(data.orders);

                    // Compile dynamic explanation report text
                    renderReportText(data.correlation);
                })
                .catch(err => {
                    showToast("Error acquiring analytics payload from server", "error");
                    console.error(err);
                });
            }

            // Quick update variant avoiding resetting core slider views to preserve focus
            function silentUpdateDashboard() {
                fetch('/api/dashboard_data')
                .then(res => res.json())
                .then(data => {
                    updateMetricCards(data);
                    renderCharts(data);
                    renderReportText(data.correlation);
                });
            }

            // Render form options for registered clients
            function renderClientOptions(clients) {
                const select = document.getElementById('form-client-id');
                select.innerHTML = '';
                clients.forEach(c => {
                    const opt = document.createElement('option');
                    opt.value = c.id;
                    opt.innerText = c.name;
                    select.appendChild(opt);
                });
            }

            // Render key performance cards
            function updateMetricCards(data) {
                document.getElementById('stat-total-revenue').innerText = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(data.summary.total_revenue);
                document.getElementById('stat-avg-csat').innerText = `${data.summary.avg_csat} / 10`;
                
                // Pearson R status card
                const rVal = data.correlation.pearson_r;
                const rText = document.getElementById('stat-pearson');
                rText.innerText = rVal.toFixed(4);
                
                const rBadge = document.getElementById('stat-pearson-badge');
                if (rVal > 0.7) {
                    rBadge.className = "inline-block mt-1 text-xs px-2 py-0.5 rounded font-medium bg-emerald-100 text-emerald-800";
                    rBadge.innerText = "Strong Positive (Ideal)";
                } else if (rVal > 0.4) {
                    rBadge.className = "inline-block mt-1 text-xs px-2 py-0.5 rounded font-medium bg-indigo-100 text-indigo-800";
                    rBadge.innerText = "Moderate Positive";
                } else if (rVal > -0.4 && rVal < 0.4) {
                    rBadge.className = "inline-block mt-1 text-xs px-2 py-0.5 rounded font-medium bg-slate-100 text-slate-800";
                    rBadge.innerText = "Negligible / Weak";
                } else {
                    rBadge.className = "inline-block mt-1 text-xs px-2 py-0.5 rounded font-medium bg-rose-100 text-rose-800";
                    rBadge.innerText = "Inverse Correlation";
                }

                // Statistical Significance P-Value
                const pVal = data.correlation.p_value;
                document.getElementById('stat-p-value').innerText = `p = ${pVal.toFixed(5)}`;
                const pBadge = document.getElementById('stat-p-badge');
                if (pVal < 0.05) {
                    pBadge.className = "inline-block mt-1 text-xs px-2 py-0.5 rounded font-medium bg-teal-100 text-teal-800";
                    pBadge.innerText = "Significant (p < 0.05)";
                } else {
                    pBadge.className = "inline-block mt-1 text-xs px-2 py-0.5 rounded font-medium bg-amber-100 text-amber-800";
                    pBadge.innerText = "Not Significant (p >= 0.05)";
                }
            }

            // Render Client CSAT interactive sliders panel
            function renderClientCSATSliders(clients) {
                const container = document.getElementById('clients-list-container');
                container.innerHTML = '';
                
                clients.forEach(client => {
                    const rowDiv = document.createElement('div');
                    rowDiv.className = "p-3 border border-slate-100 rounded-xl hover:shadow-sm transition bg-white";
                    rowDiv.innerHTML = `
                        <div class="flex justify-between items-center text-sm font-semibold mb-1">
                            <span class="text-slate-800">${client.name}</span>
                            <span id="csat-display-${client.id}" class="text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded font-mono text-xs">${client.csat.toFixed(1)}</span>
                        </div>
                        <div class="flex items-center gap-3">
                            <span class="text-[10px] text-slate-400 font-bold">0.0</span>
                            <input type="range" min="0.0" max="10.0" step="0.1" value="${client.csat}" 
                                   oninput="handleCSATChange(${client.id}, this.value)" 
                                   class="w-full h-1.5 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-indigo-600">
                            <span class="text-[10px] text-slate-400 font-bold">10.0</span>
                        </div>
                    `;
                    container.appendChild(rowDiv);
                });
            }

            // Render registered sales orders table
            function renderOrdersTable(orders) {
                const tbody = document.getElementById('orders-table-body');
                tbody.innerHTML = '';
                
                orders.forEach(order => {
                    const tr = document.createElement('tr');
                    tr.className = "hover:bg-slate-50 transition border-b border-slate-100";
                    tr.innerHTML = `
                        <td class="px-4 py-3 font-semibold text-slate-800">${order.client_name}</td>
                        <td class="px-4 py-3 text-xs text-slate-500 font-mono">${order.order_date}</td>
                        <td class="px-4 py-3 text-xs text-slate-600 max-w-[180px] truncate" title="${order.description}">${order.description}</td>
                        <td class="px-4 py-3 text-right font-mono text-xs font-bold text-slate-900">$${order.amount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                        <td class="px-4 py-3 text-center">
                            <button onclick="deleteOrder(${order.id})" class="text-rose-500 hover:text-rose-700 p-1 rounded hover:bg-rose-50 transition" title="Delete Order">
                                <i class="fa-solid fa-trash-can"></i>
                            </button>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            }

            // Render SciPy Analysis dynamic report feedback
            function renderReportText(correlation) {
                const r = correlation.pearson_r;
                const p = correlation.p_value;
                const verdictEl = document.getElementById('scipy-verdict');
                const verdictDescEl = document.getElementById('scipy-verdict-desc');
                
                // Write correlation matrix highlights
                document.getElementById('csat-revenue-r').innerText = `r = ${correlation.pearson_r.toFixed(4)} (p = ${correlation.p_value.toFixed(4)})`;
                document.getElementById('csat-frequency-r').innerText = `r = ${correlation.frequency_r.toFixed(4)} (p = ${correlation.frequency_p.toFixed(4)})`;
                document.getElementById('csat-avgvalue-r').innerText = `r = ${correlation.avg_value_r.toFixed(4)} (p = ${correlation.avg_value_p.toFixed(4)})`;

                // Display Regression formula
                const slope = correlation.slope;
                const intercept = correlation.intercept;
                const sign = intercept >= 0 ? '+' : '-';
                document.getElementById('regression-formula').innerText = `y = ${slope.toFixed(2)}x ${sign} ${Math.abs(intercept).toFixed(2)}`;

                let description = "";
                let verdict = "";

                if (r > 0.7) {
                    verdict = "Strong Positive Relationship";
                    description = `With Pearson's r at ${r.toFixed(3)}, your SciPy analysis detects a highly correlated positive structure. Satisfied customers consistently spend more money. `;
                } else if (r > 0.4) {
                    verdict = "Moderate Positive Relationship";
                    description = `With Pearson's r at ${r.toFixed(3)}, positive customer feedback generally overlaps with higher order volume, but variance elements exist. `;
                } else if (r > -0.4 && r < 0.4) {
                    verdict = "No Linear Correlation Found";
                    description = `Your current CSAT metrics and revenue records demonstrate a dispersed random pattern (Pearson r = ${r.toFixed(3)}). Changes in customer feedback do not appear to predict spending behaviors. `;
                } else {
                    verdict = "Inverse (Negative) Relationship";
                    description = `Remarkably, Pearson r shows an inverse behavior of ${r.toFixed(3)}. Clients reporting lower satisfaction might be purchasing more emergency services, or higher-paying clients are more critical. `;
                }

                if (p < 0.05) {
                    description += `Because the statistical significance (p = ${p.toFixed(4)}) is below the standard 5% significance threshold (p < 0.05), we can confidently conclude this relationship is statistically verified.`;
                } else {
                    description += `However, because the calculated significance (p = ${p.toFixed(4)}) is greater than 0.05, this mathematical correlation could easily be due to coincidental variation rather than a real structural pattern. Adjust scores to see changes.`;
                }

                verdictEl.innerText = verdict;
                verdictDescEl.innerText = description;
            }

            // Chart Render Orchestrator
            function renderCharts(data) {
                // Compile vectors
                const scatterPoints = data.aggregates.map(item => ({
                    x: item.csat,
                    y: item.total_spend,
                    label: item.name
                }));

                const sortedAggregates = [...data.aggregates].sort((a,b) => b.csat - a.csat);
                const labels = sortedAggregates.map(item => item.name);
                const csatValues = sortedAggregates.map(item => item.csat);
                const spendValues = sortedAggregates.map(item => item.total_spend);

                // --- CHART 1: Scatter Chart with Linear Regression Line ---
                if (scatterChartInstance) {
                    scatterChartInstance.destroy();
                }

                const scatterCtx = document.getElementById('scatterChart').getContext('2d');
                
                const datasets = [{
                    label: 'Active Clients',
                    data: scatterPoints,
                    backgroundColor: 'rgba(99, 102, 241, 0.85)',
                    borderColor: 'rgb(79, 70, 229)',
                    borderWidth: 2,
                    pointRadius: 7,
                    pointHoverRadius: 9,
                }];

                // Inject regression trendline dataset if computed coordinates are valid
                if (data.correlation.trendline_coords && data.correlation.trendline_coords.length > 0) {
                    datasets.push({
                        label: 'Linear Regression Trendline',
                        data: data.correlation.trendline_coords,
                        type: 'line',
                        borderColor: 'rgba(239, 68, 68, 0.9)',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        fill: false,
                        pointRadius: 0,
                        showLine: true
                    });
                }

                scatterChartInstance = new Chart(scatterCtx, {
                    type: 'scatter',
                    data: { datasets: datasets },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                labels: {
                                    usePointStyle: true
                                }
                            },
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        if (context.datasetIndex === 0) {
                                            const client = context.raw.label;
                                            return `${client}: CSAT: ${context.raw.x.toFixed(1)}, Total: $${context.raw.y.toLocaleString()}`;
                                        }
                                        return `Regression Line Fit`;
                                    }
                                }
                            }
                        },
                        scales: {
                            x: {
                                min: 0,
                                max: 10,
                                title: {
                                    display: true,
                                    text: 'Customer Satisfaction Score (CSAT)',
                                    font: { weight: 'bold' }
                                }
                            },
                            y: {
                                min: 0,
                                title: {
                                    display: true,
                                    text: 'Overall Revenue Generated ($)',
                                    font: { weight: 'bold' }
                                }
                            }
                        }
                    }
                });

                // --- CHART 2: Dual Axis Bar & Line Chart ---
                if (barLineChartInstance) {
                    barLineChartInstance.destroy();
                }

                const barCtx = document.getElementById('barLineChart').getContext('2d');
                barLineChartInstance = new Chart(barCtx, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [
                            {
                                label: 'CSAT Score (0-10)',
                                data: csatValues,
                                backgroundColor: 'rgba(99, 102, 241, 0.2)',
                                borderColor: 'rgb(79, 70, 229)',
                                borderWidth: 2,
                                yAxisID: 'y_csat',
                                order: 2
                            },
                            {
                                label: 'Total Revenue ($)',
                                data: spendValues,
                                type: 'line',
                                borderColor: 'rgb(16, 185, 129)',
                                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                                borderWidth: 3,
                                fill: true,
                                tension: 0.3,
                                pointRadius: 4,
                                yAxisID: 'y_spend',
                                order: 1
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'top'
                            }
                        },
                        scales: {
                            y_csat: {
                                type: 'linear',
                                position: 'left',
                                min: 0,
                                max: 10,
                                title: {
                                    display: true,
                                    text: 'Client CSAT Rating',
                                    font: { weight: 'bold' }
                                },
                                grid: {
                                    drawOnChartArea: false
                                }
                            },
                            y_spend: {
                                type: 'linear',
                                position: 'right',
                                min: 0,
                                title: {
                                    display: true,
                                    text: 'Aggregated Sales Total ($)',
                                    font: { weight: 'bold' }
                                }
                            }
                        }
                    }
                });
            }
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

if __name__ == '__main__':
    # Running local debugging server
    app.run(host='0.0.0.0', port=5000, debug=True)