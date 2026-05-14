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
dest_host: 192.168.178.107
dest_user: eversin
dest_dir: /data/music
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
            assert config.dest_host == "192.168.178.107"
            assert config.dest_user == "eversin"
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
            assert config.dest_host == "192.168.178.107"
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