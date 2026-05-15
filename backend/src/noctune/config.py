"""Application configuration loaded from environment and .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime settings — overridable via NOCTUNE_ prefixed env vars or .env file."""

    source_dir: Path = Path("~/Music/Incoming").expanduser()
    dest_dir: Path = Path("/data/music")
    db_path: Path = Path("~/.noctune/state.db").expanduser()
    config_path: Path = Path("~/.noctune/config.yaml").expanduser()
    debounce_seconds: float = 5.0
    confidence_threshold: float = 0.8

    model_config = {"env_prefix": "NOCTUNE_", "env_file": ".env"}