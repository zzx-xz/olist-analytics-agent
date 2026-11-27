from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.data_store import DataStoreError, OlistDataStore
from scripts.load_olist_csvs import normalize_value


class OlistDataStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "sample.db"
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("CREATE TABLE orders (order_id TEXT)")
            connection.execute("CREATE TABLE reviews (order_id TEXT)")
            connection.execute("INSERT INTO orders VALUES ('o-1')")
            connection.execute("INSERT INTO reviews VALUES ('o-1')")
        self.store = OlistDataStore(self.database_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_read_only_select_works(self) -> None:
        result = self.store.query("SELECT COUNT(*) AS order_count FROM orders")
        self.assertEqual(result["rows"], [{"order_count": 1}])

    def test_write_and_privileged_queries_are_blocked(self) -> None:
        prohibited_queries = [
            "DELETE FROM reviews",
            "DROP TABLE orders",
            (
                "WITH doomed AS (SELECT order_id FROM orders) "
                "DELETE FROM orders WHERE order_id IN (SELECT order_id FROM doomed)"
            ),
            "SELECT load_extension('unavailable_extension')",
            "PRAGMA database_list",
        ]
        for sql in prohibited_queries:
            with self.subTest(sql=sql):
                with self.assertRaises(DataStoreError):
                    self.store.query(sql)

        self.assertEqual(
            self.store.query("SELECT COUNT(*) AS n FROM orders")["rows"],
            [{"n": 1}],
        )
        self.assertEqual(
            self.store.query("SELECT COUNT(*) AS n FROM reviews")["rows"],
            [{"n": 1}],
        )


class LoaderNormalizationTests(unittest.TestCase):
    def test_slash_date_is_normalized_for_sqlite(self) -> None:
        value = normalize_value("order_purchase_timestamp", "2018/7/24 20:41")
        self.assertEqual(value, "2018-07-24 20:41:00")


if __name__ == "__main__":
    unittest.main()
