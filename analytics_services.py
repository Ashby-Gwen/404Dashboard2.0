"""Analytics calculations for Syluxent.

Maintenance guide:
- Add new report logic as a small function that accepts db/models and returns plain dict/list data.
- Expose that function through build_analytics_payload() when the manager UI should display it.
- Keep database reads here, and keep Flask route/request handling in app.py.
- For UI changes, edit templates/analytics.html and consume the JSON keys returned by this module via API routes.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any
# add numpy, scikit-learn

# create an improve rule based recommendations where the developer can 
    # easily add new rules based on the data patterns they observe in the analytics. 
    # This can be a simple function that takes in the analytics data and applies a set 
    # of predefined rules to generate actionable insights or recommendations for the 
    # manager for each data presented in the UI. 


import pandas as pd
from sqlalchemy import extract, func


MAPE_DEFAULT_THRESHOLD = 20.0
MONEY_TOLERANCE = 0.01


def db_is_postgres(db: Any) -> bool:
    return db.engine.dialect.name == "postgresql"


def db_month_key(db: Any, column: Any):
    if db_is_postgres(db):
        return func.to_char(column, 'YYYY-MM')
    return func.strftime('%Y-%m', column)


def db_weekday(db: Any, column: Any):
    if db_is_postgres(db):
        return extract('dow', column)
    return func.strftime('%w', column)


def db_year(column: Any):
    return extract('year', column)


def db_month_number(column: Any):
    return extract('month', column)


def numeric(value: Any, digits: int | None = None) -> float:
    """Return plain JSON-safe numbers for analytics responses."""
    number = float(value or 0)
    return round(number, digits) if digits is not None else number


def deduped_sales_item_revenue_subquery(db: Any, SalesOrderItem: Any, SalesOrder: Any, start_date: Any = None, end_date: Any = None):
    """Collapse exact duplicate Sales Order item rows for analytics only."""
    revenue_value = func.coalesce(SalesOrderItem.total, SalesOrderItem.quantity * SalesOrderItem.selling_price)
    query = (
        db.session.query(
            SalesOrder.order_date.label("order_date"),
            SalesOrder.so_number.label("so_number"),
            SalesOrder.sales_staff.label("sales_staff"),
            SalesOrder.company_name.label("company_name"),
            SalesOrder.store_name.label("store_name"),
            SalesOrder.store_branch.label("store_branch"),
            SalesOrderItem.particular.label("particular"),
            SalesOrderItem.quantity.label("quantity"),
            SalesOrderItem.unit_cost.label("unit_cost"),
            SalesOrderItem.selling_price.label("selling_price"),
            revenue_value.label("revenue"),
        )
        .join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
    )
    query = _apply_date_bounds(query, SalesOrder.order_date, start_date, end_date)
    return query.group_by(
        SalesOrder.order_date,
        SalesOrder.so_number,
        SalesOrder.sales_staff,
        SalesOrder.company_name,
        SalesOrder.store_name,
        SalesOrder.store_branch,
        SalesOrderItem.particular,
        SalesOrderItem.quantity,
        SalesOrderItem.unit_cost,
        SalesOrderItem.selling_price,
        revenue_value,
    ).subquery()


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


def _canonical_client_lookup(models: dict[str, Any]) -> dict[str, str]:
    Client = models["Client"]
    ClientAlias = models.get("ClientAlias")
    lookup = {
        normalize_company_match_key(client.client_name): client.client_name
        for client in Client.query.all()
        if client.client_name
    }
    if ClientAlias is not None:
        for alias in ClientAlias.query.all():
            if alias.client and alias.alias_name:
                lookup[normalize_company_match_key(alias.alias_name)] = alias.client.client_name
    return lookup


def _invoice_client_name(invoice: Any, lookup: dict[str, str]) -> str:
    if invoice.sales_order and invoice.sales_order.client:
        return invoice.sales_order.client.client_name
    uploaded = str(invoice.uploaded_client_name or "").strip()
    return lookup.get(normalize_company_match_key(uploaded), uploaded or "Admin Upload")


def build_canonical_financials(
    db: Any,
    models: dict[str, Any],
    start_date: Any = None,
    end_date: Any = None,
) -> dict[str, Any]:
    """Return the shared collected-revenue and one-balance-per-order ledger."""
    Invoice = models["Invoice"]
    CollectionReceipt = models.get("CollectionReceipt")
    SalesOrder = models["SalesOrder"]
    lookup = _canonical_client_lookup(models)
    client_revenue: dict[str, float] = defaultdict(float)
    receivables = []
    unmapped_clients: dict[str, dict[str, Any]] = {}

    if CollectionReceipt is not None:
        receipt_query = db.session.query(CollectionReceipt, Invoice).join(
            Invoice,
            CollectionReceipt.invoice_id == Invoice.id,
        )
        receipts = _apply_date_bounds(
            receipt_query,
            CollectionReceipt.receipt_date,
            start_date,
            end_date,
        ).order_by(CollectionReceipt.receipt_date.asc(), CollectionReceipt.id.asc()).all()
        for receipt, invoice in receipts:
            paid = max(float(receipt.collected_total or 0), 0)
            if paid > MONEY_TOLERANCE:
                client_revenue[_invoice_client_name(invoice, lookup)] += paid
        legacy_invoices = _apply_date_bounds(
            Invoice.query.filter(
                Invoice.amount_paid > MONEY_TOLERANCE,
                ~Invoice.collection_receipts.any(),
            ),
            Invoice.invoice_date,
            start_date,
            end_date,
        ).all()
        for invoice in legacy_invoices:
            client_revenue[_invoice_client_name(invoice, lookup)] += max(
                float(invoice.amount_paid or 0),
                0,
            )
    else:
        invoices = _apply_date_bounds(
            Invoice.query,
            Invoice.invoice_date,
            start_date,
            end_date,
        ).order_by(Invoice.invoice_date.asc(), Invoice.id.asc()).all()
        for invoice in invoices:
            paid = max(float(invoice.amount_paid or 0), 0)
            if paid > MONEY_TOLERANCE:
                client_revenue[_invoice_client_name(invoice, lookup)] += paid

    orders = _apply_date_bounds(
        SalesOrder.query,
        SalesOrder.order_date,
        start_date,
        end_date,
    ).order_by(SalesOrder.order_date.asc(), SalesOrder.id.asc()).all()
    for order in orders:
        line_total = sum(float(item.total or 0) for item in order.items)
        total = line_total if line_total > 0 else float(order.total_amount or 0)
        linked = [
            invoice for invoice in order.invoices
            if (
                (start_date is None or (invoice.invoice_date and invoice.invoice_date >= start_date))
                and (end_date is None or (invoice.invoice_date and invoice.invoice_date < end_date))
            )
        ]
        paid = sum(max(float(invoice.amount_paid or 0), 0) for invoice in linked)
        balance = max(round(total - paid, 2), 0)
        if balance <= MONEY_TOLERANCE:
            continue
        latest_invoice = max(
            linked,
            key=lambda item: (item.invoice_date or date.min, item.id or 0),
            default=None,
        )
        receivables.append({
            "sales_order_id": order.id,
            "so_number": order.so_number,
            "client_name": order.client.client_name if order.client else (order.company_name or "Unknown Client"),
            "invoice_number": latest_invoice.invoice_number if latest_invoice else None,
            "invoice_date": latest_invoice.invoice_date if latest_invoice else order.order_date,
            "total_amount": total,
            "amount_paid": paid,
            "balance": balance,
            "status": "PARTIAL" if paid > MONEY_TOLERANCE else "UNPAID",
        })

    standalone = _apply_date_bounds(
        Invoice.query.filter(Invoice.sales_order_id.is_(None)),
        Invoice.invoice_date,
        start_date,
        end_date,
    ).all()
    for invoice in standalone:
        total = float(invoice.total_amount if invoice.total_amount is not None else invoice.amount_paid or 0)
        paid = max(float(invoice.amount_paid or 0), 0)
        balance = max(float(invoice.balance if invoice.balance is not None else total - paid), 0)
        if balance <= MONEY_TOLERANCE:
            continue
        uploaded_name = str(invoice.uploaded_client_name or "").strip()
        normalized_name = normalize_company_match_key(uploaded_name)
        canonical_name = lookup.get(normalized_name)
        if not canonical_name:
            unmapped_key = normalized_name or f"UNMAPPED-{invoice.id}"
            unmapped = unmapped_clients.setdefault(unmapped_key, {
                "client_name": uploaded_name or "Unmapped Client",
                "total_invoices": 0,
                "total_amount": 0.0,
                "amount_paid": 0.0,
                "balance": 0.0,
            })
            unmapped["total_invoices"] += 1
            unmapped["total_amount"] += total
            unmapped["amount_paid"] += paid
            unmapped["balance"] += balance
        receivables.append({
            "sales_order_id": None,
            "so_number": None,
            "client_name": canonical_name or uploaded_name or "Unmapped Client",
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date,
            "total_amount": total,
            "amount_paid": paid,
            "balance": balance,
            "status": "PARTIAL" if paid > MONEY_TOLERANCE else "UNPAID",
        })

    return {
        "collected_revenue": round(sum(client_revenue.values()), 2),
        "revenue_by_client": [
            {"client_name": name, "revenue": round(amount, 2)}
            for name, amount in sorted(client_revenue.items(), key=lambda item: item[1], reverse=True)
        ],
        "receivables": receivables,
        "accounts_receivable": round(sum(item["balance"] for item in receivables), 2),
        "unmapped_clients": [
            {
                **item,
                "total_amount": round(item["total_amount"], 2),
                "amount_paid": round(item["amount_paid"], 2),
                "balance": round(item["balance"], 2),
            }
            for item in sorted(
                unmapped_clients.values(),
                key=lambda item: (-item["balance"], item["client_name"]),
            )
        ],
    }


def build_analytics_payload(
    db: Any,
    models: dict[str, Any],
    start_date: Any = None,
    end_date: Any = None,
) -> dict[str, Any]:
    """Build the complete manager analytics payload from current system data."""
    Invoice = models["Invoice"]
    CollectionReceipt = models.get("CollectionReceipt")
    PurchaseOrder = models["PurchaseOrder"]
    SalesOrder = models["SalesOrder"]
    SalesOrderItem = models["SalesOrderItem"]

    today = datetime.now().date()
    financials = build_canonical_financials(db, models, start_date, end_date)
    paid_revenue = financials["collected_revenue"]
    unpaid_receivable = financials["accounts_receivable"]
    total_expenses = db.session.query(func.sum(PurchaseOrder.cash_amount)).scalar() or 0
    pondo = max(paid_revenue - total_expenses, 0)
    client_balances: dict[str, float] = defaultdict(float)
    for item in financials["receivables"]:
        client_balances[item["client_name"]] += item["balance"]
    receivables = financials["receivables"]
    leakage = None
    if receivables:
        highest = max(receivables, key=lambda item: item["balance"])
        invoice_date = highest["invoice_date"]
        days_outstanding = (today - invoice_date).days if invoice_date else 0
        leakage = {
            "client_name": highest["client_name"],
            "unpaid_amount": round(highest["balance"], 2),
            "days_outstanding": max(days_outstanding, 0),
            "impact_amount": round(highest["balance"], 2),
            "percentage_of_total": round(
                highest["balance"] / unpaid_receivable * 100, 2
            ) if unpaid_receivable else 0,
            "analysis": f"{highest['client_name']} has the highest outstanding balance and should be prioritized for collection.",
        }

    return {
        "summary": {
            "paid_revenue": numeric(paid_revenue, 2),
            "accounts_receivable": numeric(unpaid_receivable, 2),
            "expenses": numeric(total_expenses, 2),
            "pondo_remaining": numeric(pondo, 2),
            "next_month_pondo": numeric(pondo, 2),
        },
        "weekly_cashflow": _weekly_cashflow(db, Invoice, PurchaseOrder, today, CollectionReceipt),
        "monthly_cashflow": _monthly_cashflow(db, Invoice, PurchaseOrder, today, CollectionReceipt),
        "revenue_by_client": financials["revenue_by_client"][:10],
        "sales_performance": _sales_performance(SalesOrder, Invoice),
        "revenue_leakage": leakage,
        "accounts_receivable": [
            {
                **item,
                "invoice_date": item["invoice_date"].isoformat() if item["invoice_date"] else None,
            }
            for item in receivables
        ],
        "client_balances": [
            {"client_name": name, "balance": round(balance, 2)}
            for name, balance in sorted(client_balances.items(), key=lambda item: item[1], reverse=True)
        ],
        "unmapped_clients": financials["unmapped_clients"],
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


def _weekly_cashflow(
    db: Any,
    Invoice: Any,
    PurchaseOrder: Any,
    today: Any,
    CollectionReceipt: Any = None,
) -> list[dict[str, Any]]:
    month_start = today.replace(day=1)
    week_start = month_start
    week_number = 1
    rows = []
    while week_start <= today:
        week_end = min(week_start + timedelta(days=6), today)
        rows.append(
            {
                "day": f"Week {week_number}",
                "revenue": _invoice_revenue(db, Invoice, week_start, week_end, CollectionReceipt),
                "expenses": _purchase_expenses(db, PurchaseOrder, week_start, week_end),
            }
        )
        week_start = week_end + timedelta(days=1)
        week_number += 1
    return rows


def _monthly_cashflow(
    db: Any,
    Invoice: Any,
    PurchaseOrder: Any,
    today: Any,
    CollectionReceipt: Any = None,
) -> list[dict[str, Any]]:
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
                "revenue": _invoice_revenue(db, Invoice, month_start, month_end, CollectionReceipt),
                "expenses": _purchase_expenses(db, PurchaseOrder, month_start, month_end),
            }
        )
    return rows


def _invoice_revenue(
    db: Any,
    Invoice: Any,
    start: Any,
    end: Any,
    CollectionReceipt: Any = None,
) -> float:
    if CollectionReceipt is not None:
        receipt_total = numeric(
            db.session.query(func.sum(CollectionReceipt.collected_total))
            .filter(
                CollectionReceipt.receipt_date >= start,
                CollectionReceipt.receipt_date <= end,
            )
            .scalar()
        )
        legacy_total = numeric(
            db.session.query(func.sum(Invoice.amount_paid))
            .filter(
                Invoice.amount_paid > 0,
                ~Invoice.collection_receipts.any(),
                Invoice.invoice_date >= start,
                Invoice.invoice_date <= end,
            )
            .scalar()
        )
        return numeric(receipt_total + legacy_total)
    return numeric(
        db.session.query(func.sum(Invoice.amount_paid))
        .filter(Invoice.amount_paid > 0, Invoice.invoice_date >= start, Invoice.invoice_date <= end)
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
        .filter(Invoice.amount_paid > 0)
        .group_by(Client.id)
        .order_by(func.sum(Invoice.amount_paid).desc())
        .limit(10)
        .all()
    )
    return [{"client_name": row.client_name, "revenue": numeric(row.revenue, 2)} for row in rows]


def _sales_performance(SalesOrder: Any, Invoice: Any) -> list[dict[str, Any]]:
    rows = []
    today = datetime.now().date()
    month_cursor = today.replace(day=1)
    for offset in range(5, -1, -1):
        month_index = month_cursor.month - 1 - offset
        year = month_cursor.year + month_index // 12
        month = month_index % 12 + 1
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        rows.append(
            {
                "period": start.strftime("%b %Y"),
                "sales_count": SalesOrder.query.filter(SalesOrder.order_date >= start, SalesOrder.order_date < end).count(),
                "invoice_count": Invoice.query.filter(Invoice.invoice_date >= start, Invoice.invoice_date < end).count(),
            }
        )
    return rows


def _revenue_leakage(db: Any, Client: Any, SalesOrder: Any, Invoice: Any) -> dict[str, Any] | None:
    rows = []
    today = datetime.now().date()
    for order in SalesOrder.query.all():
        total = sum(float(item.total or 0) for item in order.items) or float(order.total_amount or 0)
        paid = sum(float(invoice.amount_paid or 0) for invoice in order.invoices)
        balance = max(total - paid, 0)
        if balance <= MONEY_TOLERANCE:
            continue
        latest_date = max(
            (invoice.invoice_date for invoice in order.invoices if invoice.invoice_date),
            default=order.order_date,
        )
        rows.append({
            "client_name": order.client.client_name if order.client else (order.company_name or "Unknown Client"),
            "unpaid_amount": balance,
            "days_outstanding": max((today - latest_date).days, 0) if latest_date else 0,
        })
    if not rows:
        return None
    highest = max(rows, key=lambda row: row["unpaid_amount"])
    total_unpaid = sum(row["unpaid_amount"] for row in rows)
    percent = round(highest["unpaid_amount"] / total_unpaid * 100, 2) if total_unpaid else 0
    return {
        "client_name": highest["client_name"],
        "unpaid_amount": numeric(highest["unpaid_amount"], 2),
        "days_outstanding": highest["days_outstanding"],
        "impact_amount": numeric(highest["unpaid_amount"], 2),
        "percentage_of_total": percent,
        "analysis": f"{highest['client_name']} has the highest outstanding balance and should be prioritized for collection.",
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
        .filter(Invoice.balance > MONEY_TOLERANCE)
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
            "quantity_sold": int(row.quantity_sold or 0),
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
                "predicted_next_month_qty": max(int(round(monthly_quantity * 1.15)), 0),
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
    """Compatibility wrapper for the old public helper name.

    Client value is intentionally based on Sales Orders only. Invoice payment
    behavior is excluded from this score.
    """
    orders = db.session.query(SalesOrder).filter(SalesOrder.client_id == client_id).all()
    total_order_amount = sum(float(order.total_amount or 0) for order in orders)
    order_count = len(orders)
    if not order_count:
        return 0.0
    average_order_value = total_order_amount / order_count
    repeat_ratio = min(order_count / 12, 1.0)
    amount_ratio = min(total_order_amount / max(total_order_amount, 1), 1.0)
    average_ratio = min(average_order_value / max(average_order_value, 1), 1.0)
    return round((amount_ratio * 40) + (repeat_ratio * 35) + (average_ratio * 25), 2)


def get_client_status(score: float, revenue: float, total_revenue: float) -> str:
    """Classify Sales Order-based client value tier."""
    if score >= 80:
        return "Core Ordering Clients"
    if score >= 60:
        return "Growth Ordering Clients"
    if score >= 40:
        return "Developing Ordering Clients"
    return "Low Order Activity"


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
        .filter(Invoice.amount_paid > 0, Invoice.invoice_date >= start_date)
        .scalar() or 0
    )
    
    accounts_receivable = (
        db.session.query(func.sum(Invoice.balance))
        .filter(Invoice.balance > MONEY_TOLERANCE, Invoice.invoice_date >= start_date)
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
            .filter(Invoice.amount_paid > 0, Invoice.invoice_date >= week_start, Invoice.invoice_date <= week_end)
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


def _display_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _analytics_label_key(value: Any) -> str:
    """Normalize labels for analytics-only cleanup rules without editing source rows."""
    text = _display_text(value).upper().replace("&", " AND ")
    return " ".join(re_sub_non_company(text).split())


def analytics_expense_display_label(value: Any) -> str:
    """Return manager-facing expense labels for analytics displays only."""
    label = _display_text(value) or "Unspecified"
    if "MAILYN" in _analytics_label_key(label):
        return "Manager"
    return label


def analytics_revenue_item_display_name(value: Any) -> str:
    """Return canonical revenue item names for analytics grouping only."""
    label = _display_text(value) or "Unspecified Item"
    if _analytics_label_key(label) in {"ROLLOUT IMPLEMENTATION", "ROLL OUT IMPLEMENTATION"}:
        return "ROLL OUT IMPLEMENTATION"
    return label


ANALYTICS_ITEM_CATEGORIES = ("System", "Hardware", "Services", "Office Materials")
ANALYTICS_UNCATEGORIZED = "Uncategorized"


def analytics_item_category_key(value: Any) -> str:
    """Return the stable key used for manager-maintained item categories."""
    return _analytics_label_key(analytics_revenue_item_display_name(value))


def analytics_valid_item_category(value: Any) -> str:
    label = _display_text(value)
    for category in ANALYTICS_ITEM_CATEGORIES:
        if label.upper() == category.upper():
            return category
    return ANALYTICS_UNCATEGORIZED


def analytics_item_category_map(db: Any, models: dict[str, Any]) -> dict[str, str]:
    model = models.get("AnalyticsItemCategory")
    if model is None:
        return {}
    return {
        row.normalized_item_key: analytics_valid_item_category(row.category)
        for row in db.session.query(model).all()
    }


def exclude_from_item_forecast(value: Any) -> bool:
    """Exclude known non-managerial item noise from Item Forecasts only."""
    return _analytics_label_key(value) == "TMU220D JOURNAL PAPER SINGLE PLY"


def _store_group_key(value: Any) -> str:
    text = _display_text(value).upper()
    return " ".join(re_sub_non_company(text).split())


def _branch_group_key(value: Any) -> str:
    text = _display_text(value).upper().replace("&", " AND ")
    normalized = " ".join(re_sub_non_company(text).split())
    no_branch_placeholders = {
        "",
        "N A",
        "NA",
        "NONE",
        "NO BRANCH",
        "NO STORE BRANCH",
        "NOT APPLICABLE",
    }
    return "" if normalized in no_branch_placeholders else normalized


def get_clients_analysis(db: Any, models: dict[str, Any], start_date: Any = None, end_date: Any = None) -> dict[str, Any]:
    """Get Sales Order-based client value analysis grouped by Store Name."""
    Invoice = models["Invoice"]
    SalesOrder = models["SalesOrder"]
    SalesOrderBranch = models.get("SalesOrderBranch")
    SalesOrderItem = models["SalesOrderItem"]

    order_query = db.session.query(SalesOrder).order_by(
        SalesOrder.order_date.desc(),
        SalesOrder.created_at.desc(),
        SalesOrder.id.desc(),
    )
    orders = _apply_date_bounds(order_query, SalesOrder.order_date, start_date, end_date).all()
    if not orders:
        return {
            "clients_table": [],
            "top_3_insights": [],
            "total_clients": 0,
            "clients": [],
            "top_3": [],
            "total": 0,
        }

    today = datetime.now().date()
    order_ids = [order.id for order in orders]
    item_totals = {}
    items_by_order = defaultdict(list)
    branches_by_order = defaultdict(list)
    if order_ids:
        item_rows = (
            db.session.query(SalesOrderItem)
            .filter(SalesOrderItem.sales_order_id.in_(order_ids))
            .all()
        )
        for item in item_rows:
            items_by_order[item.sales_order_id].append(item)
        item_totals = {
            order_id: sum(float(item.total or 0) for item in order_items)
            for order_id, order_items in items_by_order.items()
        }
        if SalesOrderBranch is not None:
            branch_rows = (
                db.session.query(SalesOrderBranch)
                .filter(SalesOrderBranch.sales_order_id.in_(order_ids))
                .all()
            )
            for branch in branch_rows:
                branches_by_order[branch.sales_order_id].append(branch)

    invoice_paid_by_order = defaultdict(float)
    if order_ids:
        invoice_query = (
            db.session.query(
                Invoice.sales_order_id,
                func.coalesce(func.sum(Invoice.amount_paid), 0).label("amount_paid"),
            )
            .filter(Invoice.sales_order_id.in_(order_ids))
        )
        invoice_rows = (
            _apply_date_bounds(invoice_query, Invoice.invoice_date, start_date, end_date)
            .group_by(Invoice.sales_order_id)
            .all()
        )
        invoice_paid_by_order = defaultdict(
            float,
            {row.sales_order_id: float(row.amount_paid or 0) for row in invoice_rows},
        )

    store_groups = {}
    for order in orders:
        client_name = _display_text(order.client.client_name if order.client else "")
        company_name = _display_text(order.company_name or client_name or "Unmapped Company")
        store_name = _display_text(order.store_name or order.company_name or client_name or "Unspecified Store").upper()
        store_key = _store_group_key(store_name)
        if not store_key:
            store_key = f"STORE-{order.id}"
        group = store_groups.setdefault(
            store_key,
            {
                "store_name": store_name,
                "store_key": store_key,
                "company_names": set(),
                "client_ids": set(),
                "branches": {},
                "order_amounts": [],
                "order_count": 0,
                "total_order_amount": 0.0,
                "total_paid": 0.0,
                "latest_order_date": None,
                "items": defaultdict(lambda: {
                    "quantity": 0.0,
                    "sales_order_value": 0.0,
                    "cost": 0.0,
                    "cost_data_complete": True,
                }),
                "monthly_sales": defaultdict(float),
                "cost_data_complete": True,
            },
        )
        if len(store_name) < len(group["store_name"]):
            group["store_name"] = store_name
        if company_name:
            group["company_names"].add(company_name)
        if order.client_id:
            group["client_ids"].add(order.client_id)
        order_branches = branches_by_order.get(order.id)
        if order_branches:
            for branch in order_branches:
                branch_key = _branch_group_key(branch.branch_name)
                if branch_key and branch_key not in group["branches"]:
                    group["branches"][branch_key] = branch.branch_name
        else:
            branch_key = _branch_group_key(order.store_branch)
            if branch_key and branch_key not in group["branches"]:
                group["branches"][branch_key] = branch_key

        order_amount = item_totals.get(order.id) or float(order.total_amount or 0)
        group["order_amounts"].append(order_amount)
        group["order_count"] += 1
        group["total_order_amount"] += order_amount
        group["total_paid"] += float(invoice_paid_by_order[order.id] or 0)
        if order.order_date:
            group["monthly_sales"][order.order_date.strftime("%Y-%m")] += order_amount
        for item in items_by_order.get(order.id, []):
            item_name = _display_text(item.particular) or "Unspecified Item"
            quantity = float(item.quantity or 0)
            selling_price = float(item.selling_price or 0)
            unit_cost = float(item.unit_cost or 0)
            item_sales = float(item.total or 0) or quantity * selling_price
            item_cost = quantity * unit_cost
            item_data = group["items"][item_name]
            item_data["quantity"] += quantity
            item_data["sales_order_value"] += item_sales
            item_data["cost"] += item_cost
            if quantity <= 0 or selling_price <= 0 or unit_cost <= 0:
                item_data["cost_data_complete"] = False
                group["cost_data_complete"] = False
        if order.order_date and (
            group["latest_order_date"] is None
            or order.order_date > group["latest_order_date"]
        ):
            group["latest_order_date"] = order.order_date

    for group in store_groups.values():
        order_count = group["order_count"]
        group["average_order"] = group["total_order_amount"] / order_count if order_count else 0
        group["repeat_frequency"] = max(order_count - 1, 0)
        group["store_count"] = len(group["branches"])
        group["total_cost"] = sum(float(item["cost"] or 0) for item in group["items"].values())
        if not group["items"]:
            group["cost_data_complete"] = False

    max_revenue = max([stats["total_order_amount"] for stats in store_groups.values()] or [0])
    max_order_count = max([stats["order_count"] for stats in store_groups.values()] or [0])
    max_branch_count = max([stats["store_count"] for stats in store_groups.values()] or [0])

    def clamp(value: float, upper: float) -> float:
        return max(0.0, min(float(value or 0), upper))

    def ratio(value: float, maximum: float) -> float:
        return clamp(float(value or 0) / float(maximum or 1), 1.0) if maximum else 0.0

    def ranking_for(metric_name: str) -> dict[str, int]:
        ranked = sorted(
            store_groups.items(),
            key=lambda entry: (
                -float(entry[1].get(metric_name, 0) or 0),
                str(entry[1].get("store_name") or entry[0]),
            ),
        )
        return {store_key: rank for rank, (store_key, _) in enumerate(ranked, start=1)}

    revenue_rankings = ranking_for("total_order_amount")
    frequency_rankings = ranking_for("order_count")
    branch_rankings = ranking_for("store_count")
    client_count = max(len(store_groups), 1)

    clients_data = []
    
    for store_key, stats in store_groups.items():
        company_names = sorted(stats["company_names"])
        branch_names = sorted(stats["branches"].values())
        company_name = ", ".join(company_names) if company_names else "Unmapped Company"
        branch_display = ", ".join(branch_names) if branch_names else ""
        branches = len(branch_names)
        order_count = stats["order_count"]
        revenue = float(stats["total_order_amount"] or 0)
        total_cost = float(stats["total_cost"] or 0)
        gross_profit = revenue - total_cost
        profit_margin = (gross_profit / revenue * 100) if revenue > 0 else 0
        total_paid = float(stats["total_paid"] or 0)
        balance = max(revenue - total_paid, 0)
        last_purchase = stats.get("latest_order_date")
        recency_ratio = 0.0
        if last_purchase:
            days_since_purchase = max((today - last_purchase).days, 0)
            recency_ratio = max(0.0, 1 - min(days_since_purchase, 365) / 365)
        revenue_rank = revenue_rankings.get(store_key, client_count)
        frequency_rank = frequency_rankings.get(store_key, client_count)
        branch_rank = branch_rankings.get(store_key, client_count)
        amount_score = round(ratio(revenue, max_revenue) * 50, 2)
        order_frequency_score = round(ratio(order_count, max_order_count) * 30, 2)
        branch_count_score = round(ratio(branches, max_branch_count) * 20, 2)
        client_performance_score = round(
            clamp(amount_score, 50)
            + clamp(order_frequency_score, 30)
            + clamp(branch_count_score, 20),
            2,
        )
        item_metrics = []
        for item_name, item in stats["items"].items():
            item_sales = float(item["sales_order_value"] or 0)
            item_cost = float(item["cost"] or 0)
            item_profit = item_sales - item_cost
            item_margin = (item_profit / item_sales * 100) if item_sales > 0 else 0
            item_metrics.append({
                "item": item_name,
                "quantity": int(item["quantity"] or 0),
                "sales_order_value": round(item_sales, 2),
                "cost": round(item_cost, 2),
                "gross_profit": round(item_profit, 2),
                "profit_margin": round(item_margin, 2),
                "cost_data_complete": bool(item["cost_data_complete"]),
            })
        item_metrics.sort(key=lambda item: (-item["quantity"], -item["sales_order_value"], item["item"]))
        top_item = item_metrics[0] if item_metrics else None
        monthly_history = [
            {"period": period, "sales_order_value": round(value, 2)}
            for period, value in sorted(stats["monthly_sales"].items())
        ]
        current_month_key = today.strftime("%Y-%m")
        complete_months = [
            item for item in monthly_history
            if item["period"] < current_month_key
        ]
        trend_status = "insufficient_history"
        trend_change_percent = None
        if len(complete_months) >= 3:
            previous_value = float(complete_months[-2]["sales_order_value"] or 0)
            current_value = float(complete_months[-1]["sales_order_value"] or 0)
            if previous_value > 0:
                trend_change_percent = round((current_value - previous_value) / previous_value * 100, 2)
                trend_status = "declining" if trend_change_percent <= -10 else "stable_or_growing"
            else:
                trend_status = "not_comparable"
        client_data = {
            "store_name": stats["store_name"],
            "store_key": store_key,
            "store_branch": branch_display,
            "store_branches": branch_names,
            "company_name": company_name,
            "parent_company_name": company_name,
            "client_ids": sorted(stats["client_ids"]),
            "branches_count": branches,
            "total_revenue": round(revenue, 2),
            "sales_order_value": round(revenue, 2),
            "total_cost": round(total_cost, 2),
            "gross_profit": round(gross_profit, 2),
            "profit_margin": round(profit_margin, 2),
            "cost_data_status": "complete" if stats["cost_data_complete"] else "insufficient_cost_data",
            "total_paid": round(total_paid, 2),
            "balance": round(balance, 2),
            "balance_status": "Settled" if balance <= 0 else "Unsettled Balance",
            "value_status": "Unclassified",
            "cohort": "Unclassified",
            "score": round(client_performance_score / 100, 4),
            "client_performance_score": client_performance_score,
            "master_priority_rank": 0,
            "abc_category": "Unclassified",
            "cumulative_revenue_percent": 0,
            "order_count": order_count,
            "repeat_order_frequency": stats["repeat_frequency"],
            "average_order_value": round(float(stats["average_order"] or 0), 2),
            "top_item": top_item,
            "item_metrics": item_metrics,
            "monthly_history": monthly_history,
            "trend_status": trend_status,
            "trend_change_percent": trend_change_percent,
            "recency_ratio": round(recency_ratio, 4),
            "score_breakdown": {
                "total_sales_order_amount": amount_score,
                "order_frequency": order_frequency_score,
                "branch_count": branch_count_score,
                "revenue_rank": revenue_rank,
                "frequency_rank": frequency_rank,
                "branch_rank": branch_rank,
                "score_priority_rank": 0,
            },
            "recommendations": [],
            "last_purchase": last_purchase.isoformat() if last_purchase else None
        }
        clients_data.append(client_data)

    total_client_revenue = sum(float(client["sales_order_value"] or 0) for client in clients_data)
    cumulative_revenue = 0.0
    clients_data.sort(key=lambda x: (-x["client_performance_score"], -x["sales_order_value"], x["store_name"]))
    for priority_rank, client in enumerate(clients_data, start=1):
        client["master_priority_rank"] = priority_rank
        client["score_breakdown"]["score_priority_rank"] = priority_rank
        previous_cumulative_percent = (cumulative_revenue / total_client_revenue * 100) if total_client_revenue else 0
        cumulative_revenue += float(client["sales_order_value"] or 0)
        cumulative_percent = (cumulative_revenue / total_client_revenue * 100) if total_client_revenue else 0
        if previous_cumulative_percent < 80:
            cohort = "A-Class Clients"
        elif previous_cumulative_percent < 95:
            cohort = "B-Class Clients"
        else:
            cohort = "C-Class Clients"
        client["abc_category"] = cohort
        client["cohort"] = cohort
        client["value_status"] = cohort
        client["cumulative_revenue_percent"] = round(cumulative_percent, 2)
        recommendations = []
        if cohort == "A-Class Clients":
            recommendations.append("Protect this high-impact account with direct relationship management.")
        elif cohort == "B-Class Clients":
            recommendations.append("Nurture and upsell this client to grow them toward A-Class contribution.")
        else:
            recommendations.append("Use efficient automated follow-up and monitor for growth signals.")
        if float(client.get("recency_ratio") or 0) < 0.35 and float(client["sales_order_value"] or 0) > 0:
            recommendations.append("Re-engage client; purchasing activity is becoming stale.")
        client["recommendations"] = recommendations
    
    top_3_clients = [
        {
            "client": client["store_name"],
            "company_name": client["company_name"],
            "store_branch": client["store_branch"],
            "branches_count": client["branches_count"],
            "total_revenue": client["total_revenue"],
            "score": client["score"],
            "client_performance_score": client["client_performance_score"],
            "master_priority_rank": client["master_priority_rank"],
            "cumulative_revenue_percent": client["cumulative_revenue_percent"],
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
        "chart_data": [
            {
                "label": client["store_name"],
                "order_count": client["order_count"],
                "sales_order_value": client["sales_order_value"],
                "branches_count": client["branches_count"],
                "cohort": client["cohort"],
                "abc_category": client["abc_category"],
                "master_priority_rank": client["master_priority_rank"],
                "cumulative_revenue_percent": client["cumulative_revenue_percent"],
                "client_performance_score": client["client_performance_score"],
                "revenue_rank": client["score_breakdown"]["revenue_rank"],
                "frequency_rank": client["score_breakdown"]["frequency_rank"],
                "branch_rank": client["score_breakdown"]["branch_rank"],
                "score_breakdown": client["score_breakdown"],
            }
            for client in clients_data
        ],
        "top_3": top_3_clients,
        "total": len(clients_data),
        "cohorts": [{"label": label, "count": count} for label, count in cohort_counts.items()],
    }


def get_expenses_breakdown(
    db: Any,
    PurchaseOrder: Any,
    start_date: Any = None,
    end_date: Any = None,
) -> dict[str, Any]:
    """Get filtered expense composition and ranked expense contributors."""
    def bounded(query: Any) -> Any:
        return _apply_date_bounds(query, PurchaseOrder.date, start_date, end_date)

    category_rows = (
        bounded(
            db.session.query(
                PurchaseOrder.category,
                func.sum(PurchaseOrder.cash_amount).label("total_amount"),
            )
        )
        .group_by(PurchaseOrder.category)
        .all()
    )
    category_totals = {
        str(row.category or "VARIABLE").upper(): float(row.total_amount or 0)
        for row in category_rows
    }
    fixed_expenses = category_totals.get("FIXED", 0.0)
    variable_expenses = category_totals.get("VARIABLE", 0.0)
    total_expenses = fixed_expenses + variable_expenses

    item_rows = (
        bounded(
            db.session.query(
                PurchaseOrder.particulars,
                PurchaseOrder.supplier_payee,
                PurchaseOrder.category,
                func.sum(PurchaseOrder.cash_amount).label("total_amount"),
            )
        )
        .group_by(
            PurchaseOrder.particulars,
            PurchaseOrder.supplier_payee,
            PurchaseOrder.category,
        )
        .order_by(func.sum(PurchaseOrder.cash_amount).desc())
        .all()
    )

    def item_payload(row: Any) -> dict[str, Any]:
        return {
            "supplier_payee": analytics_expense_display_label(row.supplier_payee),
            "debit_account": analytics_expense_display_label(row.particulars),
            "amount": round(float(row.total_amount or 0), 2),
            "category": str(row.category or "VARIABLE").upper(),
        }

    fixed_list = [
        item_payload(row)
        for row in item_rows
        if str(row.category or "").upper() == "FIXED"
    ]
    variable_list = [
        item_payload(row)
        for row in item_rows
        if str(row.category or "").upper() == "VARIABLE"
    ]

    particulars_rows = (
        bounded(
            db.session.query(
                PurchaseOrder.particulars.label("label"),
                func.sum(PurchaseOrder.cash_amount).label("total_amount"),
            )
        )
        .group_by(PurchaseOrder.particulars)
        .order_by(func.sum(PurchaseOrder.cash_amount).desc())
        .all()
    )
    supplier_rows = (
        bounded(
            db.session.query(
                PurchaseOrder.supplier_payee.label("label"),
                func.sum(PurchaseOrder.cash_amount).label("total_amount"),
            )
        )
        .group_by(PurchaseOrder.supplier_payee)
        .order_by(func.sum(PurchaseOrder.cash_amount).desc())
        .all()
    )

    def ranked(rows: list[Any]) -> list[dict[str, Any]]:
        totals: dict[str, float] = defaultdict(float)
        for row in rows:
            label = analytics_expense_display_label(row.label)
            totals[label] += float(row.total_amount or 0)
        return [
            {
                "label": label,
                "amount": round(amount, 2),
                "share_percent": round(
                    amount / total_expenses * 100, 2
                ) if total_expenses else 0,
            }
            for label, amount in sorted(totals.items(), key=lambda item: item[1], reverse=True)
        ]

    return {
        "fixed_expenses": round(fixed_expenses, 2),
        "variable_expenses": round(variable_expenses, 2),
        "total_expenses": round(total_expenses, 2),
        "fixed_share_percent": round(fixed_expenses / total_expenses * 100, 2) if total_expenses else 0,
        "variable_share_percent": round(variable_expenses / total_expenses * 100, 2) if total_expenses else 0,
        "fixed_items": fixed_list,
        "variable_items": variable_list,
        "ranked_particulars": ranked(particulars_rows),
        "ranked_suppliers": ranked(supplier_rows),
        "pie_data": [
            {"label": "Fixed", "value": round(fixed_expenses, 2), "color": "#2563EB"},
            {"label": "Variable", "value": round(variable_expenses, 2), "color": "#F59E0B"},
        ],
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
    
    deduped_revenue = deduped_sales_item_revenue_subquery(db, SalesOrderItem, SalesOrder, start_date, end_date)
    revenue_total_query = db.session.query(func.sum(deduped_revenue.c.revenue))
    total_revenue = _apply_date_bounds(
        revenue_total_query,
        deduped_revenue.c.order_date,
        start_date,
        end_date,
    ).scalar() or 0

    # Total sales count
    total_sales = _apply_date_bounds(db.session.query(SalesOrder), SalesOrder.order_date, start_date, end_date).count()
    
    return {
        "top_3_clients": [{"name": row.client_name, "amount": round(float(row.total or 0), 2)} for row in top_clients],
        "top_3_items": [{"item": row.particular, "quantity": int(row.qty or 0)} for row in top_items],
        "total_sales": total_sales,
        "total_revenue": round(float(total_revenue or 0), 2),
    }


def build_client_forecasting(
    db: Any,
    models: dict[str, Any],
    clients: list[dict[str, Any]],
    start_date: Any = None,
    end_date: Any = None,
    mape_threshold: float = MAPE_DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Build Store Name forecasting slices for the Revenue analytics tab."""
    SalesOrder = models["SalesOrder"]
    SalesOrderItem = models["SalesOrderItem"]
    categories = ["A-Class Clients", "B-Class Clients", "C-Class Clients"]
    category_months: dict[str, dict[str, float]] = {category: defaultdict(float) for category in categories}

    sorted_clients = sorted(
        clients,
        key=lambda client: (
            -float(client.get("sales_order_value") or client.get("total_revenue") or 0),
            str(client.get("store_name") or ""),
        ),
    )
    top_clients = sorted_clients[:5]
    clients_by_key = {
        str(client.get("store_key") or ""): client
        for client in sorted_clients
        if client.get("store_key")
    }

    for client in clients:
        category = client.get("abc_category") or client.get("cohort") or "C-Class Clients"
        if category not in category_months:
            category = "C-Class Clients"
        for point in client.get("monthly_history") or []:
            period = point.get("period")
            if period:
                category_months[category][period] += float(point.get("sales_order_value") or 0)

    def forecast_from_months(months: dict[str, float]) -> dict[str, Any]:
        periods = sorted(months)
        values = [float(months[period] or 0) for period in periods]
        forecast = build_monthly_revenue_forecast(periods, values, horizon=3)
        forecast["accuracy"] = backtest_holt_winters(values)
        return forecast

    category_trends = []
    category_forecasts = []
    for category in categories:
        months = category_months[category]
        category_trends.append({
            "category": category,
            "points": [
                {
                    "period": period,
                    "label": month_label(period),
                    "revenue": round(float(months[period] or 0), 2),
                }
                for period in sorted(months)
            ],
        })
        category_forecasts.append({
            "category": category,
            **forecast_from_months(months),
        })

    client_forecast_lookup: dict[str, dict[str, Any]] = {}
    client_forecast_rows: list[dict[str, Any]] = []
    for client in sorted_clients:
        month_map = {
            point.get("period"): float(point.get("sales_order_value") or 0)
            for point in client.get("monthly_history") or []
            if point.get("period")
        }
        forecast = forecast_from_months(month_map)
        historical_points = [
            {
                "period": period,
                "label": month_label(period),
                "revenue": round(float(month_map[period] or 0), 2),
            }
            for period in sorted(month_map)
        ]
        peak_point = max(
            historical_points,
            key=lambda point: float(point.get("revenue") or 0),
            default=None,
        )
        summary = {
            "store_key": client.get("store_key"),
            "store_name": client.get("store_name"),
            "abc_category": client.get("abc_category") or client.get("cohort"),
            "sales_order_value": client.get("sales_order_value") or client.get("total_revenue") or 0,
            "order_count": client.get("order_count") or 0,
        }
        forecast_row = {
            **summary,
            "historical_points": historical_points,
            "peak_month": peak_point,
            **forecast,
        }
        client_forecast_rows.append(forecast_row)
        lookup_keys = {
            str(client.get("store_key") or ""),
            _store_group_key(client.get("store_name") or ""),
            _display_text(client.get("store_name") or "").upper(),
        }
        for key in lookup_keys:
            if key:
                client_forecast_lookup[key] = forecast_row

    top_client_trends = [
        {
            "store_key": row.get("store_key"),
            "store_name": row.get("store_name"),
            "abc_category": row.get("abc_category"),
            "sales_order_value": row.get("sales_order_value"),
            "order_count": row.get("order_count"),
            "points": row.get("historical_points") or [],
        }
        for row in client_forecast_rows[:5]
    ]
    top_client_forecasts = [
        row
        for row in client_forecast_rows[:5]
    ]

    order_query = _apply_date_bounds(
        db.session.query(SalesOrder),
        SalesOrder.order_date,
        start_date,
        end_date,
    )
    orders = order_query.all()
    order_ids = [order.id for order in orders]
    items_by_order: dict[int, list[Any]] = defaultdict(list)
    if order_ids:
        for item in db.session.query(SalesOrderItem).filter(SalesOrderItem.sales_order_id.in_(order_ids)).all():
            items_by_order[item.sales_order_id].append(item)

    item_groups: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for order in orders:
        client_name = _display_text(order.client.client_name if order.client else "")
        store_name = _display_text(order.store_name or order.company_name or client_name or "Unspecified Store").upper()
        store_key = _store_group_key(store_name)
        if store_key not in clients_by_key or not order.order_date:
            continue
        period = order.order_date.strftime("%Y-%m")
        for item in items_by_order.get(order.id, []):
            item_name = analytics_revenue_item_display_name(item.particular)
            quantity = float(item.quantity or 0)
            selling_price = float(item.selling_price or 0)
            revenue = float(item.total or 0) or quantity * selling_price
            group = item_groups[store_key].setdefault(
                item_name,
                {
                    "item": item_name,
                    "quantity": 0.0,
                    "revenue": 0.0,
                    "monthly_quantity": defaultdict(float),
                    "monthly_revenue": defaultdict(float),
                },
            )
            group["quantity"] += quantity
            group["revenue"] += revenue
            group["monthly_quantity"][period] += quantity
            group["monthly_revenue"][period] += revenue

    purchase_recommendation_lookup: dict[str, dict[str, Any]] = {}
    purchase_recommendation_rows = []
    for client in sorted_clients:
        store_key = str(client.get("store_key") or "")
        store_sales = float(client.get("sales_order_value") or client.get("total_revenue") or 0)
        store_items = sorted(
            item_groups.get(store_key, {}).values(),
            key=lambda item: (-float(item.get("revenue") or 0), str(item.get("item") or "")),
        )[:3]
        recommendations = []
        for item in store_items:
            periods = sorted(item["monthly_quantity"])
            monthly_quantities = [float(item["monthly_quantity"][period] or 0) for period in periods]
            backtest = backtest_holt_winters(monthly_quantities)
            if backtest["status"] == "tested":
                working = monthly_quantities[:]
                forecast_quantities = []
                for _ in range(3):
                    predicted_quantity = max(holt_winters_forecast(working), 0)
                    forecast_quantities.append(predicted_quantity)
                    working.append(predicted_quantity)
                mape = backtest["mape"]
                confidence_score = round(max(0.0, min(100.0, 100.0 - float(mape or 0))), 1) if mape is not None else 0.0
                status = "High Confidence" if mape is not None and mape <= float(mape_threshold) else "Needs Review"
                method = "holt_winters"
            else:
                average_quantity = sum(monthly_quantities[-3:]) / min(len(monthly_quantities), 3) if monthly_quantities else 0.0
                forecast_quantities = [average_quantity, average_quantity, average_quantity]
                recency_component = float(client.get("recency_ratio") or 0) * 35
                frequency_component = min(float(client.get("order_count") or 0) / 6, 1) * 25
                share_component = (float(item.get("revenue") or 0) / store_sales * 30) if store_sales else 0
                history_component = min(len(periods) / 3, 1) * 10
                confidence_score = round(min(74.0, recency_component + frequency_component + share_component + history_component), 1)
                status = "Needs Review" if len(periods) >= 2 else "Insufficient History"
                method = "fallback_average"
            total_quantity = max(round(sum(forecast_quantities), 2), 0)
            average_price = float(item.get("revenue") or 0) / float(item.get("quantity") or 1)
            recommendations.append({
                "item": item.get("item"),
                "expected_next_3_month_qty": total_quantity,
                "expected_next_3_month_revenue": round(total_quantity * average_price, 2),
                "confidence_score": confidence_score,
                "status": status,
                "method": method,
                "mape": backtest["mape"],
                "historical_months": len(periods),
            })
        recommendation_row = {
            "store_key": client.get("store_key"),
            "store_name": client.get("store_name"),
            "abc_category": client.get("abc_category") or client.get("cohort"),
            "recommendations": recommendations,
        }
        purchase_recommendation_rows.append(recommendation_row)
        lookup_keys = {
            store_key,
            _store_group_key(client.get("store_name") or ""),
            _display_text(client.get("store_name") or "").upper(),
        }
        for key in lookup_keys:
            if key:
                purchase_recommendation_lookup[key] = recommendation_row

    return {
        "category_trends": category_trends,
        "category_forecasts": category_forecasts,
        "top_client_trends": top_client_trends,
        "top_client_forecasts": top_client_forecasts,
        "purchase_recommendations": purchase_recommendation_rows[:5],
        "client_forecast_lookup": client_forecast_lookup,
        "purchase_recommendation_lookup": purchase_recommendation_lookup,
    }


def get_sales_analysis(
    db: Any,
    models: dict[str, Any],
    mape_threshold: float = MAPE_DEFAULT_THRESHOLD,
    start_date: Any = None,
    end_date: Any = None,
    forecast_start_date: Any = None,
    forecast_end_date: Any = None,
) -> dict[str, Any]:
    """Build the complete sales analytics response payload."""
    SalesOrder = models["SalesOrder"]
    SalesOrderItem = models["SalesOrderItem"]
    Invoice = models["Invoice"]
    PurchaseOrder = models.get("PurchaseOrder")
    category_map = analytics_item_category_map(db, models)
    forecast = get_sales_forecast(
        db,
        SalesOrderItem,
        SalesOrder,
        mape_threshold,
        start_date,
        end_date,
        forecast_start_date,
        forecast_end_date,
    )
    descriptive = get_sales_descriptive(db, SalesOrderItem, SalesOrder, start_date, end_date, category_map)
    clients = get_clients_analysis(db, models, start_date, end_date)
    pondo = 0.0
    if PurchaseOrder is not None:
        paid_revenue = _apply_date_bounds(db.session.query(func.sum(Invoice.amount_paid)).filter(Invoice.amount_paid > 0), Invoice.invoice_date, start_date, end_date).scalar() or 0
        total_expenses = _apply_date_bounds(db.session.query(func.sum(PurchaseOrder.cash_amount)), PurchaseOrder.date, start_date, end_date).scalar() or 0
        pondo = max(float(paid_revenue or 0) - float(total_expenses or 0), 0)
    recommendation_payload = build_rule_based_recommendations(
        forecast,
        descriptive,
        clients["clients"],
        pondo,
    )
    client_forecasting = build_client_forecasting(
        db,
        models,
        clients["clients"],
        start_date,
        end_date,
        mape_threshold,
    )
    return {
        "kpis": get_sales_kpis(db, models, start_date, end_date),
        "history": get_sales_order_history(db, SalesOrder, Invoice, SalesOrderItem, start_date=start_date, end_date=end_date),
        "forecast": forecast["forecast"],
        "holt_winters": forecast["holt_winters"],
        "descriptive": descriptive,
        "predictive": forecast["predictive"],
        "prescriptive": recommendation_payload,
        "forecast_accuracy": forecast["forecast_accuracy"],
        "store_performance": clients["clients"],
        "store_recommendations": recommendation_payload["store_recommendations"],
        "system_warnings": recommendation_payload["system_warnings"],
        "rule_thresholds": recommendation_payload["rule_thresholds"],
        "recommendations": recommendation_payload["recommendations"],
        "client_forecasting": client_forecasting,
    }


def get_sales_descriptive(db: Any, SalesOrderItem: Any, SalesOrder: Any, start_date: Any = None, end_date: Any = None, category_map: dict[str, str] | None = None) -> dict[str, Any]:
    """Build descriptive analytics for products, periods, and trend direction."""
    deduped_revenue = deduped_sales_item_revenue_subquery(db, SalesOrderItem, SalesOrder, start_date, end_date)
    month_key = db_month_key(db, deduped_revenue.c.order_date).label('month')
    monthly_query = (
        db.session.query(
            month_key,
            func.sum(deduped_revenue.c.revenue).label('revenue'),
            func.sum(deduped_revenue.c.quantity).label('quantity'),
            func.count(func.distinct(deduped_revenue.c.order_date)).label('active_sales_days'),
        )
    )
    monthly_rows = (
        _apply_date_bounds(monthly_query, deduped_revenue.c.order_date, start_date, end_date)
        .group_by(month_key)
        .order_by(month_key)
        .all()
    )
    monthly_trend = [
        {
            "period": row.month,
            "period_label": month_label(row.month),
            "revenue": numeric(row.revenue, 2),
            "quantity": int(row.quantity or 0),
            "active_sales_days": int(row.active_sales_days or 0),
            "average_quantity": numeric(
                float(row.quantity or 0) / float(row.active_sales_days or 1),
                2,
            ),
        }
        for row in monthly_rows if row.month
    ]
    item_query = (
        db.session.query(
            deduped_revenue.c.particular,
            func.sum(deduped_revenue.c.quantity).label("quantity"),
            func.sum(deduped_revenue.c.revenue).label("revenue"),
        )
    )
    item_rows = (
        _apply_date_bounds(item_query, deduped_revenue.c.order_date, start_date, end_date)
        .group_by(deduped_revenue.c.particular)
        .order_by(func.sum(deduped_revenue.c.revenue).desc())
        .all()
    )
    category_map = category_map or {}
    product_totals: dict[str, dict[str, Any]] = {}
    for row in item_rows:
        item_name = analytics_revenue_item_display_name(row.particular)
        item_key = analytics_item_category_key(item_name)
        item_category = category_map.get(item_key, ANALYTICS_UNCATEGORIZED)
        bucket = product_totals.setdefault(item_name, {"quantity": 0.0, "revenue": 0.0, "category": item_category})
        bucket["quantity"] += float(row.quantity or 0)
        bucket["revenue"] += float(row.revenue or 0)
        bucket["category"] = item_category
    product_distribution = [
        {
            "item": item,
            "category": values.get("category") or ANALYTICS_UNCATEGORIZED,
            "quantity": int(values["quantity"] or 0),
            "revenue": numeric(values["revenue"], 2),
        }
        for item, values in sorted(product_totals.items(), key=lambda entry: entry[1]["revenue"], reverse=True)
    ]
    weekday_number = db_weekday(db, deduped_revenue.c.order_date).label('weekday')
    weekday_query = (
        db.session.query(
            weekday_number,
            func.sum(deduped_revenue.c.revenue).label('revenue'),
            func.sum(deduped_revenue.c.quantity).label('quantity'),
            func.count(func.distinct(deduped_revenue.c.order_date)).label('active_sales_days'),
        )
    )
    weekday_rows = (
        _apply_date_bounds(weekday_query, deduped_revenue.c.order_date, start_date, end_date)
        .group_by(weekday_number)
        .order_by(func.sum(deduped_revenue.c.quantity).desc())
        .all()
    )
    weekday_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    peak_weekdays = [
        {
            "weekday": weekday_names[int(row.weekday or 0)],
            "revenue": numeric(row.revenue, 2),
            "quantity": int(row.quantity or 0),
            "active_sales_days": int(row.active_sales_days or 0),
            "average_quantity": numeric(
                float(row.quantity or 0) / float(row.active_sales_days or 1),
                2,
            ),
        }
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
            "months": sorted(monthly_trend, key=lambda item: item["average_quantity"], reverse=True)[:5],
            "weekdays": sorted(peak_weekdays, key=lambda item: item["average_quantity"], reverse=True)[:5],
        },
        "trend_direction": trend_direction,
        "early_warnings": early_warning,
    }


def get_sales_order_history(db: Any, SalesOrder: Any, Invoice: Any, SalesOrderItem: Any | None = None, filter_period: str = "month", start_date: Any = None, end_date: Any = None) -> dict[str, Any]:
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
            SalesOrder.order_date >= week_start,
            SalesOrder.order_date <= week_end
        )
        count = _apply_date_bounds(week_query, SalesOrder.order_date, start_date, end_date).count()
        weekly_data.append({
            "label": f"Week {week_num}",
            "count": count,
            "date": week_start.isoformat()
        })
        week_start = week_end + timedelta(days=1)
        week_num += 1
    
    if SalesOrderItem is not None:
        item_totals = (
            db.session.query(
                SalesOrderItem.sales_order_id.label("sales_order_id"),
                func.coalesce(func.sum(SalesOrderItem.total), 0).label("item_total"),
            )
            .group_by(SalesOrderItem.sales_order_id)
            .subquery()
        )
        latest_query = (
            db.session.query(
                SalesOrder,
                func.coalesce(item_totals.c.item_total, SalesOrder.total_amount, 0).label("computed_total"),
            )
            .outerjoin(item_totals, SalesOrder.id == item_totals.c.sales_order_id)
        )
    else:
        latest_query = db.session.query(SalesOrder, SalesOrder.total_amount.label("computed_total"))

    latest_order_rows = _apply_date_bounds(
        latest_query,
        SalesOrder.order_date,
        start_date,
        end_date,
    ).order_by(SalesOrder.order_date.desc(), SalesOrder.created_at.desc(), SalesOrder.id.desc()).limit(10).all()
    
    orders_list = [
        {
            "so_number": order.so_number,
            "company_name": order.company_name,
            "store_name": order.store_name,
            "store_branch": order.store_branch,
            "sales_staff": order.sales_staff,
            "date": order.order_date.isoformat() if order.order_date else None,
            "total": round(float(computed_total or 0), 2),
            "status": order.status,
        }
        for order, computed_total in latest_order_rows
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
        return datetime.strptime(f"{month_key}-01", "%Y-%m-%d").strftime("%b")
    except (TypeError, ValueError):
        return str(month_key or "Unknown period")


def build_monthly_revenue_forecast(monthly_periods: list[str], monthly_revenue: list[float], horizon: int = 12) -> dict[str, Any]:
    historical_points = [
        {
            "period": period,
            "label": month_label(period),
            "revenue": round(float(revenue or 0), 2),
            "type": "historical",
        }
        for period, revenue in zip(monthly_periods, monthly_revenue)
    ]
    if len(historical_points) < 3:
        return {
            "status": "insufficient_data",
            "message": "Not enough historical data to generate a reliable 3-month forecast.",
            "latest_historical_month": monthly_periods[-1] if monthly_periods else None,
            "forecast_start_month": None,
            "points": historical_points,
            "forecast_points": [],
            "historical_points": historical_points,
            "default_horizon": 3,
            "max_horizon": max(int(horizon or 0), 0),
            "horizon_options": [3, 6, 12],
        }

    working_values = [float(value or 0) for value in monthly_revenue]
    forecast_points = []
    latest_month = monthly_periods[-1]
    forecast_horizon = max(int(horizon or 0), 3)
    for offset in range(1, forecast_horizon + 1):
        forecast_revenue = round(holt_winters_forecast(working_values), 2)
        forecast_period = add_months(latest_month, offset)
        forecast_points.append({
            "period": forecast_period,
            "label": month_label(forecast_period),
            "revenue": forecast_revenue,
            "type": "forecast",
        })
        working_values.append(forecast_revenue)

    return {
        "status": "ready",
        "message": "Revenue forecast generated from historical Sales Order value.",
        "latest_historical_month": latest_month,
        "forecast_start_month": forecast_points[0]["period"],
        "points": historical_points + forecast_points,
        "forecast_points": forecast_points,
        "historical_points": historical_points,
        "default_horizon": 3,
        "max_horizon": forecast_horizon,
        "horizon_options": [3, 6, 12],
    }


def get_sales_forecast(
    db: Any,
    SalesOrderItem: Any,
    SalesOrder: Any | None = None,
    mape_threshold: float = MAPE_DEFAULT_THRESHOLD,
    start_date: Any = None,
    end_date: Any = None,
    forecast_start_date: Any = None,
    forecast_end_date: Any = None,
) -> dict[str, Any]:
    """Forecast expected revenue and profit from sales order item history."""
    forecast_data = []
    top_items_query = db.session.query(SalesOrderItem.particular, func.sum(SalesOrderItem.quantity).label("quantity"))
    if SalesOrder is not None:
        top_items_query = top_items_query.join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
        top_items_query = _apply_date_bounds(top_items_query, SalesOrder.order_date, start_date, end_date)
    raw_top_items = top_items_query.group_by(SalesOrderItem.particular).order_by(func.sum(SalesOrderItem.quantity).desc()).all()
    forecast_item_groups: dict[str, dict[str, Any]] = {}
    for item in raw_top_items:
        if exclude_from_item_forecast(item.particular):
            continue
        item_name = analytics_revenue_item_display_name(item.particular)
        group = forecast_item_groups.setdefault(item_name, {"quantity": 0.0, "raw_items": []})
        group["quantity"] += float(item.quantity or 0)
        group["raw_items"].append(item.particular)
    top_items = sorted(forecast_item_groups.items(), key=lambda entry: entry[1]["quantity"], reverse=True)[:10]
    for item_name, item_group in top_items:
        raw_item_names = item_group["raw_items"]
        item_rows_query = db.session.query(SalesOrderItem).filter(SalesOrderItem.particular.in_(raw_item_names))
        if SalesOrder is not None:
            item_rows_query = item_rows_query.join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
            item_rows_query = _apply_date_bounds(item_rows_query, SalesOrder.order_date, start_date, end_date)
        item_rows = item_rows_query.all()
        avg_price = sum((row.selling_price or 0) for row in item_rows) / len(item_rows) if item_rows else 0
        avg_cost = sum((row.unit_cost or 0) for row in item_rows) / len(item_rows) if item_rows else 0
        monthly_quantities = []
        if SalesOrder is not None:
            month_key = db_month_key(db, SalesOrder.order_date).label('month')
            monthly_query = (
                db.session.query(
                    month_key,
                    func.sum(SalesOrderItem.quantity).label('quantity'),
                )
                .join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
                .filter(SalesOrderItem.particular.in_(raw_item_names))
            )
            monthly_rows = _apply_date_bounds(monthly_query, SalesOrder.order_date, start_date, end_date).group_by(month_key).order_by(month_key).all()
            monthly_quantities = [float(row.quantity or 0) for row in monthly_rows]
        backtest = backtest_holt_winters(monthly_quantities)
        if backtest["status"] == "tested":
            predicted_qty = holt_winters_forecast(monthly_quantities)
            method = "holt_winters"
        else:
            predicted_qty = sum(monthly_quantities[-3:]) / min(len(monthly_quantities), 3) if monthly_quantities else float(item_group["quantity"] or 0)
            method = "fallback_average"
        accepted = backtest["mape"] is not None and backtest["mape"] <= float(mape_threshold)
        confidence = "High" if accepted else "Needs Review" if backtest["mape"] is not None else "Insufficient Data"
        forecast_quantity = max(int(round(float(predicted_qty or 0))), 0)
        forecast_data.append({
            "item": item_name,
            "predicted_qty": forecast_quantity,
            "predicted_revenue": round(forecast_quantity * avg_price, 2),
            "predicted_profit": round(forecast_quantity * (avg_price - avg_cost), 2),
            "confidence": confidence,
            "method": method,
            "mape": backtest["mape"],
            "accepted": accepted,
            "actual_validation": backtest["actual"],
            "predicted_validation": backtest["predicted"],
        })

    monthly_revenue = []
    monthly_profit = []
    forecast_monthly_periods = []
    forecast_monthly_revenue = []
    if SalesOrder is not None:
        deduped_revenue = deduped_sales_item_revenue_subquery(db, SalesOrderItem, SalesOrder, start_date, end_date)
        month_key = db_month_key(db, deduped_revenue.c.order_date).label('month')
        revenue_query = (
            db.session.query(
                month_key,
                func.sum(deduped_revenue.c.revenue).label('revenue'),
                func.sum(deduped_revenue.c.quantity * (deduped_revenue.c.selling_price - deduped_revenue.c.unit_cost)).label('profit')
            )
        )
        rows = _apply_date_bounds(revenue_query, deduped_revenue.c.order_date, start_date, end_date).group_by(month_key).order_by(month_key).all()
        monthly_periods = [row.month for row in rows if row.month]
        monthly_revenue = [float(row.revenue or 0) for row in rows]
        monthly_profit = [float(row.profit or 0) for row in rows]
        forecast_deduped_revenue = deduped_sales_item_revenue_subquery(db, SalesOrderItem, SalesOrder, forecast_start_date, forecast_end_date)
        forecast_month_key = db_month_key(db, forecast_deduped_revenue.c.order_date).label('month')
        forecast_revenue_query = db.session.query(
            forecast_month_key,
            func.sum(forecast_deduped_revenue.c.revenue).label('revenue'),
            func.sum(forecast_deduped_revenue.c.quantity * (forecast_deduped_revenue.c.selling_price - forecast_deduped_revenue.c.unit_cost)).label('profit')
        )
        all_revenue_rows = forecast_revenue_query.group_by(forecast_month_key).order_by(forecast_month_key).all()
        forecast_monthly_periods = [row.month for row in all_revenue_rows if row.month]
        forecast_monthly_revenue = [float(row.revenue or 0) for row in all_revenue_rows if row.month]
    else:
        monthly_periods = []

    revenue_backtest = backtest_holt_winters(monthly_revenue)
    profit_backtest = backtest_holt_winters(monthly_profit)
    revenue_next = round(holt_winters_forecast(monthly_revenue), 2)
    profit_next = round(holt_winters_forecast(monthly_profit), 2)
    monthly_revenue_forecast = build_monthly_revenue_forecast(forecast_monthly_periods, forecast_monthly_revenue)
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
                **monthly_revenue_forecast,
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
) -> dict[str, Any]:
    rule_label_map = {
        "high_sales_low_margin": "Strong sales but weak margin",
        "high_profit_store": "Healthy profit margin",
        "low_order_activity": "Low ordering activity",
        "declining_store_trend": "Recent sales decline",
        "insufficient_trend_history": "Not enough trend history",
        "frequently_ordered_item": "Clear lead item",
        "high_cost_low_sales_items": "High-cost items need review",
        "insufficient_cost_data": "Incomplete cost data",
        "monitor_store": "Continue monitoring",
    }

    def rule_labels(rule_matches: list[str]) -> list[str]:
        return [rule_label_map.get(rule, rule.replace("_", " ").title()) for rule in rule_matches]

    def business_summary(rule_matches: list[str], store_name: str) -> tuple[str, str]:
        if "high_sales_low_margin" in rule_matches:
            return (
                "This store has strong Sales Order value, but its profit margin is below the healthy range.",
                "The store is active, but the business may not be earning enough from those sales. Pricing, discounts, or supplier cost should be reviewed.",
            )
        if "declining_store_trend" in rule_matches:
            return (
                "This store's recent complete-month Sales Order value declined by at least 10%.",
                "Recent demand may be weakening. The account may need follow-up before the decline becomes larger.",
            )
        if "low_order_activity" in rule_matches:
            return (
                "This store orders less often than most stores in the selected period.",
                "The store may need a reorder reminder, promotion, or account follow-up to encourage repeat purchases.",
            )
        if "insufficient_cost_data" in rule_matches:
            return (
                "Some cost values are missing or zero for this store's items.",
                "Profit and margin results may be incomplete until the item cost data is corrected.",
            )
        if "high_cost_low_sales_items" in rule_matches:
            return (
                "Some items have high cost compared with their store-level sales value.",
                "These products may need a price or sourcing review before they are promoted further.",
            )
        if "high_profit_store" in rule_matches:
            return (
                "This store has a healthy profit margin in the selected period.",
                "The account is performing well and can be maintained through relationship care, bundles, or loyalty offers.",
            )
        if "insufficient_trend_history" in rule_matches:
            return (
                "This store does not yet have enough complete monthly history for a reliable trend reading.",
                "Use the current sales evidence, but avoid making a strong trend conclusion until more data is available.",
            )
        if "frequently_ordered_item" in rule_matches:
            return (
                "This store has a clear lead item based on item movement.",
                "That item can guide follow-up conversations, bundles, or cross-selling.",
            )
        return (
            f"No urgent issue was detected for {store_name}.",
            "The store should continue to be monitored using sales value, frequency, branch coverage, and item mix.",
        )

    def evidence_payload(client: dict[str, Any], store_name: str, sales_value: float, top_item: Any) -> list[dict[str, Any]]:
        return [
            {"label": "Store", "value": store_name},
            {"label": "Sales Order Value", "value": round(sales_value, 2), "type": "currency"},
            {"label": "Profit Margin", "value": client.get("profit_margin"), "suffix": "%"},
            {"label": "Order Count", "value": client.get("order_count")},
            {"label": "Branch Count", "value": client.get("branches_count")},
            {"label": "Top Item", "value": (top_item or {}).get("item") or "None"},
        ]

    def percentile(values: list[float], percentile_value: float) -> float:
        clean = sorted(float(value or 0) for value in values)
        if not clean:
            return 0.0
        if len(clean) == 1:
            return clean[0]
        position = (len(clean) - 1) * percentile_value
        lower = int(position)
        upper = min(lower + 1, len(clean) - 1)
        fraction = position - lower
        return clean[lower] + (clean[upper] - clean[lower]) * fraction

    sales_values = [float(client.get("sales_order_value") or client.get("total_revenue") or 0) for client in clients]
    frequency_values = [float(client.get("order_count") or 0) for client in clients]
    high_sales_threshold = round(percentile(sales_values, 0.75), 2)
    low_activity_threshold = round(percentile(frequency_values, 0.25), 2)
    thresholds = {
        "high_sales_percentile": 75,
        "high_sales_value": high_sales_threshold,
        "low_activity_percentile": 25,
        "low_activity_order_count": low_activity_threshold,
        "low_margin_percent": 15,
        "high_margin_percent": 30,
        "decline_percent": -10,
        "minimum_complete_months": 3,
        "client_value_formula": {
            "sales_order_value": 50,
            "order_frequency": 30,
            "branch_count": 20,
        },
    }

    store_recommendations = []
    for client in clients:
        store_name = client.get("store_name") or client.get("company_name") or "Unspecified Store"
        sales_value = float(client.get("sales_order_value") or client.get("total_revenue") or 0)
        order_count = float(client.get("order_count") or 0)
        margin = float(client.get("profit_margin") or 0)
        cost_complete = client.get("cost_data_status") == "complete"
        actions = []
        rule_matches = []
        severity = "success"

        if cost_complete and sales_value >= high_sales_threshold and margin < 15:
            actions.append("Review item pricing and supplier costs because strong Sales Order value is producing a low margin.")
            rule_matches.append("high_sales_low_margin")
            severity = "danger"
        elif cost_complete and margin >= 30:
            actions.append("Maintain the relationship and consider a store-specific loyalty or bundle offer.")
            rule_matches.append("high_profit_store")

        if order_count <= low_activity_threshold:
            actions.append("Follow up with the store and offer a targeted reorder prompt or promotion.")
            rule_matches.append("low_order_activity")
            if severity != "danger":
                severity = "warning"

        if client.get("trend_status") == "declining":
            actions.append("Review the store's recent demand and account activity because complete-month Sales Order value declined by at least 10%.")
            rule_matches.append("declining_store_trend")
            severity = "danger"
        elif client.get("trend_status") == "insufficient_history":
            actions.append("Collect at least three complete months of store activity before drawing a trend conclusion.")
            rule_matches.append("insufficient_trend_history")
            if severity == "success":
                severity = "warning"

        top_item = client.get("top_item")
        if top_item and float(top_item.get("quantity") or 0) > 0:
            actions.append(f"Use {top_item.get('item')} as the store's lead item for follow-up, bundles, or cross-selling.")
            rule_matches.append("frequently_ordered_item")

        item_metrics = client.get("item_metrics") or []
        item_sales_values = sorted(float(item.get("sales_order_value") or 0) for item in item_metrics)
        median_item_sales = percentile(item_sales_values, 0.50)
        high_cost_low_sales = [
            item for item in item_metrics
            if item.get("cost_data_complete")
            and float(item.get("sales_order_value") or 0) <= median_item_sales
            and float(item.get("sales_order_value") or 0) > 0
            and float(item.get("cost") or 0) / float(item.get("sales_order_value") or 1) >= 0.75
        ]
        if high_cost_low_sales:
            item_names = ", ".join(item.get("item") for item in high_cost_low_sales[:3])
            actions.append(f"Review pricing or sourcing for {item_names}; these items have high cost relative to their store-level sales.")
            rule_matches.append("high_cost_low_sales_items")
            if severity == "success":
                severity = "warning"

        if not cost_complete:
            actions.append("Complete missing or zero unit-cost data before using profit and margin results for decisions.")
            rule_matches.append("insufficient_cost_data")
            if severity == "success":
                severity = "warning"

        if not actions:
            actions.append("Continue monitoring this store's Sales Order value, frequency, branch coverage, and item mix.")
            rule_matches.append("monitor_store")

        why_this_appeared, what_it_means = business_summary(rule_matches, store_name)
        friendly_rule_labels = rule_labels(rule_matches)
        evidence = evidence_payload(client, store_name, sales_value, top_item)

        recommendation = {
            "type": "store_performance",
            "severity": severity,
            "store_key": client.get("store_key"),
            "store_name": store_name,
            "company_name": client.get("company_name"),
            "title": f"Recommendation for {store_name}",
            "reason": why_this_appeared,
            "trigger_condition": ", ".join(rule_matches),
            "friendly_trigger_labels": friendly_rule_labels,
            "why_this_appeared": why_this_appeared,
            "what_it_means": what_it_means,
            "recommended_action": " ".join(actions),
            "evidence": evidence,
            "data_used": [
                f"Store: {store_name}",
                f"Company: {client.get('company_name')}",
                f"Sales Order Value: {round(sales_value, 2)}",
                f"Total Cost: {client.get('total_cost')}",
                f"Gross Profit: {client.get('gross_profit')}",
                f"Profit Margin: {client.get('profit_margin')}%",
                f"Orders: {client.get('order_count')}",
                f"Branches: {client.get('branches_count')}",
                f"Top Item: {(top_item or {}).get('item') or 'None'}",
            ],
            "calculation_process": "The store was compared with the selected dataset's 75th-percentile Sales Order value and 25th-percentile order frequency. Margin rules use 15% and 30%; decline rules use the latest two complete months after at least three complete months of history.",
            "result": f"{store_name} generated {round(sales_value, 2)} in Sales Order value across {int(order_count)} order(s).",
            "business_interpretation": what_it_means,
            "suggested_action": " ".join(actions),
            "actions": actions,
            "rule_matches": rule_matches,
            "store_metrics": client,
        }
        store_recommendations.append(recommendation)

    store_recommendations.sort(
        key=lambda item: (
            {"danger": 0, "warning": 1, "success": 2}.get(item["severity"], 3),
            -float(item["store_metrics"].get("sales_order_value") or 0),
            item["store_name"],
        )
    )

    system_warnings = []
    if pondo <= 0:
        system_warnings.append({
            "type": "budget",
            "severity": "warning",
            "title": "Pondo exhausted",
            "reason": "Available operating funds are zero or below.",
            "trigger_condition": "Available pondo is zero or below.",
            "data_used": [f"Available Pondo: {pondo}"],
            "calculation_process": f"Available pondo {pondo} <= 0.",
            "result": "Procurement budget is not currently available.",
            "business_interpretation": "Purchasing without available funds can pressure cash flow.",
            "suggested_action": "Prioritize collections or budget replenishment before approving new purchases.",
        })
    for index, recommendation in enumerate(store_recommendations, start=1):
        recommendation["id"] = f"store-rec-{index}"
    for index, warning in enumerate(system_warnings, start=1):
        warning["id"] = f"system-warning-{index}"
    return {
        "store_recommendations": store_recommendations,
        "system_warnings": system_warnings,
        "rule_thresholds": thresholds,
        "recommendations": store_recommendations + system_warnings,
    }


def get_comparative_analysis(
    db: Any,
    Invoice: Any,
    year1: int,
    year2: int,
    CollectionReceipt: Any = None,
) -> dict[str, Any]:
    """Get comparative analysis between two years."""
    # Monthly comparison
    monthly_data = []
    for month in range(1, 13):
        revenue_column = (
            CollectionReceipt.collected_total if CollectionReceipt is not None
            else Invoice.amount_paid
        )
        revenue_date = (
            CollectionReceipt.receipt_date if CollectionReceipt is not None
            else Invoice.invoice_date
        )
        year1_revenue = (
            db.session.query(func.sum(revenue_column))
            .filter(
                db_year(revenue_date) == year1,
                db_month_number(revenue_date) == month,
                revenue_column > 0,
            )
            .scalar() or 0
        )
        
        year2_revenue = (
            db.session.query(func.sum(revenue_column))
            .filter(
                db_year(revenue_date) == year2,
                db_month_number(revenue_date) == month,
                revenue_column > 0,
            )
            .scalar() or 0
        )
        if CollectionReceipt is not None:
            year1_revenue += (
                db.session.query(func.sum(Invoice.amount_paid))
                .filter(
                    Invoice.amount_paid > 0,
                    ~Invoice.collection_receipts.any(),
                    db_year(Invoice.invoice_date) == year1,
                    db_month_number(Invoice.invoice_date) == month,
                )
                .scalar() or 0
            )
            year2_revenue += (
                db.session.query(func.sum(Invoice.amount_paid))
                .filter(
                    Invoice.amount_paid > 0,
                    ~Invoice.collection_receipts.any(),
                    db_year(Invoice.invoice_date) == year2,
                    db_month_number(Invoice.invoice_date) == month,
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
