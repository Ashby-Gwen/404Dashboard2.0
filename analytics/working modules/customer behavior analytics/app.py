import os
import numpy as np
import pandas as pd
from flask import Flask, render_template_string
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

app = Flask(__name__)

# =====================================================================
# 🎛️ CONFIGURATION MAPPING PANEL
# =====================================================================
EXCEL_FILE_PATH = r"C:\Users\Ruelo\Desktop\Capstone (Redeem)\2026\System\Syluxent-Working Copy\analytics\data\Ready data\Itemized Demand Data (2025 - may 21 2026)\sales_consolidator_registry_2026-05-19.xlsx"

RAW_COMPONENTS = ["Company Name", "SO Number"]
COLUMN_MAPPING = {
    "ORDER_DATE": "Order Date",
    "ITEM_NAME": "Description / Particulars",
    "AMOUNT": "Total Amount",
}
NUM_CLUSTERS = 3

def run_analytics_pipeline():
    if not os.path.exists(EXCEL_FILE_PATH):
        raise FileNotFoundError(f"❌ Could not find file at path: {EXCEL_FILE_PATH}")

    df_raw = pd.read_excel(EXCEL_FILE_PATH, engine="openpyxl")
    
    required_cols = list(COLUMN_MAPPING.values()) + RAW_COMPONENTS
    for col in required_cols:
        if col not in df_raw.columns:
            raise KeyError(f"❌ Required column '{col}' was not found.")

    # Generate company-level customer and order keys.
    for col in RAW_COMPONENTS:
        df_raw[col] = df_raw[col].fillna("").astype(str).str.strip()

    df_raw['CLIENT_ID'] = df_raw["Company Name"]
    df_raw['ORDER_ID'] = df_raw['CLIENT_ID'] + " - " + df_raw["SO Number"]

    available_cols = {v: k for k, v in COLUMN_MAPPING.items()}
    df_clean = df_raw[list(COLUMN_MAPPING.values()) + ['CLIENT_ID', 'ORDER_ID']].rename(columns=available_cols)

    df_clean['AMOUNT'] = pd.to_numeric(df_clean['AMOUNT'], errors='coerce')
    df_clean = df_clean.dropna(subset=['AMOUNT'])
    df_clean = df_clean[df_clean['AMOUNT'] > 0]

    df_clean['ORDER_DATE'] = pd.to_datetime(df_clean['ORDER_DATE'], errors='coerce')
    df_clean = df_clean.dropna(subset=['ORDER_DATE'])

    df_clean['CLIENT_ID'] = df_clean['CLIENT_ID'].str.strip()
    df_clean['ORDER_ID'] = df_clean['ORDER_ID'].str.strip()
    df_clean['ITEM_NAME'] = df_clean['ITEM_NAME'].astype(str).str.strip()

    df_clean = df_clean[df_clean['CLIENT_ID'] != '']
    df_clean = df_clean.sort_values("ORDER_DATE").reset_index(drop=True)

    client_totals = df_clean.groupby("CLIENT_ID").agg(
        Total_Spend=("AMOUNT", "sum"),
        Total_Orders=("ORDER_ID", "nunique"),
        Last_Purchase_Date=("ORDER_DATE", "max"),
        First_Purchase_Date=("ORDER_DATE", "min")
    ).reset_index()

    one_time_buyers = client_totals[client_totals["Total_Orders"] == 1]["CLIENT_ID"].tolist()

    item_counts = df_clean.groupby(["CLIENT_ID", "ITEM_NAME"]).size().reset_index(name="Item_Count")
    most_bought_items = item_counts.sort_values(["CLIENT_ID", "Item_Count"], ascending=[True, False]).drop_duplicates("CLIENT_ID")

    df_clean['Prev_Order_Date'] = df_clean.groupby('CLIENT_ID')['ORDER_DATE'].shift(1)
    df_clean['Days_Between_Orders'] = (df_clean['ORDER_DATE'] - df_clean['Prev_Order_Date']).dt.days

    avg_intervals = df_clean.groupby('CLIENT_ID')['Days_Between_Orders'].mean().reset_index()
    avg_intervals['Days_Between_Orders'] = avg_intervals['Days_Between_Orders'].fillna(0).round(1)

    client_profiles = client_totals.merge(avg_intervals, on="CLIENT_ID")
    client_profiles = client_profiles.merge(most_bought_items[["CLIENT_ID", "ITEM_NAME"]], on="CLIENT_ID")
    client_profiles.rename(columns={"Days_Between_Orders": "Avg_Order_Interval_Days", "ITEM_NAME": "Favorite_Item"}, inplace=True)

    print("Processing buying behavior forecasting parameters...")
    current_anchor_date = max(pd.Timestamp.today().normalize(), df_clean['ORDER_DATE'].max().normalize())
    
    client_profiles['Days_Since_Last_Order'] = (current_anchor_date - client_profiles['Last_Purchase_Date']).dt.days
    active_days = (client_profiles['Last_Purchase_Date'] - client_profiles['First_Purchase_Date']).dt.days + 1
    client_profiles['Buying_Frequency_30D'] = ((client_profiles['Total_Orders'] / active_days.clip(lower=30)) * 30).round(2)

    total_pipeline_days = (current_anchor_date - client_profiles['First_Purchase_Date']).dt.days.replace(0, 1)
    client_profiles['Daily_Value_Velocity'] = client_profiles['Total_Spend'] / total_pipeline_days
    client_profiles['Predicted_30Day_Spend'] = (client_profiles['Daily_Value_Velocity'] * 30).round(2)

    spend_threshold = client_profiles['Total_Spend'].median()
    frequency_threshold = client_profiles['Buying_Frequency_30D'].median()
    projected_spend_threshold = client_profiles['Predicted_30Day_Spend'].median()
    
    next_dates = []
    risk_statuses = []
    
    for idx, row in client_profiles.iterrows():
        if row['Total_Orders'] > 1 and row['Avg_Order_Interval_Days'] > 0:
            predicted_date = row['Last_Purchase_Date'] + pd.to_timedelta(int(round(row['Avg_Order_Interval_Days'])), unit='D')
            next_dates.append(predicted_date.strftime('%Y-%m-%d'))
            interval_risk = row['Days_Since_Last_Order'] / row['Avg_Order_Interval_Days']
        else:
            next_dates.append("N/A (One-Time)")
            interval_risk = 2.25 if row['Days_Since_Last_Order'] > 90 else 1.25

        risk_score = 0
        if interval_risk > 2:
            risk_score += 3
        elif interval_risk > 1:
            risk_score += 1.5

        if row['Buying_Frequency_30D'] < frequency_threshold:
            risk_score += 1
        if row['Total_Spend'] < spend_threshold:
            risk_score += 0.75
        if row['Total_Orders'] <= 1:
            risk_score += 1
        if row['Predicted_30Day_Spend'] < projected_spend_threshold:
            risk_score += 0.75

        if risk_score >= 3.5:
            risk_statuses.append("High Risk")
        elif risk_score >= 1.75:
            risk_statuses.append("Warning")
        else:
            risk_statuses.append("Active")

    client_profiles['Predicted_Next_Order'] = next_dates
    client_profiles['Churn_Risk'] = risk_statuses

    features_to_cluster = ["Total_Spend", "Total_Orders", "Buying_Frequency_30D", "Avg_Order_Interval_Days", "Predicted_30Day_Spend"]
    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(client_profiles[features_to_cluster])

    kmeans = KMeans(n_clusters=NUM_CLUSTERS, random_state=42, n_init=10)
    client_profiles["Cluster_ID"] = kmeans.fit_predict(scaled_features)
    
    cluster_mapping = client_profiles.set_index('CLIENT_ID')['Cluster_ID'].to_dict()
    df_clean['Cluster_ID'] = df_clean['CLIENT_ID'].map(cluster_mapping)
    
    return client_profiles, one_time_buyers, df_clean

# =====================================================================
# 🎨 WEB DASHBOARD VIEW TEMPLATE
# =====================================================================
DASHBOARD_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Syluxent Executive Analytics</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.0/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { 
            background-color: #f8fafc; 
            font-family: 'Inter', sans-serif; 
            color: #1e293b;
        }
        
        .dashboard-header { 
            background: linear-gradient(135deg, #0f2e16 0%, #06150a 100%); 
            color: #ffffff; 
            padding: 30px 40px; 
            border-radius: 0 0 24px 24px; 
            margin-bottom: 20px;
            box-shadow: 0 10px 25px -5px rgba(15, 46, 22, 0.15), 0 8px 10px -6px rgba(15, 46, 22, 0.15);
            border-bottom: 3px solid #10b981;
        }

        .dashboard-header h1 {
            font-size: 1.75rem;
            font-weight: 700;
            letter-spacing: -0.025em;
        }

        /* Coverage Banner Ribbon */
        .coverage-banner {
            background-color: #e2e8f0;
            border-radius: 12px;
            padding: 12px 24px;
            margin-bottom: 25px;
            border-left: 5px solid #64748b;
            font-size: 0.9rem;
            font-weight: 500;
            color: #334155;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 10px;
        }

        .metric-card { 
            background: #ffffff; 
            border: 1px solid #e2e8f0; 
            border-radius: 16px; 
            padding: 24px; 
            position: relative;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02), 0 2px 4px -1px rgba(0,0,0,0.02);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .metric-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
            background: #cbd5e1;
        }

        .metric-card.accent-emerald::before { background: #10b981; }
        .metric-card.accent-rose::before { background: #f43f5e; }
        .metric-card.accent-slate::before { background: #64748b; }
        .metric-card.accent-blue::before { background: #3b82f6; }

        .metric-card:hover { 
            transform: translateY(-4px); 
            box-shadow: 0 12px 20px -8px rgba(0, 0, 0, 0.08);
            border-color: #cbd5e1;
        }

        .metric-card h6 {
            font-size: 0.825rem;
            font-weight: 600;
            color: #64748b;
            letter-spacing: 0.05em;
            margin-bottom: 12px;
        }

        .metric-card h3 {
            font-size: 1.85rem;
            font-weight: 700;
            letter-spacing: -0.03em;
            color: #0f172a;
        }

        .content-panel { 
            background: #ffffff; 
            border: 1px solid #e2e8f0;
            border-radius: 20px; 
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02), 0 2px 4px -1px rgba(0,0,0,0.02);
            padding: 28px; 
            margin-bottom: 35px; 
        }

        .panel-title {
            font-size: 1.125rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: #0f172a;
            margin-bottom: 24px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* Tabs custom design */
        .nav-tabs-custom {
            border-bottom: 2px solid #e2e8f0;
            margin-bottom: 24px;
            gap: 10px;
        }

        .nav-tabs-custom .nav-link {
            border: none;
            color: #64748b;
            font-weight: 600;
            padding: 10px 20px;
            border-radius: 10px 10px 0 0;
            transition: all 0.2s;
            position: relative;
        }

        .nav-tabs-custom .nav-link:hover {
            color: #0f2e16;
            background-color: #f1f5f9;
        }

        .nav-tabs-custom .nav-link.active {
            color: #0f2e16;
            background-color: transparent;
        }

        .nav-tabs-custom .nav-link.active::after {
            content: '';
            position: absolute;
            bottom: -2px;
            left: 0;
            width: 100%;
            height: 3px;
            background-color: #10b981;
            border-radius: 99px;
        }

        .table-wrapper {
            max-height: 500px;
            overflow-y: auto;
            border-radius: 12px;
            border: 1px solid #f1f5f9;
        }

        .table-wrapper::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        .table-wrapper::-webkit-scrollbar-track {
            background: #f1f5f9;
        }
        .table-wrapper::-webkit-scrollbar-thumb {
            background: #cbd5e1;
            border-radius: 4px;
        }

        .table-custom {
            margin-bottom: 0;
        }

        .table-custom thead th {
            background-color: #f8fafc;
            color: #475569;
            font-weight: 600;
            font-size: 0.775rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            padding: 14px 18px;
            border-bottom: 2px solid #e2e8f0;
            position: sticky;
            top: 0;
            z-index: 10;
        }

        .table-custom tbody td {
            padding: 14px 18px;
            font-size: 0.875rem;
            color: #334155;
            border-bottom: 1px solid #f1f5f9;
        }

        .table-custom tbody tr:hover td {
            background-color: #f8fafc;
        }

        .badge-pill {
            display: inline-flex;
            align-items: center;
            padding: 6px 12px;
            border-radius: 9999px;
            font-weight: 600;
            font-size: 0.75rem;
            gap: 6px;
        }

        .badge-risk-active { background-color: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0; }
        .badge-risk-warning { background-color: #fffbef; color: #854d0e; border: 1px solid #fef08a; }
        .badge-risk-high { background-color: #fff5f5; color: #991b1b; border: 1px solid #fecaca; }

        .cluster-tag { 
            padding: 5px 12px; 
            border-radius: 10px; 
            font-weight: 600; 
            font-size: 0.75rem; 
            display: inline-block;
        }
        .c-0 { background-color: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }
        .c-1 { background-color: #fff7ed; color: #9a3412; border: 1px solid #ffedd5; }
        .c-2 { background-color: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; }

        .sticky-col-header {
            background: #f1f5f9 !important;
            font-weight: 700 !important;
        }
        
        .highlight-predictive-col {
            background-color: #fcfdfe;
        }
    </style>
</head>
<body>

<div class="container-fluid px-4 px-md-5">
    <!-- Header banner -->
    <div class="dashboard-header d-flex flex-column flex-md-row justify-content-between align-items-start align-items-md-center gap-3">
        <div>
            <h1>🔮 Strategic Customer Predictive Terminal</h1>
            <p class="m-0 opacity-75 text-sm">Real-time churn risk indicators and forward-looking purchasing velocity forecasts</p>
        </div>
        <span class="badge bg-light text-success fs-6 px-3 py-2 border border-success border-opacity-25">Predictive Model: Active</span>
    </div>

    <!-- Earliest and Most Current Date Summary Banner -->
    <div class="coverage-banner shadow-sm">
        <div>
            <span>📅 <b>Data Coverage Window:</b> Analyze raw transactional records logged across your systems.</span>
        </div>
        <div>
            <span class="badge bg-white text-dark py-2 px-3 border border-slate-300 me-2"><b>Earliest Date:</b> {{ earliest_date }}</span>
            <span class="badge bg-success text-white py-2 px-3"><b>Most Current:</b> {{ latest_date }}</span>
        </div>
    </div>

    <!-- Metrics row -->
    <div class="row g-4 mb-4">
        <div class="col-sm-6 col-lg-3">
            <div class="metric-card accent-slate">
                <h6>TOTAL ACTIVE COMPANIES</h6>
                <h3>{{ total_clients }}</h3>
            </div>
        </div>
        <div class="col-sm-6 col-lg-3">
            <div class="metric-card accent-rose">
                <h6>HIGH CHURN RISK ACCOUNTS</h6>
                <h3>{{ total_high_risk }}</h3>
            </div>
        </div>
        <div class="col-sm-6 col-lg-3">
            <div class="metric-card accent-emerald">
                <h6>GROSS TRACKED REVENUE</h6>
                <h3 class="text-success">₱{{ "{:,.2f}".format(total_revenue) }}</h3>
            </div>
        </div>
        <div class="col-sm-6 col-lg-3">
            <div class="metric-card accent-blue">
                <h6>PROJECTED NEXT 30-DAY VALUE</h6>
                <h3 class="text-primary">₱{{ "{:,.2f}".format(predicted_30day_total) }}</h3>
            </div>
        </div>
    </div>

    <!-- Forecasting Line Chart Section -->
    <div class="row mb-4">
        <div class="col-12">
            <div class="content-panel">
                <div class="panel-title">📈 Dynamic Behavior Timeline Analysis</div>
                {{ behavior_line_div|safe }}
            </div>
        </div>
    </div>

    <!-- Two-column row for subcharts -->
    <div class="row g-4 mb-4">
        <div class="col-lg-7">
            <div class="content-panel h-100">
                <div class="panel-title">🗺️ Behavioral Segmentation Space Mapping</div>
                {{ scatter_div|safe }}
            </div>
        </div>
        <div class="col-lg-5">
            <div class="content-panel h-100">
                <div class="panel-title">💰 Group Revenue Contributions</div>
                {{ bar_div|safe }}
            </div>
        </div>
    </div>

    <!-- Interactive Data Logs Section -->
    <div class="content-panel">
        <div class="panel-title">📋 Consolidated Datasets Panel</div>
        
        <!-- Navigation Tab Interfaces -->
        <ul class="nav nav-tabs nav-tabs-custom" id="dashboardTabs" role="tablist">
            <li class="nav-item" role="presentation">
                <button class="nav-link active" id="behavior-tab" data-bs-toggle="tab" data-bs-target="#behavior-content" type="button" role="tab" aria-controls="behavior-content" aria-selected="true">👥 Customer Behavioral Matrix</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="registry-tab" data-bs-toggle="tab" data-bs-target="#registry-content" type="button" role="tab" aria-controls="registry-content" aria-selected="false">📑 Full Raw Transaction Log</button>
            </li>
        </ul>

        <!-- Tabbed Content Areas -->
        <div class="tab-content" id="dashboardTabsContent">
            
            <!-- Tab A: Clustered Behavior Profiles Matrix -->
            <div class="tab-pane fade show active" id="behavior-content" role="tabpanel" aria-labelledby="behavior-tab">
                <div class="table-wrapper">
                    <table class="table table-custom align-middle">
                        <thead>
                            <tr>
                                <th class="sticky-col-header">Company Name</th>
                                <th class="text-end">Historical Spend</th>
                                <th class="text-center">Order Count</th>
                                <th class="text-center">Buying Frequency</th>
                                <th class="text-center">Interval (Days)</th>
                                <th class="text-center">Most Recent Purchase</th>
                                <th class="text-center bg-light text-primary">Predicted Next Order</th>
                                <th class="text-end bg-light text-primary">Projected 30D Spend</th>
                                <th class="text-center">Churn Risk Status</th>
                                <th class="text-center">Cluster</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for idx, row in client_data.iterrows() %}
                            <tr>
                                <td class="fw-semibold text-secondary sticky-col-header" style="max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{{ row['CLIENT_ID'] }}">
                                    {{ row['CLIENT_ID'] }}
                                </td>
                                <td class="text-end fw-bold">₱{{ "{:,.2f}".format(row['Total_Spend']) }}</td>
                                <td class="text-center fw-semibold">{{ row['Total_Orders'] }}</td>
                                <td class="text-center fw-semibold">{{ "{:,.2f}".format(row['Buying_Frequency_30D']) }} / 30D</td>
                                <td class="text-center text-muted">{{ row['Avg_Order_Interval_Days'] }}</td>
                                <td class="text-center fw-semibold">{{ row['Last_Purchase_Date'].strftime('%Y-%m-%d') }}</td>
                                <td class="text-center fw-bold text-primary highlight-predictive-col">{{ row['Predicted_Next_Order'] }}</td>
                                <td class="text-end fw-bold text-primary highlight-predictive-col">₱{{ "{:,.2f}".format(row['Predicted_30Day_Spend']) }}</td>
                                <td class="text-center">
                                    {% if row['Churn_Risk'] == 'Active' %}
                                        <span class="badge-pill badge-risk-active">🟢 Active</span>
                                    {% elif row['Churn_Risk'] == 'Warning' %}
                                        <span class="badge-pill badge-risk-warning">🟡 Warning</span>
                                    {% else %}
                                        <span class="badge-pill badge-risk-high">🔴 High Risk</span>
                                    {% endif %}
                                </td>
                                <td class="text-center">
                                    <span class="cluster-tag c-{{ row['Cluster_ID'] }}">Group {{ row['Cluster_ID'] }}</span>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Tab B: Expanded Raw Data Log -->
            <div class="tab-pane fade" id="registry-content" role="tabpanel" aria-labelledby="registry-tab">
                <div class="table-wrapper">
                    <table class="table table-custom align-middle">
                        <thead>
                            <tr>
                                <th class="sticky-col-header">Transaction Date</th>
                                <th class="sticky-col-header">Company Name</th>
                                <th>Order ID Reference</th>
                                <th>Product / Service Particular Description</th>
                                <th class="text-end">Billing Amount</th>
                                <th class="text-center">Group Cluster ID</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for idx, row in raw_transactions.iterrows() %}
                            <tr>
                                <td class="fw-bold text-dark sticky-col-header">{{ row['ORDER_DATE'].strftime('%Y-%m-%d') }}</td>
                                <td class="fw-semibold text-secondary text-truncate" style="max-width: 250px;" title="{{ row['CLIENT_ID'] }}">{{ row['CLIENT_ID'] }}</td>
                                <td class="text-muted small text-truncate" style="max-width: 180px;" title="{{ row['ORDER_ID'] }}">{{ row['ORDER_ID'] }}</td>
                                <td class="text-truncate" style="max-width: 280px;" title="{{ row['ITEM_NAME'] }}">{{ row['ITEM_NAME'] }}</td>
                                <td class="text-end fw-bold text-success">₱{{ "{:,.2f}".format(row['AMOUNT']) }}</td>
                                <td class="text-center">
                                    <span class="cluster-tag c-{{ row['Cluster_ID'] }}">Group {{ row['Cluster_ID'] }}</span>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>

        </div>
    </div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.0/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

@app.route('/')
def load_web_dashboard():
    client_profiles, one_time_buyers, df_clean = run_analytics_pipeline()
    
    # Extract structural dates variables
    earliest_date = df_clean['ORDER_DATE'].min().strftime('%B %d, %Y')
    latest_date = df_clean['ORDER_DATE'].max().strftime('%B %d, %Y')

    total_clients = len(client_profiles)
    total_revenue = client_profiles['Total_Spend'].sum()
    total_high_risk = len(client_profiles[client_profiles['Churn_Risk'] == 'High Risk'])
    predicted_30day_total = client_profiles['Predicted_30Day_Spend'].sum()

    render_df = client_profiles.sort_values('Total_Spend', ascending=False)

    # 1. Scatter Visualization Configuration
    fig_scatter = px.scatter(
        render_df, x="Total_Orders", y="Total_Spend",
        color=render_df["Cluster_ID"].astype(str), hover_name="CLIENT_ID",
        labels={"Total_Orders": "Orders", "Total_Spend": "Value (₱)", "color": "Cluster"},
        color_discrete_map={'0': '#1e40af', '1': '#9a3412', '2': '#166534'}
    )
    fig_scatter.update_traces(marker=dict(size=14, line=dict(width=1, color='White')))
    fig_scatter.update_layout(
        template="plotly_white", 
        margin=dict(l=20, r=20, t=20, b=20),
        xaxis_title="Lifetime Orders (Count)",
        yaxis_title="Total Historical Spend (₱)"
    )
    scatter_div = pio.to_html(fig_scatter, full_html=False, include_plotlyjs='cdn')

    # 2. Bar Summary Custom Palette Map
    cluster_rev = render_df.groupby("Cluster_ID")["Total_Spend"].sum().reset_index()
    fig_bar = px.bar(
        cluster_rev, x="Cluster_ID", y="Total_Spend", color=cluster_rev["Cluster_ID"].astype(str),
        color_discrete_map={'0': '#1e40af', '1': '#9a3412', '2': '#166534'}
    )
    fig_bar.update_layout(
        template="plotly_white", 
        showlegend=False, 
        margin=dict(l=20, r=20, t=20, b=20),
        xaxis_title="Cluster Group Key",
        yaxis_title="Accumulated Revenue (₱)"
    )
    bar_div = pio.to_html(fig_bar, full_html=False, include_plotlyjs='cdn')

    # 3. Monthly Line Trends Map
    monthly_trends = (
        df_clean.groupby([pd.Grouper(key='ORDER_DATE', freq='ME'), 'Cluster_ID'])['AMOUNT']
        .sum()
        .unstack(fill_value=0)
    )
    
    fig_line = go.Figure()
    cluster_colors = {'0': '#1e40af', '1': '#9a3412', '2': '#166534'}
    
    historical_timeline = monthly_trends.index
    last_historical_point = historical_timeline[-1]
    future_timeline = pd.date_range(start=last_historical_point + pd.Timedelta(days=1), periods=2, freq='ME')

    for cluster in monthly_trends.columns:
        c_str = str(int(cluster))
        color = cluster_colors.get(c_str, '#64748B')
        
        # Historical Trace
        fig_line.add_trace(go.Scatter(
            x=historical_timeline, 
            y=monthly_trends[cluster],
            mode='lines+markers',
            name=f'Group {c_str} (Historical)',
            line=dict(color=color, width=3),
            marker=dict(size=6)
        ))
        
        # Forecast Trace Vector
        historical_values = monthly_trends[cluster].values
        if len(historical_values) >= 2:
            last_delta = historical_values[-1] - historical_values[-2]
            forecasted_value = max(0, historical_values[-1] + last_delta)
            
            prediction_dates = [last_historical_point, future_timeline[0]]
            prediction_values = [historical_values[-1], forecasted_value]
            
            fig_line.add_trace(go.Scatter(
                x=prediction_dates,
                y=prediction_values,
                mode='lines',
                name=f'Group {c_str} (Predicted)',
                line=dict(color=color, width=3, dash='dash'),
                showlegend=True
            ))

    fig_line.update_layout(
        xaxis_title="Timeline Interval",
        yaxis_title="Aggregated Revenue Volume (₱)",
        template="plotly_white",
        hovermode="x unified",
        margin=dict(l=30, r=30, t=20, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    behavior_line_div = pio.to_html(fig_line, full_html=False, include_plotlyjs='cdn')

    # Sort raw historical transaction rows chronologically descending for display log audits
    raw_sorted_transactions = df_clean.sort_values('ORDER_DATE', ascending=False)

    return render_template_string(
        DASHBOARD_HTML_TEMPLATE,
        earliest_date=earliest_date,
        latest_date=latest_date,
        total_clients=total_clients,
        total_high_risk=total_high_risk,
        total_revenue=total_revenue,
        predicted_30day_total=predicted_30day_total,
        client_data=render_df,
        raw_transactions=raw_sorted_transactions,
        scatter_div=scatter_div,
        bar_div=bar_div,
        behavior_line_div=behavior_line_div
    )

if __name__ == '__main__':
    app.run(debug=True)
