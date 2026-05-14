"""Layer 3 — LLM Reconciliation.

Feeds all signals from Layer 1 (fingerprint) and Layer 2 (metadata extraction)
to the LLM, receives a normalized TagSet with confidence score. Genre is
constrained to the provided vocabulary — if the LLM returns a genre not in
the list, it's flagged for review.
"""

import json
import logging
from typing import Any

from noctune.llm_router import LLMRouter
from noctune.models.track import TagSet

logger = logging.getLogger(__name__)


class ReconciledTags(TagSet):
    """TagSet with reconciliation metadata."""

    confidence: float = 0.0
    genre_not_in_vocabulary: bool = False


def build_reconciliation_prompt(
    fingerprint_tags: TagSet | None,
    extracted_tags: TagSet,
    genre_vocabulary: list[str],
) -> str:
    """Build the LLM prompt with all available signals and genre constraint.

    The prompt includes:
    - MusicBrainz fingerprint data (if available) — highest confidence signal
    - Extracted metadata from mutagen/filename/directory
    - The genre vocabulary the LLM must pick from
    - Expected JSON output format
    """
    genre_list = ", ".join(genre_vocabulary)

    fingerprint_section = ""
    if fingerprint_tags:
        fingerprint_section = f"""
## MusicBrainz Fingerprint Data (high confidence)
These tags come from audio fingerprint lookup — they're the most authoritative signal.
- Artist: {fingerprint_tags.artist}
- Album: {fingerprint_tags.album}
- Album Artist: {fingerprint_tags.album_artist}
- Title: {fingerprint_tags.title}
- Track Number: {fingerprint_tags.track_number}
- Year: {fingerprint_tags.year}
- Genre: {fingerprint_tags.genre}
"""

    extracted_fields: list[str] = []
    if extracted_tags.artist:
        extracted_fields.append(f"- Artist: {extracted_tags.artist}")
    if extracted_tags.album_artist:
        extracted_fields.append(f"- Album Artist: {extracted_tags.album_artist}")
    if extracted_tags.album:
        extracted_fields.append(f"- Album: {extracted_tags.album}")
    if extracted_tags.title:
        extracted_fields.append(f"- Title: {extracted_tags.title}")
    if extracted_tags.track_number is not None:
        extracted_fields.append(f"- Track Number: {extracted_tags.track_number}")
    if extracted_tags.year is not None:
        extracted_fields.append(f"- Year: {extracted_tags.year}")
    if extracted_tags.genre:
        extracted_fields.append(f"- Genre: {extracted_tags.genre}")

    extracted_section = "\n".join(extracted_fields) if extracted_fields else "No extracted metadata available."

    return f"""You are a music metadata reconciler. Your job is to take conflicting and incomplete
metadata signals and produce a single, normalized set of tags.

{fingerprint_section}

## Extracted Metadata (from file tags, filename, directory)
These come from the file itself — less authoritative than fingerprint data but still valuable.
{extracted_section}

## Genre Constraint
You MUST pick the genre from this list only: [{genre_list}]
If none of these fit well, pick the closest match. If truly none fit, provide your best guess
and it will be flagged for human review.

## Instructions
1. Resolve conflicts between fingerprint and extracted data — fingerprint wins when they disagree.
2. Normalize artist names (e.g., "radiohead" → "Radiohead", "Björk" is already correct).
3. Remove deluxe/special edition suffixes from album names.
4. Pick the most specific genre from the vocabulary.
5. Assign a confidence score from 0.0 to 1.0 based on how well the signals agree.

## Output Format
Respond with ONLY a JSON object, no markdown, no explanation:
{{
    "artist": "...",
    "album_artist": "...",
    "album": "...",
    "title": "...",
    "track_number": ...,
    "year": ...,
    "genre": "...",
    "confidence": 0.0-1.0
}}"""


async def reconcile_tags(
    fingerprint_tags: TagSet | None,
    extracted_tags: TagSet,
    genre_vocabulary: list[str],
    llm_router: LLMRouter,
) -> ReconciledTags:
    """Reconcile fingerprint and extracted tags using the LLM.

    Returns a ReconciledTags with confidence score and genre vocabulary flag.
    Falls back to extracted tags with confidence=0.0 on LLM failure.
    """
    prompt = build_reconciliation_prompt(fingerprint_tags, extracted_tags, genre_vocabulary)

    try:
        response_text = await llm_router.complete(prompt)
        parsed = _parse_llm_response(response_text)

        result = ReconciledTags(
            artist=parsed.get("artist", extracted_tags.artist),
            album_artist=parsed.get("album_artist", extracted_tags.album_artist),
            album=parsed.get("album", extracted_tags.album),
            title=parsed.get("title", extracted_tags.title),
            track_number=parsed.get("track_number", extracted_tags.track_number),
            year=parsed.get("year", extracted_tags.year),
            genre=parsed.get("genre", extracted_tags.genre),
            confidence=parsed.get("confidence", 0.5),
        )

        # Check if genre is in vocabulary
        if result.genre and result.genre not in genre_vocabulary:
            result.genre_not_in_vocabulary = True
            logger.info("Genre '%s' not in vocabulary — flagging for review", result.genre)

        return result

    except Exception:
        logger.exception("LLM reconciliation failed — returning extracted tags with low confidence")
        return ReconciledTags(
            artist=extracted_tags.artist,
            album_artist=extracted_tags.album_artist,
            album=extracted_tags.album,
            title=extracted_tags.title,
            track_number=extracted_tags.track_number,
            year=extracted_tags.year,
            genre=extracted_tags.genre,
            confidence=0.0,
        )


def _parse_llm_response(response: str) -> dict[str, Any]:
    """Parse the LLM response JSON, handling common formatting issues."""
    # Strip markdown code fences if present
    text = response.strip()
    if text.startswith("```"):
        # Remove opening and closing fences
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM response as JSON: %s", text[:200])
        return {}