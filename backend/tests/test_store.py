"""Tests for SQLite state store."""

import tempfile
from pathlib import Path

from noctune.models.pipeline import FileState, PipelineStatus
from noctune.store import StateStore


class TestStateStore:
    """Tests for StateStore."""

    def test_initialize_creates_table(self, tmp_dir: Path) -> None:
        store = StateStore(tmp_dir / "test.db")
        store.initialize()
        # Should not raise — idempotent
        store.initialize()

    def test_upsert_and_get(self, tmp_dir: Path) -> None:
        store = StateStore(tmp_dir / "test.db")
        store.initialize()
        status = PipelineStatus(file_path="/music/test.flac", state=FileState.DISCOVERED)
        store.upsert(status)

        result = store.get("/music/test.flac")
        assert result is not None
        assert result.file_path == "/music/test.flac"
        assert result.state == FileState.DISCOVERED

    def test_upsert_updates_existing(self, tmp_dir: Path) -> None:
        store = StateStore(tmp_dir / "test.db")
        store.initialize()

        store.upsert(PipelineStatus(file_path="/music/test.flac", state=FileState.DISCOVERED))
        store.upsert(PipelineStatus(
            file_path="/music/test.flac",
            state=FileState.FINGERPRINTED,
            confidence=0.85,
            mb_release_group_id="mb-abc123",
        ))

        result = store.get("/music/test.flac")
        assert result is not None
        assert result.state == FileState.FINGERPRINTED
        assert result.confidence == 0.85
        assert result.mb_release_group_id == "mb-abc123"

    def test_get_nonexistent_returns_none(self, tmp_dir: Path) -> None:
        store = StateStore(tmp_dir / "test.db")
        store.initialize()
        result = store.get("/music/nonexistent.flac")
        assert result is None

    def test_list_by_state(self, tmp_dir: Path) -> None:
        store = StateStore(tmp_dir / "test.db")
        store.initialize()

        store.upsert(PipelineStatus(file_path="/music/a.flac", state=FileState.DISCOVERED))
        store.upsert(PipelineStatus(file_path="/music/b.flac", state=FileState.TAGGED))
        store.upsert(PipelineStatus(file_path="/music/c.flac", state=FileState.DISCOVERED))

        discovered = store.list_by_state(FileState.DISCOVERED)
        assert len(discovered) == 2

        tagged = store.list_by_state(FileState.TAGGED)
        assert len(tagged) == 1

        transferred = store.list_by_state(FileState.TRANSFERRED)
        assert len(transferred) == 0

    def test_list_by_state_returns_all_fields(self, tmp_dir: Path) -> None:
        store = StateStore(tmp_dir / "test.db")
        store.initialize()

        store.upsert(PipelineStatus(
            file_path="/music/test.flac",
            state=FileState.QUEUED_FOR_REVIEW,
            confidence=0.65,
            error="low confidence",
        ))

        results = store.list_by_state(FileState.QUEUED_FOR_REVIEW)
        assert len(results) == 1
        assert results[0].confidence == 0.65
        assert results[0].error == "low confidence"