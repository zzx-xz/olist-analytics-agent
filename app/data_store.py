from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from app.settings import get_database_path, get_query_timeout_seconds

MAX_RESULT_ROWS = 100
_DISALLOWED_FUNCTIONS = {"load_extension", "readfile", "writefile"}
_LEADING_SQL_COMMENTS = re.compile(r"^(?:\s|--[^\r\n]*(?:\r?\n|$)|/\*.*?\*/)*", re.DOTALL)
RELATIONSHIPS = [
    "orders.customer_id = customers.customer_id",
    "payments.order_id = orders.order_id",
    "reviews.order_id = orders.order_id",
    "order_items.order_id = orders.order_id",
    "order_items.product_id = products.product_id",
    "order_items.seller_id = sellers.seller_id",
    "products.product_category_name = category_translation.product_category_name",
    "customers.customer_zip_code_prefix = geolocation.geolocation_zip_code_prefix",
    "sellers.seller_zip_code_prefix = geolocation.geolocation_zip_code_prefix",
]


class DataStoreError(RuntimeError):
    """Raised when the local SQLite database cannot serve a safe query."""


class OlistDataStore:
    def __init__(self, database_path: Path | None = None) -> None:
        self.database_path = database_path or get_database_path()

    def _connect_read_only(self) -> sqlite3.Connection:
        if not self.database_path.is_file():
            raise DataStoreError(
                f"Database not found: {self.database_path}. "
                "Load the Olist CSV files first."
            )

        uri = self.database_path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")

        allowed_actions = {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
            sqlite3.SQLITE_PRAGMA,
            sqlite3.SQLITE_TRANSACTION,
        }
        if hasattr(sqlite3, "SQLITE_RECURSIVE"):
            allowed_actions.add(sqlite3.SQLITE_RECURSIVE)

        def authorize(
            action: int,
            arg1: str | None,
            arg2: str | None,
            _database: str | None,
            _trigger: str | None,
        ) -> int:
            if action not in allowed_actions:
                return sqlite3.SQLITE_DENY
            pragma_args = {(arg1 or "").lower(), (arg2 or "").lower()}
            if action == sqlite3.SQLITE_PRAGMA and "table_info" not in pragma_args:
                return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in _DISALLOWED_FUNCTIONS:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(authorize)
        return connection

    def schema(self) -> dict[str, Any]:
        try:
            with self._connect_read_only() as connection:
                tables = connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                ).fetchall()
                table_columns = {
                    row["name"]: [
                        column["name"]
                        for column in connection.execute(
                            f'PRAGMA table_info("{row["name"]}")'
                        ).fetchall()
                    ]
                    for row in tables
                }
                return {
                    "tables": table_columns,
                    "relationships": RELATIONSHIPS,
                    "join_notes": [
                        (
                            "orders has one row per order. payments and order_items may "
                            "have multiple rows per order; payments may omit orders with "
                            "no payment record. For a plain order count by customer state, "
                            "join orders to customers and count distinct orders.order_id."
                        ),
                        (
                            "geolocation has multiple rows per zip prefix; aggregate it "
                            "before joining when a query needs coordinates."
                        )
                    ],
                }
        except sqlite3.Error as exc:
            raise DataStoreError(f"Could not inspect database schema: {exc}") from exc

    def query(self, sql: str) -> dict[str, Any]:
        cleaned = _LEADING_SQL_COMMENTS.sub("", sql or "").strip()
        if not cleaned:
            raise DataStoreError("SQL is empty.")
        if not re.match(r"^(SELECT|WITH)\b", cleaned, re.IGNORECASE):
            raise DataStoreError("Only SELECT queries are accepted.")

        timeout_seconds = get_query_timeout_seconds()
        deadline = time.monotonic() + timeout_seconds

        try:
            with self._connect_read_only() as connection:
                connection.set_progress_handler(
                    lambda: int(time.monotonic() > deadline),
                    1000,
                )
                cursor = connection.execute(cleaned)
                rows = cursor.fetchmany(MAX_RESULT_ROWS + 1)
                truncated = len(rows) > MAX_RESULT_ROWS
                rows = rows[:MAX_RESULT_ROWS]
                return {
                    "sql": cleaned,
                    "columns": [column[0] for column in (cursor.description or [])],
                    "rows": [dict(row) for row in rows],
                    "row_count": len(rows),
                    "truncated": truncated,
                    "row_limit": MAX_RESULT_ROWS,
                    "timeout_seconds": timeout_seconds,
                }
        except sqlite3.Error as exc:
            message = str(exc)
            if "interrupted" in message.lower():
                message = f"Query exceeded the {timeout_seconds}-second time limit."
            raise DataStoreError(message) from exc
