"""SQLite schema and thin query helpers."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    image_url    TEXT,
    target_price REAL,
    created_at   TEXT NOT NULL,
    last_price   REAL,
    last_status  TEXT,
    last_checked TEXT
);

CREATE TABLE IF NOT EXISTS price_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    price      REAL NOT NULL,
    in_stock   INTEGER NOT NULL DEFAULT 1,
    checked_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_history_product ON price_history(product_id, checked_at);
"""


def _db_path() -> str:
    path = os.environ.get("DATABASE_PATH", "data/tracker.db")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    return path


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_db_path(), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def add_product(url: str, name: str, image_url: Optional[str], target_price: Optional[float]) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO products (url, name, image_url, target_price, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (url, name, image_url, target_price, now()),
        )
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute("SELECT id FROM products WHERE url = ?", (url,)).fetchone()
        return row["id"]


def list_products() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM products ORDER BY created_at DESC"
        ).fetchall()


def get_product(product_id: int) -> Optional[sqlite3.Row]:
    with connect() as conn:
        return conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()


def delete_product(product_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        return cur.rowcount > 0


def record_price(product_id: int, price: float, in_stock: bool) -> None:
    ts = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO price_history (product_id, price, in_stock, checked_at) VALUES (?, ?, ?, ?)",
            (product_id, price, 1 if in_stock else 0, ts),
        )
        conn.execute(
            "UPDATE products SET last_price = ?, last_status = ?, last_checked = ? WHERE id = ?",
            (price, "in_stock" if in_stock else "out_of_stock", ts, product_id),
        )


def price_history(product_id: int, limit: int = 500) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT price, in_stock, checked_at FROM price_history "
            "WHERE product_id = ? ORDER BY checked_at ASC LIMIT ?",
            (product_id, limit),
        ).fetchall()


def lowest_price(product_id: int) -> Optional[float]:
    with connect() as conn:
        row = conn.execute(
            "SELECT MIN(price) AS min_price FROM price_history WHERE product_id = ?",
            (product_id,),
        ).fetchone()
        return row["min_price"] if row and row["min_price"] is not None else None
