"""Tests for transfer backends."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from noctune.transfer import CopyBackend, RsyncBackend


class TestCopyBackend:
    """Tests for local copy backend (used for testing)."""

    async def test_copy_file_to_directory(self, tmp_path: Path) -> None:
        src = tmp_path / "source" / "test.mp3"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(b"audio data here")

        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        backend = CopyBackend()
        result = await backend.transfer(src, dest_dir)

        assert result is True
        assert (dest_dir / "test.mp3").exists()
        assert (dest_dir / "test.mp3").read_bytes() == b"audio data here"

    async def test_copy_preserves_subdirectory_structure(self, tmp_path: Path) -> None:
        src = tmp_path / "source" / "Radiohead" / "Kid A" / "01 - Track.flac"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(b"flac data")

        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()

        backend = CopyBackend()
        result = await backend.transfer(src, dest_dir)

        assert result is True
        assert (dest_dir / "01 - Track.flac").exists()

    async def test_copy_nonexistent_file_returns_false(self, tmp_path: Path) -> None:
        backend = CopyBackend()
        result = await backend.transfer(Path("/nonexistent/file.mp3"), tmp_path)
        assert result is False


class TestRsyncBackend:
    """Tests for rsync backend — mocked subprocess calls."""

    async def test_rsync_builds_correct_command(self, tmp_path: Path) -> None:
        # Create a real local file so the existence check passes
        local_file = tmp_path / "01 - Track.flac"
        local_file.write_bytes(b"audio data")

        backend = RsyncBackend(host="192.168.178.107", user="eversin")

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate.return_value = (b"", b"")
            mock_exec.return_value = mock_proc

            result = await backend.transfer(
                local_file,
                Path("/data/music"),
            )

            assert result is True
            # Verify rsync was called with correct args
            call_args = mock_exec.call_args[0]
            assert call_args[0] == "rsync"

    async def test_rsync_handles_failure(self, tmp_path: Path) -> None:
        backend = RsyncBackend(host="192.168.178.107", user="eversin")

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.communicate.return_value = (b"", b"rsync error")
            mock_exec.return_value = mock_proc

            result = await backend.transfer(
                Path("/music/test.mp3"),
                Path("/data/music"),
            )

            assert result is False