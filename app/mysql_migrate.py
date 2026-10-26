"""Initialize MySQL and copy the two retired SQLite databases once.

The legacy files are mounted read-only by Compose. They are never deleted.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

from app.mysql_db import connect


LEGACY = Path(os.getenv("LEGACY_DATA_DIR", "/app/legacy"))
SOURCES = ("identity.sqlite3", "financial_freedom.sqlite3")
TABLE_ORDER = (
    "users", "auth_metadata", "auth_limits", "audit", "login_challenges",
    "sms_deliveries", "recovery_codes", "sessions",
    "quotes", "watchlist", "paper_accounts", "external_accounts", "external_positions",
    "paper_orders", "paper_fills", "bars", "dataset_manifests", "history_jobs",
    "provider_health", "research_runs", "ai_research_runs", "workspace_cache",
    "ai_documents", "ai_document_pages", "paper_account_actions", "paper_contract_overrides",
    "paper_contracts", "paper_ai_runs", "research_news", "sector_rotation_snapshots",
)


def _digest(rows):
    encoded = []
    for row in rows:
        encoded.append(json.dumps([value.hex() if isinstance(value, bytes) else value for value in row],
                                  ensure_ascii=False, separators=(",", ":"), default=str))
    return hashlib.sha256("\n".join(sorted(encoded)).encode()).hexdigest()


def _copy_database(filename: str) -> None:
    path = LEGACY / filename
    if not path.is_file():
        print(f"No legacy {filename}; starting with an empty MySQL database.", flush=True)
        return
    # The legacy financial DB uses WAL mode. Its bind mount is deliberately
    # read-only, so immutable mode avoids SQLite trying to create a -shm file.
    source = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    try:
        tables = [row[0] for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        tables.sort(key=lambda table: TABLE_ORDER.index(table) if table in TABLE_ORDER else len(TABLE_ORDER))
        with connect() as target:
            # Older SQLite files contain an orphan external position. Preserve
            # every source row, then restore enforcement for future writes.
            target.execute("SET FOREIGN_KEY_CHECKS=0")
            for table in tables:
                source_count = source.execute(f"SELECT COUNT(*) FROM '{table}'").fetchone()[0]
                exists = target.execute(
                    "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s",
                    (table,),
                ).fetchone()[0]
                if not exists:
                    if source_count:
                        raise RuntimeError(f"Legacy table {table} has {source_count} rows but no MySQL table")
                    continue
                columns = [row[1] for row in source.execute(f"PRAGMA table_info('{table}')")]
                target_columns = {row["name"] for row in target.execute(f"PRAGMA table_info({table})")}
                missing = set(columns) - target_columns
                if missing:
                    raise RuntimeError(f"MySQL table {table} is missing legacy columns: {sorted(missing)}")
                quoted = ",".join(f"`{column}`" for column in columns)
                existing = target.execute(f"SELECT COUNT(*) FROM `{table}`").fetchone()[0]
                if existing not in (0, source_count):
                    raise RuntimeError(f"MySQL {table} already has {existing} rows, legacy has {source_count}; refusing merge")
                if existing == 0 and source_count:
                    query = f"INSERT INTO `{table}` ({quoted}) VALUES ({','.join(['%s'] * len(columns))})"
                    rows = source.execute(f"SELECT {quoted} FROM '{table}'")
                    while batch := rows.fetchmany(500):
                        cursor = target.raw.cursor()
                        cursor.executemany(query, batch)
                target_rows = target.execute(f"SELECT {quoted} FROM `{table}`").fetchall()
                source_rows = source.execute(f"SELECT {quoted} FROM '{table}'").fetchall()
                if len(target_rows) != source_count or _digest([tuple(r.values()) for r in target_rows]) != _digest(source_rows):
                    raise RuntimeError(f"Data verification failed for {table}; leaving legacy files untouched")
                print(f"Verified {filename}:{table} rows={source_count}", flush=True)
            target.execute("SET FOREIGN_KEY_CHECKS=1")
    finally:
        source.close()


def main() -> None:
    from app import main as application, security
    from app.market_context import initialize_context

    with connect() as c:
        state_table = c.execute(
            "SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='migration_state'"
        ).fetchone()
        if state_table and c.execute(
            "SELECT 1 FROM migration_state WHERE name='legacy_sqlite_to_mysql'"
        ).fetchone():
            print("Legacy migration already verified.", flush=True)
            return

    application.initialize()
    security.initialize()
    application.paper_broker(system=True).initialize()
    initialize_context(application.db)
    # Security bootstrap creates a policy marker/audit event before the old
    # identity data exists. Remove only these fresh rows before the first copy.
    if (LEGACY / "identity.sqlite3").is_file():
        with connect() as c:
            existing_users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if not existing_users:
                c.execute("DELETE FROM auth_metadata")
                c.execute("DELETE FROM audit")
    with connect() as c:
        c.execute("CREATE TABLE IF NOT EXISTS migration_state (name VARCHAR(100) PRIMARY KEY, completed_at VARCHAR(40) NOT NULL) ENGINE=InnoDB")
    for filename in SOURCES:
        _copy_database(filename)
    from datetime import datetime, timezone
    with connect() as c:
        c.execute("INSERT INTO migration_state(name,completed_at) VALUES(%s,%s)",
                  ("legacy_sqlite_to_mysql", datetime.now(timezone.utc).isoformat()))
    print("MySQL migration complete; legacy SQLite files preserved.", flush=True)


if __name__ == "__main__":
    main()
