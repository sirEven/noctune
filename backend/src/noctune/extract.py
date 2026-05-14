"""Layer 2 — Metadata extraction from existing tags, filename, and directory.

Gathers all available signals from the file's existing tags (mutagen),
filename pattern, and directory structure into a merged TagSet.
This is the signal-gathering layer — no hallucination, just extracting
what's already there.
"""

import logging
import re
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

from noctune.models.track import TagSet, TrackMeta

logger = logging.getLogger(__name__)

# Filename pattern: "01 - Artist - Title.ext" or "01. Title.ext"
PATTERN_TRACK_ARTIST_TITLE = re.compile(
    r"^(\d{1,2})\s*[-.]\s*(.+?)\s*[-.]\s*(.+?)\.\w+$"
)
PATTERN_ARTIST_TITLE = re.compile(r"^(.+?)\s*[-–—]\s*(.+?)\.\w+$")
PATTERN_TRACK_DOT_TITLE = re.compile(r"^(\d{1,2})\.\s*(.+?)\.\w+$")
PATTERN_JUST_TITLE = re.compile(r"^(.+?)\.\w+$")

# Album with year: "Kid A (2000)" → extract year
PATTERN_ALBUM_YEAR = re.compile(r"^(.+?)\s*\((\d{4})\)\s*$")


def parse_filename(filename: str) -> TagSet:
    """Parse a filename into partial tag data.

    Handles common patterns:
    - "01 - Artist - Title.flac"
    - "Artist - Title.flac"
    - "01. Title.flac"
    - "Title.flac"
    """
    # Strip directory, get just the filename
    name = Path(filename).name

    # Pattern: "01 - Artist - Title.ext"
    match = PATTERN_TRACK_ARTIST_TITLE.match(name)
    if match:
        return TagSet(
            track_number=int(match.group(1)),
            artist=match.group(2).strip(),
            title=match.group(3).strip(),
        )

    # Pattern: "Artist - Title.ext" (no track number)
    match = PATTERN_ARTIST_TITLE.match(name)
    if match:
        return TagSet(
            artist=match.group(1).strip(),
            title=match.group(2).strip(),
        )

    # Pattern: "01. Title.ext"
    match = PATTERN_TRACK_DOT_TITLE.match(name)
    if match:
        return TagSet(
            track_number=int(match.group(1)),
            title=match.group(2).strip(),
        )

    # Pattern: "Title.ext" (just the title) — but skip generic names like track01
    match = PATTERN_JUST_TITLE.match(name)
    if match:
        raw_title = match.group(1).strip()
        # Skip generic/low-info filenames — these aren't real titles
        if not re.match(r"^[Tt]rack\d*$", raw_title) and not re.match(r"^\d+$", raw_title):
            return TagSet(title=raw_title)

    return TagSet()


def parse_directory(file_path: Path) -> TagSet:
    """Parse directory structure into partial tag data.

    Expected structure: .../Artist/Album/NN - Track.ext
    Returns artist from parent folder and album from grandparent.
    """
    tags = TagSet()

    try:
        # Parent folder = Album (or "Album (Year)")
        parent = file_path.parent
        album_name = parent.name
        skip_album_names = {"/", "", "Incoming", "incoming", "Music", "music"}
        if album_name and album_name not in skip_album_names:
            # Check for album with year: "Kid A (2000)"
            year_match = PATTERN_ALBUM_YEAR.match(album_name)
            if year_match:
                tags.album = album_name  # Keep full name including year
                try:
                    tags.year = int(year_match.group(2))
                except ValueError:
                    pass
            else:
                tags.album = album_name

        # Grandparent folder = Artist
        grandparent = parent.parent
        artist_name = grandparent.name
        skip_artist_names = {"/", "", "Incoming", "incoming", "Music", "music"}
        if artist_name and artist_name not in skip_artist_names:
            tags.artist = artist_name
    except (IndexError, ValueError):
        logger.warning("Could not parse directory structure for %s", file_path)

    return tags


def read_mutagen_tags(file_path: Path) -> TagSet | None:
    """Read existing tags from an audio file using mutagen.

    Returns TagSet with whatever tags are present, or None if the file
    can't be read or has no tags.
    """
    try:
        audio = MutagenFile(str(file_path))
        if audio is None:
            return None

        tags = TagSet()
        has_any_tag = False

        if isinstance(audio, MP3):
            # ID3v2 tags
            if audio.tags:
                for frame_id, frame in audio.tags.items():
                    if frame_id == "TPE1":
                        tags.artist = str(frame)
                        has_any_tag = True
                    elif frame_id == "TPE2":
                        tags.album_artist = str(frame)
                        has_any_tag = True
                    elif frame_id == "TALB":
                        tags.album = str(frame)
                        has_any_tag = True
                    elif frame_id == "TIT2":
                        tags.title = str(frame)
                        has_any_tag = True
                    elif frame_id == "TRCK":
                        try:
                            tags.track_number = int(str(frame).split("/")[0])
                            has_any_tag = True
                        except (ValueError, IndexError):
                            pass
                    elif frame_id == "TDRC" or frame_id == "TYER":
                        try:
                            tags.year = int(str(frame)[:4])
                            has_any_tag = True
                        except (ValueError, TypeError):
                            pass
                    elif frame_id == "TCON":
                        tags.genre = str(frame)
                        has_any_tag = True
                    elif frame_id == "COMM":
                        tags.comment = str(frame)
                        has_any_tag = True

        elif isinstance(audio, (FLAC,)):
            # Vorbis comments
            vorbis = audio.tags
            if vorbis:
                if "artist" in vorbis:
                    tags.artist = vorbis["artist"][0]
                    has_any_tag = True
                if "albumartist" in vorbis:
                    tags.album_artist = vorbis["albumartist"][0]
                    has_any_tag = True
                if "album" in vorbis:
                    tags.album = vorbis["album"][0]
                    has_any_tag = True
                if "title" in vorbis:
                    tags.title = vorbis["title"][0]
                    has_any_tag = True
                if "tracknumber" in vorbis:
                    try:
                        tags.track_number = int(vorbis["tracknumber"][0].split("/")[0])
                        has_any_tag = True
                    except (ValueError, IndexError):
                        pass
                if "date" in vorbis:
                    try:
                        tags.year = int(vorbis["date"][0][:4])
                        has_any_tag = True
                    except (ValueError, IndexError):
                        pass
                if "genre" in vorbis:
                    tags.genre = vorbis["genre"][0]
                    has_any_tag = True

        elif isinstance(audio, MP4):
            # MP4/M4A tags
            mp4_tags = audio.tags
            if mp4_tags:
                if "\xa9ART" in mp4_tags:
                    tags.artist = str(mp4_tags["\xa9ART"][0])
                    has_any_tag = True
                if "aART" in mp4_tags:
                    tags.album_artist = str(mp4_tags["aART"][0])
                    has_any_tag = True
                if "\xa9alb" in mp4_tags:
                    tags.album = str(mp4_tags["\xa9alb"][0])
                    has_any_tag = True
                if "\xa9nam" in mp4_tags:
                    tags.title = str(mp4_tags["\xa9nam"][0])
                    has_any_tag = True
                if "trkn" in mp4_tags:
                    tags.track_number = mp4_tags["trkn"][0][0]
                    has_any_tag = True
                if "\xa9day" in mp4_tags:
                    try:
                        tags.year = int(str(mp4_tags["\xa9day"][0])[:4])
                        has_any_tag = True
                    except (ValueError, IndexError):
                        pass
                if "\xa9gen" in mp4_tags:
                    tags.genre = str(mp4_tags["\xa9gen"][0])
                    has_any_tag = True

        return tags if has_any_tag else None

    except Exception:
        logger.debug("Could not read mutagen tags from %s", file_path)
        return None


def extract_metadata(file_path: Path) -> TrackMeta:
    """Extract all available metadata signals from a file.

    Combines mutagen tags, filename patterns, and directory structure
    into a TrackMeta with all available information filled in.
    """
    # Start with what we can get from the file itself
    file_size = file_path.stat().st_size if file_path.exists() else 0
    suffix = file_path.suffix.lower().lstrip(".")

    # Merge all signal sources: mutagen > filename > directory
    # (mutagen is most authoritative, then filename, then directory)
    dir_tags = parse_directory(file_path)
    filename_tags = parse_filename(file_path.name)

    # Try mutagen last — it's the most authoritative and overwrites
    mutagen_tags = read_mutagen_tags(file_path) if file_path.exists() else None

    # Merge: start with dir, layer filename on top, then mutagen on top
    merged = _merge_tags(dir_tags, filename_tags)
    if mutagen_tags:
        merged = _merge_tags(merged, mutagen_tags)

    # Detect cover art
    has_cover_art = _detect_cover_art(file_path) if file_path.exists() else False

    # Get duration from mutagen if available
    duration = 0.0
    bitrate = None
    if file_path.exists():
        try:
            audio = MutagenFile(str(file_path))
            if audio is not None:
                duration = audio.info.length if hasattr(audio.info, "length") else 0.0
                bitrate = audio.info.bitrate if hasattr(audio.info, "bitrate") else None
        except Exception:
            pass

    return TrackMeta(
        path=file_path,
        file_size_bytes=file_size,
        duration_seconds=round(duration, 1),
        format=suffix,
        bitrate=bitrate,
        existing_tags=merged,
        has_cover_art=has_cover_art,
    )


def _merge_tags(base: TagSet, overlay: TagSet) -> TagSet:
    """Merge two TagSets — overlay values override base where they exist.

    Non-empty strings from overlay overwrite base. None values from
    overlay don't overwrite base.
    """
    return TagSet(
        artist=overlay.artist or base.artist,
        album_artist=overlay.album_artist or base.album_artist,
        album=overlay.album or base.album,
        title=overlay.title or base.title,
        track_number=overlay.track_number if overlay.track_number is not None else base.track_number,
        year=overlay.year if overlay.year is not None else base.year,
        genre=overlay.genre or base.genre,
        comment=overlay.comment or base.comment,
    )


def _detect_cover_art(file_path: Path) -> bool:
    """Check if a file has embedded cover art or a cover file alongside it.

    Checks for: embedded APIC/cover in tags, folder.jpg, cover.jpg, etc.
    """
    # Check for cover art files in the same directory
    parent = file_path.parent
    cover_names = {"folder.jpg", "folder.png", "cover.jpg", "cover.png", "art.jpg", "art.png"}
    for cover in cover_names:
        if (parent / cover).exists():
            return True

    # Check for embedded cover in mutagen
    try:
        audio = MutagenFile(str(file_path))
        if audio is not None:
            if isinstance(audio, MP3) and audio.tags:
                if any(fid.startswith("APIC") for fid in audio.tags):
                    return True
            elif isinstance(audio, FLAC) and audio.pictures:
                return True
            elif isinstance(audio, MP4) and audio.tags:
                if "covr" in audio.tags:
                    return True
    except Exception:
        pass

    return False