"""Defense-release schema compatibility checks and SQLite migrations."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
from typing import Any

from sqlalchemy import inspect, text


DEFENSE_MIGRATION_ID = "2026-06-23-user-disable-reason"
SUPABASE_MIGRATION_PATH = "docs/supabase_defense_readiness_migration.sql"

REQUIRED_COLUMNS = {
    "users": {
        "profile_photo_data": "TEXT",
        "profile_photo_mime": "VARCHAR(80)",
        "disabled_reason": "TEXT",
    },
    "evaluation_sessions": {
        "user_id": "INTEGER REFERENCES users(id)",
    },
    "sales_order_items": {
        "sales_order_branch_id": "INTEGER REFERENCES sales_order_branches(id)",
    },
    "session_records": {
        "device_id": "VARCHAR(80)",
        "device_label": "VARCHAR(120)",
        "user_agent": "TEXT",
        "ip_address": "VARCHAR(80)",
        "concurrent_note": "TEXT",
    },
}

SQLITE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_evaluation_sessions_user_id_created "
    "ON evaluation_sessions (user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_invoices_amount_paid_date "
    "ON invoices (amount_paid, invoice_date)",
    "CREATE INDEX IF NOT EXISTS idx_invoices_balance_date "
    "ON invoices (balance, invoice_date)",
    "CREATE INDEX IF NOT EXISTS idx_sales_order_items_branch_id "
    "ON sales_order_items (sales_order_branch_id)",
    "CREATE INDEX IF NOT EXISTS idx_sales_orders_number_staff "
    "ON sales_orders (so_number, sales_staff)",
    "CREATE INDEX IF NOT EXISTS idx_sales_order_branches_order_id "
    "ON sales_order_branches (sales_order_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_order_branch_key "
    "ON sales_order_branches (sales_order_id, normalized_branch_key)",
    "CREATE INDEX IF NOT EXISTS idx_collection_receipts_invoice_date "
    "ON collection_receipts (invoice_id, receipt_date DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_collection_receipts_normalized_cr "
    "ON collection_receipts (normalized_cr_number)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_collection_receipts_invoice_cr "
    "ON collection_receipts (invoice_id, normalized_cr_number)",
    "CREATE INDEX IF NOT EXISTS idx_session_records_user_status_device "
    "ON session_records (user_id, status, device_id)",
)

SQLITE_COLLECTION_RECEIPTS_TABLE = """
CREATE TABLE IF NOT EXISTS collection_receipts (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    receipt_date DATE NOT NULL,
    cr_number VARCHAR(50) NOT NULL,
    normalized_cr_number VARCHAR(50) NOT NULL,
    payment_type VARCHAR(20) NOT NULL,
    payment_amount FLOAT NOT NULL DEFAULT 0,
    tax_amount_paid FLOAT NOT NULL DEFAULT 0,
    is_2307_checked BOOLEAN NOT NULL DEFAULT 0,
    collected_total FLOAT NOT NULL DEFAULT 0,
    created_by_user_id INTEGER REFERENCES users(id),
    recorded_by VARCHAR(80) NOT NULL DEFAULT 'system',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_collection_receipts_invoice_cr
        UNIQUE (invoice_id, normalized_cr_number)
)
"""

def _apply_sqlite_indexes(db: Any, connection: Any) -> None:
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    for statement in SQLITE_INDEXES:
        table_name = statement.split(" ON ", 1)[1].split(" ", 1)[0]
        if table_name not in table_names:
            continue
        connection.execute(text(statement))


def _missing_columns(db: Any) -> dict[str, list[str]]:
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    missing: dict[str, list[str]] = {}
    for table_name, required in REQUIRED_COLUMNS.items():
        if table_name not in table_names:
            continue
        existing = {column["name"] for column in inspector.get_columns(table_name)}
        absent = [column for column in required if column not in existing]
        if absent:
            missing[table_name] = absent
    return missing


def _backup_sqlite_database(db: Any) -> str | None:
    database_path = db.engine.url.database
    if not database_path or database_path == ":memory:":
        return None
    source = Path(database_path).resolve()
    if not source.exists():
        return None
    backup_dir = source.parent / "instance" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"{source.stem}-before-{DEFENSE_MIGRATION_ID}-{stamp}{source.suffix}"
    shutil.copy2(source, target)
    return str(target)


def ensure_defense_schema(db: Any) -> dict[str, Any]:
    """Migrate SQLite safely and fail clearly for unapplied production migrations."""
    missing = _missing_columns(db)
    dialect = db.engine.dialect.name
    backup_path = None
    table_names = set(inspect(db.engine).get_table_names())
    collection_receipts_missing = "invoices" in table_names and "collection_receipts" not in table_names

    if (missing or collection_receipts_missing) and dialect == "sqlite":
        backup_path = _backup_sqlite_database(db)
    if missing and dialect == "sqlite":
        with db.engine.begin() as connection:
            for table_name, columns in missing.items():
                for column_name in columns:
                    definition = REQUIRED_COLUMNS[table_name][column_name]
                    connection.execute(
                        text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {definition}')
                    )
            _apply_sqlite_indexes(db, connection)
        missing = _missing_columns(db)

    if dialect == "sqlite":
        with db.engine.begin() as connection:
            connection.execute(text(SQLITE_COLLECTION_RECEIPTS_TABLE))
            _apply_sqlite_indexes(db, connection)
            current_tables = set(inspect(connection).get_table_names())
            invoice_columns = (
                {
                    column["name"]
                    for column in inspect(connection).get_columns("invoices")
                }
                if "invoices" in current_tables else set()
            )
            legacy_payment_columns = {
                "id", "invoice_date", "cr_number", "payment_type",
                "payment_amount", "tax_amount_paid", "is_2307_checked",
                "amount_paid", "balance",
            }
            if legacy_payment_columns.issubset(invoice_columns):
                connection.execute(text("""
                INSERT INTO collection_receipts (
                    invoice_id, receipt_date, cr_number, normalized_cr_number,
                    payment_type, payment_amount, tax_amount_paid,
                    is_2307_checked, collected_total, recorded_by
                )
                SELECT
                    invoices.id,
                    invoices.invoice_date,
                    COALESCE(NULLIF(TRIM(invoices.cr_number), ''), 'LEGACY-' || invoices.id),
                    UPPER(COALESCE(NULLIF(TRIM(invoices.cr_number), ''), 'LEGACY-' || invoices.id)),
                    CASE
                        WHEN UPPER(COALESCE(invoices.payment_type, '')) = 'FULL' THEN 'FULL'
                        WHEN invoices.balance IS NOT NULL AND invoices.balance <= 0.01 THEN 'FULL'
                        ELSE 'DOWNPAYMENT'
                    END,
                    CASE
                        WHEN COALESCE(invoices.payment_amount, 0) > 0
                            THEN invoices.payment_amount
                        ELSE invoices.amount_paid
                    END,
                    COALESCE(invoices.tax_amount_paid, 0),
                    COALESCE(invoices.is_2307_checked, 0),
                    invoices.amount_paid,
                    'legacy migration'
                FROM invoices
                WHERE COALESCE(invoices.amount_paid, 0) > 0
                  AND NOT EXISTS (
                      SELECT 1 FROM collection_receipts
                      WHERE collection_receipts.invoice_id = invoices.id
                  )
                """))

    if missing:
        details = ", ".join(
            f"{table}.{column}" for table, columns in missing.items() for column in columns
        )
        raise RuntimeError(
            f"Database schema is missing required defense-release columns: {details}. "
            f"Back up the database, apply {SUPABASE_MIGRATION_PATH}, then restart."
        )

    return {
        "migration_id": DEFENSE_MIGRATION_ID,
        "dialect": dialect,
        "backup_path": backup_path,
        "status": "ready",
    }
