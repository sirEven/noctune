"""FastAPI REST endpoints for Noctune pipeline control.

Provides endpoints for:
- Health check
- Pipeline status (counts by state)
- File listing with state filter
- Review queue (files needing human approval)
- Pipeline start/stop
- File processing triggers
- Normalization preview and execute
- Transfer triggers
"""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from noctune.config_loader import load_config
from noctune.models.config import NoctuneConfig
from noctune.models.pipeline import FileState, PipelineStatus
from noctune.models.track import TagSet
from noctune.store import StateStore

logger = logging.getLogger(__name__)

# Module-level state — set by set_store() at startup
_store: StateStore | None = None
_config: NoctuneConfig | None = None

router = APIRouter(prefix="/api")


def set_store(store: StateStore) -> None:
    """Set the state store (called at app startup or in tests)."""
    global _store
    _store = store


def set_config(config: NoctuneConfig) -> None:
    """Set the config (called at app startup or in tests)."""
    global _config
    _config = config


def get_store() -> StateStore:
    """Get the state store, raising 503 if not initialized."""
    if _store is None:
        raise HTTPException(status_code=503, detail="State store not initialized")
    return _store


def get_config() -> NoctuneConfig:
    """Get the config, raising 503 if not initialized."""
    if _config is None:
        raise HTTPException(status_code=503, detail="Config not initialized")
    return _config


# --- Health ---

@router.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


# --- Status ---

@router.get("/status")
async def status() -> dict[str, int]:
    """Get file counts by pipeline state."""
    store = get_store()
    counts: dict[str, int] = {}
    for state in FileState:
        files = store.list_by_state(state)
        counts[state.value] = len(files)
    return counts


# --- Files ---

@router.get("/files")
async def list_files(
    state: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List tracked files, optionally filtered by state."""
    store = get_store()

    if state:
        try:
            file_state = FileState(state)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid state: {state}")
        files = store.list_by_state(file_state)
    else:
        # Return all files — get all states
        files = []
        for s in FileState:
            files.extend(store.list_by_state(s))

    # Apply pagination
    files = files[offset : offset + limit]

    return [f.model_dump() for f in files]


@router.get("/files/{file_path:path}")
async def get_file(file_path: str) -> dict[str, Any]:
    """Get detail for a single file."""
    store = get_store()
    result = store.get(file_path)
    if result is None:
        raise HTTPException(status_code=404, detail="File not found")
    return result.model_dump()


@router.post("/files")
async def add_files(paths: list[str]) -> list[dict[str, Any]]:
    """Add file paths to the pipeline as DISCOVERED."""
    store = get_store()
    results = []
    for path in paths:
        status = PipelineStatus(file_path=path, state=FileState.DISCOVERED)
        store.upsert(status)
        results.append(status.model_dump())
    return results


# --- Pipeline Control ---

@router.post("/pipeline/start")
async def start_pipeline() -> dict[str, str]:
    """Start processing all DISCOVERED files through the pipeline.

    This triggers background processing. Returns immediately.
    """
    # TODO: Implement background task processing
    return {"status": "started", "message": "Pipeline processing started"}


@router.post("/pipeline/stop")
async def stop_pipeline() -> dict[str, str]:
    """Stop any running pipeline processing."""
    # TODO: Implement background task cancellation
    return {"status": "stopped", "message": "Pipeline processing stopped"}


# --- Review Queue ---

@router.get("/review")
async def list_review() -> list[dict[str, Any]]:
    """List files in the review queue (low confidence)."""
    store = get_store()
    files = store.list_by_state(FileState.QUEUED_FOR_REVIEW)
    return [f.model_dump() for f in files]


@router.post("/review/{file_path:path}/approve")
async def approve_review(file_path: str, tags: TagSet) -> dict[str, Any]:
    """Approve a review item — write tags and move to TAGGED state."""
    from noctune.pipeline import Pipeline
    from noctune.llm_router import LLMRouter

    config = get_config()
    store = get_store()
    llm_router = LLMRouter(config.llm)
    pipeline = Pipeline(config=config, store=store, llm_router=llm_router)

    try:
        result = pipeline.approve_review(file_path, tags)
        return result.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/review/{file_path:path}/reject")
async def reject_review(file_path: str) -> dict[str, Any]:
    """Reject a review item — revert tags from sidecar backup."""
    from noctune.pipeline import Pipeline
    from noctune.llm_router import LLMRouter

    config = get_config()
    store = get_store()
    llm_router = LLMRouter(config.llm)
    pipeline = Pipeline(config=config, store=store, llm_router=llm_router)

    try:
        result = pipeline.reject_review(file_path)
        return result.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Normalization ---

@router.post("/normalize/preview")
async def preview_normalize(paths: list[str]) -> list[dict[str, str]]:
    """Preview normalization — return old/new path pairs without moving files."""
    from noctune.normalize import preview_normalization

    config = get_config()
    store = get_store()

    # Get reconciled tags for each file
    tags_map: dict[str, TagSet] = {}
    for path in paths:
        status = store.get(path)
        if status and status.state in (FileState.RECONCILED, FileState.TAGGED):
            # We'd need to store the reconciled tags — for now use a placeholder
            tags_map[path] = TagSet()

    pairs = preview_normalization(tags_map, config.source_dir)
    return [{"old_path": str(p.old_path), "new_path": str(p.new_path)} for p in pairs]


@router.post("/normalize/execute")
async def execute_normalize(pairs: list[dict[str, str]]) -> list[dict[str, str]]:
    """Execute normalization — move files to their new paths.

    Accepts a list of {old_path, new_path} pairs from the preview endpoint.
    """
    from noctune.normalize import RenamePair, execute_normalization as do_execute

    rename_pairs = [
        RenamePair(old_path=Path(p["old_path"]), new_path=Path(p["new_path"]))
        for p in pairs
    ]

    try:
        results = do_execute(rename_pairs)
        return [{"old_path": str(r.old_path), "new_path": str(r.new_path)} for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Transfer ---

@router.post("/transfer/{file_path:path}")
async def transfer_file(file_path: str) -> dict[str, Any]:
    """Transfer a tagged file to the remote server via rsync."""
    from noctune.transfer import RsyncBackend
    from noctune.models.pipeline import FileState

    config = get_config()
    store = get_store()

    status = store.get(file_path)
    if status is None:
        raise HTTPException(status_code=404, detail="File not found")
    if status.state != FileState.TAGGED:
        raise HTTPException(status_code=400, detail="File must be in TAGGED state to transfer")

    backend = RsyncBackend(host=config.dest_host, user=config.dest_user)
    result = await backend.transfer(Path(file_path), config.dest_dir)

    if result:
        # Update state to TRANSFERRED
        status = PipelineStatus(file_path=file_path, state=FileState.TRANSFERRED, confidence=status.confidence)
        store.upsert(status)
        return status.model_dump()
    else:
        raise HTTPException(status_code=500, detail="Transfer failed")


# --- Config ---

@router.get("/config")
async def read_config() -> dict[str, Any]:
    """Read the current configuration."""
    config = get_config()
    return config.model_dump(mode="json")