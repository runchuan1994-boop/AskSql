import os
import sqlite3

from app.core.config import settings


def get_db_path() -> str:
    """Ensure the data directory exists and return the path to the SQLite database file."""
    db_url = settings.database_url
    if db_url.startswith("sqlite:///"):
        db_path = db_url[len("sqlite:///"):]
    else:
        db_path = db_url

    data_dir = os.path.dirname(db_path)
    if data_dir and not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)

    return db_path


def get_connection() -> sqlite3.Connection:
    """Get a SQLite connection with row factory set to sqlite3.Row."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the database schema (create tables if they don't exist)."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS datasources (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                host TEXT,
                port INTEGER,
                database TEXT,
                username TEXT,
                password_encrypted TEXT,
                schema_file TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                sql_text TEXT,
                result_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS generation_logs (
                id TEXT PRIMARY KEY,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                project_id TEXT,
                datasource_id TEXT,
                session_id TEXT,
                user_query TEXT,
                generated_sql TEXT,
                intent_summary TEXT,
                execution_success INTEGER,
                execution_time_ms INTEGER,
                row_count INTEGER,
                error_message TEXT,
                iteration INTEGER,
                reflection_notes TEXT,
                user_feedback TEXT,
                model TEXT,
                final_selected INTEGER
            )
        """)

        conn.commit()
    finally:
        conn.close()
