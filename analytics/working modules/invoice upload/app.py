# app.py
import os
import re
import sqlite3
from datetime import datetime
from flask import Flask, request, render_template_string, redirect, url_for, flash
import pandas as pd
from flask import send_file
from io import BytesIO

app = Flask(__name__)
app.secret_key = "invoice_mapper_secret"

DB_NAME = "invoice_mapper.db"
UPLOAD_FOLDER = "uploads"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# =========================================================
# DATABASE
# =========================================================

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def create_table():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS historical_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        sheet_name TEXT,
        service_invoice TEXT,
        sales_invoice TEXT,
        invoice_date TEXT,
        client TEXT,
        particulars TEXT,

        total_amount REAL,
        downpayment_date TEXT,
        fullpayment_date TEXT,
        amount_paid REAL,

        tax_payable REAL,
        accounts_receivable REAL,

        invoice_status TEXT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()


# =========================================================
# HELPERS
# =========================================================

MONTHS = [
    "JANUARY", "FEBRUARY", "MARCH", "APRIL",
    "MAY", "JUNE", "JULY", "AUGUST",
    "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"
]


def normalize_sheet_name(sheet_name):
    if not sheet_name:
        return "UNKNOWN"

    cleaned = str(sheet_name).strip().upper()

    for month in MONTHS:
        if month[:3] in cleaned or month in cleaned:
            return month

    return cleaned


def safe_string(value):
    if pd.isna(value):
        return ""

    return str(value).strip()


def parse_amount(value):
    try:
        if pd.isna(value):
            return 0.0

        value = str(value).replace(",", "").replace("₱", "").strip()

        if value == "":
            return 0.0

        return float(value)

    except:
        return 0.0


def parse_date(value):
    if pd.isna(value):
        return ""

    value = str(value).strip()

    if value == "":
        return ""

    date_formats = [
        "%d-%b",
        "%m/%d/%Y",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%b-%d",
        "%d-%b-%Y"
    ]

    for fmt in date_formats:
        try:
            parsed = datetime.strptime(value, fmt)

            # Add current year if no year
            if parsed.year == 1900:
                parsed = parsed.replace(year=datetime.now().year)

            return parsed.strftime("%Y-%m-%d")
        except:
            pass

    try:
        parsed = pd.to_datetime(value)
        return parsed.strftime("%Y-%m-%d")
    except:
        return value


def is_valid_row(row):
    non_empty = 0

    for val in row:
        if str(val).strip() not in ["", "nan", "None"]:
            non_empty += 1

    return non_empty > 1


def compute_tax_and_ar(total_amount, amount_paid):
    difference = round(total_amount - amount_paid, 2)

    if difference <= 0:
        return 0.0, 0.0

    vat_reference = ((total_amount / 1.12) * 0.01)

    lower_limit = vat_reference * 0.01
    upper_limit = vat_reference * 0.10

    # TAX PAYABLE + AR
    if lower_limit <= difference <= upper_limit:
        return round(difference, 2), round(difference, 2)

    # AR ONLY
    return 0.0, round(difference, 2)


def detect_headers(df):
    important_headers = {
        "SERVICE INVOICE": None,
        "SALES INVOICE": None,
        "DATE": None,
        "CLIENT": None,
        "PARTICULARS": None,
        "TOTAL AMOUNT": None,
        "DOWNPAYMENT": None,
        "FULLPAYMENT": None
    }

    header_row_index = None

    for idx in range(len(df)):
        row = df.iloc[idx]

        for col_idx, value in enumerate(row):
            text = str(value).strip().upper()

            for key in important_headers.keys():
                if key in text:
                    important_headers[key] = col_idx
                    header_row_index = idx

    return header_row_index, important_headers


# =========================================================
# EXCEL PROCESSING
# =========================================================

def process_excel(file_path):
    excel_file = pd.ExcelFile(file_path)

    conn = get_connection()
    cur = conn.cursor()

    preview_data = []

    for sheet in excel_file.sheet_names:

        normalized_sheet = normalize_sheet_name(sheet)

        try:
            df = pd.read_excel(
                file_path,
                sheet_name=sheet,
                header=None,
                dtype=str
            )

            header_row_index, headers = detect_headers(df)

            if header_row_index is None:
                continue

            for idx in range(header_row_index + 1, len(df)):

                row = df.iloc[idx]

                if not is_valid_row(row):
                    continue

                try:
                    service_invoice = safe_string(
                        row[headers["SERVICE INVOICE"]]
                    ) if headers["SERVICE INVOICE"] is not None else ""

                    sales_invoice = safe_string(
                        row[headers["SALES INVOICE"]]
                    ) if headers["SALES INVOICE"] is not None else ""

                    invoice_date = parse_date(
                        row[headers["DATE"]]
                    ) if headers["DATE"] is not None else ""

                    client = safe_string(
                        row[headers["CLIENT"]]
                    ) if headers["CLIENT"] is not None else ""

                    particulars = safe_string(
                        row[headers["PARTICULARS"]]
                    ) if headers["PARTICULARS"] is not None else ""

                    total_amount = parse_amount(
                        row[headers["TOTAL AMOUNT"]]
                    ) if headers["TOTAL AMOUNT"] is not None else 0.0

                    downpayment_date = parse_date(
                        row[headers["DOWNPAYMENT"]]
                    ) if headers["DOWNPAYMENT"] is not None else ""

                    fullpayment_date = parse_date(
                        row[headers["FULLPAYMENT"]]
                    ) if headers["FULLPAYMENT"] is not None else ""

                    # Next column after FULLPAYMENT = Amount Paid
                    amount_paid_col = None

                    if headers["FULLPAYMENT"] is not None:
                        amount_paid_col = headers["FULLPAYMENT"] + 1

                    amount_paid = 0.0

                    if amount_paid_col is not None and amount_paid_col < len(row):
                        amount_paid = parse_amount(row[amount_paid_col])

                    tax_payable, accounts_receivable = compute_tax_and_ar(
                        total_amount,
                        amount_paid
                    )

                    combined_text = " ".join(
                        [str(v).upper() for v in row.values]
                    )

                    if "CANCEL" in combined_text:
                        invoice_status = "CANCELLED"
                    else:
                        balance = round(total_amount - amount_paid, 2)

                        if balance <= 0:
                            invoice_status = "PAID"
                        else:
                            invoice_status = "PENDING"
                    cur.execute("""
                    INSERT INTO historical_data (
                        sheet_name,
                        service_invoice,
                        sales_invoice,
                        invoice_date,
                        client,
                        particulars,
                        total_amount,
                        downpayment_date,
                        fullpayment_date,
                        amount_paid,
                        tax_payable,
                        accounts_receivable,
                        invoice_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        normalized_sheet,
                        service_invoice,
                        sales_invoice,
                        invoice_date,
                        client,
                        particulars,
                        total_amount,
                        downpayment_date,
                        fullpayment_date,
                        amount_paid,
                        tax_payable,
                        accounts_receivable,
                        invoice_status
                    ))

                    preview_data.append({
                        "sheet": normalized_sheet,
                        "service_invoice": service_invoice,
                        "sales_invoice": sales_invoice,
                        "date": invoice_date,
                        "client": client,
                        "particulars": particulars,
                        "total_amount": total_amount,
                        "amount_paid": amount_paid,
                        "tax_payable": tax_payable,
                        "accounts_receivable": accounts_receivable,
                        "status": invoice_status
                    })

                except Exception as row_error:
                    print("ROW ERROR:", row_error)

        except Exception as sheet_error:
            print("SHEET ERROR:", sheet_error)

    conn.commit()
    conn.close()

    return preview_data


# =========================================================
# ROUTES
# =========================================================

@app.route("/export")
def export_excel():

    conn = get_connection()

    df = pd.read_sql_query("""
        SELECT *
        FROM historical_data
        ORDER BY invoice_date ASC
    """, conn)

    conn.close()

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Historical Data")

    output.seek(0)

    return send_file(
        output,
        download_name="historical_data.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@app.route("/", methods=["GET", "POST"])
def index():

    preview_data = []

    if request.method == "POST":

        if "excel_file" not in request.files:
            flash("No file uploaded")
            return redirect(request.url)

        file = request.files["excel_file"]

        if file.filename == "":
            flash("No selected file")
            return redirect(request.url)

        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)

        preview_data = process_excel(filepath)

        flash("Excel file processed successfully!")

    conn = get_connection()
    records = conn.execute("""
        SELECT *
        FROM historical_data
        ORDER BY id DESC
        LIMIT 5
    """).fetchall()

    total_rows = conn.execute("""
        SELECT COUNT(*) as count
        FROM historical_data
    """).fetchone()["count"]

    earliest_record = conn.execute("""
        SELECT invoice_date
        FROM historical_data
        WHERE invoice_date IS NOT NULL
        ORDER BY invoice_date ASC
        LIMIT 1
    """).fetchone()

    latest_record = conn.execute("""
        SELECT invoice_date
        FROM historical_data
        WHERE invoice_date IS NOT NULL
        ORDER BY invoice_date DESC
        LIMIT 1
    """).fetchone()

    earliest_date = earliest_record["invoice_date"] if earliest_record else "N/A"
    latest_date = latest_record["invoice_date"] if latest_record else "N/A"

    conn.close()

    return render_template_string(
        TEMPLATE,
        preview_data=preview_data,
        records=records,
        total_rows=total_rows,
        earliest_date=earliest_date,
        latest_date=latest_date
)


# =========================================================
# UI TEMPLATE
# =========================================================

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Invoice Mapper Dashboard</title>

    <style>

        *{
            margin:0;
            padding:0;
            box-sizing:border-box;
        }

        body{
            font-family:Segoe UI, Arial;
            background:#f1f5f9;
            padding:30px;
            color:#222;
        }

        .container{
            max-width:1600px;
            margin:auto;
        }

        .header{
            margin-bottom:30px;
        }

        .header h1{
            font-size:34px;
            margin-bottom:10px;
        }

        .header p{
            color:#666;
        }

        .card-grid{
            display:grid;
            grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
            gap:20px;
            margin-bottom:30px;
        }

        .card{
            background:white;
            border-radius:14px;
            padding:20px;
            box-shadow:0 2px 10px rgba(0,0,0,0.06);
        }

        .card h3{
            font-size:14px;
            color:#777;
            margin-bottom:10px;
        }

        .card .value{
            font-size:28px;
            font-weight:bold;
        }

        .upload-box{
            background:white;
            padding:25px;
            border-radius:14px;
            margin-bottom:30px;
            box-shadow:0 2px 10px rgba(0,0,0,0.06);
        }

        .upload-box form{
            display:flex;
            gap:15px;
            align-items:center;
            flex-wrap:wrap;
        }

        input[type=file]{
            padding:10px;
            background:#f8fafc;
            border:1px solid #ddd;
            border-radius:8px;
        }

        button,
        .export-btn{
            padding:12px 20px;
            border:none;
            border-radius:8px;
            background:#111827;
            color:white;
            cursor:pointer;
            text-decoration:none;
            font-weight:600;
        }

        button:hover,
        .export-btn:hover{
            opacity:0.9;
        }

        .table-card{
            background:white;
            border-radius:14px;
            padding:20px;
            margin-bottom:30px;
            box-shadow:0 2px 10px rgba(0,0,0,0.06);
            overflow:auto;
        }

        .table-title{
            display:flex;
            justify-content:space-between;
            align-items:center;
            margin-bottom:20px;
        }

        table{
            width:100%;
            border-collapse:collapse;
        }

        th{
            background:#0f172a;
            color:white;
            padding:14px;
            font-size:13px;
            text-align:left;
        }

        td{
            padding:12px;
            border-bottom:1px solid #eee;
            font-size:13px;
        }

        tr:hover{
            background:#f8fafc;
        }

        .badge{
            padding:6px 10px;
            border-radius:20px;
            font-size:11px;
            font-weight:bold;
            display:inline-block;
        }

        .paid{
            background:#dcfce7;
            color:#166534;
        }

        .pending{
            background:#fef3c7;
            color:#92400e;
        }

        .cancelled{
            background:#fee2e2;
            color:#991b1b;
        }

        .success{
            background:#dcfce7;
            color:#166534;
            padding:12px;
            border-radius:10px;
            margin-bottom:20px;
        }

    </style>
</head>

<body>

<div class="container">

    <div class="header">
        <h1>Invoice Mapper Dashboard</h1>
        <p>Excel Consolidation • SQLite Storage • Invoice Analytics</p>
    </div>

    {% with messages = get_flashed_messages() %}
        {% if messages %}
            {% for msg in messages %}
                <div class="success">{{ msg }}</div>
            {% endfor %}
        {% endif %}
    {% endwith %}

    <div class="card-grid">

        <div class="card">
            <h3>Total Rows</h3>
            <div class="value">{{ total_rows }}</div>
        </div>

        <div class="card">
            <h3>Earliest Data</h3>
            <div class="value" style="font-size:18px;">
                {{ earliest_date }}
            </div>
        </div>

        <div class="card">
            <h3>Most Current Data</h3>
            <div class="value" style="font-size:18px;">
                {{ latest_date }}
            </div>
        </div>

    </div>

    <div class="upload-box">

        <form method="POST" enctype="multipart/form-data">

            <input
                type="file"
                name="excel_file"
                accept=".xlsx,.xls"
            >

            <button type="submit">
                Upload Excel File
            </button>

            <a href="/export" class="export-btn">
                Export Database as Excel
            </a>

        </form>

    </div>

    <div class="table-card">

        <div class="table-title">
            <h2>Preview (First 5 Rows)</h2>
        </div>

        <table>

            <thead>
                <tr>
                    <th>Sheet</th>
                    <th>Service Invoice</th>
                    <th>Sales Invoice</th>
                    <th>Date</th>
                    <th>Client</th>
                    <th>Total</th>
                    <th>Paid</th>
                    <th>Tax</th>
                    <th>Balance</th>
                    <th>Status</th>
                </tr>
            </thead>

            <tbody>

            {% for row in preview_data[:5] %}

                <tr>

                    <td>{{ row.sheet }}</td>

                    <td>{{ row.service_invoice }}</td>

                    <td>{{ row.sales_invoice }}</td>

                    <td>{{ row.date }}</td>

                    <td>{{ row.client }}</td>

                    <td>{{ row.total_amount }}</td>

                    <td>{{ row.amount_paid }}</td>

                    <td>{{ row.tax_payable }}</td>

                    <td>{{ row.accounts_receivable }}</td>

                    <td>

                        {% if row.status == "PAID" %}
                            <span class="badge paid">
                                PAID
                            </span>

                        {% elif row.status == "PENDING" %}
                            <span class="badge pending">
                                PENDING
                            </span>

                        {% else %}
                            <span class="badge cancelled">
                                CANCELLED
                            </span>
                        {% endif %}

                    </td>

                </tr>

            {% endfor %}

            </tbody>

        </table>

    </div>

    <div class="table-card">

        <div class="table-title">
            <h2>Historical Records (Latest 5)</h2>
        </div>

        <table>

            <thead>
                <tr>
                    <th>ID</th>
                    <th>Sheet</th>
                    <th>Client</th>
                    <th>Total</th>
                    <th>Paid</th>
                    <th>Tax</th>
                    <th>Balance</th>
                    <th>Status</th>
                </tr>
            </thead>

            <tbody>

            {% for row in records %}

                <tr>

                    <td>{{ row.id }}</td>

                    <td>{{ row.sheet_name }}</td>

                    <td>{{ row.client }}</td>

                    <td>{{ row.total_amount }}</td>

                    <td>{{ row.amount_paid }}</td>

                    <td>{{ row.tax_payable }}</td>

                    <td>{{ row.accounts_receivable }}</td>

                    <td>

                        {% if row.invoice_status == "PAID" %}
                            <span class="badge paid">
                                PAID
                            </span>

                        {% elif row.invoice_status == "PENDING" %}
                            <span class="badge pending">
                                PENDING
                            </span>

                        {% else %}
                            <span class="badge cancelled">
                                CANCELLED
                            </span>
                        {% endif %}

                    </td>

                </tr>

            {% endfor %}

            </tbody>

        </table>

    </div>

</div>

</body>
</html>
"""


# =========================================================
# START APP
# =========================================================

if __name__ == "__main__":
    create_table()
    app.run(debug=True)
