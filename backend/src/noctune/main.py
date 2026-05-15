"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI

from noctune.api import router as api_router
from noctune.daemon import DaemonManager
from noctune.store import StateStore
from noctune.config_loader import load_config

app = FastAPI(title="Noctune", version="0.1.0")

# Module-level singleton instances
_store: StateStore | None = None
_daemon: DaemonManager | None = None


def initialize_app(config_path: str = "config.yaml") -> None:
    """Initialize store, config, and daemon at startup."""
    global _store, _daemon
    config = load_config(Path(config_path))
    store = StateStore(config.source_dir / ".noctune" / "state.db")
    store.initialize()
    daemon = DaemonManager(store=store, config=config)

    from noctune.api import set_store, set_config, set_daemon
    set_store(store)
    set_config(config)
    set_daemon(daemon)

    _store = store
    _daemon = daemon


# Include API routes
app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint (root level)."""
    return {"status": "ok"}