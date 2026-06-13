import os
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import openpyxl
import matplotlib.pyplot as plt
import seaborn as sns

# =====================================================================
# 🎛️ CONFIGURATION MAPPING PANEL
# Change the strings below to match the EXACT column names in your Excel file.
# =====================================================================
EXCEL_FILE_PATH = r"C:\Users\Ruelo\Desktop\Syluxent-Working Copy\analytics test\version 2\ready data\Itemized Demand Data (2025 - may 21 2026)\sales_consolidator_registry_2026-05-19.xlsx"

COLUMN_MAPPING = {
    "CLIENT_ID": "Client ID",
    "ORDER_ID": "Order ID",                   # Name of your unique Transaction/Invoice ID column
    "ORDER_DATE": "Order Date",               # Name of your Transaction Date column
    "ITEM_NAME": "Description / Particulars",  # Name of your Product/Service column
    "AMOUNT": "Total Amount",                 # Name of your Sales Amount column
}

# Number of clusters you want for grouping (3-4 is generally optimal for customer profiles)
NUM_CLUSTERS = 3


# =====================================================================
# 🧼 DATA PIPELINE & CLEANING WING
# =====================================================================
print("🚀 Phase 1: Initiating Excel Data Pipeline using OpenPyXL engine...")

if not os.path.exists(EXCEL_FILE_PATH):
    raise FileNotFoundError(f"❌ Could not find file at path: {EXCEL_FILE_PATH}. Check your file path string.")

# Read the Excel dataset explicitly passing the openpyxl engine
df_raw = pd.read_excel(EXCEL_FILE_PATH, engine="openpyxl")
print(f"✅ Successfully imported raw file containing {len(df_raw)} records.")

print("🧼 Phase 2: Processing data cleaning and type-casting...")

# Check for mapped columns
for col in COLUMN_MAPPING.values():
    if col not in df_raw.columns:
        raise KeyError(f"❌ Column '{col}' defined in COLUMN_MAPPING was not found in the Excel file.")

# Extract relevant columns to match pipeline internal schema
available_cols = {v: k for k, v in COLUMN_MAPPING.items()}
df_clean = df_raw[list(COLUMN_MAPPING.values())].rename(columns=available_cols)

# A. Clean Sales Amount: Convert to numeric, force conversion errors to NaN, drop empty rows
df_clean['AMOUNT'] = pd.to_numeric(df_clean['AMOUNT'], errors='coerce')
df_clean = df_clean.dropna(subset=['AMOUNT'])
df_clean = df_clean[df_clean['AMOUNT'] > 0]  # Strip out negative adjustments or 0 values

# B. Clean Dates: Force string dates into standard system Datetime layout
df_clean['ORDER_DATE'] = pd.to_datetime(df_clean['ORDER_DATE'], errors='coerce')
df_clean = df_clean.dropna(subset=['ORDER_DATE'])

# C. Clean Strings: Convert to string and eliminate empty spaces around text characters
df_clean['CLIENT_ID'] = df_clean['CLIENT_ID'].astype(str).str.strip()
df_clean['ORDER_ID'] = df_clean['ORDER_ID'].astype(str).str.strip()
df_clean['ITEM_NAME'] = df_clean['ITEM_NAME'].astype(str).str.strip()

# Ensure we drop rows if vital string keys are blank or read as 'nan'
df_clean = df_clean[(df_clean['CLIENT_ID'] != '') & (df_clean['CLIENT_ID'] != 'nan')]
df_clean = df_clean[(df_clean['ORDER_ID'] != '') & (df_clean['ORDER_ID'] != 'nan')]

print(f"📊 Cleaning absolute. {len(df_clean)} records passed structural validation audits.\n")


# =====================================================================
# 📈 ALGORITHMIC CALCULATIONS ENGINE
# =====================================================================
print("⚙️ Phase 3: Executing Behavior Calculations Matrix...")
df_clean = df_clean.sort_values("ORDER_DATE").reset_index(drop=True)

# A & B: Total Spend, Total Transaction Volume, and One-Time Buyers
client_totals = df_clean.groupby("CLIENT_ID").agg(
    Total_Spend=("AMOUNT", "sum"),
    Total_Orders=("ORDER_ID", "nunique") # Counting unique invoice keys
).reset_index()

one_time_buyers = client_totals[client_totals["Total_Orders"] == 1]["CLIENT_ID"].tolist()

# C: Extract Favorite/Most Frequently Bought Item Per Client
item_counts = df_clean.groupby(["CLIENT_ID", "ITEM_NAME"]).size().reset_index(name="Item_Count")
most_bought_items = item_counts.sort_values(["CLIENT_ID", "Item_Count"], ascending=[True, False]).drop_duplicates("CLIENT_ID")

# D: Average Re-order Intervals (Velocity Tracking)
df_clean['Prev_Order_Date'] = df_clean.groupby('CLIENT_ID')['ORDER_DATE'].shift(1)
df_clean['Days_Between_Orders'] = (df_clean['ORDER_DATE'] - df_clean['Prev_Order_Date']).dt.days

avg_intervals = df_clean.groupby('CLIENT_ID')['Days_Between_Orders'].mean().reset_index()
avg_intervals['Days_Between_Orders'] = avg_intervals['Days_Between_Orders'].fillna(0).round(1)

# Consolidate Profiles Matrix
client_profiles = client_totals.merge(avg_intervals, on="CLIENT_ID")
client_profiles = client_profiles.merge(most_bought_items[["CLIENT_ID", "ITEM_NAME"]], on="CLIENT_ID")
client_profiles.rename(columns={"Days_Between_Orders": "Avg_Order_Interval_Days", "ITEM_NAME": "Favorite_Item"}, inplace=True)


# =====================================================================
# 🤖 K-MEANS BEHAVIORAL SEGMENTATION
# =====================================================================
print("🤖 Phase 4: Constructing Cluster Segmentation Models...")

features_to_cluster = ["Total_Spend", "Total_Orders", "Avg_Order_Interval_Days"]

# Scale features so that large currency scales don't mathematically out-weigh days intervals
scaler = StandardScaler()
scaled_features = scaler.fit_transform(client_profiles[features_to_cluster])

# Run K-Means Clustering Model
kmeans = KMeans(n_clusters=NUM_CLUSTERS, random_state=42, n_init=10)
client_profiles["Cluster_ID"] = kmeans.fit_predict(scaled_features)


# =====================================================================
# 📋 SYSTEM STATUS REPORTS
# =====================================================================
print("\n" + "="*50)
print("✨ REAL DATA INSIGHTS ENGINE COMPLETED ✨")
print("="*50 + "\n")

# a. Top 10 Clients
print("🏆 A. TOP 10 CLIENTS BY SALES VOLUME:")
top_10 = client_profiles.sort_values("Total_Spend", ascending=False).head(10)
for idx, row in top_10.iterrows():
    print(f"   - {row['CLIENT_ID']}: ₱{row['Total_Spend']:,.2f} ({row['Total_Orders']} distinct orders)")

# b. One-Time Buyers
print("\n🙋‍♂️ B. ONE-TIME BUYERS RUNNING SUMMARY:")
print(f"   - Found {len(one_time_buyers)} clients who made exactly 1 purchase.")
if len(one_time_buyers) > 0:
    print(f"     Sample Profile Names: {', '.join(one_time_buyers[:5])}...")

# c & d. Comprehensive Profile View Preview
print("\n📊 C & D. CUSTOMER ENGAGEMENT PROFILES (Top 5 Active Sample):")
preview_profiles = client_profiles.sort_values("Total_Orders", ascending=False).head(5)
for idx, row in preview_profiles.iterrows():
    interval_txt = f"every {row['Avg_Order_Interval_Days']} days" if row['Avg_Order_Interval_Days'] > 0 else "N/A (One-time buyer)"
    print(f"   - {row['CLIENT_ID']}: Prefers ordering '{row['Favorite_Item']}' with touchpoints occurring roughly {interval_txt}.")

# e. Algorithmic Client Cluster Profiles
print("\n📁 E. SYSTEM DETECTED CUSTOMER BEHAVIORAL GROUPS:")
for cluster in sorted(client_profiles["Cluster_ID"].unique()):
    cluster_group = client_profiles[client_profiles["Cluster_ID"] == cluster]
    print(f"\n   📂 [Group/Cluster ID: {cluster}] Characteristics:")
    print(f"     • Total Client Count: {len(cluster_group)}")
    print(f"     • Average Client Group Spend: ₱{cluster_group['Total_Spend'].mean():,.2f}")
    print(f"     • Average Orders Placed: {cluster_group['Total_Orders'].mean():.1f} times")
    print(f"     • Average Transaction Loop Frequency: Every {cluster_group['Avg_Order_Interval_Days'].mean():.1f} days")

print("\n📊 Phase 5: Generating Behavioral Analytics Dashboard Charts...")

# =====================================================================
# 📊 PHASE 5: DATA VISUALIZATION WING
# =====================================================================

# Set a clean, professional aesthetic style for the dashboard window
sns.set_theme(style="whitegrid")
fig, axes = plt.subplots(1, 2, figsize=(16, 6))

# Main overall dashboard title arrangement
fig.suptitle("📌 Customer Behavioral Segmentation Analytics", fontsize=16, fontweight='bold')
fig.subplots_adjust(top=0.85) # Creates structural room for the main heading

# Chart 1: Behavioral Scatter Plot Matrix (Spend vs. Order Volume)
sns.scatterplot(
    ax=axes[0],
    data=client_profiles,
    x="Total_Orders",
    y="Total_Spend",
    hue="Cluster_ID",
    palette="deep",
    s=100,
    alpha=0.8,
    edgecolor="w"
)
axes[0].set_title("Customer Clusters: Transaction Count vs Total Spend", fontsize=12, fontweight='bold', pad=15)
axes[0].set_xlabel("Total Orders Placed (Distinct Count)", fontsize=11)
axes[0].set_ylabel("Total Revenue Spend (₱)", fontsize=11)
axes[0].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'₱{x:,.0f}'))
axes[0].legend(title="Cluster ID", loc="upper left")

# Chart 2: Revenue Impact Analysis Per Segment (Bar Chart Summary)
cluster_revenue = client_profiles.groupby("Cluster_ID")["Total_Spend"].sum().reset_index()

sns.barplot(
    ax=axes[1],
    data=cluster_revenue,
    x="Cluster_ID",
    y="Total_Spend",
    palette="deep",
    hue="Cluster_ID",
    legend=False
)
axes[1].set_title("Total Revenue Distribution by Behavioral Group", fontsize=12, fontweight='bold', pad=15)
axes[1].set_xlabel("Cluster / Behavioral Group ID", fontsize=11)
axes[1].set_ylabel("Combined Group Revenue (₱)", fontsize=11)
axes[1].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'₱{x:,.0f}'))

# Automatically optimize margins and space between figures
plt.tight_layout()

# Render the interactive graphic dashboard frame to your monitor screen
print("🚀 Launching interactive visual chart panel window...")
plt.show()