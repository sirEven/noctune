"""Tests for Layer 2 — metadata extraction."""

from pathlib import Path

from noctune.extract import parse_filename, parse_directory, extract_metadata


class TestParseFilename:
    """Tests for filename pattern parsing."""

    def test_standard_track_artist_title(self) -> None:
        result = parse_filename("01 - Radiohead - Everything In Its Right Place.flac")
        assert result.artist == "Radiohead"
        assert result.track_number == 1
        assert result.title == "Everything In Its Right Place"

    def test_artist_dash_title(self) -> None:
        result = parse_filename("Radiohead - Kid A.flac")
        assert result.artist == "Radiohead"
        assert result.title == "Kid A"

    def test_track_number_dot_title(self) -> None:
        result = parse_filename("01. Everything In Its Right Place.flac")
        assert result.track_number == 1
        assert result.title == "Everything In Its Right Place"

    def test_just_title(self) -> None:
        result = parse_filename("Everything In Its Right Place.flac")
        assert result.title == "Everything In Its Right Place"

    def test_unparseable_returns_empty(self) -> None:
        result = parse_filename("track01.flac")
        assert result.title == ""

    def test_preserves_extension_in_format_detection(self) -> None:
        result = parse_filename("01 - Radiohead - Kid A.mp3")
        assert result.artist == "Radiohead"
        assert result.title == "Kid A"


class TestParseDirectory:
    """Tests for directory structure parsing."""

    def test_artist_album_structure(self) -> None:
        result = parse_directory(Path("/music/Radiohead/Kid A/01 - Track.flac"))
        assert result.artist == "Radiohead"
        assert result.album == "Kid A"

    def test_nested_compilation_structure(self) -> None:
        result = parse_directory(Path("/music/Compilations/Best of 2024/01 - Track.flac"))
        assert result.album == "Best of 2024"

    def test_single_folder(self) -> None:
        result = parse_directory(Path("/music/Incoming/track.flac"))
        assert result.artist == ""
        assert result.album == ""  # "Incoming" is a skip name

    def test_album_with_year(self) -> None:
        result = parse_directory(Path("/music/Radiohead/Kid A (2000)/01 - Track.flac"))
        assert result.artist == "Radiohead"
        assert result.album == "Kid A (2000)"


class TestExtractMetadata:
    """Tests for the combined metadata extraction pipeline."""

    def test_extracts_file_metadata(self) -> None:
        with ExtractMetadataTestHelper() as helper:
            # Create a minimal FLAC-like file for mutagen to read
            path = helper.create_test_file("01 - Radiohead - Kid A.flac")
            result = extract_metadata(path)

            # At minimum, filename parsing should work
            assert result is not None
            assert result.format == "flac"

    def test_merges_all_signals(self) -> None:
        """When filename and directory both provide info, they should merge."""
        # Use a filename that clearly has artist+title format
        result = extract_metadata(Path("/music/Radiohead/Kid A/01 - Everything In Its Right Place.flac"))
        assert result is not None
        # Directory should provide artist + album
        assert result.existing_tags is not None
        assert result.existing_tags.album == "Kid A"
        # Title should be parsed from filename
        assert result.existing_tags.title == "Everything In Its Right Place"

    def test_handles_missing_file_gracefully(self) -> None:
        result = extract_metadata(Path("/nonexistent/path.flac"))
        # Should at least return filename-parsed tags
        assert result is not None


class ExtractMetadataTestHelper:
    """Helper to create temporary audio files for testing."""

    def __init__(self) -> None:
        import tempfile
        self.tmp_dir = Path(tempfile.mkdtemp())

    def __enter__(self) -> "ExtractMetadataTestHelper":
        return self

    def __exit__(self, *args: object) -> None:
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def create_test_file(self, name: str) -> Path:
        """Create a minimal test audio file (empty but with correct extension)."""
        path = self.tmp_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
        return path