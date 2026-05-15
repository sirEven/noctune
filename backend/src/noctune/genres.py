"""Curated genre vocabulary for Noctune.

The LLM must pick from this list during reconciliation. New genres require
human approval via the review queue. This list prioritizes breadth for
real music collections while avoiding over-fragmentation.

Organized by family for maintainability. The flat list is what gets used.
"""

# The canonical genre vocabulary — ~65 genres
GENRE_VOCABULARY: list[str] = [
    # Rock family
    "Rock",
    "Alternative Rock",
    "Indie Rock",
    "Post-Punk",
    "Punk",
    "Shoegaze",
    "Grunge",
    "Hard Rock",
    "Progressive Rock",
    "Psychedelic Rock",
    "Stoner Rock",
    "Surf Rock",

    # Metal family
    "Metal",
    "Black Metal",
    "Death Metal",
    "Doom Metal",
    "Thrash Metal",

    # Electronic family
    "Electronic",
    "Ambient",
    "Techno",
    "House",
    "Drum and Bass",
    "IDM",
    "Synthpop",
    "Industrial",
    "Dubstep",
    "Trance",
    "Downtempo",
    "Lo-Fi",

    # Hip Hop / R&B family
    "Hip Hop",
    "Rap",
    "R&B",
    "Soul",
    "Funk",
    "Neo-Soul",

    # Jazz / Blues family
    "Jazz",
    "Smooth Jazz",
    "Blues",
    "Swing",

    # Folk / Country family
    "Folk",
    "Indie Folk",
    "Country",
    "Bluegrass",

    # Pop family
    "Pop",
    "Indie Pop",
    "Dream Pop",
    "New Wave",
    "K-Pop",

    # Reggae / Latin / World family
    "Reggae",
    "Dub",
    "Latin",
    "Bossa Nova",
    "World",
    "Afrobeat",

    # Classical / Experimental family
    "Classical",
    "Neoclassical",
    "Experimental",
    "Noise",
    "Soundtrack",
    "Singer-Songwriter",
    "Spoken Word",
    "Comedy",
]


def get_genre_vocabulary() -> list[str]:
    """Return the canonical genre vocabulary."""
    return GENRE_VOCABULARY.copy()


def validate_genre(genre: str) -> str | None:
    """Validate a genre against the vocabulary.

    Returns the canonical genre name if valid, None otherwise.
    Case-insensitive matching. Strips whitespace.
    """
    genre_stripped = genre.strip()
    if not genre_stripped:
        return None
    genre_lower = genre_stripped.lower()
    for g in GENRE_VOCABULARY:
        if g.lower() == genre_lower:
            return g
    return None


def find_closest_genre(genre: str) -> str | None:
    """Find the closest matching genre using simple substring matching.

    For when the LLM returns a genre not in the vocabulary.
    Returns the closest match or None.
    """
    genre_stripped = genre.strip()
    if not genre_stripped:
        return None
    genre_lower = genre_stripped.lower()

    # Exact match (case-insensitive)
    for g in GENRE_VOCABULARY:
        if g.lower() == genre_lower:
            return g

    # Substring match — check if the input contains or is contained in a vocab genre
    # e.g., "Alt Rock" → "Alternative Rock", "Post Rock" → None (not in vocab)
    for g in GENRE_VOCABULARY:
        g_lower = g.lower()
        if genre_lower in g_lower or g_lower in genre_lower:
            return g

    # Word overlap match
    input_words = set(genre_lower.split())
    best_match = None
    best_overlap = 0
    for g in GENRE_VOCABULARY:
        vocab_words = set(g.lower().split())
        overlap = len(input_words & vocab_words)
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = g

    if best_overlap >= 1:
        return best_match

    return None