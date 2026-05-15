"""Tests for Noctune CLI."""

import subprocess
import sys
import tempfile
from pathlib import Path


class TestCLIHelp:
    """CLI help and subcommand discovery."""

    def test_cli_no_args_shows_help(self) -> None:
        """Running noctune with no arguments shows help."""
        result = subprocess.run(
            [sys.executable, "-m", "noctune.cli"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Should exit 0 (help shown) or non-zero but with help in output
        assert "noctune" in result.stdout.lower() or "noctune" in result.stderr.lower()

    def test_cli_genres_lists_vocabulary(self) -> None:
        """noctune genres prints the vocabulary without needing a config file."""
        result = subprocess.run(
            [sys.executable, "-m", "noctune.cli", "genres"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "Rock" in result.stdout
        assert "Electronic" in result.stdout
        assert "Jazz" in result.stdout
        assert "Classical" in result.stdout

    def test_cli_genres_count(self) -> None:
        """noctune genres reports the genre count."""
        result = subprocess.run(
            [sys.executable, "-m", "noctune.cli", "genres"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "62 genres" in result.stdout


class TestCLIScan:
    """Scan subcommand with a temp directory and config."""

    def test_scan_empty_dir(self) -> None:
        """Scan on empty directory reports 0 discovered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            incoming = tmpdir_path / "incoming"
            incoming.mkdir()

            config_content = f"""source_dir: {incoming}
dest_host: localhost
dest_user: test
dest_dir: {tmpdir_path}/dest
llm:
  direction: local
"""
            config_path = tmpdir_path / "config.yaml"
            config_path.write_text(config_content)

            result = subprocess.run(
                [sys.executable, "-m", "noctune.cli", "--config", str(config_path), "scan"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0
            assert "0 files discovered" in result.stdout

    def test_scan_with_mp3(self) -> None:
        """Scan discovers MP3 files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            incoming = tmpdir_path / "incoming"
            incoming.mkdir()

            # Create a dummy MP3 file
            (incoming / "test.mp3").write_bytes(b"\xff\xfb\x90\x00" * 100)

            config_content = f"""source_dir: {incoming}
dest_host: localhost
dest_user: test
dest_dir: {tmpdir_path}/dest
llm:
  direction: local
"""
            config_path = tmpdir_path / "config.yaml"
            config_path.write_text(config_content)

            result = subprocess.run(
                [sys.executable, "-m", "noctune.cli", "--config", str(config_path), "scan"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0
            assert "1 files discovered" in result.stdout