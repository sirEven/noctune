"""SQLite state store for pipeline resumability."""

import sqlite3
from pathlib import Path

from noctune.models.pipeline import FileState, PipelineStatus


class StateStore:
    """Persistent SQLite store for file pipeline state.

    Allows the bulk processing job to resume after a crash — every file's
    state is recorded so we can pick up where we left off.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> None:
        """Create the pipeline_state table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_state (
                    file_path TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    confidence REAL DEFAULT 0.0,
                    mb_release_group_id TEXT,
                    error TEXT,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)

    def upsert(self, status: PipelineStatus) -> None:
        """Insert or update a file's pipeline status."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO pipeline_state (file_path, state, confidence, mb_release_group_id, error)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    state = excluded.state,
                    confidence = excluded.confidence,
                    mb_release_group_id = excluded.mb_release_group_id,
                    error = excluded.error,
                    updated_at = datetime('now')
                """,
                (
                    status.file_path,
                    status.state,
                    status.confidence,
                    status.mb_release_group_id,
                    status.error,
                ),
            )

    def get(self, file_path: str) -> PipelineStatus | None:
        """Get the pipeline status for a file, or None if not found."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT file_path, state, confidence, mb_release_group_id, error
                FROM pipeline_state WHERE file_path = ?
                """,
                (file_path,),
            ).fetchone()
            if row is None:
                return None
            return PipelineStatus(
                file_path=row[0],
                state=FileState(row[1]),
                confidence=row[2],
                mb_release_group_id=row[3],
                error=row[4],
            )

    def list_by_state(self, state: FileState) -> list[PipelineStatus]:
        """List all files in a given pipeline state."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT file_path, state, confidence, mb_release_group_id, error
                FROM pipeline_state WHERE state = ?
                """,
                (state.value,),
            ).fetchall()
            return [
                PipelineStatus(
                    file_path=r[0],
                    state=FileState(r[1]),
                    confidence=r[2],
                    mb_release_group_id=r[3],
                    error=r[4],
                )
                for r in rows
            ]