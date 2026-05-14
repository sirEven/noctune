"""Layer 1 — Fingerprint and MusicBrainz lookup.

Generates an audio fingerprint using chromaprint (via pyacoustid),
then looks it up against the Acoustid/MusicBrainz database to get
canonical tag data. This is the zero-hallucination layer — database
ground truth only.
"""

import logging
from pathlib import Path
from typing import Any

import acoustid
import httpx

from noctune.models.track import TagSet

logger = logging.getLogger(__name__)


class FingerprintResult:
    """Result of fingerprinting an audio file."""

    def __init__(self, duration: float, fingerprint: bytes) -> None:
        self.duration = duration
        self.fingerprint = fingerprint


class MusicBrainzResult:
    """Parsed result from a MusicBrainz lookup."""

    def __init__(
        self,
        artist: str,
        album: str,
        title: str,
        track_number: int | None,
        year: int | None,
        release_group_id: str,
        score: float,
    ) -> None:
        self.artist = artist
        self.album = album
        self.title = title
        self.track_number = track_number
        self.year = year
        self.release_group_id = release_group_id
        self.score = score

    def to_tagset(self) -> TagSet:
        """Convert to a TagSet for pipeline consumption."""
        return TagSet(
            artist=self.artist,
            album=self.album,
            title=self.title,
            track_number=self.track_number,
            year=self.year,
        )


def fingerprint_file(file_path: Path, api_key: str) -> FingerprintResult | None:
    """Generate an audio fingerprint for a file using chromaprint.

    Returns FingerprintResult on success, None on failure.
    """
    try:
        duration, fingerprint = acoustid.fingerprint(str(file_path), api_key)
        return FingerprintResult(duration=duration, fingerprint=fingerprint)
    except Exception:
        logger.exception("Failed to fingerprint %s", file_path)
        return None


def lookup_on_musicbrainz(
    fingerprint: bytes,
    duration: float,
    api_key: str,
) -> dict[str, Any] | None:
    """Look up a fingerprint against the Acoustid/MusicBrainz database.

    Returns a parsed dict with tag data on match, None on no match or error.
    """
    try:
        results = acoustid.lookup(api_key, fingerprint, duration)
        return _parse_musicbrainz_results(results)
    except Exception:
        logger.exception("MusicBrainz lookup failed")
        return None


def _parse_musicbrainz_results(results: dict[str, Any]) -> dict[str, Any] | None:
    """Parse Acoustid lookup results into a flat dict of tag data.

    Returns None if no high-confidence match found.
    """
    matches = results.get("results", [])
    if not matches:
        return None

    # Take the best match (highest score)
    best = max(matches, key=lambda m: m.get("score", 0))
    score = best.get("score", 0)

    if score < 0.5:
        logger.info("Best MusicBrainz match score too low: %.2f", score)
        return None

    recordings = best.get("recordings", [])
    if not recordings:
        return None

    recording = recordings[0]
    title = recording.get("title", "")
    artists = recording.get("artists", [])
    artist_name = artists[0]["name"] if artists else ""

    releases = recording.get("releases", [])
    album = ""
    year: int | None = None
    release_group_id = ""
    track_number: int | None = None

    if releases:
        release = releases[0]
        album = release.get("title", "")
        date_str = release.get("date", "")
        if date_str and len(date_str) >= 4:
            try:
                year = int(date_str[:4])
            except ValueError:
                year = None
        release_group = release.get("release-group", {})
        release_group_id = release_group.get("id", "")
        medium_list = release.get("medium-list", [])
        if medium_list:
            track_list = medium_list[0].get("track-list", [])
            for track in track_list:
                if track.get("recording", {}).get("title") == title:
                    track_number = track.get("position")
                    break

    return {
        "artist": artist_name,
        "album": album,
        "title": title,
        "track_number": track_number,
        "year": year,
        "release_group_id": release_group_id,
        "score": score,
    }


def fingerprint_and_lookup(file_path: Path, api_key: str) -> TagSet | None:
    """Combined fingerprint + MusicBrainz lookup.

    The primary entry point for Layer 1 of the pipeline.
    Returns a TagSet with canonical tag data, or None if no match.
    """
    fp_result = fingerprint_file(file_path, api_key)
    if fp_result is None:
        logger.warning("Fingerprinting failed for %s — skipping lookup", file_path)
        return None

    mb_result = lookup_on_musicbrainz(
        fingerprint=fp_result.fingerprint,
        duration=fp_result.duration,
        api_key=api_key,
    )
    if mb_result is None:
        logger.info("No MusicBrainz match for %s", file_path)
        return None

    return TagSet(
        artist=mb_result.get("artist", ""),
        album=mb_result.get("album", ""),
        title=mb_result.get("title", ""),
        track_number=mb_result.get("track_number"),
        year=mb_result.get("year"),
    )