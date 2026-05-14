"""Tests for Layer 1 — fingerprint and MusicBrainz lookup."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from noctune.fingerprint import FingerprintResult, fingerprint_file, lookup_on_musicbrainz, fingerprint_and_lookup


class TestFingerprintFile:
    """Tests for fingerprint_file."""

    def test_fingerprint_file_returns_result_on_success(self) -> None:
        with patch("noctune.fingerprint.acoustid") as mock_acoustid:
            mock_acoustid.fingerprint.return_value = (
                30.5,
                b"\x00\x01\x02\x03fake_fingerprint",
            )

            result = fingerprint_file(Path("/music/test.flac"), api_key="test-key")
            assert isinstance(result, FingerprintResult)
            assert result.duration == 30.5
            assert result.fingerprint == b"\x00\x01\x02\x03fake_fingerprint"

    def test_fingerprint_file_returns_none_on_failure(self) -> None:
        with patch("noctune.fingerprint.acoustid") as mock_acoustid:
            mock_acoustid.fingerprint.side_effect = Exception("file not found")

            result = fingerprint_file(Path("/music/missing.flac"), api_key="test-key")
            assert result is None


class TestLookupOnMusicBrainz:
    """Tests for lookup_on_musicbrainz."""

    def test_lookup_returns_tagset_on_match(self) -> None:
        with patch("noctune.fingerprint.acoustid") as mock_acoustid:
            mock_acoustid.lookup.return_value = {
                "results": [
                    {
                        "score": 0.95,
                        "recordings": [
                            {
                                "title": "Everything In Its Right Place",
                                "artists": [{"name": "Radiohead"}],
                                "releases": [
                                    {
                                        "title": "Kid A",
                                        "date": "2000",
                                        "release-group": {"id": "mb-abc123"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }

            result = lookup_on_musicbrainz(
                fingerprint=b"\x00\x01\x02\x03",
                duration=30.5,
                api_key="test-key",
            )
            assert result is not None
            assert result["artist"] == "Radiohead"
            assert result["album"] == "Kid A"
            assert result["title"] == "Everything In Its Right Place"
            assert result["year"] == 2000
            assert result["release_group_id"] == "mb-abc123"

    def test_lookup_returns_none_on_no_match(self) -> None:
        with patch("noctune.fingerprint.acoustid") as mock_acoustid:
            mock_acoustid.lookup.return_value = {"results": []}

            result = lookup_on_musicbrainz(
                fingerprint=b"\x00\x01\x02\x03",
                duration=30.5,
                api_key="test-key",
            )
            assert result is None

    def test_lookup_returns_none_on_exception(self) -> None:
        with patch("noctune.fingerprint.acoustid") as mock_acoustid:
            mock_acoustid.lookup.side_effect = Exception("API error")

            result = lookup_on_musicbrainz(
                fingerprint=b"\x00\x01\x02\x03",
                duration=30.5,
                api_key="test-key",
            )
            assert result is None


class TestFingerprintAndLookup:
    """Tests for the combined fingerprint + lookup pipeline."""

    def test_fingerprint_and_lookup_returns_musicbrainz_result(self) -> None:
        with patch("noctune.fingerprint.fingerprint_file") as mock_fp, \
             patch("noctune.fingerprint.lookup_on_musicbrainz") as mock_lookup:
            mock_fp.return_value = FingerprintResult(
                duration=30.5,
                fingerprint=b"\x00\x01\x02\x03",
            )
            mock_lookup.return_value = {
                "artist": "Radiohead",
                "album": "Kid A",
                "title": "Everything In Its Right Place",
                "track_number": 1,
                "year": 2000,
                "release_group_id": "mb-abc123",
            }

            result = fingerprint_and_lookup(Path("/music/test.flac"), api_key="test-key")
            assert result is not None
            assert result.artist == "Radiohead"
            assert result.album == "Kid A"

    def test_fingerprint_and_lookup_returns_none_if_fingerprint_fails(self) -> None:
        with patch("noctune.fingerprint.fingerprint_file") as mock_fp:
            mock_fp.return_value = None

            result = fingerprint_and_lookup(Path("/music/broken.flac"), api_key="test-key")
            assert result is None

    def test_fingerprint_and_lookup_returns_none_if_no_musicbrainz_match(self) -> None:
        with patch("noctune.fingerprint.fingerprint_file") as mock_fp, \
             patch("noctune.fingerprint.lookup_on_musicbrainz") as mock_lookup:
            mock_fp.return_value = FingerprintResult(
                duration=30.5,
                fingerprint=b"\x00\x01\x02\x03",
            )
            mock_lookup.return_value = None

            result = fingerprint_and_lookup(Path("/music/unknown.flac"), api_key="test-key")
            assert result is None