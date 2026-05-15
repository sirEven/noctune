"""Tests for Layer 3 — LLM reconciliation with genre constraint."""

import json
from unittest.mock import AsyncMock

from noctune.models.config import LLMConfig
from noctune.models.track import TagSet
from noctune.llm_router import LLMRouter
from noctune.reconcile import reconcile_tags, build_reconciliation_prompt


class TestBuildReconciliationPrompt:
    """Tests for prompt construction."""

    def test_prompt_includes_all_signals(self) -> None:
        fingerprint_tags = TagSet(
            artist="Radiohead", album="Kid A", title="Everything In Its Right Place", year=2000
        )
        extracted_tags = TagSet(
            artist="radiohead", album="Kid A (Deluxe)", title="Everything in its right place"
        )
        genre_vocabulary = ["Rock", "Electronic", "Jazz"]

        prompt = build_reconciliation_prompt(
            fingerprint_tags=fingerprint_tags,
            extracted_tags=extracted_tags,
            genre_vocabulary=genre_vocabulary,
        )

        assert "Radiohead" in prompt
        assert "radiohead" in prompt
        assert "Kid A" in prompt
        assert "Rock" in prompt
        assert "Electronic" in prompt

    def test_prompt_includes_genre_vocabulary(self) -> None:
        genre_vocabulary = ["Rock", "Pop", "Electronic", "Jazz"]
        prompt = build_reconciliation_prompt(
            fingerprint_tags=TagSet(),
            extracted_tags=TagSet(),
            genre_vocabulary=genre_vocabulary,
        )
        # All genres must be in the prompt
        for genre in genre_vocabulary:
            assert genre in prompt

    def test_prompt_with_no_fingerprint_tags(self) -> None:
        prompt = build_reconciliation_prompt(
            fingerprint_tags=None,
            extracted_tags=TagSet(artist="Bjork"),
            genre_vocabulary=["Electronic"],
        )
        assert "Bjork" in prompt


class TestLLMRouter:
    """Tests for LLM routing."""

    async def test_router_uses_local_endpoint(self) -> None:
        config = LLMConfig(direction="local", local_base_url="http://localhost:11434", local_model="llama3:8b")
        router = LLMRouter(config)
        assert router.base_url == "http://localhost:11434"
        assert router.model == "llama3:8b"

    async def test_router_uses_cloud_endpoint(self) -> None:
        config = LLMConfig(
            direction="cloud",
            cloud_base_url="https://api.ollama.com/v1",
            cloud_model="llama3:70b",
        )
        router = LLMRouter(config)
        assert router.base_url == "https://api.ollama.com/v1"
        assert router.model == "llama3:70b"


class TestReconcileTags:
    """Tests for the full reconciliation pipeline."""

    async def test_reconcile_produces_normalized_tagset(self) -> None:
        mock_router = AsyncMock(spec=LLMRouter)
        mock_router.complete.return_value = json.dumps({
            "artist": "Radiohead",
            "album_artist": "Radiohead",
            "album": "Kid A",
            "title": "Everything In Its Right Place",
            "track_number": 1,
            "year": 2000,
            "genre": "Electronic",
            "confidence": 0.95,
        })

        result = await reconcile_tags(
            fingerprint_tags=TagSet(
                artist="Radiohead", album="Kid A",
                title="Everything In Its Right Place", year=2000
            ),
            extracted_tags=TagSet(
                artist="radiohead", album="Kid A (Deluxe)",
                title="Everything in its right place"
            ),
            genre_vocabulary=["Rock", "Pop", "Electronic", "Jazz"],
            llm_router=mock_router,
        )

        assert result.artist == "Radiohead"
        assert result.album == "Kid A"
        assert result.genre == "Electronic"
        assert result.confidence == 0.95

    async def test_reconcile_clamps_unknown_genre(self) -> None:
        """LLM returns a genre not in vocabulary — maps to closest match if possible, flags if not."""
        mock_router = AsyncMock(spec=LLMRouter)
        mock_router.complete.return_value = json.dumps({
            "artist": "Radiohead",
            "album_artist": "Radiohead",
            "album": "Kid A",
            "title": "Everything In Its Right Place",
            "track_number": 1,
            "year": 2000,
            "genre": "Experimental Electronica",  # NOT in vocabulary
            "confidence": 0.8,
        })

        result = await reconcile_tags(
            fingerprint_tags=TagSet(artist="Radiohead"),
            extracted_tags=TagSet(artist="Radiohead"),
            genre_vocabulary=["Rock", "Electronic", "Jazz"],
            llm_router=mock_router,
        )

        # "Experimental Electronica" contains "Electronic" — mapped to closest match
        assert result.genre == "Electronic"
        assert result.genre_not_in_vocabulary is not True  # Mapped, not flagged

    async def test_reconcile_flags_unmappable_genre(self) -> None:
        """Completely unmappable genre is flagged for review."""
        mock_router = AsyncMock(spec=LLMRouter)
        mock_router.complete.return_value = json.dumps({
            "artist": "Artist",
            "title": "Song",
            "genre": "Zydeco",  # No close match in vocabulary
            "confidence": 0.8,
        })

        result = await reconcile_tags(
            fingerprint_tags=TagSet(),
            extracted_tags=TagSet(),
            genre_vocabulary=["Rock", "Electronic", "Jazz"],
            llm_router=mock_router,
        )

        # "Zydeco" has no close match — flagged for review
        assert result.genre == "Zydeco"
        assert result.genre_not_in_vocabulary is True

    async def test_reconcile_with_no_fingerprint_tags(self) -> None:
        mock_router = AsyncMock(spec=LLMRouter)
        mock_router.complete.return_value = json.dumps({
            "artist": "Bjork",
            "album_artist": "Bjork",
            "album": "Homogenic",
            "title": "Joga",
            "track_number": 1,
            "year": 1997,
            "genre": "Electronic",
            "confidence": 0.7,
        })

        result = await reconcile_tags(
            fingerprint_tags=None,
            extracted_tags=TagSet(artist="Bjork", album="Homogenic"),
            genre_vocabulary=["Electronic", "Jazz"],
            llm_router=mock_router,
        )

        assert result.artist == "Bjork"
        assert result.album == "Homogenic"
        assert result.confidence == 0.7

    async def test_reconcile_handles_llm_error(self) -> None:
        mock_router = AsyncMock(spec=LLMRouter)
        mock_router.complete.side_effect = Exception("LLM connection failed")

        result = await reconcile_tags(
            fingerprint_tags=TagSet(artist="Radiohead"),
            extracted_tags=TagSet(artist="Radiohead"),
            genre_vocabulary=["Rock"],
            llm_router=mock_router,
        )

        # On error, return extracted tags with low confidence
        assert result.artist == "Radiohead"
        assert result.confidence == 0.0