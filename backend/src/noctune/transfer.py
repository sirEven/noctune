"""Transfer backends — rsync to remote server, local copy for testing.

Uses the Strategy pattern: swap between RsyncBackend (production) and
CopyBackend (testing) without changing any calling code.
"""

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class TransferBackend(Protocol):
    """Protocol for file transfer backends."""

    async def transfer(self, local_path: Path, remote_dir: Path) -> bool:
        """Transfer a file to the destination.

        Returns True on success, False on failure.
        """
        ...


class RsyncBackend:
    """Transfer files to a remote server via rsync over SSH.

    Uses incremental transfers — only changed blocks are sent.
    Preserves permissions, timestamps, and handles partial transfers.
    """

    def __init__(self, host: str, user: str = "eversin", port: int = 22) -> None:
        self.host = host
        self.user = user
        self.port = port

    async def transfer(self, local_path: Path, remote_dir: Path) -> bool:
        """Transfer a single file to the remote server.

        Uses rsync with archive, verbose, and compress flags.
        Creates the remote directory if it doesn't exist.
        """
        if not local_path.exists():
            logger.error("Source file does not exist: %s", local_path)
            return False

        remote_spec = f"{self.user}@{self.host}:{remote_dir}/"

        cmd = [
            "rsync",
            "-avz",          # archive, verbose, compress
            "--progress",
            "--mkpath",      # create remote directory if needed
            "-e", f"ssh -p {self.port}",
            str(local_path),
            remote_spec,
        ]

        logger.info("Transferring %s to %s", local_path.name, remote_spec)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info("Successfully transferred %s", local_path.name)
                return True
            else:
                logger.error("rsync failed for %s: %s", local_path.name, stderr.decode())
                return False

        except Exception:
            logger.exception("rsync exception for %s", local_path.name)
            return False


class CopyBackend:
    """Local copy backend — for testing and development.

    Simply copies files to a local directory instead of rsyncing to a remote server.
    """

    async def transfer(self, local_path: Path, remote_dir: Path) -> bool:
        """Copy a file to a local directory.

        Creates the destination directory if it doesn't exist.
        """
        if not local_path.exists():
            logger.error("Source file does not exist: %s", local_path)
            return False

        try:
            remote_dir.mkdir(parents=True, exist_ok=True)
            dest = remote_dir / local_path.name
            shutil.copy2(str(local_path), str(dest))
            logger.info("Copied %s to %s", local_path.name, dest)
            return True
        except Exception:
            logger.exception("Copy failed for %s", local_path.name)
            return False