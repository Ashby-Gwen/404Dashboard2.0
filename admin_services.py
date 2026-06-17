"""Admin database utilities for Syluxent.

Maintenance guide:
- Add tables to TABLE_CONFIG when they should appear in the admin data grid.
- Keep SQL execution guarded here; routes should pass user input through these helpers.
- Bulk operations intentionally allow only status updates and whitelisted tables.
"""

from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime
from typing import Any

from sqlalchemy import String, cast, inspect, or_, text


TABLE_CONFIG = {
    "users": {"model": "User", "search": ["username", "email", "status"], "status": "status"},
    "roles": {"model": "Role", "search": ["role_name", "description"], "status": None},
    "clients": {"model": "Client", "search": ["client_name", "contact_info"], "status": None},
    "sales_orders": {"model": "SalesOrder", "search": ["so_number", "company_name", "store_name", "sales_staff", "notes"], "status": "status"},
    "invoices": {"model": "Invoice", "search": ["invoice_number", "invoice_type", "summary", "status", "cr_number"], "status": "status"},
    "purchase_orders": {"model": "PurchaseOrder", "search": ["check_voucher_number", "check_number", "supplier_payee", "particulars", "status"], "status": "status"},
    "session_records": {"model": "SessionRecord", "search": ["username", "role_name", "status"], "status": "status"},
    "analytics_data": {"model": "AnalyticsData", "search": ["source_type", "source_id", "party_name", "party_role", "category", "status", "description"], "status": "status"},
}

BLOCKED_SQL_KEYWORDS = ("drop", "alter", "attach", "detach", "pragma", "vacuum", "analyze", "reindex")


def get_data_grid(db: Any, models: dict[str, Any], table: str, args: Any) -> dict[str, Any]:
    model = _model_for(models, table)
    column_map = _model_column_map(model)
    display_columns = _display_columns(model, table)
    queryable_display_columns = [column for column in display_columns if column in column_map]
    page = max(_safe_int(args.get("page"), 1), 1)
    page_size = min(max(_safe_int(args.get("page_size"), 25), 5), 200)
    search = (args.get("search") or "").strip()
    status = (args.get("status") or "").strip()
    requested_sort = args.get("sort") or ("id" if "id" in column_map else queryable_display_columns[0])
    sort = requested_sort if requested_sort in column_map else ("id" if "id" in column_map else queryable_display_columns[0])
    direction = "desc" if (args.get("direction") or "desc").lower() == "desc" else "asc"
    filters = _parse_filters(args.get("filters"), queryable_display_columns)

    query = model.query
    config = TABLE_CONFIG[table]
    if search:
        clauses = []
        for column_name in config["search"]:
            column = column_map.get(column_name)
            if column is not None:
                clauses.append(cast(column, String).ilike(f"%{search}%"))
        if clauses:
            query = query.filter(or_(*clauses))
    if status and config["status"]:
        query = query.filter(column_map[config["status"]] == status)
    for column_name, value in filters.items():
        column = column_map.get(column_name)
        if column is not None and value not in ("", None):
            query = query.filter(cast(column, String).ilike(f"%{value}%"))

    total = query.count()
    pages = max((total + page_size - 1) // page_size, 1)
    page = min(page, pages)
    sort_column = column_map[sort]
    query = query.order_by(sort_column.desc() if direction == "desc" else sort_column.asc())
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "table": table,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": pages,
        "columns": display_columns,
        "sortable_columns": queryable_display_columns,
        "filterable_columns": queryable_display_columns,
        "sort": sort,
        "direction": direction,
        "filters": filters,
        "rows": [_serialize_model(row, table) for row in rows],
    }


def export_data_grid_csv(db: Any, models: dict[str, Any], table: str, args: Any) -> io.BytesIO:
    export_args = args.copy()
    export_args["page"] = 1
    export_args["page_size"] = 10000
    payload = get_data_grid(db, models, table, export_args)
    text_stream = io.StringIO()
    writer = csv.DictWriter(text_stream, fieldnames=payload["columns"])
    writer.writeheader()
    writer.writerows(payload["rows"])
    return io.BytesIO(text_stream.getvalue().encode("utf-8-sig"))


def get_db_health(db_path: str, backup_dir: str) -> dict[str, Any]:
    file_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    backups = []
    if os.path.isdir(backup_dir):
        backups = [os.path.join(backup_dir, name) for name in os.listdir(backup_dir) if name.endswith((".db", ".sqlite", ".bak"))]
    last_backup = max((os.path.getmtime(path) for path in backups), default=None)
    return {
        "database_size_bytes": file_size,
        "database_size_mb": round(file_size / (1024 * 1024), 2),
        "last_backup": datetime.fromtimestamp(last_backup).isoformat() if last_backup else None,
    }


def run_maintenance(db: Any, command: str) -> None:
    command = command.upper()
    if command not in {"VACUUM", "ANALYZE"}:
        raise ValueError("Only VACUUM and ANALYZE are supported.")
    db.session.rollback()
    with db.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(command))


def get_schema(db: Any) -> dict[str, Any]:
    inspector = inspect(db.engine)
    tables = []
    for table_name in inspector.get_table_names():
        tables.append(
            {
                "name": table_name,
                "columns": [
                    {
                        "name": column["name"],
                        "type": str(column["type"]),
                        "nullable": column["nullable"],
                        "default": column.get("default"),
                    }
                    for column in inspector.get_columns(table_name)
                ],
                "indexes": inspector.get_indexes(table_name),
            }
        )
    return {"tables": tables}


def run_safe_sql(db: Any, sql: str, dry_run: bool = True) -> dict[str, Any]:
    statement = (sql or "").strip()
    if not statement:
        raise ValueError("SQL query is required.")
    lowered = statement.lower()
    if any(keyword in lowered.split() for keyword in BLOCKED_SQL_KEYWORDS):
        raise ValueError("Schema and maintenance commands are blocked here. Use System Maintenance for VACUUM/ANALYZE.")

    result = db.session.execute(text(statement))
    rows = []
    columns = []
    if result.returns_rows:
        columns = list(result.keys())
        rows = [{key: _json_value(value) for key, value in dict(row._mapping).items()} for row in result.fetchmany(200)]

    if dry_run:
        db.session.rollback()
    else:
        if lowered.startswith("select"):
            db.session.rollback()
        else:
            db.session.commit()

    return {"dry_run": dry_run, "columns": columns, "rows": rows, "row_count": len(rows)}


def bulk_update_status(db: Any, models: dict[str, Any], table: str, ids: list[int], status: str) -> int:
    model = _model_for(models, table)
    status_column = TABLE_CONFIG[table]["status"]
    if not status_column:
        raise ValueError("This table does not support status updates.")
    rows = model.query.filter(model.id.in_(ids)).all()
    for row in rows:
        setattr(row, status_column, status)
    db.session.commit()
    return len(rows)


def bulk_delete(db: Any, models: dict[str, Any], table: str, ids: list[int]) -> int:
    model = _model_for(models, table)
    if table in {"users", "roles"}:
        raise ValueError("Bulk delete is disabled for users and roles.")
    rows = model.query.filter(model.id.in_(ids)).all()
    for row in rows:
        db.session.delete(row)
    db.session.commit()
    return len(rows)


def _model_for(models: dict[str, Any], table: str) -> Any:
    if table not in TABLE_CONFIG:
        raise ValueError("Unsupported table.")
    return models[TABLE_CONFIG[table]["model"]]


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _model_column_map(model: Any) -> dict[str, Any]:
    return {column.name: getattr(model, column.name) for column in model.__table__.columns}


def _display_columns(model: Any, table: str) -> list[str]:
    columns = [column.name for column in model.__table__.columns]
    if table == "users":
        return ["password" if column == "password_hash" else column for column in columns]
    return columns


def _parse_filters(raw_filters: str | None, allowed_columns: list[str]) -> dict[str, Any]:
    if not raw_filters:
        return {}
    try:
        parsed = json.loads(raw_filters)
        if not isinstance(parsed, dict):
            return {}
        allowed = set(allowed_columns)
        return {
            str(key): str(value).strip()
            for key, value in parsed.items()
            if key in allowed and str(value).strip()
        }
    except json.JSONDecodeError:
        return {}


def _serialize_model(row: Any, table: str | None = None) -> dict[str, Any]:
    data = {}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        if column.name == "password_hash":
            if table == "users":
                data["password"] = "********"
            continue
        data[column.name] = value
    if "id" not in data and hasattr(row, "id"):
        data["id"] = getattr(row, "id")
    return data


def _json_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
