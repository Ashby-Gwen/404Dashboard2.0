"""Analytics calculations for Syluxent.

Maintenance guide:
- Add new report logic as a small function that accepts db/models and returns plain dict/list data.
- Expose that function through build_analytics_payload() when the manager UI should display it.
- Keep database reads here, and keep Flask route/request handling in app.py.
- For UI changes, edit templates/analytics.html and consume the JSON keys returned by this module via API routes.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any
# add numpy, scikit-learn

# create an improve rule based recommendations where the developer can 
    # easily add new rules based on the data patterns they observe in the analytics. 
    # This can be a simple function that takes in the analytics data and applies a set 
    # of predefined rules to generate actionable insights or recommendations for the 
    # manager for each data presented in the UI. 


import pandas as pd
from sqlalchemy import func


MAPE_DEFAULT_THRESHOLD = 20.0


def numeric(value: Any, digits: int | None = None) -> float:
    """Return plain JSON-safe numbers for analytics responses."""
    number = float(value or 0)
    return round(number, digits) if digits is not None else number


def normalize_company_match_key(value: Any) -> str:
    text = str(value or "").upper().replace("&", " AND ")
    text = re_sub_non_company(text)
    return " ".join(text.split())


def re_sub_non_company(value: str) -> str:
    import re
    value = re.sub(r"[.,]", " ", value)
    return re.sub(r"[^A-Z0-9\s]", " ", value)


def company_match_percent(left: Any, right: Any) -> float:
    left_key = normalize_company_match_key(left)
    right_key = normalize_company_match_key(right)
    if not left_key or not right_key:
        return 0
    if left_key == right_key:
        return 100
    return SequenceMatcher(None, left_key, right_key).ratio() * 100


def best_company_match(name: Any, candidates: list[str], threshold: float = 85) -> str | None:
    normalized = normalize_company_match_key(name)
    if not normalized:
        return None
    exact_lookup = {normalize_company_match_key(candidate): candidate for candidate in candidates}
    if normalized in exact_lookup:
        return exact_lookup[normalized]
    best = None
    best_score = 0
    for candidate in candidates:
        score = company_match_percent(name, candidate)
        if score > best_score:
            best = candidate
            best_score = score
    return best if best_score >= threshold else None


def build_analytics_payload(db: Any, models: dict[str, Any]) -> dict[str, Any]:
    """Build the complete manager analytics payload from current system data."""
    Client = models["Client"]
    Invoice = models["Invoice"]
    PurchaseOrder = models["PurchaseOrder"]
    SalesOrder = models["SalesOrder"]
    SalesOrderItem = models["SalesOrderItem"]

    today = datetime.now().date()
    paid_revenue = db.session.query(func.sum(Invoice.amount_paid)).filter(Invoice.status == "PAID").scalar() or 0
    unpaid_receivable = db.session.query(func.sum(Invoice.balance)).filter(Invoice.status != "PAID").scalar() or 0
    total_expenses = db.session.query(func.sum(PurchaseOrder.cash_amount)).scalar() or 0
    pondo = max(paid_revenue - total_expenses, 0)

    return {
        "summary": {
            "paid_revenue": numeric(paid_revenue, 2),
            "accounts_receivable": numeric(unpaid_receivable, 2),
            "expenses": numeric(total_expenses, 2),
            "pondo_remaining": numeric(pondo, 2),
            "next_month_pondo": numeric(pondo, 2),
        },
        "weekly_cashflow": _weekly_cashflow(db, Invoice, PurchaseOrder, today),
        "monthly_cashflow": _monthly_cashflow(db, Invoice, PurchaseOrder, today),
        "revenue_by_client": _revenue_by_client(db, Client, SalesOrder, Invoice),
        "sales_performance": _sales_performance(SalesOrder, Invoice),
        "revenue_leakage": _revenue_leakage(db, Client, SalesOrder, Invoice),
        "accounts_receivable": _accounts_receivable(db, Client, SalesOrder, Invoice),
        "client_balances": _client_balances(db, Client, SalesOrder, Invoice),
        "top_items": _top_items(db, SalesOrderItem),
        "demand_predictions": _demand_predictions(db, SalesOrderItem),
        "purchase_recommendations": _purchase_recommendations(db, SalesOrderItem, pondo),
    }



def preview_excel_workbook(file_storage: Any, max_rows: int = 25) -> dict[str, Any]:
    """Read every sheet in an uploaded Excel workbook as previewable table data."""
    workbook = pd.read_excel(file_storage, sheet_name=None)
    sheets = []
    for sheet_name, frame in workbook.items():
        clean = frame.fillna("")
        sheets.append(
            {
                "sheet_name": sheet_name,
                "columns": [str(column) for column in clean.columns],
                "row_count": int(len(clean)),
                "rows": clean.head(max_rows).to_dict(orient="records"),
            }
        )
    return {"sheets": sheets}


def _weekly_cashflow(db: Any, Invoice: Any, PurchaseOrder: Any, today: Any) -> list[dict[str, Any]]:
    month_start = today.replace(day=1)
    week_start = month_start
    week_number = 1
    rows = []
    while week_start <= today:
        week_end = min(week_start + timedelta(days=6), today)
        rows.append(
            {
                "day": f"Week {week_number}",
                "revenue": _invoice_revenue(db, Invoice, week_start, week_end),
                "expenses": _purchase_expenses(db, PurchaseOrder, week_start, week_end),
            }
        )
        week_start = week_end + timedelta(days=1)
        week_number += 1
    return rows


def _monthly_cashflow(db: Any, Invoice: Any, PurchaseOrder: Any, today: Any) -> list[dict[str, Any]]:
    rows = []
    for month in range(1, 13):
        month_start = today.replace(month=month, day=1)
        if month == 12:
            month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = today.replace(month=month + 1, day=1) - timedelta(days=1)
        rows.append(
            {
                "month": month_start.strftime("%b"),
                "revenue": _invoice_revenue(db, Invoice, month_start, month_end),
                "expenses": _purchase_expenses(db, PurchaseOrder, month_start, month_end),
            }
        )
    return rows


def _invoice_revenue(db: Any, Invoice: Any, start: Any, end: Any) -> float:
    return numeric(
        db.session.query(func.sum(Invoice.amount_paid))
        .filter(Invoice.status == "PAID", Invoice.invoice_date >= start, Invoice.invoice_date <= end)
        .scalar()
    )


def _purchase_expenses(db: Any, PurchaseOrder: Any, start: Any, end: Any) -> float:
    return numeric(
        db.session.query(func.sum(PurchaseOrder.cash_amount))
        .filter(PurchaseOrder.date >= start, PurchaseOrder.date <= end)
        .scalar()
    )


def _revenue_by_client(db: Any, Client: Any, SalesOrder: Any, Invoice: Any) -> list[dict[str, Any]]:
    rows = (
        db.session.query(Client.client_name, func.sum(Invoice.amount_paid).label("revenue"))
        .select_from(Client)
        .join(SalesOrder, Client.id == SalesOrder.client_id)
        .join(Invoice, SalesOrder.id == Invoice.sales_order_id)
        .filter(Invoice.status == "PAID")
        .group_by(Client.id)
        .order_by(func.sum(Invoice.amount_paid).desc())
        .limit(10)
        .all()
    )
    return [{"client_name": row.client_name, "revenue": numeric(row.revenue, 2)} for row in rows]


def _sales_performance(SalesOrder: Any, Invoice: Any) -> list[dict[str, Any]]:
    rows = []
    now = datetime.now()
    for i in range(6):
        start = now - timedelta(days=i * 30)
        end = start + timedelta(days=30)
        rows.append(
            {
                "period": start.strftime("%b %Y"),
                "sales_count": SalesOrder.query.filter(SalesOrder.created_at >= start, SalesOrder.created_at < end).count(),
                "invoice_count": Invoice.query.filter(Invoice.created_at >= start, Invoice.created_at < end).count(),
            }
        )
    return list(reversed(rows))


def _revenue_leakage(db: Any, Client: Any, SalesOrder: Any, Invoice: Any) -> dict[str, Any] | None:
    rows = (
        db.session.query(
            Client.client_name,
            func.sum(Invoice.balance).label("unpaid_amount"),
            func.avg(func.julianday(func.current_date()) - func.julianday(Invoice.invoice_date)).label("days_outstanding"),
        )
        .select_from(Client)
        .join(SalesOrder, Client.id == SalesOrder.client_id)
        .join(Invoice, SalesOrder.id == Invoice.sales_order_id)
        .filter(Invoice.status != "PAID")
        .group_by(Client.id)
        .all()
    )
    if not rows:
        return None
    highest = max(rows, key=lambda row: row.unpaid_amount or 0)
    total_unpaid = sum(row.unpaid_amount or 0 for row in rows)
    percent = round((highest.unpaid_amount or 0) / total_unpaid * 100, 2) if total_unpaid else 0
    return {
        "client_name": highest.client_name,
        "unpaid_amount": numeric(highest.unpaid_amount, 2),
        "days_outstanding": int(highest.days_outstanding or 0),
        "impact_amount": numeric(highest.unpaid_amount, 2),
        "percentage_of_total": percent,
        "analysis": f"{highest.client_name} has the highest outstanding balance and should be prioritized for collection.",
    }


def _accounts_receivable(db: Any, Client: Any, SalesOrder: Any, Invoice: Any) -> list[dict[str, Any]]:
    rows = (
        db.session.query(
            SalesOrder.so_number,
            Client.client_name,
            Invoice.invoice_number,
            Invoice.invoice_date,
            Invoice.total_amount,
            Invoice.balance,
            Invoice.status,
        )
        .select_from(SalesOrder)
        .join(Client, SalesOrder.client_id == Client.id)
        .join(Invoice, SalesOrder.id == Invoice.sales_order_id)
        .filter(Invoice.status != "PAID")
        .order_by(Invoice.invoice_date.asc())
        .all()
    )
    return [
        {
            "so_number": row.so_number,
            "client_name": row.client_name,
            "invoice_number": row.invoice_number,
            "invoice_date": row.invoice_date.isoformat() if row.invoice_date else None,
            "total_amount": numeric(row.total_amount, 2),
            "balance": numeric(row.balance, 2),
            "status": row.status,
        }
        for row in rows
    ]


def _client_balances(db: Any, Client: Any, SalesOrder: Any, Invoice: Any) -> list[dict[str, Any]]:
    rows = (
        db.session.query(Client.client_name, func.sum(Invoice.balance).label("balance"))
        .select_from(Client)
        .join(SalesOrder, Client.id == SalesOrder.client_id)
        .join(Invoice, SalesOrder.id == Invoice.sales_order_id)
        .group_by(Client.id)
        .order_by(func.sum(Invoice.balance).desc())
        .all()
    )
    return [{"client_name": row.client_name, "balance": numeric(row.balance, 2)} for row in rows]


def _top_items(db: Any, SalesOrderItem: Any) -> list[dict[str, Any]]:
    rows = (
        db.session.query(
            SalesOrderItem.particular,
            func.sum(SalesOrderItem.quantity).label("quantity_sold"),
            func.sum(SalesOrderItem.total).label("sales_total"),
            func.avg(SalesOrderItem.unit_cost).label("avg_unit_cost"),
        )
        .group_by(SalesOrderItem.particular)
        .order_by(func.sum(SalesOrderItem.quantity).desc())
        .limit(20)
        .all()
    )
    return [
        {
            "item": row.particular,
            "quantity_sold": numeric(row.quantity_sold),
            "sales_total": numeric(row.sales_total, 2),
            "avg_unit_cost": numeric(row.avg_unit_cost, 2),
        }
        for row in rows
    ]


def _demand_predictions(db: Any, SalesOrderItem: Any) -> list[dict[str, Any]]:
    rows = (
        db.session.query(
            SalesOrderItem.particular,
            func.sum(SalesOrderItem.quantity).label("quantity_sold"),
            func.count(SalesOrderItem.id).label("line_count"),
            func.avg(SalesOrderItem.unit_cost).label("avg_unit_cost"),
        )
        .group_by(SalesOrderItem.particular)
        .order_by(func.sum(SalesOrderItem.quantity).desc())
        .limit(20)
        .all()
    )
    predictions = []
    for row in rows:
        monthly_quantity = float(row.quantity_sold or 0)
        confidence = "High" if (row.line_count or 0) >= 5 else "Medium" if (row.line_count or 0) >= 2 else "Low"
        predictions.append(
            {
                "item": row.particular,
                "predicted_next_month_qty": numeric(monthly_quantity * 1.15, 2),
                "confidence": confidence,
                "avg_unit_cost": numeric(row.avg_unit_cost, 2),
            }
        )
    return predictions


def _purchase_recommendations(db: Any, SalesOrderItem: Any, pondo: float) -> list[dict[str, Any]]:
    predictions = _demand_predictions(db, SalesOrderItem)
    recommendations = []
    remaining_budget = pondo
    for prediction in predictions:
        unit_cost = float(prediction["avg_unit_cost"] or 0)
        if unit_cost <= 0 or remaining_budget <= 0:
            continue
        target_qty = int(prediction["predicted_next_month_qty"])
        affordable_qty = int(remaining_budget // unit_cost)
        buy_qty = max(min(target_qty, affordable_qty), 0)
        if buy_qty == 0:
            continue
        estimated_cost = buy_qty * unit_cost
        remaining_budget -= estimated_cost
        recommendations.append(
            {
                "item": prediction["item"],
                "recommended_qty": buy_qty,
                "estimated_cost": numeric(estimated_cost, 2),
                "reason": f"Demand forecast is {prediction['predicted_next_month_qty']} units with {prediction['confidence']} confidence.",
            }
        )
    return recommendations


# ===== NEW ANALYTICS FUNCTIONS FOR IMPROVED INTERFACE =====

def calculate_customer_behavior_score(db: Any, client_id: int, Invoice: Any, SalesOrder: Any) -> float:
    """Calculate customer behavior score (0-100) based on:
    - Revenue volume (40%)
    - Payment consistency (40%)
    - Order frequency (20%)
    """
    # Revenue volume (max: 40 points)
    total_revenue = (
        db.session.query(func.sum(Invoice.amount_paid))
        .join(SalesOrder, Invoice.sales_order_id == SalesOrder.id)
        .filter(SalesOrder.client_id == client_id, Invoice.status == "PAID")
        .scalar() or 0
    )
    max_revenue = db.session.query(func.sum(Invoice.amount_paid)).filter(Invoice.status == "PAID").scalar() or 1
    revenue_score = min(40 * (total_revenue / max_revenue), 40) if max_revenue > 0 else 0

    # Payment consistency: % of invoices paid on time (40 points)
    terms_default = 30
    invoices = db.session.query(Invoice).join(SalesOrder, Invoice.sales_order_id == SalesOrder.id).filter(
        SalesOrder.client_id == client_id
    ).all()
    
    if invoices:
        on_time_count = sum(
            1 for inv in invoices
            if inv.status == "PAID" and (datetime.now().date() - inv.invoice_date).days <= terms_default
        )
        payment_consistency = 40 * (on_time_count / len(invoices)) if invoices else 0
    else:
        payment_consistency = 0

    # Order frequency: number of orders in last 90 days (20 points)
    recent_orders = db.session.query(SalesOrder).filter(
        SalesOrder.client_id == client_id,
        SalesOrder.created_at >= datetime.now() - timedelta(days=90)
    ).count()
    max_orders = 12  # Assume 12 orders per quarter is excellent
    order_frequency = min(20 * (recent_orders / max_orders), 20) if max_orders > 0 else 0

    score = revenue_score + payment_consistency + order_frequency
    return round(score, 2)


def get_client_status(score: float, revenue: float, total_revenue: float) -> str:
    """Classify client status based on score and revenue contribution.
    - Core Partners: score >= 80 AND revenue >= 20% of total
    - At-Risk Whales: score < 60 AND revenue >= 15% of total
    - Active Explorers: score >= 60 AND score < 80
    - Casual Niche: score < 60 OR revenue < 15% of total
    """
    revenue_pct = (revenue / total_revenue * 100) if total_revenue > 0 else 0
    
    if score >= 80 and revenue_pct >= 20:
        return "Core Partners"
    elif score < 60 and revenue_pct >= 15:
        return "At-Risk Whales"
    elif score >= 60 and score < 80:
        return "Active Explorers"
    else:
        return "Casual Niche"


def get_overview_kpis(db: Any, Invoice: Any, SalesOrder: Any, filter_period: str = "month") -> dict[str, Any]:
    """Get overview KPIs for the current period.
    filter_period: 'week', 'month', or 'quarter'
    """
    today = datetime.now().date()
    
    if filter_period == "week":
        start_date = today - timedelta(days=today.weekday())
    elif filter_period == "quarter":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start_date = today.replace(month=quarter_start_month, day=1)
    else:  # default: month
        start_date = today.replace(day=1)
    
    gross_revenue = (
        db.session.query(func.sum(Invoice.amount_paid))
        .filter(Invoice.status == "PAID", Invoice.invoice_date >= start_date)
        .scalar() or 0
    )
    
    accounts_receivable = (
        db.session.query(func.sum(Invoice.balance))
        .filter(Invoice.status != "PAID", Invoice.invoice_date >= start_date)
        .scalar() or 0
    )
    
    return {
        "gross_revenue": round(float(gross_revenue), 2),
        "accounts_receivable": round(float(accounts_receivable), 2),
        "period": filter_period
    }


def get_sales_trend_graph(db: Any, Invoice: Any, filter_period: str = "month", year: int | None = None) -> list[dict[str, Any]]:
    """Get weekly revenue trend data for a selected year."""
    today = datetime.now().date()
    selected_year = year or today.year
    data = []
    year_start = datetime(selected_year, 1, 1).date()
    year_end = datetime(selected_year, 12, 31).date()
    week_start = year_start
    week_num = 1
    while week_start <= year_end:
        week_end = min(week_start + timedelta(days=6), year_end)
        revenue = (
            db.session.query(func.sum(Invoice.amount_paid))
            .filter(Invoice.status == "PAID", Invoice.invoice_date >= week_start, Invoice.invoice_date <= week_end)
            .scalar() or 0
        )
        data.append({
            "label": f"W{week_num}",
            "revenue": round(float(revenue), 2),
            "date": week_start.isoformat()
        })
        week_start = week_end + timedelta(days=1)
        week_num += 1
    return data

def _apply_date_bounds(query: Any, column: Any, start_date: Any = None, end_date: Any = None) -> Any:
    if start_date is not None:
        query = query.filter(column >= start_date)
    if end_date is not None:
        query = query.filter(column < end_date)
    return query


def get_clients_analysis(db: Any, models: dict[str, Any], start_date: Any = None, end_date: Any = None) -> dict[str, Any]:
    """Get formal Client Performance Score plus cohort analysis."""
    Client = models["Client"]
    Invoice = models["Invoice"]
    SalesOrder = models["SalesOrder"]
    AnalyticsData = models["AnalyticsData"]

    clients = Client.query.order_by(Client.client_name.asc()).all()
    if not clients:
        return {
            "clients_table": [],
            "top_3_insights": [],
            "total_clients": 0,
            "clients": [],
            "top_3": [],
            "total": 0,
        }
    
    analytics_query = (
        db.session.query(
            AnalyticsData.party_name.label("company_name"),
            func.count(func.distinct(AnalyticsData.source_id)).label("branches"),
            func.count(AnalyticsData.analytics_id).label("frequency"),
            func.max(AnalyticsData.transaction_date).label("last_purchase"),
        )
        .filter(AnalyticsData.party_role == "CUSTOMER")
        .filter(AnalyticsData.party_name.isnot(None))
    )
    analytics_rows = _apply_date_bounds(
        analytics_query,
        AnalyticsData.transaction_date,
        start_date,
        end_date,
    ).group_by(AnalyticsData.party_name).all()

    client_names = [client.client_name for client in clients]
    activity_by_client = {
        client.client_name: {"branches": 0, "frequency": 0, "last_purchase": None}
        for client in clients
    }
    for row in analytics_rows:
        matched_client_name = best_company_match(row.company_name, client_names)
        if not matched_client_name:
            continue
        activity = activity_by_client[matched_client_name]
        activity["branches"] += int(row.branches or 0)
        activity["frequency"] += int(row.frequency or 0)
        if row.last_purchase and (activity["last_purchase"] is None or row.last_purchase > activity["last_purchase"]):
            activity["last_purchase"] = row.last_purchase

    today = datetime.now().date()
    max_revenue = max([float(client.total_revenue or 0) for client in clients] or [0])
    max_order_count = max([
        _apply_date_bounds(
            db.session.query(SalesOrder).filter(SalesOrder.client_id == client.id),
            SalesOrder.order_date,
            start_date,
            end_date,
        ).count()
        for client in clients
    ] or [0])
    max_average_order = 0.0
    client_order_stats = {}
    for client in clients:
        orders = _apply_date_bounds(
            db.session.query(SalesOrder).filter(SalesOrder.client_id == client.id),
            SalesOrder.order_date,
            start_date,
            end_date,
        ).all()
        order_count = len(orders)
        average_order = sum(float(order.total_amount or 0) for order in orders) / order_count if order_count else 0
        max_average_order = max(max_average_order, average_order)
        client_order_stats[client.id] = {"orders": orders, "order_count": order_count, "average_order": average_order}

    def clamp(value: float, upper: float) -> float:
        return max(0.0, min(float(value or 0), upper))

    def ratio(value: float, maximum: float) -> float:
        return clamp(float(value or 0) / float(maximum or 1), 1.0) if maximum else 0.0

    def cohort_for(score: float, balance: float, revenue: float) -> str:
        high_unpaid_exposure = balance > 0 and revenue > 0 and (balance / revenue) >= 0.30
        if score >= 80 and not high_unpaid_exposure:
            return "Core Partners"
        if score >= 60 and not high_unpaid_exposure:
            return "Growth Clients"
        if score >= 40 or high_unpaid_exposure:
            return "At-Risk Clients"
        return "Low Engagement"

    clients_data = []
    
    for client in clients:
        company_name = client.client_name
        activity = activity_by_client.get(company_name, {})
        branches = activity.get("branches", 0) or 0
        stats = client_order_stats.get(client.id, {"orders": [], "order_count": 0, "average_order": 0})
        orders = stats["orders"]
        order_count = stats["order_count"]
        revenue = sum(float(order.total_amount or 0) for order in orders)
        frequency = activity.get("frequency", 0) or 0
        invoice_query = db.session.query(Invoice).join(SalesOrder, Invoice.sales_order_id == SalesOrder.id).filter(
            SalesOrder.client_id == client.id
        )
        invoices = _apply_date_bounds(invoice_query, Invoice.invoice_date, start_date, end_date).all()
        total_paid = sum(float(invoice.amount_paid or 0) for invoice in invoices)
        balance = max(revenue - total_paid, 0)
        if start_date is None and end_date is None:
            revenue = float(client.total_revenue or revenue or 0)
            total_paid = float(client.total_paid or total_paid or 0)
            balance = float(client.total_balance or max(revenue - total_paid, 0))
        last_purchase = activity.get("last_purchase") or client.last_invoice_date or client.last_payment_date
        repeat_purchase_ratio = 1.0 if order_count >= 2 else 0.0
        recency_ratio = 0.0
        if last_purchase:
            days_since_purchase = max((today - last_purchase).days, 0)
            recency_ratio = max(0.0, 1 - min(days_since_purchase, 365) / 365)
        purchasing_score = round(
            (ratio(order_count, max_order_count) * 15)
            + (recency_ratio * 10)
            + (repeat_purchase_ratio * 10),
            2,
        )

        invoice_count = len(invoices)
        paid_count = sum(1 for invoice in invoices if str(invoice.status or "").upper() == "PAID" or float(invoice.balance or 0) <= 0)
        paid_ratio = paid_count / invoice_count if invoice_count else (1.0 if total_paid > 0 and balance <= 0 else 0.0)
        unpaid_ratio = (balance / revenue) if revenue > 0 else (1.0 if balance > 0 else 0.0)
        overdue_count = 0
        for invoice in invoices:
            invoice_date = invoice.invoice_date
            terms = invoice.sales_order.terms if invoice.sales_order else 30
            if invoice_date and float(invoice.balance or 0) > 0 and (today - invoice_date).days > int(terms or 30):
                overdue_count += 1
        overdue_ratio = overdue_count / invoice_count if invoice_count else 0.0
        payment_score = round((paid_ratio * 15) + ((1 - min(unpaid_ratio, 1)) * 10) + ((1 - min(overdue_ratio, 1)) * 10), 2)

        business_value_score = round(
            (ratio(revenue, max_revenue) * 18)
            + (ratio(stats["average_order"], max_average_order) * 12),
            2,
        )
        client_performance_score = round(clamp(purchasing_score, 35) + clamp(payment_score, 35) + clamp(business_value_score, 30), 2)
        cohort = cohort_for(client_performance_score, balance, revenue)
        recommendations = []
        if cohort == "At-Risk Clients":
            recommendations.append("Prioritize collection or account follow-up before extending more exposure.")
        if recency_ratio < 0.35 and revenue > 0:
            recommendations.append("Re-engage client; purchasing activity is becoming stale.")
        if client_performance_score >= 80:
            recommendations.append("Protect relationship and consider priority fulfillment.")
        if not recommendations:
            recommendations.append("Continue monitoring regular purchasing and payment behavior.")

        client_data = {
            "company_name": company_name,
            "branches_count": branches,
            "total_revenue": round(revenue, 2),
            "total_paid": round(total_paid, 2),
            "balance": round(balance, 2),
            "balance_status": client.balance_status or ("Settled" if balance <= 0 else "Unsettled Balance"),
            "value_status": cohort,
            "cohort": cohort,
            "score": round(client_performance_score / 100, 4),
            "client_performance_score": client_performance_score,
            "score_breakdown": {
                "purchasing_behavior": purchasing_score,
                "payment_reliability": payment_score,
                "business_value": business_value_score,
            },
            "recommendations": recommendations,
            "last_purchase": last_purchase.isoformat() if last_purchase else None
        }
        clients_data.append(client_data)
        
    clients_data.sort(key=lambda x: x["client_performance_score"], reverse=True)
    
    top_3_clients = [
        {
            "client": client["company_name"], 
            "score": client["score"],
            "client_performance_score": client["client_performance_score"],
            "cohort": client["cohort"],
            "balance_status": client["balance_status"]
        }
        for client in clients_data[:3]
    ]
    cohort_counts = defaultdict(int)
    for client in clients_data:
        cohort_counts[client["cohort"]] += 1
    
    return {
        "clients_table": clients_data,
        "top_3_insights": top_3_clients,
        "total_clients": len(clients_data),
        "clients": clients_data,
        "top_3": top_3_clients,
        "total": len(clients_data),
        "cohorts": [{"label": label, "count": count} for label, count in cohort_counts.items()],
    }


def get_expenses_breakdown(db: Any, PurchaseOrder: Any) -> dict[str, Any]:
    """Get expenses breakdown: fixed vs variable categorization."""
    fixed_expenses = (
        db.session.query(func.sum(PurchaseOrder.cash_amount))
        .filter(PurchaseOrder.category == "FIXED")
        .scalar() or 0
    )
    
    variable_expenses = (
        db.session.query(func.sum(PurchaseOrder.cash_amount))
        .filter(PurchaseOrder.category == "VARIABLE")
        .scalar() or 0
    )
    
    total_expenses = fixed_expenses + variable_expenses
    
    # Get detailed expenses by type
    fixed_items = (
        db.session.query(
            PurchaseOrder.particulars,
            PurchaseOrder.supplier_payee,
            func.sum(PurchaseOrder.cash_amount).label("total_amount"),
            PurchaseOrder.date
        )
        .filter(PurchaseOrder.category == "FIXED")
        .group_by(PurchaseOrder.particulars, PurchaseOrder.supplier_payee)
        .order_by(func.sum(PurchaseOrder.cash_amount).desc())
        .all()
    )
    
    variable_items = (
        db.session.query(
            PurchaseOrder.particulars,
            PurchaseOrder.supplier_payee,
            func.sum(PurchaseOrder.cash_amount).label("total_amount"),
            PurchaseOrder.date
        )
        .filter(PurchaseOrder.category == "VARIABLE")
        .group_by(PurchaseOrder.particulars, PurchaseOrder.supplier_payee)
        .order_by(func.sum(PurchaseOrder.cash_amount).desc())
        .all()
    )
    
    fixed_list = [
        {
            "supplier_payee": row.supplier_payee,
            "debit_account": row.particulars,
            "amount": round(float(row.total_amount or 0), 2),
            "date": row.date.isoformat() if row.date else None
        }
        for row in fixed_items
    ]
    
    variable_list = [
        {
            "supplier_payee": row.supplier_payee,
            "debit_account": row.particulars,
            "amount": round(float(row.total_amount or 0), 2),
            "date": row.date.isoformat() if row.date else None
        }
        for row in variable_items
    ]
    
    return {
        "fixed_expenses": round(float(fixed_expenses), 2),
        "variable_expenses": round(float(variable_expenses), 2),
        "total_expenses": round(float(total_expenses), 2),
        "fixed_items": fixed_list,
        "variable_items": variable_list,
        "pie_data": [
            {"label": "Fixed", "value": round(float(fixed_expenses), 2), "color": "#3B82F6"},
            {"label": "Variable", "value": round(float(variable_expenses), 2), "color": "#EF4444"}
        ]
    }


def get_sales_kpis(db: Any, models: dict[str, Any], start_date: Any = None, end_date: Any = None) -> dict[str, Any]:
    """Get sales KPIs: top 3 clients, top 3 items, number of sales."""
    Client = models["Client"]
    Invoice = models["Invoice"]
    SalesOrder = models["SalesOrder"]
    SalesOrderItem = models["SalesOrderItem"]
    
    # Top 3 clients
    top_clients_query = (
        db.session.query(Client.client_name, func.sum(Invoice.total_amount).label("total"))
        .select_from(Client)
        .join(SalesOrder, Client.id == SalesOrder.client_id)
        .join(Invoice, SalesOrder.id == Invoice.sales_order_id)
    )
    top_clients = _apply_date_bounds(top_clients_query, Invoice.invoice_date, start_date, end_date).group_by(Client.id).order_by(func.sum(Invoice.total_amount).desc()).limit(3).all()
    
    # Top 3 items
    top_items_query = (
        db.session.query(SalesOrderItem.particular, func.sum(SalesOrderItem.quantity).label("qty"))
        .join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
    )
    top_items = (
        _apply_date_bounds(top_items_query, SalesOrder.order_date, start_date, end_date)
        .group_by(SalesOrderItem.particular)
        .order_by(func.sum(SalesOrderItem.quantity).desc())
        .limit(3)
        .all()
    )
    
    # Total sales count
    total_sales = _apply_date_bounds(db.session.query(SalesOrder), SalesOrder.order_date, start_date, end_date).count()
    
    return {
        "top_3_clients": [{"name": row.client_name, "amount": round(float(row.total or 0), 2)} for row in top_clients],
        "top_3_items": [{"item": row.particular, "quantity": float(row.qty or 0)} for row in top_items],
        "total_sales": total_sales
    }


def get_sales_analysis(db: Any, models: dict[str, Any], mape_threshold: float = MAPE_DEFAULT_THRESHOLD, start_date: Any = None, end_date: Any = None) -> dict[str, Any]:
    """Build the complete sales analytics response payload."""
    SalesOrder = models["SalesOrder"]
    SalesOrderItem = models["SalesOrderItem"]
    Invoice = models["Invoice"]
    PurchaseOrder = models.get("PurchaseOrder")
    forecast = get_sales_forecast(db, SalesOrderItem, SalesOrder, mape_threshold, start_date, end_date)
    descriptive = get_sales_descriptive(db, SalesOrderItem, SalesOrder, start_date, end_date)
    clients = get_clients_analysis(db, models, start_date, end_date)
    pondo = 0.0
    if PurchaseOrder is not None:
        paid_revenue = _apply_date_bounds(db.session.query(func.sum(Invoice.amount_paid)).filter(Invoice.status == "PAID"), Invoice.invoice_date, start_date, end_date).scalar() or 0
        total_expenses = _apply_date_bounds(db.session.query(func.sum(PurchaseOrder.cash_amount)), PurchaseOrder.date, start_date, end_date).scalar() or 0
        pondo = max(float(paid_revenue or 0) - float(total_expenses or 0), 0)
    recommendations = build_rule_based_recommendations(forecast, descriptive, clients["clients"], pondo)
    return {
        "kpis": get_sales_kpis(db, models, start_date, end_date),
        "history": get_sales_order_history(db, SalesOrder, Invoice, start_date=start_date, end_date=end_date),
        "forecast": forecast["forecast"],
        "holt_winters": forecast["holt_winters"],
        "descriptive": descriptive,
        "predictive": forecast["predictive"],
        "prescriptive": {"recommendations": recommendations},
        "forecast_accuracy": forecast["forecast_accuracy"],
        "recommendations": recommendations,
    }


def get_sales_descriptive(db: Any, SalesOrderItem: Any, SalesOrder: Any, start_date: Any = None, end_date: Any = None) -> dict[str, Any]:
    """Build descriptive analytics for products, periods, and trend direction."""
    monthly_query = (
        db.session.query(
            func.strftime('%Y-%m', SalesOrder.order_date).label('month'),
            func.sum(SalesOrderItem.quantity * SalesOrderItem.selling_price).label('revenue'),
            func.sum(SalesOrderItem.quantity).label('quantity'),
        )
        .join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
    )
    monthly_rows = (
        _apply_date_bounds(monthly_query, SalesOrder.order_date, start_date, end_date)
        .group_by(func.strftime('%Y-%m', SalesOrder.order_date))
        .order_by(func.strftime('%Y-%m', SalesOrder.order_date))
        .all()
    )
    monthly_trend = [
        {"period": row.month, "revenue": numeric(row.revenue, 2), "quantity": numeric(row.quantity, 2)}
        for row in monthly_rows if row.month
    ]
    item_query = (
        db.session.query(
            SalesOrderItem.particular,
            func.sum(SalesOrderItem.quantity).label("quantity"),
            func.sum(SalesOrderItem.total).label("revenue"),
        )
        .join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
    )
    item_rows = (
        _apply_date_bounds(item_query, SalesOrder.order_date, start_date, end_date)
        .group_by(SalesOrderItem.particular)
        .order_by(func.sum(SalesOrderItem.total).desc())
        .all()
    )
    product_distribution = [
        {"item": row.particular, "quantity": numeric(row.quantity, 2), "revenue": numeric(row.revenue, 2)}
        for row in item_rows
    ]
    weekday_query = (
        db.session.query(
            func.strftime('%w', SalesOrder.order_date).label('weekday'),
            func.sum(SalesOrderItem.total).label('revenue'),
        )
        .join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
    )
    weekday_rows = (
        _apply_date_bounds(weekday_query, SalesOrder.order_date, start_date, end_date)
        .group_by(func.strftime('%w', SalesOrder.order_date))
        .order_by(func.sum(SalesOrderItem.total).desc())
        .all()
    )
    weekday_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    peak_weekdays = [
        {"weekday": weekday_names[int(row.weekday or 0)], "revenue": numeric(row.revenue, 2)}
        for row in weekday_rows
    ]
    trend_direction = "stable"
    early_warning = []
    if len(monthly_trend) >= 2:
        previous = monthly_trend[-2]["revenue"]
        current = monthly_trend[-1]["revenue"]
        change_pct = ((current - previous) / previous * 100) if previous else (100 if current else 0)
        if change_pct >= 10:
            trend_direction = "increasing"
            early_warning.append(f"Sales increased by {round(change_pct, 2)}% versus the prior period.")
        elif change_pct <= -10:
            trend_direction = "declining"
            early_warning.append(f"Sales declined by {round(abs(change_pct), 2)}% versus the prior period.")
    declining_products = []
    for row in product_distribution[-5:]:
        if row["revenue"] <= 0:
            declining_products.append({"item": row["item"], "warning": "No measurable revenue contribution."})
    return {
        "monthly_trend": monthly_trend,
        "product_distribution": product_distribution,
        "top_products": product_distribution[:10],
        "declining_products": declining_products,
        "peak_periods": {
            "months": sorted(monthly_trend, key=lambda item: item["revenue"], reverse=True)[:5],
            "weekdays": peak_weekdays[:5],
        },
        "trend_direction": trend_direction,
        "early_warnings": early_warning,
    }


def get_sales_order_history(db: Any, SalesOrder: Any, Invoice: Any, filter_period: str = "month", start_date: Any = None, end_date: Any = None) -> dict[str, Any]:
    """Get sales order history graph and table data."""
    today = datetime.now().date()
    month_start = today.replace(day=1)
    
    # Generate weekly data for current month
    weekly_data = []
    week_start = month_start
    week_num = 1
    while week_start <= today:
        week_end = min(week_start + timedelta(days=6), today)
        week_query = db.session.query(SalesOrder).filter(
            SalesOrder.created_at >= datetime.combine(week_start, datetime.min.time()),
            SalesOrder.created_at <= datetime.combine(week_end, datetime.max.time())
        )
        count = _apply_date_bounds(week_query, SalesOrder.order_date, start_date, end_date).count()
        weekly_data.append({
            "label": f"Week {week_num}",
            "count": count,
            "date": week_start.isoformat()
        })
        week_start = week_end + timedelta(days=1)
        week_num += 1
    
    # Get latest 10 sales orders
    latest_order_rows = _apply_date_bounds(
        db.session.query(SalesOrder),
        SalesOrder.order_date,
        start_date,
        end_date,
    ).order_by(SalesOrder.created_at.desc()).limit(10).all()
    
    orders_list = [
        {
            "so_number": order.so_number,
            "date": order.order_date.isoformat() if order.order_date else None,
            "total": round(float(sum(float(invoice.total_amount or 0) for invoice in getattr(order, "invoices", [])) or 0), 2),
            "status": order.status
        }
        for order in latest_order_rows
    ]
    
    return {
        "graph_data": weekly_data,
        "table_data": orders_list
    }


def holt_winters_forecast(values: list[float], season_length: int = 12) -> float:
    """Small additive Holt-Winters implementation for one-step forecasting."""
    clean = [float(v or 0) for v in values]
    if not clean:
        return 0.0
    if len(clean) < season_length * 2:
        return max(sum(clean[-3:]) / min(len(clean), 3), 0)
    alpha, beta, gamma = 0.35, 0.15, 0.25
    level = sum(clean[:season_length]) / season_length
    trend = (sum(clean[season_length:season_length * 2]) / season_length - level) / season_length
    seasonals = [clean[i] - level for i in range(season_length)]
    for i, value in enumerate(clean):
        season = seasonals[i % season_length]
        last_level = level
        level = alpha * (value - season) + (1 - alpha) * (level + trend)
        trend = beta * (level - last_level) + (1 - beta) * trend
        seasonals[i % season_length] = gamma * (value - level) + (1 - gamma) * season
    return max(level + trend + seasonals[len(clean) % season_length], 0)


def mean_absolute_percentage_error(actual: list[float], predicted: list[float]) -> float | None:
    pairs = [(float(a), float(p)) for a, p in zip(actual, predicted) if float(a or 0) != 0]
    if not pairs:
        return None
    return round(sum(abs((a - p) / a) for a, p in pairs) / len(pairs) * 100, 2)


def backtest_holt_winters(values: list[float], season_length: int = 12, validation_periods: int = 3) -> dict[str, Any]:
    clean = [float(value or 0) for value in values]
    if len(clean) < 6:
        return {"status": "insufficient_data", "mape": None, "actual": [], "predicted": []}
    validation_count = min(validation_periods, max(1, len(clean) // 4))
    actual = clean[-validation_count:]
    predicted = []
    for offset in range(validation_count, 0, -1):
        train = clean[:-offset]
        predicted.append(holt_winters_forecast(train, season_length))
    return {
        "status": "tested",
        "mape": mean_absolute_percentage_error(actual, predicted),
        "actual": [round(value, 2) for value in actual],
        "predicted": [round(value, 2) for value in predicted],
    }

def add_months(month_key: str, offset: int) -> str:
    try:
        base = datetime.strptime(f"{month_key}-01", "%Y-%m-%d")
        month_index = base.month - 1 + offset
        year = base.year + month_index // 12
        month = month_index % 12 + 1
        return datetime(year, month, 1).strftime("%Y-%m")
    except (TypeError, ValueError):
        return f"Forecast Period {offset}"

def month_label(month_key: str) -> str:
    try:
        return datetime.strptime(f"{month_key}-01", "%Y-%m-%d").strftime("%B %Y")
    except (TypeError, ValueError):
        return str(month_key or "Unknown period")


def get_sales_forecast(
    db: Any,
    SalesOrderItem: Any,
    SalesOrder: Any | None = None,
    mape_threshold: float = MAPE_DEFAULT_THRESHOLD,
    start_date: Any = None,
    end_date: Any = None,
) -> dict[str, Any]:
    """Forecast expected revenue and profit from sales order item history."""
    forecast_data = []
    top_items_query = db.session.query(SalesOrderItem.particular, func.sum(SalesOrderItem.quantity).label("quantity"))
    if SalesOrder is not None:
        top_items_query = top_items_query.join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
        top_items_query = _apply_date_bounds(top_items_query, SalesOrder.order_date, start_date, end_date)
    top_items = top_items_query.group_by(SalesOrderItem.particular).order_by(func.sum(SalesOrderItem.quantity).desc()).limit(10).all()
    for item in top_items:
        item_rows_query = db.session.query(SalesOrderItem).filter(SalesOrderItem.particular == item.particular)
        if SalesOrder is not None:
            item_rows_query = item_rows_query.join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
            item_rows_query = _apply_date_bounds(item_rows_query, SalesOrder.order_date, start_date, end_date)
        item_rows = item_rows_query.all()
        avg_price = sum((row.selling_price or 0) for row in item_rows) / len(item_rows) if item_rows else 0
        avg_cost = sum((row.unit_cost or 0) for row in item_rows) / len(item_rows) if item_rows else 0
        monthly_quantities = []
        if SalesOrder is not None:
            monthly_query = (
                db.session.query(
                    func.strftime('%Y-%m', SalesOrder.order_date).label('month'),
                    func.sum(SalesOrderItem.quantity).label('quantity'),
                )
                .join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
                .filter(SalesOrderItem.particular == item.particular)
            )
            monthly_rows = _apply_date_bounds(monthly_query, SalesOrder.order_date, start_date, end_date).group_by(func.strftime('%Y-%m', SalesOrder.order_date)).order_by(func.strftime('%Y-%m', SalesOrder.order_date)).all()
            monthly_quantities = [float(row.quantity or 0) for row in monthly_rows]
        backtest = backtest_holt_winters(monthly_quantities)
        if backtest["status"] == "tested":
            predicted_qty = holt_winters_forecast(monthly_quantities)
            method = "holt_winters"
        else:
            predicted_qty = sum(monthly_quantities[-3:]) / min(len(monthly_quantities), 3) if monthly_quantities else float(item.quantity or 0)
            method = "fallback_average"
        accepted = backtest["mape"] is not None and backtest["mape"] <= float(mape_threshold)
        confidence = "High" if accepted else "Needs Review" if backtest["mape"] is not None else "Insufficient Data"
        forecast_data.append({
            "item": item.particular,
            "predicted_qty": round(float(predicted_qty or 0), 2),
            "predicted_revenue": round(predicted_qty * avg_price, 2),
            "predicted_profit": round(predicted_qty * (avg_price - avg_cost), 2),
            "confidence": confidence,
            "method": method,
            "mape": backtest["mape"],
            "accepted": accepted,
            "actual_validation": backtest["actual"],
            "predicted_validation": backtest["predicted"],
        })

    monthly_revenue = []
    monthly_profit = []
    if SalesOrder is not None:
        revenue_query = (
            db.session.query(
                func.strftime('%Y-%m', SalesOrder.order_date).label('month'),
                func.sum(SalesOrderItem.quantity * SalesOrderItem.selling_price).label('revenue'),
                func.sum(SalesOrderItem.quantity * (SalesOrderItem.selling_price - SalesOrderItem.unit_cost)).label('profit')
            )
            .join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
        )
        rows = _apply_date_bounds(revenue_query, SalesOrder.order_date, start_date, end_date).group_by(func.strftime('%Y-%m', SalesOrder.order_date)).order_by(func.strftime('%Y-%m', SalesOrder.order_date)).all()
        monthly_periods = [row.month for row in rows if row.month]
        monthly_revenue = [float(row.revenue or 0) for row in rows]
        monthly_profit = [float(row.profit or 0) for row in rows]
    else:
        monthly_periods = []

    revenue_backtest = backtest_holt_winters(monthly_revenue)
    profit_backtest = backtest_holt_winters(monthly_profit)
    revenue_next = round(holt_winters_forecast(monthly_revenue), 2)
    profit_next = round(holt_winters_forecast(monthly_profit), 2)
    revenue_mape = revenue_backtest["mape"]
    accepted = revenue_mape is not None and revenue_mape <= float(mape_threshold)
    if revenue_backtest["status"] == "insufficient_data":
        accuracy_status = "insufficient_data"
    else:
        accuracy_status = "accepted" if accepted else "above_threshold"
    return {
        "forecast": forecast_data,
        "holt_winters": {
            "next_period_revenue": revenue_next,
            "next_period_profit": profit_next,
            "method": "holt_winters" if revenue_backtest["status"] == "tested" else "fallback_average",
        },
        "forecast_accuracy": {
            "mape_threshold": float(mape_threshold),
            "mape": revenue_mape,
            "status": accuracy_status,
            "actual": revenue_backtest["actual"],
            "predicted": revenue_backtest["predicted"],
            "periods": [
                {
                    "code": f"P{index + 1}",
                    "period": period,
                    "label": f"P{index + 1} = {month_label(period)}",
                    "description": f"Forecast Period {index + 1}",
                }
                for index, period in enumerate(monthly_periods[-len(revenue_backtest["actual"]):])
            ],
            "next_periods": [
                {
                    "code": f"P{index + 1}",
                    "period": add_months(monthly_periods[-1], index + 1) if monthly_periods else f"Period {index + 1}",
                    "label": f"P{index + 1} = {month_label(add_months(monthly_periods[-1], index + 1)) if monthly_periods else f'Forecast Period {index + 1}'}",
                    "description": f"Forecast Period {index + 1}",
                }
                for index in range(3)
            ],
        },
        "predictive": {
            "item_forecasts": forecast_data,
            "monthly_revenue_forecast": {
                "next_period_revenue": revenue_next,
                "next_period_profit": profit_next,
                "accuracy": revenue_backtest,
                "profit_accuracy": profit_backtest,
            },
        },
    }


def build_rule_based_recommendations(
    forecast: dict[str, Any],
    descriptive: dict[str, Any],
    clients: list[dict[str, Any]],
    pondo: float,
) -> list[dict[str, Any]]:
    recommendations = []
    for item in forecast.get("forecast", [])[:8]:
        if item.get("accepted") and descriptive.get("trend_direction") == "increasing":
            predicted_qty = item.get("predicted_qty")
            recommendations.append({
                "type": "procurement",
                "severity": "success",
                "title": f"Increase stock for {item['item']}",
                "reason": f"Forecast passed MAPE threshold and predicts {item['predicted_qty']} units.",
                "trigger_condition": "Sales trend is increasing and the item forecast passed the selected MAPE threshold.",
                "data_used": [
                    f"Item: {item['item']}",
                    f"Predicted Quantity: {predicted_qty}",
                    f"Predicted Revenue: {item.get('predicted_revenue')}",
                    f"MAPE: {item.get('mape')}%",
                ],
                "calculation_process": f"Holt-Winters forecast predicted {predicted_qty} unit(s); MAPE {item.get('mape')}% is within the threshold.",
                "result": f"{item['item']} is expected to need about {predicted_qty} unit(s).",
                "business_interpretation": "Demand is moving upward and the forecast passed validation, so stock planning can be more confident.",
                "suggested_action": "Review current inventory and prepare replenishment if available stock is below the forecasted demand.",
            })
        elif item.get("mape") is None:
            recommendations.append({
                "type": "forecast_review",
                "severity": "warning",
                "title": f"Review forecast for {item['item']}",
                "reason": "Historical periods are insufficient for reliable Holt-Winters validation.",
                "trigger_condition": "The item does not have enough historical periods for validation.",
                "data_used": [
                    f"Item: {item['item']}",
                    f"Predicted Quantity: {item.get('predicted_qty')}",
                    "MAPE: Insufficient data",
                ],
                "calculation_process": "The system used fallback averaging because validated Holt-Winters testing was not available.",
                "result": "Forecast confidence is limited.",
                "business_interpretation": "The item may still be important, but the system cannot strongly validate the forecast yet.",
                "suggested_action": "Review recent orders manually before making a large procurement decision.",
            })
        elif not item.get("accepted"):
            recommendations.append({
                "type": "forecast_review",
                "severity": "warning",
                "title": f"Validate demand volatility for {item['item']}",
                "reason": f"MAPE is {item['mape']}%, above the selected threshold.",
                "trigger_condition": "Forecast validation error is above the selected MAPE threshold.",
                "data_used": [
                    f"Item: {item['item']}",
                    f"MAPE: {item.get('mape')}%",
                    f"Predicted Quantity: {item.get('predicted_qty')}",
                ],
                "calculation_process": f"MAPE {item.get('mape')}% was compared with the selected threshold and did not pass.",
                "result": "The item forecast needs review before use.",
                "business_interpretation": "Demand may be irregular, seasonal, or affected by one-time sales movement.",
                "suggested_action": "Check recent customer orders and avoid overstocking until the pattern is clearer.",
            })
    for client in clients[:10]:
        if client.get("cohort") == "At-Risk Clients" and float(client.get("balance") or 0) > 0:
            balance = float(client.get("balance") or 0)
            recommendations.append({
                "type": "collections",
                "severity": "danger",
                "title": f"Follow up {client['company_name']}",
                "reason": f"High-value/risk cohort with {client['balance']} outstanding balance.",
                "trigger_condition": "Client belongs to the At-Risk cohort and has an outstanding balance.",
                "data_used": [
                    f"Client: {client['company_name']}",
                    f"Outstanding Balance: {balance}",
                    f"Cohort: {client.get('cohort')}",
                ],
                "calculation_process": "Client cohort classification was combined with the current unpaid balance.",
                "result": f"{client['company_name']} has an outstanding balance requiring attention.",
                "business_interpretation": "Delayed collection can reduce available cash for operations and procurement.",
                "suggested_action": "Contact the client, confirm payment schedule, and pause new exposure if needed.",
            })
    if descriptive.get("trend_direction") == "declining":
        months = descriptive.get("monthly_trend") or []
        current = months[-1]["revenue"] if months else 0
        previous = months[-2]["revenue"] if len(months) >= 2 else 0
        change_pct = round(((current - previous) / previous * 100), 2) if previous else 0
        recommendations.append({
            "type": "sales_monitoring",
            "severity": "danger",
            "title": "Investigate declining sales",
            "reason": "Latest revenue period is materially below the prior period.",
            "trigger_condition": "Latest period revenue decreased by at least 10% versus the previous period.",
            "data_used": [
                f"Previous Period Sales: {previous}",
                f"Current Period Sales: {current}",
            ],
            "calculation_process": f"(({current} - {previous}) / {previous}) x 100 = {change_pct}%" if previous else "Previous period sales were not available for percentage comparison.",
            "result": f"Sales changed by {change_pct}%.",
            "business_interpretation": "A sales decline can point to lower demand, delayed orders, or client inactivity.",
            "suggested_action": "Review customer engagement, large account activity, and recent order pipeline.",
        })
    if pondo <= 0:
        recommendations.append({
            "type": "budget",
            "severity": "warning",
            "title": "Pondo exhausted",
            "reason": "Procurement recommendations should wait for additional collections.",
            "trigger_condition": "Available pondo is zero or below.",
            "data_used": [f"Available Pondo: {pondo}"],
            "calculation_process": f"Available pondo {pondo} <= 0.",
            "result": "Procurement budget is not currently available.",
            "business_interpretation": "Purchasing without available funds can pressure cash flow.",
            "suggested_action": "Prioritize collections or budget replenishment before approving new purchases.",
        })
    for index, recommendation in enumerate(recommendations, start=1):
        recommendation["id"] = f"rec-{index}"
    return recommendations[:12]


def get_comparative_analysis(db: Any, Invoice: Any, year1: int, year2: int) -> dict[str, Any]:
    """Get comparative analysis between two years."""
    # Monthly comparison
    monthly_data = []
    for month in range(1, 13):
        year1_revenue = (
            db.session.query(func.sum(Invoice.amount_paid))
            .filter(
                func.extract("year", Invoice.invoice_date) == year1,
                func.extract("month", Invoice.invoice_date) == month,
                Invoice.status == "PAID"
            )
            .scalar() or 0
        )
        
        year2_revenue = (
            db.session.query(func.sum(Invoice.amount_paid))
            .filter(
                func.extract("year", Invoice.invoice_date) == year2,
                func.extract("month", Invoice.invoice_date) == month,
                Invoice.status == "PAID"
            )
            .scalar() or 0
        )
        
        month_name = datetime(2024, month, 1).strftime("%b")
        monthly_data.append({
            "month": month_name,
            "year1": round(float(year1_revenue or 0), 2),
            "year2": round(float(year2_revenue or 0), 2)
        })
    
    # Calculate overall increase
    year1_total = sum(m["year1"] for m in monthly_data)
    year2_total = sum(m["year2"] for m in monthly_data)
    overall_increase = round(((year2_total - year1_total) / year1_total * 100) if year1_total > 0 else 0, 2)
    
    return {
        "monthly_comparison": monthly_data,
        "year1": year1,
        "year2": year2,
        "overall_increase_percentage": overall_increase,
        "year1_total": round(float(year1_total), 2),
        "year2_total": round(float(year2_total), 2)
    }
