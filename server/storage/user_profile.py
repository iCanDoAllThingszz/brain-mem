"""
Persistent storage for user profile and goals across sessions.
Uses SQLite with upsert semantics — one row per (tenant_id, user_id).
"""

import json
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, List


class UserProfileStore:
    """
    SQLite-backed store for user profile facts and goal list.

    Profile is a free-form dict (name, occupation, location, preferences, …).
    Goals is a list of dicts: {"name", "status": active|completed|paused, "progress"}.

    Both are written atomically as JSON blobs and updated incrementally by
    ProfileUpdater after each successfully encoded conversation turn.
    """

    _lock = threading.Lock()

    def __init__(self, db_path: str = "./data/user_profiles.db") -> None:
        self.db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """Return {"profile": dict, "goals": list}. Empty if no record yet."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT profile_json, goals_json FROM user_profiles "
                "WHERE tenant_id=? AND user_id=?",
                (tenant_id, user_id),
            ).fetchone()
            if row:
                return {
                    "profile": json.loads(row["profile_json"]),
                    "goals": json.loads(row["goals_json"]),
                }
            return {"profile": {}, "goals": []}
        finally:
            conn.close()

    def save(
        self,
        tenant_id: str,
        user_id: str,
        profile: Dict[str, Any],
        goals: List[Any],
    ) -> None:
        """Upsert profile and goals for a user."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO user_profiles
                        (tenant_id, user_id, profile_json, goals_json, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(tenant_id, user_id) DO UPDATE SET
                        profile_json = excluded.profile_json,
                        goals_json   = excluded.goals_json,
                        updated_at   = excluded.updated_at
                    """,
                    (
                        tenant_id,
                        user_id,
                        json.dumps(profile, ensure_ascii=False),
                        json.dumps(goals, ensure_ascii=False),
                        datetime.utcnow().isoformat(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_profiles (
                        tenant_id    TEXT NOT NULL,
                        user_id      TEXT NOT NULL,
                        profile_json TEXT NOT NULL DEFAULT '{}',
                        goals_json   TEXT NOT NULL DEFAULT '[]',
                        updated_at   TEXT NOT NULL,
                        PRIMARY KEY (tenant_id, user_id)
                    )
                """)
                conn.commit()
            finally:
                conn.close()