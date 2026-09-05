import sqlite3
import os

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nova.db")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")

def get_connection(db_path=DEFAULT_DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def _migrate_add_column(cursor, conn, table: str, column: str, col_type: str):
    """Safely add a column to an existing table if it doesn't already exist."""
    cursor.execute(f"PRAGMA table_info({table})")
    existing_cols = [row[1] for row in cursor.fetchall()]
    if column not in existing_cols:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        conn.commit()
        print(f"Migration: added column '{column}' to table '{table}'")

def init_db(db_path=DEFAULT_DB_PATH):
    print(f"Initializing database at: {db_path}")
    conn = get_connection(db_path)
    cursor = conn.cursor()
    
    # Read and execute schema
    with open(SCHEMA_PATH, "r") as f:
        schema_sql = f.read()
    
    cursor.executescript(schema_sql)
    conn.commit()

    # Migrations for orders and products tables
    _migrate_add_column(cursor, conn, "orders", "razorpay_order_id", "TEXT")
    _migrate_add_column(cursor, conn, "orders", "razorpay_payment_id", "TEXT")
    _migrate_add_column(cursor, conn, "products", "merchant_name", "TEXT")
    _migrate_add_column(cursor, conn, "products", "source_name", "TEXT")
    _migrate_add_column(cursor, conn, "products", "product_url", "TEXT")
    _migrate_add_column(cursor, conn, "products", "retrieved_at", "TEXT")
    _migrate_add_column(cursor, conn, "products", "is_verified", "INTEGER DEFAULT 1")
    _migrate_add_column(cursor, conn, "products", "is_demo", "INTEGER DEFAULT 0")
    _migrate_add_column(cursor, conn, "products", "is_individual_product", "INTEGER DEFAULT 1")
    _migrate_add_column(cursor, conn, "products", "result_type", "TEXT DEFAULT 'product'")
    _migrate_add_column(cursor, conn, "session_states", "current_page_product_ids", "TEXT")
    _migrate_add_column(cursor, conn, "session_states", "current_page_url", "TEXT")
    _migrate_add_column(cursor, conn, "session_states", "current_page_source", "TEXT")
    _migrate_add_column(cursor, conn, "session_states", "pending_order_id", "TEXT")
    _migrate_add_column(cursor, conn, "session_states", "catalogue_debug", "TEXT")
    _migrate_add_column(cursor, conn, "session_states", "pending_navigation", "TEXT")
    _migrate_add_column(cursor, conn, "session_states", "last_shop_query", "TEXT")

    # Clean startup with zero static products (fully dynamic discovery)
    conn.close()
    print("Database initialization complete (Dynamic zero-catalogue mode).")

if __name__ == "__main__":
    init_db()
