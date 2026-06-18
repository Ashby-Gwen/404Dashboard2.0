"""Defense-release schema compatibility checks and SQLite migrations."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
from typing import Any

from sqlalchemy import inspect, text


DEFENSE_MIGRATION_ID = "2026-06-18-defense-readiness"
SUPABASE_MIGRATION_PATH = "docs/supabase_defense_readiness_migration.sql"

REQUIRED_COLUMNS = {
    "users": {
        "profile_photo_data": "TEXT",
        "profile_photo_mime": "VARCHAR(80)",
    },
    "evaluation_sessions": {
        "user_id": "INTEGER REFERENCES users(id)",
    },
}

SQLITE_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_evaluation_sessions_user_id_created "
    "ON evaluation_sessions (user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_invoices_amount_paid_date "
    "ON invoices (amount_paid, invoice_date)",
    "CREATE INDEX IF NOT EXISTS idx_invoices_balance_date "
    "ON invoices (balance, invoice_date)",
)


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

    if missing and dialect == "sqlite":
        backup_path = _backup_sqlite_database(db)
        with db.engine.begin() as connection:
            for table_name, columns in missing.items():
                for column_name in columns:
                    definition = REQUIRED_COLUMNS[table_name][column_name]
                    connection.execute(
                        text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {definition}')
                    )
            for statement in SQLITE_INDEXES:
                connection.execute(text(statement))
        missing = _missing_columns(db)

    if missing:
        details = ", ".join(
            f"{table}.{column}" for table, columns in missing.items() for column in columns
        )
        raise RuntimeError(
            f"Database schema is missing required defense-release columns: {details}. "
            f"Back up the database, apply {SUPABASE_MIGRATION_PATH}, then restart."
        )

    if dialect == "sqlite":
        with db.engine.begin() as connection:
            for statement in SQLITE_INDEXES:
                connection.execute(text(statement))

    return {
        "migration_id": DEFENSE_MIGRATION_ID,
        "dialect": dialect,
        "backup_path": backup_path,
        "status": "ready",
    }
