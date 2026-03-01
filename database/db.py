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
            -- Registered users
            CREATE TABLE IF NOT EXISTS users (
                chat_id     INTEGER PRIMARY KEY,
                created_at  INTEGER DEFAULT (strftime('%s', 'now'))
            );

            -- OAuth tokens storage (per user)
            CREATE TABLE IF NOT EXISTS oauth_tokens (
                chat_id       INTEGER NOT NULL,
                provider      TEXT NOT NULL,
                access_token  TEXT NOT NULL,
                refresh_token TEXT,
                expires_at    INTEGER,
                updated_at    INTEGER DEFAULT (strftime('%s', 'now')),
                PRIMARY KEY (chat_id, provider)
            );

            -- OAuth state tokens (for CSRF protection)
            CREATE TABLE IF NOT EXISTS oauth_states (
                state       TEXT PRIMARY KEY,
                provider    TEXT NOT NULL,
                chat_id     INTEGER NOT NULL,
                created_at  INTEGER DEFAULT (strftime('%s', 'now'))
            );

            -- Whoop daily snapshots (per user)
            CREATE TABLE IF NOT EXISTS whoop_metrics (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id         INTEGER NOT NULL,
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
                day_strain      REAL,
                day_calories_kcal REAL,
                day_avg_hr      REAL,
                day_max_hr      REAL,
                workout_sport   TEXT,
                workout_avg_hr  REAL,
                workout_max_hr  REAL,
                workout_calories_kcal REAL,
                workout_distance_m REAL,
                workout_altitude_m REAL,
                workout_zone_0_min REAL,
                workout_zone_1_min REAL,
                workout_zone_2_min REAL,
                workout_zone_3_min REAL,
                workout_zone_4_min REAL,
                workout_zone_5_min REAL,
                raw_json        TEXT,
                created_at      INTEGER DEFAULT (strftime('%s', 'now')),
                UNIQUE(chat_id, date)
            );

            -- Oura daily snapshots (per user)
            CREATE TABLE IF NOT EXISTS oura_metrics (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id         INTEGER NOT NULL,
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
                resilience_level TEXT,
                resilience_contributors TEXT,
                vo2_max         REAL,
                oura_workout_type TEXT,
                oura_workout_calories REAL,
                oura_workout_distance_m REAL,
                oura_workout_intensity TEXT,
                oura_workout_avg_hr REAL,
                oura_workout_max_hr REAL,
                optimal_bedtime_start TEXT,
                optimal_bedtime_end TEXT,
                optimal_bedtime_status TEXT,
                raw_json        TEXT,
                created_at      INTEGER DEFAULT (strftime('%s', 'now')),
                UNIQUE(chat_id, date)
            );

            -- Composite daily scores (per user)
            CREATE TABLE IF NOT EXISTS daily_scores (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id                 INTEGER NOT NULL,
                date                    TEXT NOT NULL,
                composite_recovery      REAL,
                training_readiness      REAL,
                whoop_weight            REAL DEFAULT 0.5,
                oura_weight             REAL DEFAULT 0.5,
                notes                   TEXT,
                created_at              INTEGER DEFAULT (strftime('%s', 'now')),
                UNIQUE(chat_id, date)
            );

            -- Conversation history (per user)
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id    INTEGER NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at INTEGER DEFAULT (strftime('%s', 'now'))
            );
            CREATE INDEX IF NOT EXISTS idx_messages_chat
                ON messages(chat_id, created_at);

        """)
    _migrate_db()
    print(f"[DB] Initialized at {DATABASE_PATH}")


def _migrate_db() -> None:
    """Add new columns to existing tables (idempotent)."""
    whoop_cols = [
        ("day_strain", "REAL"), ("day_calories_kcal", "REAL"),
        ("day_avg_hr", "REAL"), ("day_max_hr", "REAL"),
        ("workout_sport", "TEXT"), ("workout_avg_hr", "REAL"),
        ("workout_max_hr", "REAL"), ("workout_calories_kcal", "REAL"),
        ("workout_distance_m", "REAL"), ("workout_altitude_m", "REAL"),
        ("workout_zone_0_min", "REAL"), ("workout_zone_1_min", "REAL"),
        ("workout_zone_2_min", "REAL"), ("workout_zone_3_min", "REAL"),
        ("workout_zone_4_min", "REAL"), ("workout_zone_5_min", "REAL"),
    ]
    oura_cols = [
        ("resilience_level", "TEXT"), ("resilience_contributors", "TEXT"),
        ("vo2_max", "REAL"),
        ("oura_workout_type", "TEXT"), ("oura_workout_calories", "REAL"),
        ("oura_workout_distance_m", "REAL"), ("oura_workout_intensity", "TEXT"),
        ("oura_workout_avg_hr", "REAL"), ("oura_workout_max_hr", "REAL"),
        ("optimal_bedtime_start", "TEXT"), ("optimal_bedtime_end", "TEXT"),
        ("optimal_bedtime_status", "TEXT"),
    ]
    with db() as conn:
        for col, typ in whoop_cols:
            try:
                conn.execute(f"ALTER TABLE whoop_metrics ADD COLUMN {col} {typ}")
            except Exception:
                pass
        for col, typ in oura_cols:
            try:
                conn.execute(f"ALTER TABLE oura_metrics ADD COLUMN {col} {typ}")
            except Exception:
                pass


def ensure_user(chat_id: int) -> None:
    """Register user if not already in the database."""
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (chat_id) VALUES (?)", (chat_id,)
        )


def get_all_users() -> list[int]:
    """Return list of all registered chat_ids."""
    with db() as conn:
        rows = conn.execute("SELECT chat_id FROM users").fetchall()
    return [r["chat_id"] for r in rows]


def save_message(chat_id: int, role: str, content: str) -> None:
    """Store a conversation message."""
    with db() as conn:
        conn.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )


def get_recent_messages(chat_id: int, limit: int = 50) -> list[dict]:
    """Return last N messages for a user, oldest first."""
    with db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages "
            "WHERE chat_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
