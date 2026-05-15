"""Tests for curated genre vocabulary."""

from noctune.genres import (
    GENRE_VOCABULARY,
    find_closest_genre,
    get_genre_vocabulary,
    validate_genre,
)


class TestGenreVocabulary:
    """Vocabulary structure and completeness."""

    def test_vocabulary_has_around_65_genres(self) -> None:
        """Vocabulary should have ~60-70 genres."""
        assert 60 <= len(GENRE_VOCABULARY) <= 75

    def test_no_duplicates(self) -> None:
        """Vocabulary should have no duplicate genres."""
        assert len(GENRE_VOCABULARY) == len(set(GENRE_VOCABULARY))

    def test_all_strings(self) -> None:
        """Every genre should be a non-empty string."""
        for genre in GENRE_VOCABULARY:
            assert isinstance(genre, str)
            assert len(genre) > 0

    def test_no_trailing_whitespace(self) -> None:
        """No genre should have leading/trailing whitespace."""
        for genre in GENRE_VOCABULARY:
            assert genre == genre.strip()

    def test_get_genre_vocabulary_returns_copy(self) -> None:
        """get_genre_vocabulary should return a copy, not the original."""
        vocab = get_genre_vocabulary()
        assert vocab == GENRE_VOCABULARY
        vocab.append("Fake Genre")
        assert "Fake Genre" not in GENRE_VOCABULARY

    def test_core_genres_present(self) -> None:
        """Essential genres must be in the vocabulary."""
        essential = ["Rock", "Pop", "Electronic", "Jazz", "Hip Hop", "Classical", "Metal"]
        for genre in essential:
            assert genre in GENRE_VOCABULARY, f"{genre} missing from vocabulary"

    def test_covers_major_families(self) -> None:
        """Vocabulary should cover rock, electronic, hip hop, jazz, classical, world."""
        families = {
            "Rock": ["Rock", "Alternative Rock", "Punk", "Shoegaze"],
            "Electronic": ["Electronic", "Techno", "House", "Ambient"],
            "Hip Hop": ["Hip Hop", "Rap", "R&B"],
            "Jazz": ["Jazz", "Blues"],
            "Classical": ["Classical", "Neoclassical"],
            "World": ["World", "Afrobeat", "Latin"],
        }
        for family, genres in families.items():
            for genre in genres:
                assert genre in GENRE_VOCABULARY, f"{family} family missing {genre}"


class TestValidateGenre:
    """Genre validation against vocabulary."""

    def test_exact_match(self) -> None:
        """Exact genre name validates correctly."""
        assert validate_genre("Rock") == "Rock"
        assert validate_genre("Hip Hop") == "Hip Hop"

    def test_case_insensitive(self) -> None:
        """Validation is case-insensitive, returns canonical form."""
        assert validate_genre("rock") == "Rock"
        assert validate_genre("ELECTRONIC") == "Electronic"
        assert validate_genre("hip hop") == "Hip Hop"

    def test_invalid_genre_returns_none(self) -> None:
        """Genre not in vocabulary returns None."""
        assert validate_genre("Zydeco") is None
        assert validate_genre("Polka Metal") is None
        assert validate_genre("") is None

    def test_whitespace_handling(self) -> None:
        """Leading/trailing whitespace still matches."""
        assert validate_genre("  Rock  ") == "Rock"


class TestFindClosestGenre:
    """Fuzzy genre matching for LLM outputs not in vocabulary."""

    def test_exact_match(self) -> None:
        """Exact match returns the canonical genre."""
        assert find_closest_genre("Rock") == "Rock"
        assert find_closest_genre("Jazz") == "Jazz"

    def test_case_insensitive_exact(self) -> None:
        """Case-insensitive exact match."""
        assert find_closest_genre("rock") == "Rock"

    def test_substring_match(self) -> None:
        """Substring matching for partial genres."""
        # "Alt Rock" contains "Rock" which is in "Alternative Rock"
        result = find_closest_genre("Alt Rock")
        assert result is not None
        assert "Rock" in result

    def test_contained_match(self) -> None:
        """Input that contains a vocab genre."""
        # "Electronic Dance" contains "Electronic"
        result = find_closest_genre("Electronic Dance")
        assert result == "Electronic"

    def test_word_overlap_match(self) -> None:
        """Word overlap matching for partial matches."""
        # "Indie Pop Rock" shares "Indie" and "Pop" and "Rock" with multiple genres
        result = find_closest_genre("Indie Pop Rock")
        assert result is not None
        # Should match one of the overlapping genres
        assert "Indie" in result or "Pop" in result or "Rock" in result

    def test_no_match_returns_none(self) -> None:
        """Completely unrelated genre returns None."""
        assert find_closest_genre("Xyzzy") is None

    def test_close_match(self) -> None:
        """Common LLM mistakes map to closest genre."""
        # LLM might say "Alt-Rock" or "Alternative"
        result = find_closest_genre("Alternative")
        assert result is not None  # Should find "Alternative Rock"

    def test_none_for_empty(self) -> None:
        """Empty string returns None."""
        assert find_closest_genre("") is None