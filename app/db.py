"""SQLite persistence. The schema is identical to the Checkpoint 1 database,
so an existing lending.db keeps working."""
import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "lending.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS equipment (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT
);
CREATE TABLE IF NOT EXISTS loan (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_id INTEGER NOT NULL,
    from_date    TEXT NOT NULL,
    to_date      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active',
    FOREIGN KEY (equipment_id) REFERENCES equipment(id)
);
"""


def db_path():
    return os.environ.get("LENDING_DB", str(DEFAULT_DB))


def connect(path=None):
    # isolation_level=None -> we issue BEGIN/COMMIT ourselves (see services.transaction)
    conn = sqlite3.connect(path or db_path(), timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(path=None):
    Path(path or db_path()).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()
