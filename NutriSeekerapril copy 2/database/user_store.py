import hashlib
import json
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "nutriseeker_users.db"


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS profiles (
                user_id INTEGER PRIMARY KEY,
                age INTEGER,
                gender TEXT DEFAULT '',
                height_cm INTEGER DEFAULT 170,
                weight_kg INTEGER DEFAULT 68,
                activity TEXT DEFAULT 'Moderate',
                goal TEXT DEFAULT 'Maintain',
                avatar TEXT DEFAULT '',
                profile_ready INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS meal_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                date TEXT NOT NULL,
                meal_bucket TEXT NOT NULL,
                foods_json TEXT NOT NULL,
                raw_output TEXT DEFAULT '',
                grams INTEGER NOT NULL DEFAULT 0,
                results_json TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_user_by_email(email: str):
    with connect() as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()


def create_user(email: str, password: str, display_name: str):
    email_value = email.strip().lower()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO users (email, password_hash, display_name)
            VALUES (?, ?, ?)
            """,
            (email_value, hash_password(password), display_name.strip() or "Alex"),
        )
        user_id = cursor.lastrowid
        conn.execute(
            """
            INSERT INTO profiles (user_id)
            VALUES (?)
            """,
            (user_id,),
        )
        return get_user_bundle_by_id(user_id)


def verify_user(email: str, password: str):
    user = get_user_by_email(email)
    if not user:
        return None
    if user["password_hash"] != hash_password(password):
        return False
    return get_user_bundle_by_id(user["id"])


def get_user_bundle_by_id(user_id: int):
    with connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        profile = conn.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
        history_rows = conn.execute(
            """
            SELECT * FROM meal_history
            WHERE user_id = ?
            ORDER BY timestamp DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
    return {
        "user": dict(user) if user else None,
        "profile": dict(profile) if profile else None,
        "history": [deserialize_history_row(row) for row in history_rows],
    }


def update_user_identity(user_id: int, display_name: str, age, gender: str, avatar: str, profile_ready: bool) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE users
            SET display_name = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (display_name.strip() or "Alex", user_id),
        )
        conn.execute(
            """
            UPDATE profiles
            SET age = ?, gender = ?, avatar = ?, profile_ready = ?
            WHERE user_id = ?
            """,
            (age, gender.strip(), avatar, 1 if profile_ready else 0, user_id),
        )


def update_profile_guidance(user_id: int, height_cm: int, weight_kg: int, activity: str, goal: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            UPDATE profiles
            SET height_cm = ?, weight_kg = ?, activity = ?, goal = ?
            WHERE user_id = ?
            """,
            (height_cm, weight_kg, activity, goal, user_id),
        )


def replace_meal_history(user_id: int, entries: list[dict]) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM meal_history WHERE user_id = ?", (user_id,))
        conn.executemany(
            """
            INSERT INTO meal_history (
                user_id, timestamp, date, meal_bucket, foods_json, raw_output, grams, results_json, summary_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    user_id,
                    entry["timestamp"],
                    entry["date"],
                    entry["meal_bucket"],
                    json.dumps(entry["foods"]),
                    entry.get("raw_output", ""),
                    int(entry.get("grams", 0)),
                    json.dumps(entry.get("results", [])),
                    json.dumps(entry.get("summary", {})),
                )
                for entry in entries
            ],
        )


def append_history_entry(user_id: int, entry: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO meal_history (
                user_id, timestamp, date, meal_bucket, foods_json, raw_output, grams, results_json, summary_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                entry["timestamp"],
                entry["date"],
                entry["meal_bucket"],
                json.dumps(entry["foods"]),
                entry.get("raw_output", ""),
                int(entry.get("grams", 0)),
                json.dumps(entry.get("results", [])),
                json.dumps(entry.get("summary", {})),
            ),
        )


def deserialize_history_row(row) -> dict:
    data = dict(row)
    return {
        "timestamp": data["timestamp"],
        "date": data["date"],
        "meal_bucket": data["meal_bucket"],
        "foods": json.loads(data["foods_json"]),
        "raw_output": data.get("raw_output", ""),
        "grams": int(data["grams"]),
        "results": json.loads(data["results_json"]),
        "summary": json.loads(data["summary_json"]),
    }
