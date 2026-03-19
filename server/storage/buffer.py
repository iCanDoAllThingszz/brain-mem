"""
Encoder buffer for the brain-memory service.
Provides a SQLite-backed short-term memory buffer for raw memory units
before they are consolidated into the Neo4j knowledge graph.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS memory_buffer (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL DEFAULT 'memory',
    tenant_id   TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    data        TEXT NOT NULL,   -- JSON blob of the full memory_unit
    importance  REAL NOT NULL DEFAULT 0.0,
    timestamp   TEXT NOT NULL,
    archived    INTEGER NOT NULL DEFAULT 0,  -- 0=False, 1=True
    date        TEXT NOT NULL                -- YYYY-MM-DD extracted from timestamp
);

CREATE INDEX IF NOT EXISTS idx_session    ON memory_buffer (session_id);
CREATE INDEX IF NOT EXISTS idx_tenant_user ON memory_buffer (tenant_id, user_id);
CREATE INDEX IF NOT EXISTS idx_date       ON memory_buffer (tenant_id, user_id, date);
CREATE INDEX IF NOT EXISTS idx_archived   ON memory_buffer (tenant_id, user_id, archived);
"""


class EncoderBuffer:
    """
    SQLite-backed short-term memory buffer.

    Stores raw memory units produced by the encoder before they are
    consolidated (archived) into the long-term Neo4j graph.
    """

    def __init__(self, db_path: str) -> None:
        """
        Initialize the buffer and ensure the database schema exists.

        Args:
            db_path: Path to the SQLite database file.
                     Parent directories are created automatically.
        """
        import os
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._db_path = db_path
        self._init_db()

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager that yields a SQLite connection with row_factory set."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self._conn() as conn:
            conn.executescript(_CREATE_TABLE_SQL)
            # Add embedding column if not exists (v3.1 migration)
            try:
                conn.execute("SELECT embedding FROM memory_buffer LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE memory_buffer ADD COLUMN embedding BLOB")
                logger.info("Added embedding column to memory_buffer")
        logger.debug("EncoderBuffer initialized at %s", self._db_path)

    @staticmethod
    def _row_to_unit(row: sqlite3.Row) -> Dict[str, Any]:
        """Deserialize a database row back into a memory_unit dict."""
        unit: Dict[str, Any] = json.loads(row["data"])
        unit["archived"] = bool(row["archived"])
        return unit

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def write(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        memory_unit: Dict[str, Any],
    ) -> str:
        """
        Write a memory unit to the buffer.

        The memory_unit dict is stored as-is (JSON serialized).
        If 'id' is absent, a new UUID is generated.
        If 'timestamp' is absent, the current UTC time is used.

        Args:
            tenant_id: Tenant identifier
            user_id: User identifier
            session_id: Session identifier
            memory_unit: Memory unit dict (see module docstring for schema)

        Returns:
            The ID of the written memory unit
        """
        unit = dict(memory_unit)
        unit.setdefault("id", str(uuid.uuid4()))
        unit.setdefault("timestamp", datetime.utcnow().isoformat())
        unit.setdefault("archived", False)
        unit["tenant_id"] = tenant_id
        unit["user_id"] = user_id
        unit["session_id"] = session_id

        # Extract date for indexing
        ts = unit["timestamp"]
        date_str = ts[:10] if len(ts) >= 10 else datetime.utcnow().strftime("%Y-%m-%d")

        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_buffer
                    (id, type, tenant_id, user_id, session_id, data, importance, timestamp, archived, date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    unit["id"],
                    unit.get("type", "memory"),
                    tenant_id,
                    user_id,
                    session_id,
                    json.dumps(unit, ensure_ascii=False),
                    float(unit.get("importance", 0.0)),
                    unit["timestamp"],
                    1 if unit["archived"] else 0,
                    date_str,
                ),
            )
        logger.debug("Wrote memory unit %s to buffer", unit["id"])
        return unit["id"]

    def read_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Read all memory units for a given session, ordered by timestamp.

        Args:
            session_id: Session identifier

        Returns:
            List of memory unit dicts
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_buffer WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,),
            ).fetchall()
        return [self._row_to_unit(r) for r in rows]

    def read_by_date(self, tenant_id: str, user_id: str, date: str) -> List[Dict[str, Any]]:
        """
        Read all memory units for a specific date (YYYY-MM-DD).

        Args:
            tenant_id: Tenant scope
            user_id: User scope
            date: Date string in YYYY-MM-DD format

        Returns:
            List of memory unit dicts ordered by timestamp
        """
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_buffer
                WHERE tenant_id = ? AND user_id = ? AND date = ?
                ORDER BY timestamp ASC
                """,
                (tenant_id, user_id, date),
            ).fetchall()
        return [self._row_to_unit(r) for r in rows]

    def read_recent(
        self, tenant_id: str, user_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Read the most recent N memory units for a tenant/user.
        Excludes session_summary units — use get_latest_session_summary() for those.

        Args:
            tenant_id: Tenant scope
            user_id: User scope
            limit: Maximum number of units to return (default 20)

        Returns:
            List of memory unit dicts, most recent first
        """
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_buffer
                WHERE tenant_id = ? AND user_id = ? AND type != 'session_summary'
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (tenant_id, user_id, limit),
            ).fetchall()
        return [self._row_to_unit(r) for r in rows]

    def get_latest_session_summary(
        self, tenant_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve the most recent session_summary unit for a tenant/user.

        Args:
            tenant_id: Tenant scope
            user_id: User scope

        Returns:
            The latest session_summary dict, or None if none exists
        """
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM memory_buffer
                WHERE tenant_id = ? AND user_id = ? AND type = 'session_summary'
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (tenant_id, user_id),
            ).fetchone()
        return self._row_to_unit(row) if row else None

    def archive(self, tenant_id: str, user_id: str, date: str) -> None:
        """
        Mark all memory units for a given date as archived (consolidated).

        Args:
            tenant_id: Tenant scope
            user_id: User scope
            date: Date string in YYYY-MM-DD format
        """
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE memory_buffer
                SET archived = 1
                WHERE tenant_id = ? AND user_id = ? AND date = ?
                """,
                (tenant_id, user_id, date),
            )
        logger.info("Archived memory units for tenant=%s user=%s date=%s", tenant_id, user_id, date)

    def archive_by_id(self, unit_id: str) -> None:
        """Archive a single memory unit by ID."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE memory_buffer SET archived = 1 WHERE id = ?",
                (unit_id,),
            )

    def read_unarchived(self, tenant_id: str, user_id: str) -> List[Dict[str, Any]]:
        """
        Read all unarchived memory units for a tenant/user, oldest first.
        Excludes session_summary units — those are metadata, not consolidation targets.

        Args:
            tenant_id: Tenant scope
            user_id: User scope

        Returns:
            List of unarchived memory unit dicts
        """
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memory_buffer
                WHERE tenant_id = ? AND user_id = ? AND archived = 0
                  AND type != 'session_summary'
                ORDER BY timestamp ASC
                """,
                (tenant_id, user_id),
            ).fetchall()
        return [self._row_to_unit(r) for r in rows]

    # -------------------------------------------------------------------------
    # Vector embedding support
    # -------------------------------------------------------------------------

    def update_embedding(self, unit_id: str, embedding_bytes: bytes) -> None:
        """Store embedding for a buffer unit."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE memory_buffer SET embedding = ? WHERE id = ?",
                (embedding_bytes, unit_id)
            )

    def get_embeddings(self, tenant_id: str, user_id: str) -> list:
        """Get all non-archived units that have embeddings. Returns [(id, embedding_bytes)]."""
        with self._conn() as conn:
            cursor = conn.execute(
                "SELECT id, embedding FROM memory_buffer WHERE tenant_id=? AND user_id=? AND archived=0 AND embedding IS NOT NULL",
                (tenant_id, user_id)
            )
            return [(row["id"], row["embedding"]) for row in cursor.fetchall()]
