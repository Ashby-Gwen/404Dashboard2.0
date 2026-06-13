import os
import sqlite3
import pandas as pd
import logging
import json
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash
from werkzeug.utils import secure_filename

# ==================================================
# CONFIGURATION & LOGGING
# ==================================================
class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'enterprise-secure-key-998877')
    DATABASE = os.getenv('DATABASE_PATH', 'analytics.db')
    DEBUG = os.getenv('FLASK_DEBUG', 'False') == 'True'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload size
    UPLOAD_FOLDER = 'uploads'

# Ensure upload directory exists for robust data ingestion
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

# ==================================================
# DATABASE MANAGEMENT
# ==================================================
def get_db_connection():
    """Establish a secure connection to the SQLite database."""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.critical(f"Database connection failed: {e}")
        return None

def init_db():
    """Initialize the database schema and seed mock data if empty."""
    conn = get_db_connection()
    if conn:
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_id TEXT UNIQUE,
                    client_name TEXT,
                    invoice_amount REAL,
                    status TEXT,
                    expense_amount REAL,
                    expense_type TEXT,
                    sales_orders INTEGER,
                    purchase_frequency TEXT,
                    average_order_value REAL,
                    risk_index TEXT,
                    last_purchase TEXT,
                    product_preference TEXT
                )
            ''')
            
            # Seed data (Expanded for realistic charting)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM analytics")
            if cursor.fetchone()[0] == 0:
                mock_data = [
                    ('INV-001', 'Acme Corp', 5000, 'Paid', 1200, 'Marketing', 10, 'High', 500, 'Low', '2026-04-10', 'Software'),
                    ('INV-002', 'Globex', 12000, 'Pending', 3000, 'Logistics', 25, 'Medium', 480, 'Medium', '2026-04-12', 'Hardware'),
                    ('INV-003', 'Stark Ind', 8500, 'Paid', 1500, 'R&D', 15, 'High', 566, 'Low', '2026-04-14', 'Software'),
                    ('INV-004', 'Wayne Ent', 3200, 'Paid', 800, 'Marketing', 5, 'Low', 640, 'High', '2026-05-01', 'Hardware'),
                    ('INV-005', 'Oscorp', 15000, 'Overdue', 4000, 'Logistics', 30, 'High', 500, 'High', '2026-05-05', 'Consulting'),
                    ('INV-006', 'Cyberdyne', 9400, 'Paid', 2000, 'R&D', 18, 'Medium', 522, 'Low', '2026-05-10', 'Hardware'),
                    ('INV-007', 'Umbrella', 21000, 'Pending', 5000, 'Legal', 40, 'High', 525, 'Medium', '2026-05-15', 'Software'),
                    ('INV-008', 'InGen', 4500, 'Paid', 1000, 'Marketing', 8, 'Low', 562, 'Low', '2026-05-18', 'Consulting'),
                    ('INV-009', 'Massive Dyn', 11200, 'Paid', 2500, 'Logistics', 22, 'Medium', 509, 'Low', '2026-05-20', 'Hardware'),
                    ('INV-010', 'Soylent', 7800, 'Overdue', 1800, 'Marketing', 12, 'High', 650, 'High', '2026-05-22', 'Software'),
                ]
                cursor.executemany('''
                    INSERT INTO analytics (invoice_id, client_name, invoice_amount, status, expense_amount, expense_type, sales_orders, purchase_frequency, average_order_value, risk_index, last_purchase, product_preference)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', mock_data)
                conn.commit()
                logger.info("Enterprise database initialized and seeded successfully.")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database schema: {e}")
        finally:
            conn.close()

# ==================================================
# GLOBAL TEMPLATE ENGINE
# ==================================================
TEMPLATE = """
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ORANGE BI | Enterprise Analytics</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
        :root {
            --bg-dark: #020617;
            --glass-bg: rgba(30, 41, 59, 0.4);
            --glass-border: rgba(255, 255, 255, 0.05);
            --brand-orange: #f97316;
        }
        body { 
            background-color: var(--bg-dark); 
            color: #f8fafc; 
            font-family: 'Inter', sans-serif; 
        }
        .glass-card { 
            background: var(--glass-bg); 
            backdrop-filter: blur(12px); 
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--glass-border); 
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .glass-card:hover {
            box-shadow: 0 10px 30px -10px rgba(0,0,0,0.5);
            border-color: rgba(255, 255, 255, 0.1);
        }
        .pulse-ring { 
            animation: pulse-ring 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; 
        }
        @keyframes pulse-ring { 
            0%, 100% { opacity: 1; } 
            50% { opacity: 0.3; } 
        }
        
        /* Custom Scrollbar */
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: #0f172a; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #475569; }
    </style>
</head>
<body class="flex min-h-screen">
    <!-- Sidebar Navigation -->
    <aside class="w-64 bg-slate-950/80 border-r border-slate-800 p-6 fixed h-full z-20 backdrop-blur-md">
        <h1 class="text-2xl font-black mb-10 tracking-tighter text-white flex items-center gap-2">
            <svg class="w-8 h-8 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
            ORANGE<span class="text-orange-500">BI</span>
        </h1>
        <nav class="space-y-2 text-sm font-medium">
            <a href="/" class="flex items-center gap-3 p-3 rounded-lg transition-all duration-200 {% if active_page == 'dashboard' %}bg-orange-500/10 text-orange-500 border border-orange-500/20{% else %}text-slate-400 hover:bg-slate-800 hover:text-white{% endif %}">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"></path></svg>
                Executive Dashboard
            </a>
            <a href="/revenue-report" class="flex items-center gap-3 p-3 rounded-lg transition-all duration-200 {% if active_page == 'revenue' %}bg-orange-500/10 text-orange-500 border border-orange-500/20{% else %}text-slate-400 hover:bg-slate-800 hover:text-white{% endif %}">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                Financial Intelligence
            </a>
            <a href="/client-report" class="flex items-center gap-3 p-3 rounded-lg transition-all duration-200 {% if active_page == 'client' %}bg-orange-500/10 text-orange-500 border border-orange-500/20{% else %}text-slate-400 hover:bg-slate-800 hover:text-white{% endif %}">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
                Client Insights
            </a>
            <a href="/invoice-report" class="flex items-center gap-3 p-3 rounded-lg transition-all duration-200 {% if active_page == 'invoice' %}bg-orange-500/10 text-orange-500 border border-orange-500/20{% else %}text-slate-400 hover:bg-slate-800 hover:text-white{% endif %}">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                Invoice Ledger
            </a>
            <a href="/upload" class="flex items-center gap-3 p-3 rounded-lg transition-all duration-200 mt-8 {% if active_page == 'upload' %}bg-orange-500/10 text-orange-500 border border-orange-500/20{% else %}text-slate-400 hover:bg-slate-800 hover:text-white{% endif %}">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path></svg>
                Data Ingestion
            </a>
        </nav>
        <div class="absolute bottom-6 left-6 right-6">
            <div class="glass-card p-4 rounded-xl text-xs text-slate-400">
                <p>System Status: <span class="text-green-400 font-bold">Online</span></p>
                <p class="mt-1">Last Sync: Just now</p>
            </div>
        </div>
    </aside>

    <!-- Main Content Area -->
    <main class="ml-64 p-8 w-full max-w-7xl mx-auto">
        <!-- Flash Messages for Action Feedback -->
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="mb-6 space-y-2">
                    {% for category, message in messages %}
                        <div class="p-4 rounded-lg flex items-center justify-between {% if category == 'error' %}bg-red-900/50 border border-red-500/50 text-red-200{% else %}bg-green-900/50 border border-green-500/50 text-green-200{% endif %}">
                            <span>{{ message }}</span>
                            <button onclick="this.parentElement.style.display='none'" class="text-slate-400 hover:text-white">✕</button>
                        </div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}

        <!-- Dynamic Page Content -->
        {{ content_placeholder | safe }}
    </main>
</body>
</html>
"""

# ==================================================
# ROUTE: EXECUTIVE DASHBOARD
# ==================================================
@app.route('/')
def dashboard():
    conn = get_db_connection()
    if not conn:
        return "Database Error: Please check logs.", 500
    
    try:
        df = pd.read_sql_query("SELECT * FROM analytics", conn)
        
        # Calculate Key Metrics
        if df.empty:
            rev = expenses = net = total_sales = avg_order = 0
            insight_msg = "No data available. Please ingest data to begin analysis."
            revenue_dates = []
            revenue_amounts = []
            risk_counts = [0, 0, 0]
        else:
            rev = df['invoice_amount'].sum()
            expenses = df['expense_amount'].sum()
            net = rev - expenses
            total_sales = df['sales_orders'].sum()
            avg_order = df['average_order_value'].mean()
            
            # Simple AI-like Insight Generation
            profit_margin = (net / rev * 100) if rev > 0 else 0
            if profit_margin > 40:
                insight_msg = f"Strong financial health. Profit margin is exceptionally high at {profit_margin:.1f}%. Recommend scaling marketing expenditure."
            elif profit_margin > 20:
                insight_msg = f"Stable performance. Net margin stands at {profit_margin:.1f}%. Optimization recommended on Logistics expenditure to boost net income."
            else:
                insight_msg = f"Critical alert: Margins are low ({profit_margin:.1f}%). Immediate audit of Operational Expenses required."

            # Chart Data Prep
            # Group revenue by date for the line chart
            df['last_purchase'] = pd.to_datetime(df['last_purchase'])
            rev_trend = df.groupby('last_purchase')['invoice_amount'].sum().reset_index().sort_values('last_purchase')
            revenue_dates = rev_trend['last_purchase'].dt.strftime('%Y-%m-%d').tolist()
            revenue_amounts = rev_trend['invoice_amount'].tolist()

            # Risk distribution for doughnut chart
            risk_dist = df['risk_index'].value_counts().to_dict()
            risk_counts = [
                risk_dist.get('Low', 0),
                risk_dist.get('Medium', 0),
                risk_dist.get('High', 0)
            ]

        content = f"""
        <!-- Executive Pulse Layer -->
        <div class="mb-8 p-6 glass-card rounded-2xl border-l-4 border-orange-500 relative overflow-hidden group">
            <div class="absolute top-0 right-0 p-4 opacity-10">
                <svg class="w-32 h-32" fill="currentColor" viewBox="0 0 24 24"><path d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
            </div>
            <h2 class="text-xs font-bold text-orange-500 uppercase tracking-widest mb-2 flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-orange-500 pulse-ring"></span>
                Executive Pulse & AI Narrative
            </h2>
            <p class="text-2xl font-light text-slate-200 leading-relaxed">{insight_msg}</p>
        </div>

        <!-- The "So What?" Triad Widgets -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <!-- Triad Widget: Gross Revenue -->
            <div class="glass-card p-6 rounded-2xl flex flex-col justify-between">
                <div>
                    <div class="flex justify-between items-start mb-2">
                        <p class="text-slate-400 text-sm font-medium">Gross Revenue</p>
                        <span class="text-xs font-bold px-2 py-1 bg-green-500/10 text-green-400 rounded">+12.5%</span>
                    </div>
                    <h3 class="text-4xl font-black mb-2 text-white">${rev:,.0f}</h3>
                    <p class="text-sm text-slate-400 mb-6">Insight: Tracking ahead of Q2 historical averages.</p>
                </div>
                <div class="flex gap-3 mt-auto">
                    <a href="/revenue-report" class="flex-1 text-center bg-orange-600 hover:bg-orange-500 text-white font-medium px-4 py-2.5 rounded-lg text-sm transition">Investigate</a>
                </div>
            </div>

            <!-- Triad Widget: Risk Assessment -->
            <div class="glass-card p-6 rounded-2xl border border-red-900/50 flex flex-col justify-between">
                <div>
                    <div class="flex justify-between items-start mb-2">
                        <p class="text-slate-400 text-sm font-medium">At-Risk Invoices</p>
                        <span class="text-xs font-bold px-2 py-1 bg-red-500/10 text-red-400 rounded pulse-ring">Action Req</span>
                    </div>
                    <h3 class="text-4xl font-black mb-2 text-red-400">{risk_counts[2]} Clients</h3>
                    <p class="text-sm text-slate-400 mb-6">Alert: High risk detected in logistics flow collections.</p>
                </div>
                <div class="flex gap-3 mt-auto">
                    <a href="/client-report" class="flex-1 text-center bg-red-900/40 hover:bg-red-800 text-red-200 border border-red-800 font-medium px-4 py-2.5 rounded-lg text-sm transition">Remediate Risk</a>
                </div>
            </div>
            
            <!-- Triad Widget: Net Income -->
            <div class="glass-card p-6 rounded-2xl flex flex-col justify-between">
                <div>
                    <div class="flex justify-between items-start mb-2">
                        <p class="text-slate-400 text-sm font-medium">Net Income</p>
                        <span class="text-xs font-bold px-2 py-1 bg-blue-500/10 text-blue-400 rounded">+5.2%</span>
                    </div>
                    <h3 class="text-4xl font-black mb-2 text-white">${net:,.0f}</h3>
                    <p class="text-sm text-slate-400 mb-6">Insight: Operational efficiency improved MoM.</p>
                </div>
                <div class="flex gap-3 mt-auto">
                    <a href="/revenue-report" class="flex-1 text-center bg-slate-800 hover:bg-slate-700 text-white border border-slate-700 font-medium px-4 py-2.5 rounded-lg text-sm transition">View Ledger</a>
                </div>
            </div>
        </div>

        <!-- Charts Section -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
            <div class="glass-card p-6 rounded-2xl lg:col-span-2">
                <h3 class="text-lg font-bold mb-4">Revenue Trend Analysis</h3>
                <div class="relative h-64 w-full">
                    <canvas id="revenueChart"></canvas>
                </div>
            </div>
            <div class="glass-card p-6 rounded-2xl">
                <h3 class="text-lg font-bold mb-4">Client Risk Distribution</h3>
                <div class="relative h-64 w-full flex justify-center">
                    <canvas id="riskChart"></canvas>
                </div>
            </div>
        </div>

        <!-- Recent Analytics Table -->
        <div class="glass-card p-6 rounded-2xl">
            <div class="flex justify-between items-center mb-6">
                <h3 class="text-lg font-bold">Recent Ingestion Records</h3>
                <a href="/invoice-report" class="text-sm text-orange-500 hover:text-orange-400 font-medium">View Full Table &rarr;</a>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="text-xs uppercase text-slate-500 border-b border-slate-800/50">
                            <th class="pb-3 px-4 font-semibold">Invoice ID</th>
                            <th class="pb-3 px-4 font-semibold">Client Name</th>
                            <th class="pb-3 px-4 font-semibold text-right">Revenue</th>
                            <th class="pb-3 px-4 font-semibold text-center">Status</th>
                            <th class="pb-3 px-4 font-semibold">Risk Index</th>
                        </tr>
                    </thead>
                    <tbody class="text-sm">
                        {"".join([f'''
                        <tr class="border-b border-slate-800/30 hover:bg-slate-800/20 transition">
                            <td class="py-4 px-4 font-medium text-slate-300">{r['invoice_id']}</td>
                            <td class="py-4 px-4">{r['client_name']}</td>
                            <td class="py-4 px-4 text-right font-mono">${r['invoice_amount']:,.2f}</td>
                            <td class="py-4 px-4 text-center">
                                <span class="px-2.5 py-1 rounded-full text-xs font-medium {'bg-green-500/10 text-green-400' if r['status'] == 'Paid' else 'bg-yellow-500/10 text-yellow-400' if r['status'] == 'Pending' else 'bg-red-500/10 text-red-400'}">
                                    {r['status']}
                                </span>
                            </td>
                            <td class="py-4 px-4">
                                <span class="flex items-center gap-2">
                                    <span class="w-2 h-2 rounded-full {'bg-red-500' if r['risk_index'] == 'High' else 'bg-yellow-500' if r['risk_index'] == 'Medium' else 'bg-green-500'}"></span>
                                    {r['risk_index']}
                                </span>
                            </td>
                        </tr>
                        ''' for _, r in df.head(5).iterrows()])}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Chart.js Injection -->
        <script>
            // Revenue Line Chart
            const revCtx = document.getElementById('revenueChart').getContext('2d');
            new Chart(revCtx, {{
                type: 'line',
                data: {{
                    labels: {json.dumps(revenue_dates)},
                    datasets: [{{
                        label: 'Gross Revenue ($)',
                        data: {json.dumps(revenue_amounts)},
                        borderColor: '#f97316',
                        backgroundColor: 'rgba(249, 115, 22, 0.1)',
                        borderWidth: 2,
                        pointBackgroundColor: '#020617',
                        pointBorderColor: '#f97316',
                        pointBorderWidth: 2,
                        pointRadius: 4,
                        fill: true,
                        tension: 0.4
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{
                        y: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#94a3b8' }} }},
                        x: {{ grid: {{ display: false }}, ticks: {{ color: '#94a3b8' }} }}
                    }}
                }}
            }});

            // Risk Doughnut Chart
            const riskCtx = document.getElementById('riskChart').getContext('2d');
            new Chart(riskCtx, {{
                type: 'doughnut',
                data: {{
                    labels: ['Low Risk', 'Medium Risk', 'High Risk'],
                    datasets: [{{
                        data: {json.dumps(risk_counts)},
                        backgroundColor: ['#22c55e', '#eab308', '#ef4444'],
                        borderWidth: 0,
                        hoverOffset: 4
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '75%',
                    plugins: {{
                        legend: {{ position: 'bottom', labels: {{ color: '#94a3b8', padding: 20, usePointStyle: true }} }}
                    }}
                }}
            }});
        </script>
        """
        return render_template_string(TEMPLATE, content_placeholder=content, active_page='dashboard')
    
    except Exception as e:
        logger.error(f"Dashboard exception: {e}")
        return f"Internal Server Error: {str(e)}", 500
    finally:
        conn.close()

# ==================================================
# ROUTE: REVENUE REPORT
# ==================================================
@app.route('/revenue-report')
def revenue_report():
    conn = get_db_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM analytics", conn)
        
        # Aggregate by Expense Type
        exp_group = df.groupby('expense_type')['expense_amount'].sum().reset_index()
        
        content = f"""
        <div class="mb-6 flex justify-between items-center">
            <h2 class="text-3xl font-black text-white">Financial Intelligence</h2>
            <button class="bg-slate-800 hover:bg-slate-700 text-sm px-4 py-2 rounded-lg text-white transition flex items-center gap-2">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                Export PDF
            </button>
        </div>

        <div class="glass-card p-6 rounded-2xl mb-8">
            <h3 class="text-lg font-bold mb-4">Expense Allocation Breakdown</h3>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                {"".join([f'''
                <div class="p-4 bg-slate-900/50 rounded-xl border border-slate-800">
                    <p class="text-sm text-slate-400 mb-1">{r["expense_type"]}</p>
                    <p class="text-2xl font-bold text-white">${r["expense_amount"]:,.2f}</p>
                </div>
                ''' for _, r in exp_group.iterrows()])}
            </div>
        </div>
        """
        return render_template_string(TEMPLATE, content_placeholder=content, active_page='revenue')
    finally:
        conn.close()

# ==================================================
# ROUTE: CLIENT REPORT
# ==================================================
@app.route('/client-report')
def client_report():
    conn = get_db_connection()
    try:
        df = pd.read_sql_query("SELECT client_name, purchase_frequency, average_order_value, risk_index, product_preference FROM analytics", conn)
        
        content = f"""
        <div class="mb-6">
            <h2 class="text-3xl font-black text-white">Client Insights & Segmentation</h2>
            <p class="text-slate-400 mt-2">Behavioral analysis and risk profiling for active accounts.</p>
        </div>

        <div class="glass-card p-6 rounded-2xl">
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="text-xs uppercase text-slate-500 border-b border-slate-800/50">
                            <th class="pb-3 px-4 font-semibold">Client Name</th>
                            <th class="pb-3 px-4 font-semibold text-center">Frequency</th>
                            <th class="pb-3 px-4 font-semibold text-right">Avg Order Value</th>
                            <th class="pb-3 px-4 font-semibold">Preference</th>
                            <th class="pb-3 px-4 font-semibold">Risk Index</th>
                        </tr>
                    </thead>
                    <tbody class="text-sm">
                        {"".join([f'''
                        <tr class="border-b border-slate-800/30 hover:bg-slate-800/20 transition">
                            <td class="py-4 px-4 font-bold text-white">{r['client_name']}</td>
                            <td class="py-4 px-4 text-center">
                                <span class="px-2 py-1 rounded bg-slate-800 text-xs border border-slate-700">{r['purchase_frequency']}</span>
                            </td>
                            <td class="py-4 px-4 text-right font-mono">${r['average_order_value']:,.2f}</td>
                            <td class="py-4 px-4 text-slate-300">{r['product_preference']}</td>
                            <td class="py-4 px-4">
                                <span class="flex items-center gap-2 text-xs font-medium uppercase tracking-wider {'text-red-400' if r['risk_index'] == 'High' else 'text-yellow-400' if r['risk_index'] == 'Medium' else 'text-green-400'}">
                                    <span class="w-1.5 h-1.5 rounded-full {'bg-red-500' if r['risk_index'] == 'High' else 'bg-yellow-500' if r['risk_index'] == 'Medium' else 'bg-green-500'}"></span>
                                    {r['risk_index']}
                                </span>
                            </td>
                        </tr>
                        ''' for _, r in df.iterrows()])}
                    </tbody>
                </table>
            </div>
        </div>
        """
        return render_template_string(TEMPLATE, content_placeholder=content, active_page='client')
    finally:
        conn.close()

# ==================================================
# ROUTE: INVOICE REPORT
# ==================================================
@app.route('/invoice-report')
def invoice_report():
    conn = get_db_connection()
    try:
        df = pd.read_sql_query("SELECT invoice_id, client_name, invoice_amount, status, last_purchase FROM analytics ORDER BY id DESC", conn)
        
        content = f"""
        <div class="mb-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
            <div>
                <h2 class="text-3xl font-black text-white">Invoice Ledger</h2>
                <p class="text-slate-400 mt-1">Comprehensive directory of all billing records.</p>
            </div>
            
            <div class="relative w-full md:w-64">
                <input type="text" id="searchInput" onkeyup="filterTable()" placeholder="Search invoices or clients..." class="w-full bg-slate-900 border border-slate-700 text-white rounded-lg pl-10 pr-4 py-2 focus:outline-none focus:border-orange-500 transition">
                <svg class="w-4 h-4 text-slate-400 absolute left-3 top-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
            </div>
        </div>

        <div class="glass-card rounded-2xl overflow-hidden border border-slate-800">
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse" id="invoiceTable">
                    <thead class="bg-slate-900/80">
                        <tr class="text-xs uppercase text-slate-400">
                            <th class="py-4 px-6 font-semibold">Invoice ID</th>
                            <th class="py-4 px-6 font-semibold">Client Name</th>
                            <th class="py-4 px-6 font-semibold">Date</th>
                            <th class="py-4 px-6 font-semibold text-right">Amount</th>
                            <th class="py-4 px-6 font-semibold text-center">Status</th>
                        </tr>
                    </thead>
                    <tbody class="text-sm divide-y divide-slate-800/50">
                        {"".join([f'''
                        <tr class="hover:bg-slate-800/30 transition">
                            <td class="py-4 px-6 font-medium text-slate-300">{r['invoice_id']}</td>
                            <td class="py-4 px-6 font-semibold text-white">{r['client_name']}</td>
                            <td class="py-4 px-6 text-slate-400">{r['last_purchase']}</td>
                            <td class="py-4 px-6 text-right font-mono">${r['invoice_amount']:,.2f}</td>
                            <td class="py-4 px-6 text-center">
                                <span class="px-2.5 py-1 rounded-full text-xs font-medium {'bg-green-500/10 text-green-400 border border-green-500/20' if r['status'] == 'Paid' else 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20' if r['status'] == 'Pending' else 'bg-red-500/10 text-red-400 border border-red-500/20'}">
                                    {r['status']}
                                </span>
                            </td>
                        </tr>
                        ''' for _, r in df.iterrows()])}
                    </tbody>
                </table>
            </div>
            <div id="noResults" class="hidden py-8 text-center text-slate-500">No matching invoices found.</div>
        </div>

        <script>
        function filterTable() {{
            var input, filter, table, tr, td, i, txtValue, found;
            input = document.getElementById("searchInput");
            filter = input.value.toUpperCase();
            table = document.getElementById("invoiceTable");
            tr = table.getElementsByTagName("tr");
            var visibleCount = 0;

            for (i = 1; i < tr.length; i++) {{ // Start at 1 to skip header
                tr[i].style.display = "none";
                td = tr[i].getElementsByTagName("td");
                found = false;
                for (var j = 0; j < td.length; j++) {{
                    if (td[j]) {{
                        txtValue = td[j].textContent || td[j].innerText;
                        if (txtValue.toUpperCase().indexOf(filter) > -1) {{
                            found = true;
                            break;
                        }}
                    }}
                }}
                if (found) {{
                    tr[i].style.display = "";
                    visibleCount++;
                }}
            }}
            
            document.getElementById('noResults').style.display = visibleCount === 0 ? 'block' : 'none';
        }}
        </script>
        """
        return render_template_string(TEMPLATE, content_placeholder=content, active_page='invoice')
    finally:
        conn.close()

# ==================================================
# ROUTE: DATA INGESTION (UPLOAD)
# ==================================================
@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part in the request.', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected for ingestion.', 'error')
            return redirect(request.url)

        if file and (file.filename.endswith('.csv') or file.filename.endswith('.xlsx')):
            try:
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                # Process File based on extension
                if filename.endswith('.csv'):
                    df = pd.read_csv(filepath)
                else:
                    try:
                        df = pd.read_excel(filepath)
                    except ImportError:
                        flash("Server missing 'openpyxl' library for Excel. Please upload CSV.", 'error')
                        return redirect(request.url)

                # Required columns validation
                required_cols = ['invoice_id', 'client_name', 'invoice_amount', 'status']
                if not all(col in df.columns for col in required_cols):
                    flash(f"Data format error. Required columns: {', '.join(required_cols)}", 'error')
                    return redirect(request.url)

                # Push to database
                conn = get_db_connection()
                if conn:
                    # Append new records; Note: in production, handle unique 'invoice_id' constraints elegantly (e.g., ON CONFLICT)
                    df.to_sql('analytics', conn, if_exists='append', index=False)
                    conn.commit()
                    conn.close()
                    flash(f'Successfully ingested {len(df)} records from {filename}.', 'success')
                    return redirect(url_for('dashboard'))
                
            except Exception as e:
                logger.error(f"Ingestion Error: {e}")
                flash(f'Failed to process file: {str(e)}', 'error')
        else:
            flash('Unsupported file format. Please upload .csv or .xlsx', 'error')
            return redirect(request.url)

    content = """
    <div class="max-w-2xl mx-auto">
        <h2 class="text-3xl font-black text-white mb-2">Data Ingestion Pipeline</h2>
        <p class="text-slate-400 mb-8">Upload external data sources to integrate into the enterprise data warehouse. Supported formats: CSV, XLSX.</p>

        <form action="/upload" method="POST" enctype="multipart/form-data" class="glass-card p-8 rounded-2xl border border-slate-700 border-dashed hover:border-orange-500 transition-colors group cursor-pointer text-center relative" onclick="document.getElementById('fileInput').click()">
            <input type="file" name="file" id="fileInput" class="hidden" accept=".csv, .xlsx" onchange="document.getElementById('fileName').textContent = this.files[0].name; document.getElementById('submitBtn').classList.remove('opacity-50', 'cursor-not-allowed');">
            
            <div class="mb-6 flex justify-center">
                <div class="w-16 h-16 rounded-full bg-slate-800 flex items-center justify-center group-hover:bg-orange-500/20 group-hover:text-orange-500 transition">
                    <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path></svg>
                </div>
            </div>
            
            <h3 class="text-lg font-bold text-white mb-1">Click to browse or drag and drop</h3>
            <p class="text-sm text-slate-500 mb-4">Strictly CSV or Excel files. Max size: 16MB.</p>
            
            <div id="fileName" class="text-orange-400 font-medium text-sm mb-6 h-5"></div>

            <button type="submit" id="submitBtn" class="bg-orange-600 hover:bg-orange-500 text-white font-bold py-3 px-8 rounded-lg transition opacity-50 cursor-not-allowed" onclick="event.stopPropagation();">
                Initialize Ingestion
            </button>
        </form>
    </div>
    """
    return render_template_string(TEMPLATE, content_placeholder=content, active_page='upload')

# ==================================================
# APPLICATION ENTRY POINT
# ==================================================
if __name__ == '__main__':
    # Initialize the required infrastructure
    init_db()
    
    # Launch Enterprise Web Server
    logger.info("Starting Enterprise BI Application Server...")
    app.run(debug=Config.DEBUG, port=5000, host='0.0.0.0')