"""Library normalizer — restructures files into Artist/Album (Year)/NN - Title.ext based on tags.

First preview, then execute. Never moves files until confirmed.
"""

import logging
import re
import shutil
from pathlib import Path

from pydantic import BaseModel

from noctune.models.track import TagSet

logger = logging.getLogger(__name__)


class RenamePair(BaseModel):
    """A file rename pair — old path to new path."""

    old_path: Path
    new_path: Path


def compute_target_path(
    tags: TagSet,
    base_dir: Path,
    original_suffix: str = ".flac",
) -> Path:
    """Compute the target path for a file based on its tags.

    Structure: base_dir/Artist/Album (Year)/NN - Title.ext
    If year is missing: base_dir/Artist/Album/NN - Title.ext
    If track number is missing: base_dir/Artist/Album/Title.ext
    """
    # Sanitize path components
    artist = sanitize_path_component(tags.artist) or "Unknown Artist"
    album = sanitize_path_component(tags.album) or "Unknown Album"

    # Album folder includes year if available
    if tags.year is not None:
        album_folder = f"{album} ({tags.year})"
    else:
        album_folder = album

    # Track filename
    ext = original_suffix or ".flac"
    title = sanitize_path_component(tags.title) or "Unknown Title"

    if tags.track_number is not None:
        filename = f"{tags.track_number:02d} - {title}{ext}"
    else:
        filename = f"{title}{ext}"

    return base_dir / artist / album_folder / filename


def sanitize_path_component(name: str) -> str:
    """Sanitize a path component — remove characters not valid in filenames.

    Keeps letters, numbers, spaces, hyphens, underscores, and parentheses.
    Replaces forward slashes with underscores (e.g., "AC/DC" → "AC_DC").
    Strips leading/trailing whitespace and dots.
    """
    if not name:
        return ""

    # Replace forward slashes with underscores
    result = name.replace("/", "_")

    # Remove characters that are problematic in filenames
    # Keep: letters, numbers, spaces, hyphens, underscores, parentheses, dots, ampersands
    result = re.sub(r'[<>:"|?*]', "", result)

    # Strip leading/trailing whitespace and dots
    result = result.strip().strip(".")

    return result


def preview_normalization(
    tags_map: dict[str, TagSet],
    source_dir: Path,
    dest_dir: Path | None = None,
) -> list[RenamePair]:
    """Preview normalization — return old/new path pairs without moving files.

    Args:
        tags_map: Mapping of file path strings to their reconciled tags.
        source_dir: Directory containing source files.
        dest_dir: Destination directory. If None, restructures in place (source_dir).

    Returns:
        List of RenamePair objects showing old → new paths.
    """
    base_dir = dest_dir or source_dir
    pairs: list[RenamePair] = []

    for file_path_str, tags in tags_map.items():
        file_path = Path(file_path_str)
        if not file_path.exists():
            logger.warning("File not found, skipping: %s", file_path)
            continue

        # Determine original extension
        original_suffix = file_path.suffix or ".flac"

        new_path = compute_target_path(tags, base_dir, original_suffix)

        # Skip if path wouldn't change
        if file_path == new_path:
            logger.debug("Path unchanged, skipping: %s", file_path)
            continue

        pairs.append(RenamePair(old_path=file_path, new_path=new_path))

    return pairs


def execute_normalization(pairs: list[RenamePair]) -> list[RenamePair]:
    """Execute normalization — move files from old paths to new paths.

    Creates destination directories as needed. Returns the list of
    successfully moved pairs (old_path will no longer exist, new_path will).

    Raises IOError if a move fails.
    """
    results: list[RenamePair] = []

    for pair in pairs:
        try:
            # Create destination directory
            pair.new_path.parent.mkdir(parents=True, exist_ok=True)

            # Move the file
            shutil.move(str(pair.old_path), str(pair.new_path))
            logger.info("Moved %s → %s", pair.old_path.name, pair.new_path)

            results.append(pair)

        except Exception:
            logger.exception("Failed to move %s → %s", pair.old_path, pair.new_path)
            raise

    return results