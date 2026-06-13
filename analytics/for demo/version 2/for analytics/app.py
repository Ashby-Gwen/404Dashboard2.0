import os
import numpy as np
import pandas as pd
from flask import Flask, render_template_string
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import plotly.express as px
import plotly.io as pio

app = Flask(__name__)

# =====================================================================
# 🎛️ CONFIGURATION MAPPING PANEL
# =====================================================================
EXCEL_FILE_PATH = r"C:\Users\Ruelo\Desktop\Syluxent-Working Copy\analytics test\version 2\ready data\Itemized Demand Data (2025 - may 21 2026)\sales_consolidator_registry_2026-05-19.xlsx"

# Raw columns required to execute your formula definitions
RAW_COMPONENTS = [
    "Company Name", 
    "Store Name", 
    "Store Branch / Address", 
    "SO Number"
]

COLUMN_MAPPING = {
    "ORDER_DATE": "Order Date",
    "ITEM_NAME": "Description / Particulars",
    "AMOUNT": "Total Amount",
}

NUM_CLUSTERS = 3

def run_analytics_pipeline():
    """Reads raw data, builds custom formula columns dynamically, and applies cleaning arrays."""
    if not os.path.exists(EXCEL_FILE_PATH):
        raise FileNotFoundError(f"❌ Could not find file at path: {EXCEL_FILE_PATH}")

    # Read the Excel dataset
    df_raw = pd.read_excel(EXCEL_FILE_PATH, engine="openpyxl")
    
    # Structural verification check
    required_cols = list(COLUMN_MAPPING.values()) + RAW_COMPONENTS
    for col in required_cols:
        if col not in df_raw.columns:
            raise KeyError(f"❌ Required column '{col}' was not found in your Excel spreadsheet file layout.")

    # 🛠️ DYNAMIC CONCATENATION ENGINE (Replicating your Excel Formulas)
    print("🔗 Programmatically generating unified transaction columns...")
    
    # Formitize text entries to strip out erratic whitespace bugs
    for col in RAW_COMPONENTS:
        df_raw[col] = df_raw[col].fillna("").astype(str).str.strip()

    # Formula 1: Client ID = [Company Name] - [Store Name] - [Store Branch / Address]
    df_raw['CLIENT_ID'] = df_raw["Company Name"] + " - " + df_raw["Store Name"] + " - " + df_raw["Store Branch / Address"]
    
    # Formula 2: Order ID = [Client ID] - [SO Number]
    df_raw['ORDER_ID'] = df_raw['CLIENT_ID'] + " - " + df_raw["SO Number"]

    # Extract relevant metrics targets to fit internal schema pipeline
    available_cols = {v: k for k, v in COLUMN_MAPPING.items()}
    df_clean = df_raw[list(COLUMN_MAPPING.values()) + ['CLIENT_ID', 'ORDER_ID']].rename(columns=available_cols)

    # Clean Sales Amounts
    df_clean['AMOUNT'] = pd.to_numeric(df_clean['AMOUNT'], errors='coerce')
    df_clean = df_clean.dropna(subset=['AMOUNT'])
    df_clean = df_clean[df_clean['AMOUNT'] > 0]

    # Clean Transaction Dates
    df_clean['ORDER_DATE'] = pd.to_datetime(df_clean['ORDER_DATE'], errors='coerce')
    df_clean = df_clean.dropna(subset=['ORDER_DATE'])

    # Strip and evaluate final string integrity matrices
    df_clean['CLIENT_ID'] = df_clean['CLIENT_ID'].str.strip()
    df_clean['ORDER_ID'] = df_clean['ORDER_ID'].str.strip()
    df_clean['ITEM_NAME'] = df_clean['ITEM_NAME'].astype(str).str.strip()

    df_clean = df_clean[(df_clean['CLIENT_ID'] != '') & (df_clean['CLIENT_ID'] != 'nan') & (df_clean['CLIENT_ID'] != ' -  - ')]
    df_clean = df_clean[(df_clean['ORDER_ID'] != '') & (df_clean['ORDER_ID'] != 'nan')]

    # Chronological sort sequencing
    df_clean = df_clean.sort_values("ORDER_DATE").reset_index(drop=True)

    # Group Behavioral Summary Calculations
    client_totals = df_clean.groupby("CLIENT_ID").agg(
        Total_Spend=("AMOUNT", "sum"),
        Total_Orders=("ORDER_ID", "nunique")
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

    # Machine Learning Clustering Space
    features_to_cluster = ["Total_Spend", "Total_Orders", "Avg_Order_Interval_Days"]
    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(client_profiles[features_to_cluster])

    kmeans = KMeans(n_clusters=NUM_CLUSTERS, random_state=42, n_init=10)
    client_profiles["Cluster_ID"] = kmeans.fit_predict(scaled_features)
    
    return client_profiles, one_time_buyers

# =====================================================================
# 🎨 WEB DASHBOARD VIEW TEMPLATE
# =====================================================================
DASHBOARD_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Syluxent Analytics Hub</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.0/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f4f6f9; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .dashboard-header { background: linear-gradient(135deg, #1e4620 0%, #0f2310 100%); color: white; padding: 25px; border-radius: 0 0 15px 15px; margin-bottom: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        .metric-card { background: white; border: none; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); padding: 20px; transition: transform 0.2s; }
        .metric-card:hover { transform: translateY(-3px); }
        .table-container { background: white; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); padding: 20px; margin-bottom: 30px; }
        .cluster-tag { padding: 4px 10px; border-radius: 20px; font-weight: 600; font-size: 0.85em; }
        .c-0 { background-color: #e3f2fd; color: #0d47a1; }
        .c-1 { background-color: #e8f5e9; color: #1b5e20; }
        .c-2 { background-color: #fff3e0; color: #e65100; }
    </style>
</head>
<body>

<div class="container-fluid px-4">
    <div class="dashboard-header d-flex justify-content-between align-items-center">
        <div>
            <h1 class="m-0 h3 font-weight-bold">🎯 Strategic Customer Analytics Terminal</h1>
            <p class="m-0 opacity-75 text-sm">Dynamic string merging models and clustering engines</p>
        </div>
        <span class="badge bg-light text-success fs-6 px-3 py-2">Status: Connected</span>
    </div>

    <div class="row g-4 mb-4">
        <div class="col-md-4">
            <div class="metric-card">
                <h6 class="text-muted text-uppercase small">Total Active Accounts</h6>
                <h2 class="text-dark font-weight-bold m-0">{{ total_clients }}</h2>
            </div>
        </div>
        <div class="col-md-4">
            <div class="metric-card">
                <h6 class="text-muted text-uppercase small">One-Time Retention Leakage</h6>
                <h2 class="text-danger font-weight-bold m-0">{{ total_onetime }} <span class="fs-6 fw-normal text-muted">Accounts</span></h2>
            </div>
        </div>
        <div class="col-md-4">
            <div class="metric-card">
                <h6 class="text-muted text-uppercase small">Total Gross Tracked Revenue</h6>
                <h2 class="text-success font-weight-bold m-0">₱{{ "{:,.2f}".format(total_revenue) }}</h2>
            </div>
        </div>
    </div>

    <div class="row g-4 mb-4">
        <div class="col-lg-7">
            <div class="table-container">
                <h5 class="mb-3 fw-bold">🗺️ Behavioral Segmentation Space Matrix</h5>
                {{ scatter_div|safe }}
            </div>
        </div>
        <div class="col-lg-5">
            <div class="table-container">
                <h5 class="mb-3 fw-bold">💰 Revenue Breakdown by Group Segment</h5>
                {{ bar_div|safe }}
            </div>
        </div>
    </div>

    <div class="table-container">
        <h5 class="mb-4 fw-bold">📋 Complete Customer Engagement Profiles Table</h5>
        <div class="table-responsive">
            <table class="table table-hover align-middle">
                <thead class="table-light">
                    <tr>
                        <th>Customer / Client Unique ID String</th>
                        <th class="text-end">Total Spend (₱)</th>
                        <th class="text-center">Total Orders</th>
                        <th class="text-center">Avg Loop Frequency</th>
                        <th>Favorite Product Particular</th>
                        <th class="text-center">Cluster Assignment</th>
                    </tr>
                </thead>
                <tbody>
                    {% for idx, row in client_data.iterrows() %}
                    <tr>
                        <td class="fw-medium text-secondary" style="max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ row['CLIENT_ID'] }}</td>
                        <td class="text-end fw-bold text-dark">₱{{ "{:,.2f}".format(row['Total_Spend']) }}</td>
                        <td class="text-center fw-bold">{{ row['Total_Orders'] }}</td>
                        <td class="text-center text-muted">
                            {% if row['Avg_Order_Interval_Days'] > 0 %}
                                Every {{ row['Avg_Order_Interval_Days'] }} days
                            {% else %}
                                N/A (One-time)
                            {% endif %}
                        </td>
                        <td><span class="text-truncate d-inline-block text-muted" style="max-width: 250px;">{{ row['Favorite_Item'] }}</span></td>
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

</body>
</html>
"""

# =====================================================================
# 🕸️ APPS SYSTEM ROUTER ENDPOINTS
# =====================================================================
@app.route('/')
def load_web_dashboard():
    client_profiles, one_time_buyers = run_analytics_pipeline()
    
    total_clients = len(client_profiles)
    total_onetime = len(one_time_buyers)
    total_revenue = client_profiles['Total_Spend'].sum()

    render_df = client_profiles.sort_values('Total_Spend', ascending=False)

    # Build Scatter Plot using official 'plotly_white' registry layout
    fig_scatter = px.scatter(
        render_df, 
        x="Total_Orders", 
        y="Total_Spend",
        color=render_df["Cluster_ID"].astype(str),
        hover_name="CLIENT_ID",
        labels={"Total_Orders": "Total Distinct Orders placed", "Total_Spend": "Total Gross Value (₱)", "color": "Cluster Group ID"},
        title="Account Volume Matrix Space"
    )
    fig_scatter.update_traces(marker=dict(size=12, line=dict(width=1, color='White')))
    fig_scatter.update_layout(template="plotly_white", margin=dict(l=20, r=20, t=40, b=20))
    scatter_div = pio.to_html(fig_scatter, full_html=False, include_plotlyjs='cdn')

    # Build Bar Chart using official 'plotly_white' registry layout
    cluster_rev = render_df.groupby("Cluster_ID")["Total_Spend"].sum().reset_index()
    fig_bar = px.bar(
        cluster_rev, 
        x="Cluster_ID", 
        y="Total_Spend",
        color=cluster_rev["Cluster_ID"].astype(str),
        labels={"Total_Spend": "Aggregated Revenue Contribution (₱)", "Cluster_ID": "Cluster Designation Key"},
        title="Financial Revenue Breakdown Across Profiles"
    )
    fig_bar.update_layout(template="plotly_white", showlegend=False, margin=dict(l=20, r=20, t=40, b=20))
    bar_div = pio.to_html(fig_bar, full_html=False, include_plotlyjs='cdn')

    return render_template_string(
        DASHBOARD_HTML_TEMPLATE,
        total_clients=total_clients,
        total_onetime=total_onetime,
        total_revenue=total_revenue,
        client_data=render_df,
        scatter_div=scatter_div,
        bar_div=bar_div
    )

if __name__ == '__main__':
    app.run(debug=True)