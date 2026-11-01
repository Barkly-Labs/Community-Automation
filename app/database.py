import sqlite3
from pathlib import Path
from .config import DATABASE_URL

def _db_path() -> str:
    prefix = "sqlite:///./"
    if DATABASE_URL.startswith(prefix):
        return DATABASE_URL[len(prefix):]
    if DATABASE_URL.startswith("sqlite:///"):
        return DATABASE_URL[len("sqlite:///"):]
    return "barkly.db"

DB_PATH = _db_path()

def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            public_context TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            platform TEXT NOT NULL DEFAULT 'Discord',
            post_type TEXT NOT NULL DEFAULT 'development_update',
            content TEXT NOT NULL,
            model TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )
        """)
