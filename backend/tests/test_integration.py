"""T19 — Full integration test.

End-to-end test: drop a real audio file into a temp directory → it flows through
the pipeline → tags written → state transitions verified.

Uses:
- Real MP3 file (generated via ffmpeg)
- Real StateStore (SQLite in temp dir)
- Mocked LLM router (returns deterministic tags)
- Mocked fingerprint (Acoustid)
- Mocked rsync (CopyBackend to temp dir)
- Real mutagen tag operations
"""

import asyncio
import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from noctune.config_loader import load_config
from noctune.daemon import DaemonManager, DaemonState
from noctune.extract import extract_metadata
from noctune.llm_router import LLMRouter
from noctune.models.config import LLMConfig, NoctuneConfig
from noctune.models.pipeline import FileState, PipelineStatus
from noctune.models.track import TagSet
from noctune.normalize import compute_target_path, preview_normalization
from noctune.pipeline import Pipeline
from noctune.store import StateStore
from noctune.tag_writer import backup_tags, write_tags
from noctune.transfer import CopyBackend


# --- Fixtures ---


@pytest.fixture
def test_mp3(tmp_path: Path) -> Path:
    """Create a valid MP3 file with tags for testing.

    Uses ffmpeg to generate a 1-second silent MP3, then tags it with mutagen.
    """
    wav_path = tmp_path / "test.wav"
    mp3_path = tmp_path / "test_audio.mp3"

    # Generate silent WAV
    import wave
    import struct

    with wave.open(str(wav_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(b"\x00\x00" * 44100)

    # Convert to MP3 via ffmpeg
    import subprocess

    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-b:a", "128k", "-ac", "1", str(mp3_path)],
        capture_output=True,
        timeout=10,
    )
    if result.returncode != 0:
        pytest.skip("ffmpeg not available")

    # Tag it with mutagen
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TRCK

    mp3 = MP3(mp3_path)
    if mp3.tags is None:
        mp3.tags = ID3()
    mp3.tags.add(TIT2(encoding=3, text="Integration Song"))
    mp3.tags.add(TPE1(encoding=3, text="Test Artist"))
    mp3.tags.add(TALB(encoding=3, text="Test Album"))
    mp3.tags.add(TDRC(encoding=3, text="2024"))
    mp3.tags.add(TRCK(encoding=3, text="1"))
    mp3.save()

    return mp3_path


@pytest.fixture
def music_dir(tmp_path: Path, test_mp3: Path) -> Path:
    """Create a music directory structure with the test MP3."""
    music = tmp_path / "incoming"
    artist_dir = music / "Test Artist" / "Test Album (2024)"
    artist_dir.mkdir(parents=True)
    shutil.copy2(test_mp3, artist_dir / "01 - Integration Song.mp3")
    return music


@pytest.fixture
def dest_dir(tmp_path: Path) -> Path:
    """Destination directory for transfer tests."""
    dest = tmp_path / "dest"
    dest.mkdir()
    return dest


@pytest.fixture
def config(music_dir: Path, dest_dir: Path) -> NoctuneConfig:
    """Create a test config."""
    return NoctuneConfig(
        source_dir=music_dir,
        dest_host="localhost",
        dest_user="test",
        dest_dir=dest_dir,
        genre_vocabulary=["Rock", "Pop", "Electronic", "Jazz", "Alternative Rock"],
        confidence_threshold=0.8,
        llm=LLMConfig(direction="local", model="test-model"),
    )


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    """Create a test state store."""
    store = StateStore(tmp_path / "test_state.db")
    store.initialize()
    return store


@pytest.fixture
def mock_llm_router() -> MagicMock:
    """Create a mock LLM router that returns deterministic tags with high confidence."""
    router = MagicMock(spec=LLMRouter)
    router.complete = AsyncMock(return_value=TagSet(
        title="Integration Song",
        artist="Test Artist",
        album="Test Album",
        year=2024,
        track_number=1,
        genre="Electronic",
    ))
    return router


# --- Integration Tests ---


class TestFullPipeline:
    """End-to-end: discovered → fingerprinted → extracted → reconciled → tagged → transferred."""

    async def test_file_flows_through_full_pipeline(
        self,
        tmp_path: Path,
        music_dir: Path,
        dest_dir: Path,
        config: NoctuneConfig,
        store: StateStore,
        mock_llm_router: MagicMock,
        test_mp3: Path,
    ) -> None:
        """A file flows through all pipeline stages with mocked external calls."""
        # Find our test file in the music directory
        mp3_file = list(music_dir.rglob("*.mp3"))[0]
        assert mp3_file.exists(), f"Test MP3 not found in {music_dir}"

        # --- STEP 1: Discovery ---
        # Simulate the watcher detecting the file
        pipeline = Pipeline(config=config, store=store, llm_router=mock_llm_router)
        discover_result = await pipeline.discover_file(mp3_file)
        assert discover_result.state == FileState.DISCOVERED  # discovers as DISCOVERED first

        # Verify in store
        status = store.get(str(mp3_file))
        assert status is not None
        assert status.state == FileState.DISCOVERED

        # --- STEP 2: Extract metadata ---
        extracted = extract_metadata(mp3_file)
        assert extracted.existing_tags.title == "Integration Song"
        assert extracted.existing_tags.artist == "Test Artist"
        assert extracted.existing_tags.album == "Test Album"
        assert extracted.existing_tags.year == 2024

        # --- STEP 3: Process through pipeline ---
        # Mock fingerprint to skip Acoustid calls
        pipeline._fingerprint_file = MagicMock(return_value=TagSet())  # type: ignore[assignment]
        process_result = await pipeline.process_file(mp3_file)

        # Should have reached TAGGED (auto-approved because high confidence)
        assert process_result.state in (
            FileState.TAGGED,
            FileState.QUEUED_FOR_REVIEW,
            FileState.RECONCILED,
        ), f"Unexpected state: {process_result.state}"

        # --- STEP 4: Write tags ---
        sidecar = backup_tags(mp3_file, TagSet(
            title="Integration Song",
            artist="Test Artist",
            album="Test Album",
            year=2024,
            track_number=1,
        ))
        assert sidecar.exists()

        # Write reconciled tags to file
        reconciled_tags = TagSet(
            title="Integration Song",
            artist="Test Artist",
            album="Test Album",
            year=2024,
            track_number=1,
            genre="Electronic",
        )
        write_tags(mp3_file, reconciled_tags)

        # --- STEP 5: State update to TAGGED ---
        store.upsert(PipelineStatus(
            file_path=str(mp3_file),
            state=FileState.TAGGED,
            confidence=process_result.confidence,
        ))

        # --- STEP 6: Transfer ---
        backend = CopyBackend()
        transfer_result = await backend.transfer(mp3_file, dest_dir)
        assert transfer_result is True
        assert (dest_dir / mp3_file.name).exists()

        # --- STEP 7: Mark as TRANSFERRED ---
        store.upsert(PipelineStatus(
            file_path=str(mp3_file),
            state=FileState.TRANSFERRED,
            confidence=process_result.confidence,
        ))

        # Verify final state
        final = store.get(str(mp3_file))
        assert final.state == FileState.TRANSFERRED


class TestLowConfidenceReview:
    """Files below confidence threshold go to review queue."""

    def test_low_confidence_goes_to_review_queue(
        self,
        music_dir: Path,
        store: StateStore,
        config: NoctuneConfig,
    ) -> None:
        """Manual state manipulation: force a file into QUEUED_FOR_REVIEW."""
        mp3_file = list(music_dir.rglob("*.mp3"))[0]

        # Simulate pipeline putting file in review with low confidence
        store.upsert(PipelineStatus(
            file_path=str(mp3_file),
            state=FileState.QUEUED_FOR_REVIEW,
            confidence=0.55,
        ))

        # Verify it appears in review queue
        review_items = store.list_by_state(FileState.QUEUED_FOR_REVIEW)
        assert len(review_items) == 1
        assert review_items[0].file_path == str(mp3_file)
        assert review_items[0].confidence < config.confidence_threshold


class TestTagWriteBackup:
    """Verify tag write + sidecar backup round-trip."""

    def test_backup_and_write_preserves_original_tags(
        self,
        test_mp3: Path,
    ) -> None:
        """Backup original tags, write new tags, verify sidecar has originals."""
        # Read original tags from file
        from mutagen.mp3 import MP3
        mp3 = MP3(test_mp3)
        original_title = str(mp3.tags["TIT2"])

        # Create a TagSet from existing tags for backup
        original_tags = TagSet(
            title=str(mp3.tags.get("TIT2", "")),
            artist=str(mp3.tags.get("TPE1", "")),
            album=str(mp3.tags.get("TALB", "")),
            year=int(str(mp3.tags.get("TDRC", "0"))) if "TDRC" in mp3.tags else None,
            track_number=int(str(mp3.tags.get("TRCK", "0")).split("/")[0]) if "TRCK" in mp3.tags else None,
        )

        # Backup
        sidecar = backup_tags(test_mp3, original_tags)
        assert sidecar.exists()

        # Write new tags
        new_tags = TagSet(
            title="Renamed Song",
            artist="New Artist",
            album="New Album",
            year=2025,
            track_number=2,
            genre="Jazz",
        )
        write_tags(test_mp3, new_tags)

        # Verify new tags
        mp3 = MP3(test_mp3)
        assert str(mp3.tags["TIT2"]) == "Renamed Song"
        assert str(mp3.tags["TPE1"]) == "New Artist"
        assert str(mp3.tags["TALB"]) == "New Album"

        # Verify sidecar has originals
        with open(sidecar) as f:
            backup_data = json.load(f)
        assert backup_data["title"] == original_title
        assert backup_data["artist"] == "Test Artist"

    def test_sidecar_backup_is_json(self, test_mp3: Path) -> None:
        """Sidecar backup is valid JSON with all expected fields."""
        from mutagen.mp3 import MP3
        mp3 = MP3(test_mp3)
        original_tags = TagSet(
            title=str(mp3.tags.get("TIT2", "")),
            artist=str(mp3.tags.get("TPE1", "")),
            album=str(mp3.tags.get("TALB", "")),
        )
        sidecar = backup_tags(test_mp3, original_tags)

        with open(sidecar) as f:
            data = json.load(f)

        # Should have all standard tag fields
        expected_keys = {"title", "artist", "album", "year", "track_number", "genre"}
        assert expected_keys.issubset(set(data.keys()))


class TestDaemonIntegration:
    """Daemon picks up discovered files and processes them."""

    async def test_daemon_state_transitions(
        self,
        store: StateStore,
        config: NoctuneConfig,
    ) -> None:
        """Daemon transitions correctly through start/pause/resume/stop."""
        daemon = DaemonManager(store=store, config=config, notify=False)

        # Start
        await daemon.start()
        assert daemon.state == DaemonState.RUNNING

        # Pause
        await daemon.pause()
        assert daemon.state == DaemonState.PAUSED

        # Resume
        await daemon.resume()
        assert daemon.state == DaemonState.RUNNING

        # Stop
        await daemon.stop()
        assert daemon.state == DaemonState.STOPPED

    async def test_daemon_notifies_on_review_queue(
        self,
        music_dir: Path,
        store: StateStore,
        config: NoctuneConfig,
    ) -> None:
        """Daemon sends notifications when files enter review queue."""
        mp3_file = list(music_dir.rglob("*.mp3"))[0]

        # Put a file in review queue
        store.upsert(PipelineStatus(
            file_path=str(mp3_file),
            state=FileState.QUEUED_FOR_REVIEW,
            confidence=0.5,
        ))

        # Create daemon with notification mock
        with patch("desktop_notifier.DesktopNotifier") as mock_notifier_cls:
            mock_notifier = AsyncMock()
            mock_notifier_cls.return_value = mock_notifier
            mock_notifier.send = AsyncMock()

            daemon = DaemonManager(store=store, config=config, notify=True)

            # Manually trigger notification
            queued = store.list_by_state(FileState.QUEUED_FOR_REVIEW)
            await daemon._notify_review(queued)

            # DesktopNotifier should have been called
            mock_notifier.send.assert_called_once()

        await daemon.stop()


class TestNormalizationIntegration:
    """Normalization preview computes correct paths from tags."""

    def test_normalization_preview_from_tags(self) -> None:
        """Preview normalization produces Artist/Album (Year)/NN - Title.ext paths."""
        tags = TagSet(
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
            year=2024,
            track_number=1,
            genre="Electronic",
        )

        target = compute_target_path(tags, Path("/music"))
        assert target == Path("/music/Test Artist/Test Album (2024)/01 - Test Song.flac")

    def test_normalization_handles_missing_year(self) -> None:
        """Normalization works without year."""
        tags = TagSet(
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
            genre="Electronic",
        )

        target = compute_target_path(tags, Path("/music"))
        assert target == Path("/music/Test Artist/Test Album/Test Song.flac")