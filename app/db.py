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
    category     TEXT NOT NULL DEFAULT 'other',
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

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint      TEXT NOT NULL UNIQUE,
    p256dh        TEXT NOT NULL,
    auth          TEXT NOT NULL,
    user_agent    TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drop_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id     INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    previous_price REAL NOT NULL,
    new_price      REAL NOT NULL,
    percent        REAL NOT NULL,
    is_new_low     INTEGER NOT NULL DEFAULT 0,
    in_stock       INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_drop_events_created ON drop_events(created_at);
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


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        # Idempotent migrations for older installs.
        _ensure_column(conn, "products", "category", "TEXT NOT NULL DEFAULT 'other'")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def add_product(
    url: str,
    name: str,
    image_url: Optional[str],
    target_price: Optional[float],
    category: str = "other",
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO products (url, name, image_url, target_price, category, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (url, name, image_url, target_price, category, now()),
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


# ---------------------------------------------------------------------------
# Highlights / featured queries
# ---------------------------------------------------------------------------

def at_historic_low(limit: int = 12) -> list[sqlite3.Row]:
    """Products whose current price equals their historic minimum.

    Requires at least 2 recorded samples so the "minimum" is meaningful.
    """
    with connect() as conn:
        return conn.execute(
            """
            SELECT p.*,
                   (SELECT MIN(price) FROM price_history h WHERE h.product_id = p.id) AS min_price,
                   (SELECT COUNT(*)   FROM price_history h WHERE h.product_id = p.id) AS sample_count
            FROM products p
            WHERE p.last_price IS NOT NULL
              AND (SELECT COUNT(*) FROM price_history h WHERE h.product_id = p.id) >= 2
              AND p.last_price <= (SELECT MIN(price) FROM price_history h WHERE h.product_id = p.id) + 0.01
            ORDER BY p.last_checked DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def biggest_drops(days: int = 30, limit: int = 12) -> list[sqlite3.Row]:
    """Products with the biggest percentage drop in the given window."""
    with connect() as conn:
        return conn.execute(
            """
            SELECT p.*,
                   (SELECT MAX(price) FROM price_history h
                    WHERE h.product_id = p.id AND h.checked_at >= datetime('now', ?)) AS window_max,
                   p.last_price AS current_price
            FROM products p
            WHERE p.last_price IS NOT NULL
              AND window_max IS NOT NULL
              AND window_max > 0
              AND p.last_price < window_max
            ORDER BY ((window_max - p.last_price) / window_max) DESC
            LIMIT ?
            """,
            (f"-{int(days)} days", limit),
        ).fetchall()


def near_target(limit: int = 12) -> list[sqlite3.Row]:
    """Products whose current price is at or below the user's target."""
    with connect() as conn:
        return conn.execute(
            """
            SELECT * FROM products
            WHERE target_price IS NOT NULL
              AND last_price IS NOT NULL
              AND last_price <= target_price
            ORDER BY (target_price - last_price) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def category_counts() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT category, COUNT(*) AS n FROM products GROUP BY category"
        ).fetchall()


# ---------------------------------------------------------------------------
# Drop events (for web notifications)
# ---------------------------------------------------------------------------

def record_drop_event(
    product_id: int,
    previous_price: float,
    new_price: float,
    percent: float,
    is_new_low: bool,
    in_stock: bool,
) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO drop_events (product_id, previous_price, new_price, percent, is_new_low, in_stock, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (product_id, previous_price, new_price, percent,
             1 if is_new_low else 0, 1 if in_stock else 0, now()),
        )
        return cur.lastrowid


def recent_drops(limit: int = 20, since: Optional[str] = None) -> list[sqlite3.Row]:
    with connect() as conn:
        if since:
            return conn.execute(
                """
                SELECT d.*, p.name, p.image_url, p.url, p.category
                FROM drop_events d
                JOIN products p ON p.id = d.product_id
                WHERE d.created_at > ?
                ORDER BY d.created_at DESC
                LIMIT ?
                """,
                (since, limit),
            ).fetchall()
        return conn.execute(
            """
            SELECT d.*, p.name, p.image_url, p.url, p.category
            FROM drop_events d
            JOIN products p ON p.id = d.product_id
            ORDER BY d.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


# ---------------------------------------------------------------------------
# Push subscriptions
# ---------------------------------------------------------------------------

def save_push_subscription(endpoint: str, p256dh: str, auth: str, user_agent: Optional[str]) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT OR REPLACE INTO push_subscriptions (endpoint, p256dh, auth, user_agent, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (endpoint, p256dh, auth, user_agent, now()),
        )
        return cur.lastrowid


def delete_push_subscription(endpoint: str) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
        return cur.rowcount > 0


def list_push_subscriptions() -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute("SELECT * FROM push_subscriptions").fetchall()
