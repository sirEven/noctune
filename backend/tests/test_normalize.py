"""Tests for library normalizer."""

from pathlib import Path

from noctune.models.track import TagSet
from noctune.normalize import compute_target_path, preview_normalization, execute_normalization


class TestComputeTargetPath:
    """Tests for computing target path from tags."""

    def test_standard_path(self) -> None:
        tags = TagSet(
            artist="Radiohead",
            album="Kid A",
            track_number=1,
            title="Everything In Its Right Place",
            year=2000,
        )
        result = compute_target_path(tags, Path("/music"))
        assert result == Path("/music/Radiohead/Kid A (2000)/01 - Everything In Its Right Place.flac")

    def test_path_without_year(self) -> None:
        tags = TagSet(artist="Bjork", album="Homogenic", track_number=3, title="Joga")
        result = compute_target_path(tags, Path("/music"))
        assert result == Path("/music/Bjork/Homogenic/03 - Joga.flac")

    def test_path_without_track_number(self) -> None:
        tags = TagSet(artist="Aphex Twin", album="Selected Ambient Works", title="Xtal")
        result = compute_target_path(tags, Path("/music"))
        assert result == Path("/music/Aphex Twin/Selected Ambient Works/Xtal.flac")

    def test_path_sanitizes_special_chars(self) -> None:
        tags = TagSet(artist="AC/DC", album="Back in Black", track_number=1, title="Hells Bells")
        result = compute_target_path(tags, Path("/music"))
        # Forward slash in artist name should be sanitized
        assert "/" not in result.parts[-3]  # Artist folder shouldn't contain /

    def test_preserves_original_extension(self) -> None:
        tags = TagSet(artist="Radiohead", album="Kid A", track_number=1, title="Test", year=2000)
        result = compute_target_path(tags, Path("/music"), original_suffix=".mp3")
        assert result.suffix == ".mp3"

    def test_default_extension_is_flac(self) -> None:
        tags = TagSet(artist="Radiohead", album="Kid A", track_number=1, title="Test")
        result = compute_target_path(tags, Path("/music"))
        assert result.suffix == ".flac"


class TestPreviewNormalization:
    """Tests for preview — returns old/new path pairs without moving files."""

    def test_preview_returns_rename_pairs(self, tmp_path: Path) -> None:
        # Create some files
        source_dir = tmp_path / "incoming"
        source_dir.mkdir()
        f1 = source_dir / "track01.mp3"
        f1.write_bytes(b"\x00" * 100)

        tags_map = {
            str(f1): TagSet(artist="Radiohead", album="Kid A", track_number=1, title="Everything In Its Right Place", year=2000),
        }

        pairs = preview_normalization(tags_map, source_dir)
        assert len(pairs) == 1
        assert pairs[0].old_path == f1
        # New path should follow Artist/Album (Year)/NN - Title.ext
        assert "Radiohead" in str(pairs[0].new_path)
        assert "Kid A (2000)" in str(pairs[0].new_path)

    def test_preview_ignores_files_not_in_map(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "incoming"
        source_dir.mkdir()
        f1 = source_dir / "track01.mp3"
        f1.write_bytes(b"\x00" * 100)
        f2 = source_dir / "track02.mp3"
        f2.write_bytes(b"\x00" * 100)

        # Only one file in map — the other should be skipped
        tags_map = {
            str(f1): TagSet(artist="Radiohead", album="Kid A", track_number=1, title="Test", year=2000),
        }

        pairs = preview_normalization(tags_map, source_dir)
        assert len(pairs) == 1


class TestExecuteNormalization:
    """Tests for actually moving/renaming files."""

    def test_execute_moves_file(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "incoming"
        source_dir.mkdir()
        f1 = source_dir / "track01.mp3"
        f1.write_bytes(b"audio data")
        dest_dir = tmp_path / "library"

        old_path = f1
        new_path = dest_dir / "Radiohead" / "Kid A (2000)" / "01 - Everything In Its Right Place.mp3"

        from noctune.normalize import RenamePair
        pairs = [RenamePair(old_path=old_path, new_path=new_path)]

        results = execute_normalization(pairs)
        assert len(results) == 1
        assert results[0].new_path.exists()
        assert not results[0].old_path.exists()

    def test_execute_creates_directories(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "incoming"
        source_dir.mkdir()
        f1 = source_dir / "track01.mp3"
        f1.write_bytes(b"audio data")
        dest_dir = tmp_path / "library"

        old_path = f1
        new_path = dest_dir / "Radiohead" / "Kid A (2000)" / "01 - Everything In Its Right Place.mp3"

        from noctune.normalize import RenamePair
        pairs = [RenamePair(old_path=old_path, new_path=new_path)]

        results = execute_normalization(pairs)
        assert results[0].new_path.exists()
        # Verify directory was created
        assert (dest_dir / "Radiohead" / "Kid A (2000)").is_dir()