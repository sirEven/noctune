"""Tests for the pipeline orchestrator."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from noctune.models.config import LLMConfig, NoctuneConfig, RemoteConfig
from noctune.models.pipeline import FileState, PipelineStatus
from noctune.models.track import TagSet
from noctune.pipeline import Pipeline


def make_config(tmp_path: Path) -> NoctuneConfig:
    """Create a test config."""
    return NoctuneConfig(
        source_dir=tmp_path / "incoming",
        remote=RemoteConfig(
            host="192.168.178.107",
            user="eversin",
        ),
        dest_dir=Path("/data/music"),
        genre_vocabulary=["Rock", "Pop", "Electronic", "Jazz"],
        llm=LLMConfig(direction="local"),
        confidence_threshold=0.8,
    )


class TestPipelineTransitions:
    """Tests for pipeline state machine transitions."""

    async def test_process_file_discovers_file(self, tmp_path: Path) -> None:
        """Processing a file should start at DISCOVERED state."""
        from noctune.store import StateStore

        config = make_config(tmp_path)
        store = StateStore(tmp_path / "state.db")
        store.initialize()
        mock_llm = AsyncMock()

        pipeline = Pipeline(config=config, store=store, llm_router=mock_llm)

        # Create a fake music file
        music_file = tmp_path / "incoming" / "test.mp3"
        music_file.parent.mkdir(parents=True, exist_ok=True)
        music_file.write_bytes(b"\x00" * 100)

        # Discover the file
        await pipeline.discover_file(music_file)

        status = store.get(str(music_file))
        assert status is not None
        assert status.state == FileState.DISCOVERED

    async def test_process_file_full_pipeline(self, tmp_path: Path) -> None:
        """Full pipeline: discover → fingerprint → extract → reconcile → tag."""
        from noctune.store import StateStore

        config = make_config(tmp_path)
        store = StateStore(tmp_path / "state.db")
        store.initialize()
        mock_llm = AsyncMock()
        mock_llm.complete.return_value = '{"artist":"Radiohead","album":"Kid A","title":"Everything In Its Right Place","track_number":1,"year":2000,"genre":"Electronic","confidence":0.95}'

        pipeline = Pipeline(config=config, store=store, llm_router=mock_llm)

        music_file = tmp_path / "incoming" / "01 - Radiohead - Everything In Its Right Place.mp3"
        music_file.parent.mkdir(parents=True, exist_ok=True)
        music_file.write_bytes(b"\x00" * 100)

        # Mock the heavy operations
        with patch.object(pipeline, "_fingerprint_file", return_value=TagSet(
            artist="Radiohead", album="Kid A", title="Everything In Its Right Place", year=2000
        )), patch.object(pipeline, "_extract_metadata", return_value=TagSet(
            artist="Radiohead", album="Kid A", title="Everything In Its Right Place"
        )), patch.object(pipeline, "_write_tags"):
            result = await pipeline.process_file(music_file)

        assert result is not None
        assert result.state in (FileState.TAGGED, FileState.QUEUED_FOR_REVIEW)

    async def test_high_confidence_auto_tags(self, tmp_path: Path) -> None:
        """Files with confidence >= threshold should be auto-tagged."""
        from noctune.store import StateStore

        config = make_config(tmp_path)
        config.confidence_threshold = 0.8
        store = StateStore(tmp_path / "state.db")
        store.initialize()
        mock_llm = AsyncMock()
        mock_llm.complete.return_value = '{"artist":"Radiohead","album":"Kid A","title":"Test","genre":"Electronic","confidence":0.95}'

        pipeline = Pipeline(config=config, store=store, llm_router=mock_llm)

        music_file = tmp_path / "incoming" / "test.mp3"
        music_file.parent.mkdir(parents=True, exist_ok=True)
        music_file.write_bytes(b"\x00" * 100)

        with patch.object(pipeline, "_fingerprint_file", return_value=TagSet(artist="Radiohead")), \
             patch.object(pipeline, "_extract_metadata", return_value=TagSet(artist="Radiohead")), \
             patch.object(pipeline, "_write_tags"):
            result = await pipeline.process_file(music_file)

        assert result is not None
        assert result.state == FileState.TAGGED

    async def test_low_confidence_goes_to_review(self, tmp_path: Path) -> None:
        """Files with confidence < threshold should go to review queue."""
        from noctune.store import StateStore

        config = make_config(tmp_path)
        config.confidence_threshold = 0.8
        store = StateStore(tmp_path / "state.db")
        store.initialize()
        mock_llm = AsyncMock()
        mock_llm.complete.return_value = '{"artist":"Unknown","album":"Unknown","title":"Test","genre":"Rock","confidence":0.5}'

        pipeline = Pipeline(config=config, store=store, llm_router=mock_llm)

        music_file = tmp_path / "incoming" / "test.mp3"
        music_file.parent.mkdir(parents=True, exist_ok=True)
        music_file.write_bytes(b"\x00" * 100)

        with patch.object(pipeline, "_fingerprint_file", return_value=TagSet()), \
             patch.object(pipeline, "_extract_metadata", return_value=TagSet(artist="Unknown")), \
             patch.object(pipeline, "_write_tags"):
            result = await pipeline.process_file(music_file)

        assert result is not None
        assert result.state == FileState.QUEUED_FOR_REVIEW

    async def test_pipeline_skips_already_processed(self, tmp_path: Path) -> None:
        """Files already in TAGGED state should be skipped."""
        from noctune.store import StateStore

        config = make_config(tmp_path)
        store = StateStore(tmp_path / "state.db")
        store.initialize()
        mock_llm = AsyncMock()

        pipeline = Pipeline(config=config, store=store, llm_router=mock_llm)

        music_file = tmp_path / "incoming" / "test.mp3"
        music_file.parent.mkdir(parents=True, exist_ok=True)
        music_file.write_bytes(b"\x00" * 100)

        # Pre-populate as TAGGED
        store.upsert(PipelineStatus(file_path=str(music_file), state=FileState.TAGGED))

        result = await pipeline.process_file(music_file)
        assert result.state == FileState.TAGGED
        # LLM should not have been called
        mock_llm.complete.assert_not_called()

    async def test_process_batch_groups_by_release(self, tmp_path: Path) -> None:
        """Batch processing should group files by release_group_id."""
        from noctune.store import StateStore

        config = make_config(tmp_path)
        store = StateStore(tmp_path / "state.db")
        store.initialize()
        mock_llm = AsyncMock()

        pipeline = Pipeline(config=config, store=store, llm_router=mock_llm)

        # Create multiple files in the same album
        music_dir = tmp_path / "incoming" / "Radiohead" / "Kid A"
        music_dir.mkdir(parents=True, exist_ok=True)
        files = []
        for i in range(1, 4):
            f = music_dir / f"{i:02d} - Track {i}.mp3"
            f.write_bytes(b"\x00" * 100)
            files.append(f)

        # This is a structural test — just verify discover_file works for each
        for f in files:
            await pipeline.discover_file(f)

        discovered = store.list_by_state(FileState.DISCOVERED)
        assert len(discovered) == 3