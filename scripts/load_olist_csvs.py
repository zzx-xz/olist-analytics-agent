from __future__ import annotations

import argparse
import csv
import os
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TABLE_FILES = {
    "customers": "olist_customers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}
INDEXES = {
    "customers": ["customer_id", "customer_unique_id"],
    "orders": ["order_id", "customer_id", "order_status"],
    "order_items": ["order_id", "product_id", "seller_id"],
    "payments": ["order_id"],
    "reviews": ["order_id"],
    "products": ["product_id"],
    "sellers": ["seller_id"],
}
BATCH_SIZE = 5000
DATETIME_FORMATS = (
    "%Y/%m/%d %H:%M:%S.%f",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def normalize_column(value: str) -> str:
    normalized = re.sub(r"\W+", "_", value.strip(), flags=re.UNICODE).strip("_").lower()
    if not normalized:
        raise ValueError(f"Column name cannot be normalized: {value!r}")
    if normalized[0].isdigit():
        normalized = f"col_{normalized}"
    return normalized


def normalize_value(column: str, value: str) -> str | None:
    if value == "":
        return None
    if column.endswith(("_timestamp", "_date", "_at")):
        for date_format in DATETIME_FORMATS:
            try:
                parsed = datetime.strptime(value.strip(), date_format)
                return parsed.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
    return value


def load_table(connection: sqlite3.Connection, table_name: str, csv_path: Path) -> int:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        try:
            original_columns = next(reader)
        except StopIteration as exc:
            raise ValueError(f"CSV is empty: {csv_path}") from exc

        columns = [normalize_column(column) for column in original_columns]
        if len(set(columns)) != len(columns):
            raise ValueError(f"Column names collide after normalization in {csv_path}")

        column_sql = ", ".join(f"{quote_identifier(column)} TEXT" for column in columns)
        connection.execute(
            f"CREATE TABLE {quote_identifier(table_name)} ({column_sql})"
        )
        placeholders = ", ".join("?" for _ in columns)
        insert_sql = (
            f"INSERT INTO {quote_identifier(table_name)} "
            f"VALUES ({placeholders})"
        )

        batch: list[list[str | None]] = []
        row_count = 0
        for row in reader:
            if len(row) != len(columns):
                raise ValueError(
                    f"Unexpected column count in {csv_path} at CSV row {row_count + 2}"
                )
            batch.append(
                [
                    normalize_value(column, value)
                    for column, value in zip(columns, row)
                ]
            )
            if len(batch) >= BATCH_SIZE:
                connection.executemany(insert_sql, batch)
                row_count += len(batch)
                batch.clear()
        if batch:
            connection.executemany(insert_sql, batch)
            row_count += len(batch)
        return row_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the nine Olist CSV files into SQLite.")
    parser.add_argument(
        "--source",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw",
        help="Directory containing the original Olist CSV files.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=PROJECT_ROOT / "data" / "olist.db",
        help="Destination SQLite database path.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Atomically replace an existing generated database after a successful load.",
    )
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    database = args.db.expanduser().resolve()

    missing = [filename for filename in TABLE_FILES.values() if not (source / filename).is_file()]
    if missing:
        missing_list = "\n".join(f"  - {filename}" for filename in missing)
        raise SystemExit(f"Missing Olist CSV files in {source}:\n{missing_list}")

    if database.exists() and not args.replace:
        raise SystemExit(
            f"Database already exists: {database}. Use --replace to rebuild it from the source CSVs."
        )

    database.parent.mkdir(parents=True, exist_ok=True)
    build_database = (
        database.with_name(
            f"{database.stem}.building-{uuid.uuid4().hex}{database.suffix}"
        )
        if args.replace
        else database
    )

    with sqlite3.connect(build_database) as connection:
        existing = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conflicts = sorted(existing.intersection(TABLE_FILES))
        if conflicts:
            raise SystemExit(
                "Database already contains Olist tables "
                f"({', '.join(conflicts)}). Choose a new database path to avoid duplicate loads."
            )

        for table_name, filename in TABLE_FILES.items():
            count = load_table(connection, table_name, source / filename)
            connection.commit()
            print(f"Loaded {table_name}: {count:,} rows")

        for table_name, columns in INDEXES.items():
            for column in columns:
                index_name = f"idx_{table_name}_{column}"
                connection.execute(
                    f"CREATE INDEX {quote_identifier(index_name)} "
                    f"ON {quote_identifier(table_name)} ({quote_identifier(column)})"
                )
        connection.commit()
        connection.close()

    if args.replace:
        os.replace(build_database, database)
    print(f"Database ready: {database}")


if __name__ == "__main__":
    main()
