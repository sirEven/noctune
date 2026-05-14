"""Track-level data models — tags and metadata."""

from pathlib import Path

from pydantic import BaseModel


class TagSet(BaseModel):
    """Normalized set of tags for a music track."""

    artist: str = ""
    album_artist: str = ""
    album: str = ""
    title: str = ""
    track_number: int | None = None
    year: int | None = None
    genre: str = ""
    comment: str = ""


class TrackMeta(BaseModel):
    """File-level metadata extracted from the audio file itself."""

    path: Path
    file_size_bytes: int
    duration_seconds: float
    format: str
    bitrate: int | None = None
    existing_tags: TagSet | None = None
    has_cover_art: bool = False