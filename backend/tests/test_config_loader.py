"""Tests for YAML config loading."""

import tempfile
from pathlib import Path

from noctune.config_loader import load_config


class TestLoadConfig:
    """Tests for YAML config loading."""

    def test_load_full_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text("""
source_dir: ~/Music/Incoming
dest_dir: /data/music
remote:
  host: 192.168.178.107
  port: 22
  user: eversin
  password: ""
valid_extensions: [.mp3, .flac, .m4a, .ogg]
genre_vocabulary:
  - Rock
  - Pop
  - Electronic
  - Jazz
  - Hip Hop
llm:
  direction: local
  local_base_url: http://localhost:11434
  local_model: llama3:8b
  batch_size: 20
confidence_threshold: 0.8
debounce_seconds: 5.0
""")
            config = load_config(config_path)
            assert config.source_dir == Path("~/Music/Incoming").expanduser()
            assert config.remote.host == "192.168.178.107"
            assert config.remote.user == "eversin"
            assert config.remote.port == 22
            assert config.dest_dir == Path("/data/music")
            assert len(config.genre_vocabulary) == 5
            assert config.genre_vocabulary[2] == "Electronic"
            assert config.llm.direction == "local"
            assert config.llm.local_model == "llama3:8b"
            assert config.llm.batch_size == 20
            assert config.confidence_threshold == 0.8

    def test_load_minimal_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text("""
source_dir: ~/Music/Incoming
""")
            config = load_config(config_path)
            assert config.source_dir == Path("~/Music/Incoming").expanduser()
            assert config.remote.host == "192.168.178.107"
            assert config.dest_dir == Path("/data/music")
            assert config.llm.direction == "local"
            assert config.confidence_threshold == 0.8

    def test_genre_vocabulary_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text("""
source_dir: ~/Music/Incoming
genre_vocabulary:
  - Ambient
  - Classical
  - Folk
""")
            config = load_config(config_path)
            assert len(config.genre_vocabulary) == 3
            assert config.genre_vocabulary[0] == "Ambient"

    def test_llm_cloud_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text("""
source_dir: ~/Music/Incoming
llm:
  direction: cloud
  cloud_base_url: https://api.ollama.com/v1
  cloud_model: llama3:70b
  fallback: local
""")
            config = load_config(config_path)
            assert config.llm.direction == "cloud"
            assert config.llm.cloud_model == "llama3:70b"
            assert config.llm.fallback == "local"

    def test_load_legacy_dest_host_user(self) -> None:
        """Legacy dest_host/dest_user keys should be migrated to remote config."""
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text("""
source_dir: ~/Music/Incoming
dest_host: myserver.local
dest_user: myuser
dest_dir: /data/music
""")
            config = load_config(config_path)
            assert config.source_dir == Path("~/Music/Incoming").expanduser()
            assert config.remote.host == "myserver.local"
            assert config.remote.user == "myuser"
            assert config.dest_dir == Path("/data/music")

    def test_load_navidrome_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.yaml"
            config_path.write_text("""
source_dir: ~/Music/Incoming
navidrome:
  url: http://192.168.178.107:4533
  username: admin
  password: secret
  music_folder: /data/music
""")
            config = load_config(config_path)
            assert config.navidrome is not None
            assert config.navidrome.url == "http://192.168.178.107:4533"
            assert config.navidrome.username == "admin"
            assert config.navidrome.password == "secret"
            assert config.navidrome.music_folder == "/data/music"