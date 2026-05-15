"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI

from noctune.api import router as api_router
from noctune.daemon import DaemonManager
from noctune.store import StateStore
from noctune.config_loader import load_config


def create_app(config_path: Path = Path("config.yaml")) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="Noctune", version="0.1.0")

    # Load config and initialize services
    config = load_config(config_path)
    store = StateStore(config.source_dir / ".noctune" / "state.db")
    store.initialize()
    daemon = DaemonManager(store=store, config=config)

    from noctune.api import set_store, set_config, set_daemon
    set_store(store)
    set_config(config)
    set_daemon(daemon)

    # Include API routes
    app.include_router(api_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Health check endpoint (root level)."""
        return {"status": "ok"}

    return app