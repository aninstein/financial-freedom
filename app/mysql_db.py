"""Small DB-API facade while the application's existing SQL moves to MySQL.

Only the fixed SQL in this repository is accepted. New queries should use MySQL
syntax directly; this adapter exists to keep the migration reviewable.
"""
from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

import pymysql
from pymysql.cursors import DictCursor


class Row(dict):
    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class Cursor:
    def __init__(self, cursor: pymysql.cursors.Cursor | None = None, rows: list[Row] | None = None):
        self._cursor = cursor
        self._rows = rows
        self._position = 0
        self.rowcount = cursor.rowcount if cursor else len(rows or [])
        self.lastrowid = cursor.lastrowid if cursor else None

    def fetchone(self) -> Row | None:
        if self._rows is not None:
            if self._position >= len(self._rows):
                return None
            item = self._rows[self._position]
            self._position += 1
            return item
        row = self._cursor.fetchone() if self._cursor else None
        return Row(row) if row is not None else None

    def fetchall(self) -> list[Row]:
        if self._rows is not None:
            rows = self._rows[self._position:]
            self._position = len(self._rows)
            return rows
        return [Row(row) for row in self._cursor.fetchall()] if self._cursor else []

    def __iter__(self):
        while (row := self.fetchone()) is not None:
            yield row


_LONG_TEXT = {
    "payload", "content", "answer", "evidence_json", "risk_result", "parameters",
    "metrics", "request_json", "result_json", "body", "text", "note", "error",
    "last_error", "excerpt", "target", "device", "filename", "title",
}
_KEY_SIZES = {
    "instrument_id": 64, "interval": 16, "bar_time": 40, "adjustment": 32,
    "owner_id": 64, "account_id": 80, "order_id": 80, "fill_id": 80,
    "document_id": 80, "run_id": 80, "market": 32, "symbol": 40,
    "status": 32, "created_at": 40, "published_at": 40,
    "observed_date": 20, "source_kind": 32, "recipient_hash": 128,
    "key": 191, "cache_key": 191, "request_key": 128,
}
_IDENTIFIERS = {"key", "window", "interval", "rank", "rows"}


def _quote_identifiers(sql: str) -> str:
    """Quote the few MySQL reserved identifiers used by existing queries."""
    pattern = re.compile(r"`[^`]*`|'(?:''|[^'])*'|\b(?:key|window|interval|rank|rows)\b", re.I | re.S)
    def quote(match: re.Match[str]) -> str:
        word = match.group(0)
        if word.startswith(("'", "`")):
            return word
        before = sql[:match.start()].rstrip()
        previous = re.search(r"([A-Za-z_]+)$", before)
        if word.lower() == "key" and previous and previous[1].upper() in {"PRIMARY", "FOREIGN", "DUPLICATE", "UNIQUE"}:
            return word
        return f"`{word}`"
    return pattern.sub(quote, sql)


def _table_ddl(sql: str) -> str:
    sql = re.sub(r"\bAUTOINCREMENT\b", "AUTO_INCREMENT", sql, flags=re.I)
    sql = re.sub(r"\bREAL\b", "DOUBLE", sql, flags=re.I)
    sql = re.sub(r"\bBLOB\b", "LONGBLOB", sql, flags=re.I)
    foreign_keys: list[str] = []

    def column(match: re.Match[str]) -> str:
        name = match.group(1)
        length = _KEY_SIZES.get(name, 191)
        if name in _LONG_TEXT:
            return f"{name} LONGTEXT"
        return f"{name} VARCHAR({length})"

    sql = re.sub(r"\b([a-z_][a-z_0-9]*)\s+TEXT\b", column, sql, flags=re.I)
    # TEXT defaults need expression syntax in MySQL; used by evidence fields.
    sql = re.sub(r"(LONGTEXT\s+NOT\s+NULL\s+)DEFAULT\s+('[^']*')", r"\1DEFAULT (\2)", sql, flags=re.I)

    def inline_fk(match: re.Match[str]) -> str:
        name, column_type, required, unique, target, target_col, cascade = match.groups()
        foreign_keys.append(f"FOREIGN KEY ({name}) REFERENCES {target}({target_col})" + (" ON DELETE CASCADE" if cascade else ""))
        return f"{name} {column_type}{required or ''}{unique or ''}"

    sql = re.sub(
        r"\b([a-z_][a-z_0-9]*)\s+(VARCHAR\(\d+\)|LONGTEXT|INTEGER)(\s+NOT NULL)?(\s+UNIQUE)?\s+REFERENCES\s+([a-z_][a-z_0-9]*)\(([a-z_][a-z_0-9]*)\)(\s+ON DELETE CASCADE)?",
        inline_fk, sql, flags=re.I,
    )
    if foreign_keys:
        position = sql.rfind(")")
        sql = sql[:position] + ", " + ", ".join(foreign_keys) + sql[position:]
    return _quote_identifiers(sql) + " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"


def _translate(sql: str) -> str:
    sql = sql.strip().rstrip(";")
    if re.match(r"CREATE\s+TABLE\b", sql, re.I):
        return _table_ddl(sql)
    if re.match(r"ALTER\s+TABLE\b", sql, re.I):
        sql = re.sub(r"\bREAL\b", "DOUBLE", sql, flags=re.I)
        sql = re.sub(r"\bBLOB\b", "LONGBLOB", sql, flags=re.I)
        sql = re.sub(r"\b([a-z_][a-z_0-9]*)\s+TEXT\b", lambda m: f"{m[1]} " +
                     ("LONGTEXT" if m[1] in _LONG_TEXT else f"VARCHAR({_KEY_SIZES.get(m[1], 191)})"), sql, flags=re.I)
    sql = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT IGNORE INTO", sql, flags=re.I)
    sql = re.sub(r"\bINSERT\s+OR\s+REPLACE\s+INTO\b", "REPLACE INTO", sql, flags=re.I)
    sql = re.sub(r"\bON\s+CONFLICT\s*\([^)]*\)\s+DO\s+UPDATE\s+SET\b", "ON DUPLICATE KEY UPDATE", sql, flags=re.I)
    sql = re.sub(r"\bexcluded\.([a-z_][a-z_0-9]*)\b", r"VALUES(\1)", sql, flags=re.I)
    sql = _quote_identifiers(sql)
    # PyMySQL interpolates query parameters with Python %-formatting. Escape
    # literal SQL percent signs (LIKE patterns, date formats) before emitting
    # the qmark placeholders as %s.
    return sql.replace("%", "%%").replace("?", "%s")


class Connection:
    def __init__(self):
        password_file = os.getenv("MYSQL_PASSWORD_FILE")
        password = Path(password_file).read_text().strip() if password_file else os.getenv("MYSQL_PASSWORD", "")
        if not password:
            raise RuntimeError("MYSQL_PASSWORD_FILE or MYSQL_PASSWORD is required")
        self.raw = pymysql.connect(
            host=os.getenv("MYSQL_HOST", "mysql"), port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.getenv("MYSQL_USER", "financial_freedom"), password=password,
            database=os.getenv("MYSQL_DATABASE", "financial_freedom"),
            charset="utf8mb4", cursorclass=DictCursor, autocommit=False,
            connect_timeout=10, read_timeout=30, write_timeout=30,
        )
        self.in_transaction = False
        self._writer_lock = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, _value, _tb):
        try:
            self.raw.rollback() if exc_type else self.raw.commit()
        finally:
            if self._writer_lock:
                with self.raw.cursor() as cursor:
                    cursor.execute("DO RELEASE_LOCK('financial_freedom_writer')")
            self.raw.close()

    def close(self):
        self.raw.close()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> Cursor:
        stripped = sql.strip()
        if not stripped:
            return Cursor(rows=[])
        if re.match(r"PRAGMA\s+(journal_mode|foreign_keys)\b", stripped, re.I):
            return Cursor(rows=[])
        info = re.match(r"PRAGMA\s+table_info\(([a-z_][a-z_0-9]*)\)", stripped, re.I)
        if info:
            cur = self.raw.cursor()
            cur.execute("SELECT COLUMN_NAME AS name FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION", (info[1],))
            return Cursor(cur)
        if stripped.upper() == "BEGIN IMMEDIATE":
            # Preserve the old ledger's serialized-writer boundary across
            # MySQL connections until the broker is converted to row locks.
            if not self._writer_lock:
                cur = self.raw.cursor()
                cur.execute("SELECT GET_LOCK('financial_freedom_writer', 15) AS acquired")
                if cur.fetchone()["acquired"] != 1:
                    raise TimeoutError("Could not acquire the ledger writer lock")
                self._writer_lock = True
            if not self.in_transaction:
                self.raw.begin()
            self.in_transaction = True
            return Cursor(rows=[])
        if re.match(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\b", stripped, re.I):
            return self._create_index(stripped)
        cur = self.raw.cursor()
        cur.execute(_translate(sql), tuple(params))
        if re.match(r"(?:INSERT|UPDATE|DELETE|REPLACE)\b", stripped, re.I):
            self.in_transaction = True
        return Cursor(cur)

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> Cursor:
        cur = self.raw.cursor()
        cur.executemany(_translate(sql), [tuple(row) for row in rows])
        self.in_transaction = True
        return Cursor(cur)

    def executescript(self, script: str):
        # Existing scripts contain DDL only. MySQL commits DDL independently.
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def _create_index(self, sql: str) -> Cursor:
        match = re.match(r"CREATE\s+(UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+(\w+)\s+ON\s+(\w+)\s*\(([^)]+)\)(?:\s+WHERE\s+(.+))?", sql, re.I | re.S)
        if not match:
            raise ValueError(f"Unsupported index DDL: {sql[:100]}")
        unique, name, table, columns, where = match.groups()
        cur = self.raw.cursor()
        cur.execute("SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND INDEX_NAME=%s LIMIT 1", (table, name))
        if cur.fetchone():
            return Cursor(rows=[])
        if where:
            if name != "idx_paper_running_account":
                raise ValueError(f"Unsupported partial index: {name}")
            cur.execute("SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='paper_ai_runs' AND COLUMN_NAME='running_account_id'")
            if not cur.fetchone():
                cur.execute("ALTER TABLE paper_ai_runs ADD COLUMN running_account_id VARCHAR(80) GENERATED ALWAYS AS (CASE WHEN status='running' THEN account_id ELSE NULL END) STORED")
            columns = "running_account_id"
        cur.execute(f"CREATE {'UNIQUE ' if unique else ''}INDEX `{name}` ON `{table}` ({_quote_identifiers(columns)})")
        return Cursor(cur)


def connect(database: str = 'financial_freedom'):
    if database not in {'financial_freedom', 'identity'}:
        raise ValueError('Unknown database')
    # Keep the existing local launch path usable when Docker/MySQL is absent.
    # Containers require the explicit MySQL secret and never fall back to a
    # private SQLite file inside the image.
    if not os.getenv('MYSQL_PASSWORD_FILE') and not os.getenv('MYSQL_PASSWORD'):
        if os.getenv('CONTAINER_RUNTIME') == 'true':
            raise RuntimeError('MYSQL_PASSWORD_FILE or MYSQL_PASSWORD is required')
        return _local_sqlite(database)
    return Connection()


@contextmanager
def _local_sqlite(database: str):
    data_dir = Path(os.getenv('DATA_DIR', Path(__file__).resolve().parent.parent / 'data'))
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f'{database}.sqlite3'
    raw = sqlite3.connect(path, timeout=30)
    raw.row_factory = sqlite3.Row
    raw.execute('PRAGMA foreign_keys=ON')
    raw.execute('PRAGMA busy_timeout=30000')
    try:
        yield raw
        raw.commit()
    except BaseException:
        raw.rollback()
        raise
    finally:
        raw.close()
