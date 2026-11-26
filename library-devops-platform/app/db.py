"""PostgreSQL access. Run `python -m app.db` to create the schema."""
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

SCHEMA = Path(__file__).with_name("schema.sql")
SCHEMA_LOCK_ID = 727274  # arbitrary, shared by every replica


class Database:
    def __init__(self, url: str):
        self.pool = ConnectionPool(
            url, min_size=1, max_size=8, timeout=3, open=True,
            kwargs={"row_factory": dict_row, "connect_timeout": 3},
            check=ConnectionPool.check_connection,
        )

    @contextmanager
    def transaction(self):
        """Commit on success, roll back on any exception."""
        with self.pool.connection() as conn, conn.transaction():
            yield conn

    def close(self):
        self.pool.close()


def init_schema(url: str, attempts: int = 30, delay: float = 2.0) -> None:
    """Wait for the database, then apply the schema under an advisory lock."""
    for attempt in range(1, attempts + 1):
        try:
            with psycopg.connect(url, connect_timeout=3) as conn:
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_LOCK_ID,))
                conn.execute(SCHEMA.read_text())
            return
        except psycopg.OperationalError:
            if attempt == attempts:
                raise
            print(f"database not ready (attempt {attempt}/{attempts})", file=sys.stderr)
            time.sleep(delay)


if __name__ == "__main__":
    init_schema(os.environ["DATABASE_URL"])
    print("schema is up to date")
