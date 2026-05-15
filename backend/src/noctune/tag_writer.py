"""Tag writer — writes normalized tags to audio files via mutagen.

Before writing, backs up original tags to a .tags.json sidecar file.
Supports MP3 (ID3v2.4), FLAC (Vorbis comments), M4A (MP4), and OGG.
"""

import json
import logging
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TPE1, TPE2, TALB, TIT2, TRCK, TDRC, TCON, COMM
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis

from noctune.models.track import TagSet

logger = logging.getLogger(__name__)


def backup_tags(audio_path: Path, tags: TagSet) -> Path:
    """Save original tags to a sidecar JSON file before writing.

    The sidecar file is named `<filename>.<ext>.tags.json` and sits
    next to the audio file. This allows reverting if needed.
    """
    sidecar_path = audio_path.with_suffix(audio_path.suffix + ".tags.json")
    data = tags.model_dump()

    # Convert None values to null explicitly for JSON clarity
    sidecar_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    logger.info("Backed up original tags to %s", sidecar_path)
    return sidecar_path


def write_tags(audio_path: Path, tags: TagSet) -> Path:
    """Write normalized tags to an audio file.

    First backs up any existing tags to a sidecar file, then writes
    the new tags. Returns the audio file path on success.

    Raises:
        ValueError: If the file format is not supported.
        Exception: If mutagen fails to write tags.
    """
    # Read existing tags and back them up first
    existing = _read_existing_tags(audio_path)
    if existing:
        backup_tags(audio_path, existing)
    else:
        # Even if no existing tags, create an empty backup to mark the file was processed
        backup_tags(audio_path, TagSet())

    # Write new tags based on format
    suffix = audio_path.suffix.lower()
    if suffix == ".mp3":
        _write_mp3_tags(audio_path, tags)
    elif suffix == ".flac":
        _write_flac_tags(audio_path, tags)
    elif suffix in (".m4a", ".aac"):
        _write_mp4_tags(audio_path, tags)
    elif suffix == ".ogg":
        _write_ogg_tags(audio_path, tags)
    else:
        raise ValueError(f"Unsupported audio format: {suffix}")

    logger.info("Wrote tags to %s: %s", audio_path, tags.artist)
    return audio_path


def _read_existing_tags(audio_path: Path) -> TagSet | None:
    """Read existing tags from an audio file for backup."""
    try:
        # Import extract module to reuse existing tag reading
        from noctune.extract import read_mutagen_tags
        return read_mutagen_tags(audio_path)
    except Exception:
        logger.debug("Could not read existing tags from %s for backup", audio_path)
        return None


def _write_mp3_tags(audio_path: Path, tags: TagSet) -> None:
    """Write tags to an MP3 file using ID3v2.4."""
    try:
        audio = MP3(audio_path)
    except Exception:
        audio = MP3()
        audio.filename = str(audio_path)

    if audio.tags is None:
        audio.add_tags()

    assert audio.tags is not None  # for type checker

    id3 = audio.tags

    # Clear existing tags we're overwriting
    for frame_id in ["TPE1", "TPE2", "TALB", "TIT2", "TRCK", "TDRC", "TCON", "COMM::eng"]:
        if frame_id in id3:
            del id3[frame_id]

    # Write new tags
    if tags.artist:
        id3.add(TPE1(encoding=3, text=[tags.artist]))
    if tags.album_artist:
        id3.add(TPE2(encoding=3, text=[tags.album_artist]))
    if tags.album:
        id3.add(TALB(encoding=3, text=[tags.album]))
    if tags.title:
        id3.add(TIT2(encoding=3, text=[tags.title]))
    if tags.track_number is not None:
        id3.add(TRCK(encoding=3, text=[str(tags.track_number)]))
    if tags.year is not None:
        id3.add(TDRC(encoding=3, text=[str(tags.year)]))
    if tags.genre:
        id3.add(TCON(encoding=3, text=[tags.genre]))
    if tags.comment:
        id3.add(COMM(encoding=3, lang="eng", desc="comment", text=[tags.comment]))

    audio.save()


def _write_flac_tags(audio_path: Path, tags: TagSet) -> None:
    """Write tags to a FLAC file using Vorbis comments."""
    audio = FLAC(audio_path)

    # Clear existing tags we're overwriting
    for key in ["artist", "albumartist", "album", "title", "tracknumber", "date", "genre", "comment"]:
        if key in audio:
            del audio[key]

    if tags.artist:
        audio["artist"] = [tags.artist]
    if tags.album_artist:
        audio["albumartist"] = [tags.album_artist]
    if tags.album:
        audio["album"] = [tags.album]
    if tags.title:
        audio["title"] = [tags.title]
    if tags.track_number is not None:
        audio["tracknumber"] = [str(tags.track_number)]
    if tags.year is not None:
        audio["date"] = [str(tags.year)]
    if tags.genre:
        audio["genre"] = [tags.genre]
    if tags.comment:
        audio["comment"] = [tags.comment]

    audio.save()


def _write_mp4_tags(audio_path: Path, tags: TagSet) -> None:
    """Write tags to an M4A/AAC file using MP4 atoms."""
    audio = MP4(audio_path)
    if audio.tags is None:
        audio.add_tags()

    assert audio.tags is not None

    # MP4 tag keys
    tag_map: dict[str, str] = {
        "\xa9ART": "artist",       # Artist
        "aART": "album_artist",   # Album Artist
        "\xa9alb": "album",        # Album
        "\xa9nam": "title",        # Title
        "trkn": "track_number",    # Track Number
        "\xa9day": "year",          # Year
        "\xa9gen": "genre",        # Genre
        "\xa9cmt": "comment",      # Comment
    }

    # Clear existing tags
    for mp4_key in tag_map:
        if mp4_key in audio.tags:
            del audio.tags[mp4_key]

    # Write new tags
    if tags.artist:
        audio.tags["\xa9ART"] = [tags.artist]
    if tags.album_artist:
        audio.tags["aART"] = [tags.album_artist]
    if tags.album:
        audio.tags["\xa9alb"] = [tags.album]
    if tags.title:
        audio.tags["\xa9nam"] = [tags.title]
    if tags.track_number is not None:
        # MP4 track number format: (track_number, total_tracks)
        audio.tags["trkn"] = [(tags.track_number, 0)]
    if tags.year is not None:
        audio.tags["\xa9day"] = [str(tags.year)]
    if tags.genre:
        audio.tags["\xa9gen"] = [tags.genre]
    if tags.comment:
        audio.tags["\xa9cmt"] = [tags.comment]

    audio.save()


def _write_ogg_tags(audio_path: Path, tags: TagSet) -> None:
    """Write tags to an OGG file using Vorbis comments."""
    audio = OggVorbis(audio_path)

    # Clear and write (same keys as FLAC)
    for key in ["artist", "albumartist", "album", "title", "tracknumber", "date", "genre", "comment"]:
        if key in audio:
            del audio[key]

    if tags.artist:
        audio["artist"] = [tags.artist]
    if tags.album_artist:
        audio["albumartist"] = [tags.album_artist]
    if tags.album:
        audio["album"] = [tags.album]
    if tags.title:
        audio["title"] = [tags.title]
    if tags.track_number is not None:
        audio["tracknumber"] = [str(tags.track_number)]
    if tags.year is not None:
        audio["date"] = [str(tags.year)]
    if tags.genre:
        audio["genre"] = [tags.genre]
    if tags.comment:
        audio["comment"] = [tags.comment]

    audio.save()