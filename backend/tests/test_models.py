"""Tests for core data models."""

from pathlib import Path

from noctune.models.track import TagSet, TrackMeta
from noctune.models.pipeline import FileState, PipelineStatus
from noctune.models.config import LLMConfig, NoctuneConfig


class TestTagSet:
    """Tests for TagSet model."""

    def test_tagset_creation_with_all_fields(self) -> None:
        tags = TagSet(
            artist="Radiohead",
            album_artist="Radiohead",
            album="Kid A",
            title="Everything In Its Right Place",
            track_number=1,
            year=2000,
            genre="Electronic",
            comment="",
        )
        assert tags.artist == "Radiohead"
        assert tags.album == "Kid A"
        assert tags.genre == "Electronic"
        assert tags.year == 2000

    def test_tagset_defaults_to_empty_strings(self) -> None:
        tags = TagSet()
        assert tags.artist == ""
        assert tags.album == ""
        assert tags.title == ""
        assert tags.genre == ""
        assert tags.track_number is None
        assert tags.year is None

    def test_tagset_from_dict(self) -> None:
        tags = TagSet(**{"artist": "Bjork", "album": "Homogenic", "title": "Joga"})
        assert tags.artist == "Bjork"


class TestTrackMeta:
    """Tests for TrackMeta model."""

    def test_trackmeta_creation(self) -> None:
        meta = TrackMeta(
            path=Path("/music/01 - Radiohead - Kid A.flac"),
            file_size_bytes=45000000,
            duration_seconds=248.5,
            format="flac",
            bitrate=942,
        )
        assert meta.format == "flac"
        assert meta.duration_seconds == 248.5
        assert meta.bitrate == 942
        assert meta.existing_tags is None
        assert meta.has_cover_art is False

    def test_trackmeta_with_existing_tags(self) -> None:
        tags = TagSet(artist="Radiohead", album="Kid A")
        meta = TrackMeta(
            path=Path("/music/test.flac"),
            file_size_bytes=100,
            duration_seconds=60.0,
            format="flac",
            existing_tags=tags,
        )
        assert meta.existing_tags is not None
        assert meta.existing_tags.artist == "Radiohead"


class TestFileState:
    """Tests for FileState enum."""

    def test_filestate_values(self) -> None:
        assert FileState.DISCOVERED == "discovered"
        assert FileState.STABLE == "stable"
        assert FileState.FINGERPRINTED == "fingerprinted"
        assert FileState.EXTRACTED == "extracted"
        assert FileState.RECONCILED == "reconciled"
        assert FileState.TAGGED == "tagged"
        assert FileState.QUEUED_FOR_REVIEW == "queued_for_review"
        assert FileState.TRANSFERRED == "transferred"
        assert FileState.FAILED == "failed"

    def test_filestate_from_string(self) -> None:
        state = FileState("fingerprinted")
        assert state == FileState.FINGERPRINTED


class TestPipelineStatus:
    """Tests for PipelineStatus model."""

    def test_pipeline_status_defaults(self) -> None:
        status = PipelineStatus(file_path="/music/test.flac")
        assert status.state == FileState.DISCOVERED
        assert status.confidence == 0.0
        assert status.mb_release_group_id is None
        assert status.error is None

    def test_pipeline_status_with_values(self) -> None:
        status = PipelineStatus(
            file_path="/music/test.flac",
            state=FileState.RECONCILED,
            confidence=0.92,
            mb_release_group_id="mb-abc123",
        )
        assert status.state == FileState.RECONCILED
        assert status.confidence == 0.92
        assert status.mb_release_group_id == "mb-abc123"

    def test_pipeline_status_failed(self) -> None:
        status = PipelineStatus(
            file_path="/music/broken.mp3",
            state=FileState.FAILED,
            error="fingerprint failed: corrupt file",
        )
        assert status.state == FileState.FAILED
        assert status.error == "fingerprint failed: corrupt file"


class TestNoctuneConfig:
    """Tests for configuration models."""

    def test_llm_config_defaults(self) -> None:
        config = LLMConfig()
        assert config.direction == "local"
        assert config.local_base_url == "http://localhost:11434"
        assert config.local_model == "llama3:8b"
        assert config.batch_size == 20

    def test_noctune_config_with_source_dir(self) -> None:
        config = NoctuneConfig(source_dir=Path("~/Music/Incoming").expanduser())
        assert config.source_dir.is_absolute()
        assert config.confidence_threshold == 0.8
        assert ".flac" in config.valid_extensions
        assert config.llm.direction == "local"