"""Tests for FastAPI REST endpoints."""

import tempfile
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport

from noctune.main import create_app
from noctune.models.config import NoctuneConfig, LLMConfig, RemoteConfig
from noctune.models.pipeline import FileState
from noctune.store import StateStore

# Create a test app instance with defaults (no config file needed)
app = create_app()


@pytest.fixture
def test_config(tmp_path: Path) -> NoctuneConfig:
    return NoctuneConfig(
        source_dir=tmp_path / "incoming",
        remote=RemoteConfig(
            host="192.168.178.107",
            user="eversin",
        ),
        dest_dir=Path("/data/music"),
        genre_vocabulary=["Rock", "Pop", "Electronic", "Jazz"],
        llm=LLMConfig(direction="local"),
    )


@pytest.fixture
def test_store(tmp_path: Path) -> StateStore:
    store = StateStore(tmp_path / "test.db")
    store.initialize()
    return store


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    async def test_health_returns_ok(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"


class TestStatusEndpoint:
    """Tests for the status/count endpoints."""

    async def test_status_returns_counts(self, tmp_path: Path, test_store: StateStore) -> None:
        # Insert some files
        test_store.upsert(
            __import__("noctune.models.pipeline", fromlist=["PipelineStatus"]).PipelineStatus(
                file_path="/music/a.flac", state=FileState.DISCOVERED
            )
        )
        test_store.upsert(
            __import__("noctune.models.pipeline", fromlist=["PipelineStatus"]).PipelineStatus(
                file_path="/music/b.flac", state=FileState.TAGGED
            )
        )

        from noctune.api import set_store
        set_store(test_store)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/status")
            assert response.status_code == 200
            data = response.json()
            assert "discovered" in data
            assert "tagged" in data


class TestFilesEndpoint:
    """Tests for file listing and detail endpoints."""

    async def test_list_files_empty(self, tmp_path: Path, test_store: StateStore) -> None:
        from noctune.api import set_store
        set_store(test_store)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/files")
            assert response.status_code == 200
            assert response.json() == []

    async def test_list_files_by_state(self, tmp_path: Path, test_store: StateStore) -> None:
        from noctune.models.pipeline import PipelineStatus
        test_store.upsert(PipelineStatus(file_path="/music/a.flac", state=FileState.DISCOVERED))
        test_store.upsert(PipelineStatus(file_path="/music/b.flac", state=FileState.TAGGED))

        from noctune.api import set_store
        set_store(test_store)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # Filter by state
            response = await client.get("/api/files", params={"state": "discovered"})
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["state"] == "discovered"


class TestReviewEndpoint:
    """Tests for the review queue endpoint."""

    async def test_review_queue_empty(self, tmp_path: Path, test_store: StateStore) -> None:
        from noctune.api import set_store
        set_store(test_store)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/review")
            assert response.status_code == 200
            assert response.json() == []

    async def test_review_queue_returns_queued_files(self, tmp_path: Path, test_store: StateStore) -> None:
        from noctune.models.pipeline import PipelineStatus
        test_store.upsert(PipelineStatus(
            file_path="/music/a.flac", state=FileState.QUEUED_FOR_REVIEW, confidence=0.5
        ))
        test_store.upsert(PipelineStatus(file_path="/music/b.flac", state=FileState.TAGGED))

        from noctune.api import set_store
        set_store(test_store)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/review")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["state"] == "queued_for_review"