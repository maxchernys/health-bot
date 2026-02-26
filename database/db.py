import sqlite3
from contextlib import contextmanager
from config import DATABASE_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create all tables if they don't exist."""
    with db() as conn:
        conn.executescript("""
            -- OAuth tokens storage
            CREATE TABLE IF NOT EXISTS oauth_tokens (
                provider    TEXT PRIMARY KEY,
                access_token  TEXT NOT NULL,
                refresh_token TEXT,
                expires_at    INTEGER,
                updated_at    INTEGER DEFAULT (strftime('%s', 'now'))
            );

            -- Whoop daily snapshots
            CREATE TABLE IF NOT EXISTS whoop_metrics (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT NOT NULL,
                recovery_score  REAL,
                hrv_rmssd       REAL,
                rhr             REAL,
                spo2            REAL,
                skin_temp_c     REAL,
                sleep_score     REAL,
                sleep_duration_min REAL,
                sleep_efficiency REAL,
                workout_strain  REAL,
                raw_json        TEXT,
                created_at      INTEGER DEFAULT (strftime('%s', 'now')),
                UNIQUE(date)
            );

            -- Oura daily snapshots
            CREATE TABLE IF NOT EXISTS oura_metrics (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT NOT NULL,
                readiness_score INTEGER,
                readiness_contributors TEXT,
                sleep_score     INTEGER,
                sleep_contributors  TEXT,
                activity_score  INTEGER,
                activity_contributors TEXT,
                stress_high     REAL,
                recovery_high   REAL,
                day_summary     TEXT,
                temperature_deviation REAL,
                temperature_trend_deviation REAL,
                raw_json        TEXT,
                created_at      INTEGER DEFAULT (strftime('%s', 'now')),
                UNIQUE(date)
            );

            -- Composite daily scores
            CREATE TABLE IF NOT EXISTS daily_scores (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                date                    TEXT NOT NULL UNIQUE,
                composite_recovery      REAL,
                training_readiness      REAL,
                whoop_weight            REAL DEFAULT 0.5,
                oura_weight             REAL DEFAULT 0.5,
                notes                   TEXT,
                created_at              INTEGER DEFAULT (strftime('%s', 'now'))
            );

        """)
    print(f"[DB] Initialized at {DATABASE_PATH}")
