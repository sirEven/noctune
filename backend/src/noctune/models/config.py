"""Configuration models."""

from pathlib import Path

from pydantic import BaseModel

from noctune.genres import GENRE_VOCABULARY

class RemoteConfig(BaseModel):
    """SSH connection to the remote machine running Navidrome.

    Single source of truth — used for rsync, SSH commands, and path probing.
    """

    host: str = "192.168.178.107"
    port: int = 22
    user: str = "eversin"
    password: str = ""  # empty = key-based auth only


class NavidromeConfig(BaseModel):
    """Navidrome Subsonic API configuration for library browsing and deletion."""

    url: str = "http://192.168.178.107:4533"
    username: str = "eversin"
    password: str = ""
    music_folder: str = "/data/music"


class LLMConfig(BaseModel):
    """LLM routing configuration — local Ollama, cloud, or any OpenAI-compatible endpoint."""

    direction: str = "local"
    local_base_url: str = "http://localhost:11434"
    local_model: str = "llama3:8b"
    cloud_base_url: str = "https://api.ollama.com/v1"
    cloud_api_key: str = ""
    cloud_model: str = "llama3:70b"
    fallback: str = "cloud"
    batch_size: int = 20


class NoctuneConfig(BaseModel):
    """Root configuration for Noctune."""

    source_dir: Path
    dest_dir: Path = Path("/data/music")
    remote: RemoteConfig = RemoteConfig()
    valid_extensions: list[str] = [".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac"]
    genre_vocabulary: list[str] = list(GENRE_VOCABULARY)
    llm: LLMConfig = LLMConfig()
    confidence_threshold: float = 0.8
    debounce_seconds: float = 5.0
    navidrome: NavidromeConfig | None = None