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

import httpx
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from noctune.config_loader import load_config
from noctune.models.config import NavidromeConfig, NoctuneConfig
from noctune.models.pipeline import FileState, PipelineStatus
from noctune.models.track import TagSet
from noctune.store import StateStore
from noctune.daemon import DaemonManager
from noctune.genres import GENRE_VOCABULARY, find_closest_genre, validate_genre
from noctune.navidrome import NavidromeClient, SubsonicError
from noctune.path_probe import probe_local_paths, probe_remote_paths, probe_navidrome_connection

logger = logging.getLogger(__name__)

# Module-level state — set by set_store() at startup
_store: StateStore | None = None
_config: NoctuneConfig | None = None
_daemon: DaemonManager | None = None

router = APIRouter(prefix="/api")


def set_store(store: StateStore) -> None:
    """Set the state store (called at app startup or in tests)."""
    global _store
    _store = store


def set_config(config: NoctuneConfig) -> None:
    """Set the config (called at app startup or in tests)."""
    global _config
    _config = config


def set_daemon(daemon: DaemonManager) -> None:
    """Set the daemon manager (called at app startup or in tests)."""
    global _daemon
    _daemon = daemon


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


# --- Daemon Control ---

@router.post("/daemon/start")
async def start_daemon() -> dict[str, str]:
    """Start the background daemon — begins processing discovered files."""
    daemon = _daemon
    if daemon is None:
        raise HTTPException(status_code=503, detail="Daemon not initialized")
    await daemon.start()
    return {"status": daemon.state.value, "message": "Daemon started"}


@router.post("/daemon/stop")
async def stop_daemon() -> dict[str, str]:
    """Stop the background daemon completely."""
    daemon = _daemon
    if daemon is None:
        raise HTTPException(status_code=503, detail="Daemon not initialized")
    await daemon.stop()
    return {"status": daemon.state.value, "message": "Daemon stopped"}


@router.post("/daemon/pause")
async def pause_daemon() -> dict[str, str]:
    """Pause the daemon — files queue up but aren't processed."""
    daemon = _daemon
    if daemon is None:
        raise HTTPException(status_code=503, detail="Daemon not initialized")
    await daemon.pause()
    return {"status": daemon.state.value, "message": "Daemon paused"}


@router.post("/daemon/resume")
async def resume_daemon() -> dict[str, str]:
    """Resume the daemon from paused state."""
    daemon = _daemon
    if daemon is None:
        raise HTTPException(status_code=503, detail="Daemon not initialized")
    await daemon.resume()
    return {"status": daemon.state.value, "message": "Daemon resumed"}


@router.get("/daemon/status")
async def daemon_status() -> dict[str, str]:
    """Get the current daemon state."""
    daemon = _daemon
    if daemon is None:
        raise HTTPException(status_code=503, detail="Daemon not initialized")
    return {"state": daemon.state.value}


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


# --- Genres ---

@router.get("/genres")
async def list_genres() -> dict[str, list[str]]:
    """Return the curated genre vocabulary."""
    return {"genres": list(GENRE_VOCABULARY)}


@router.get("/genres/validate")
async def validate_genre_endpoint(genre: str) -> dict[str, Any]:
    """Validate a genre against the vocabulary.

    Returns the canonical name if valid, or the closest match if not.
    """
    validated = validate_genre(genre)
    if validated:
        return {"genre": validated, "valid": True, "closest": None}

    closest = find_closest_genre(genre)
    return {"genre": genre, "valid": False, "closest": closest}


# --- Navidrome Library Browsing & Deletion ---

_navidrome_client: NavidromeClient | None = None


def _get_navidrome() -> NavidromeClient:
    """Get the Navidrome client, raising 503 if not configured."""
    config = get_config()
    if config.navidrome is None:
        raise HTTPException(status_code=503, detail="Navidrome not configured")
    global _navidrome_client
    if _navidrome_client is None:
        _navidrome_client = NavidromeClient(config.navidrome)
    return _navidrome_client


@router.get("/library/search")
async def library_search(query: str, song_count: int = 20, album_count: int = 10) -> dict[str, Any]:
    """Search the Navidrome library via Subsonic API."""
    client = _get_navidrome()
    try:
        return client.search(query, song_count=song_count, album_count=album_count)
    except SubsonicError as e:
        raise HTTPException(status_code=502, detail=f"Navidrome error: {e.message}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Navidrome connection error: {e}")


@router.get("/library/albums")
async def library_albums(ltype: str = "alphabeticalByName", offset: int = 0, size: int = 50) -> dict[str, Any]:
    """List albums from Navidrome."""
    client = _get_navidrome()
    try:
        return client.get_album_list(ltype=ltype, offset=offset, size=size)
    except SubsonicError as e:
        raise HTTPException(status_code=502, detail=f"Navidrome error: {e.message}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Navidrome connection error: {e}")


@router.get("/library/album/{album_id}")
async def library_album(album_id: str) -> dict[str, Any]:
    """Get album details + songs from Navidrome."""
    client = _get_navidrome()
    try:
        return client.get_album(album_id)
    except SubsonicError as e:
        raise HTTPException(status_code=502, detail=f"Navidrome error: {e.message}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Navidrome connection error: {e}")


@router.delete("/library/file")
async def delete_library_file(path: str) -> dict[str, str]:
    """Delete a file from the remote Navidrome library.

    The path must be the relative path from Navidrome's music folder root.
    After deletion, triggers a Navidrome rescan.
    """
    client = _get_navidrome()
    try:
        client.delete_remote_file(path)
        # Trigger rescan so Navidrome sees the file is gone
        client.start_scan()
        return {"status": "deleted", "path": path}
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"SSH delete error: {e}")
    except SubsonicError as e:
        raise HTTPException(status_code=502, detail=f"Navidrome error: {e.message}")


@router.delete("/library/directory")
async def delete_library_directory(path: str) -> dict[str, str]:
    """Delete an entire directory (e.g. album) from the remote Navidrome library.

    The path must be the relative path from Navidrome's music folder root.
    After deletion, triggers a Navidrome rescan.
    """
    client = _get_navidrome()
    try:
        client.delete_remote_directory(path)
        client.start_scan()
        return {"status": "deleted", "path": path}
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"SSH delete error: {e}")
    except SubsonicError as e:
        raise HTTPException(status_code=502, detail=f"Navidrome error: {e.message}")


# --- Settings & Path Probing ---

@router.get("/settings/paths/local")
async def settings_paths_local() -> dict[str, list[dict[str, str | bool]]]:
    """Probe local filesystem for likely source and destination directories."""
    return probe_local_paths()


@router.get("/settings/paths/remote")
async def settings_paths_remote() -> dict:
    """Probe the remote machine for likely Navidrome music folder paths."""
    config = get_config()
    if config.navidrome is None:
        raise HTTPException(
            status_code=424,
            detail="Navidrome not configured — go to Settings and fill in the Remote Host, SSH User, and Navidrome URL first",
        )
    if not config.navidrome.ssh_host:
        raise HTTPException(
            status_code=424,
            detail="Remote Host not set — enter the IP or hostname of your remote machine in Settings",
        )
    return probe_remote_paths(
        host=config.navidrome.ssh_host,
        user=config.navidrome.ssh_user,
        port=config.navidrome.ssh_port,
        password=config.navidrome.ssh_password,
    )


@router.get("/settings/navidrome/test")
async def settings_navidrome_test() -> dict[str, str | bool]:
    """Test connection to Navidrome — checks reachability and auth."""
    config = get_config()
    if config.navidrome is None:
        raise HTTPException(
            status_code=424,
            detail="Navidrome not configured — enter the URL, username, and password in Settings first",
        )
    if not config.navidrome.url:
        raise HTTPException(
            status_code=424,
            detail="Navidrome URL not set — enter it in Settings first",
        )
    return probe_navidrome_connection(
        url=config.navidrome.url,
        username=config.navidrome.username,
        password=config.navidrome.password,
    )


class ConfigUpdate(BaseModel):
    """Partial config update — only provided fields are updated."""
    source_dir: str | None = None
    dest_dir: str | None = None
    dest_host: str | None = None
    dest_user: str | None = None
    navidrome_url: str | None = None
    navidrome_username: str | None = None
    navidrome_password: str | None = None
    navidrome_music_folder: str | None = None
    navidrome_ssh_host: str | None = None
    navidrome_ssh_user: str | None = None
    navidrome_ssh_password: str | None = None
    navidrome_ssh_port: int | None = None


@router.put("/config")
async def update_config(update: ConfigUpdate) -> dict[str, Any]:
    """Update configuration values at runtime.

    Updates are persisted to config file and applied immediately.
    """
    import yaml as _yaml

    config = get_config()

    # Apply updates to the in-memory config
    if update.source_dir is not None:
        config.source_dir = Path(update.source_dir)
    if update.dest_dir is not None:
        config.dest_dir = Path(update.dest_dir)
    if update.dest_host is not None:
        config.dest_host = update.dest_host
    if update.dest_user is not None:
        config.dest_user = update.dest_user
    if any([update.navidrome_url, update.navidrome_username,
            update.navidrome_password, update.navidrome_music_folder,
            update.navidrome_ssh_host, update.navidrome_ssh_user,
            update.navidrome_ssh_password, update.navidrome_ssh_port]):
        if config.navidrome is None:
            config.navidrome = NavidromeConfig()
        assert config.navidrome is not None  # guaranteed after assignment
        if update.navidrome_url is not None:
            config.navidrome.url = update.navidrome_url
        if update.navidrome_username is not None:
            config.navidrome.username = update.navidrome_username
        if update.navidrome_password is not None:
            config.navidrome.password = update.navidrome_password
        if update.navidrome_music_folder is not None:
            config.navidrome.music_folder = update.navidrome_music_folder
        if update.navidrome_ssh_host is not None:
            config.navidrome.ssh_host = update.navidrome_ssh_host
        if update.navidrome_ssh_user is not None:
            config.navidrome.ssh_user = update.navidrome_ssh_user
        if update.navidrome_ssh_password is not None:
            config.navidrome.ssh_password = update.navidrome_ssh_password
        if update.navidrome_ssh_port is not None:
            config.navidrome.ssh_port = update.navidrome_ssh_port
        # Reset cached client so next request uses new config
        global _navidrome_client
        if _navidrome_client is not None:
            _navidrome_client.close()
            _navidrome_client = None

    # Persist to config file
    config_path = Path("~/.noctune/config.yaml").expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_data = config.model_dump(mode="json")
    with open(config_path, "w") as f:
        _yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

    return config.model_dump(mode="json")