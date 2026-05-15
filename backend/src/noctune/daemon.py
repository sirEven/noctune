"""Daemon manager — persistent background processing that survives browser close.

Architecture:
- DaemonManager runs inside the FastAPI process as an asyncio background task.
- When toggled ON from UI, it starts polling the StateStore for DISCOVERED files
  and processes them through the pipeline.
- When toggled OFF or PAUSED, it stops processing but the daemon task remains.
- OS notifications (desktop-notifier) fire when files enter QUEUED_FOR_REVIEW.
- Clicking the notification opens the browser to /review.

The daemon is NOT a separate process — it's an in-process asyncio task.
This is simpler, more reliable, and the FastAPI server already persists
independently of the browser. If the user wants true system-level persistence,
they can run the whole app as a systemd user unit.
"""

import asyncio
import logging
import webbrowser
from enum import StrEnum
from pathlib import Path
from typing import Callable

from noctune.config_loader import load_config
from noctune.llm_router import LLMRouter
from noctune.models.config import NoctuneConfig
from noctune.models.pipeline import FileState, PipelineStatus
from noctune.models.track import TagSet
from noctune.store import StateStore

logger = logging.getLogger(__name__)


class DaemonState(StrEnum):
    """Daemon state — controlled via UI toggle."""

    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class DaemonManager:
    """Manages the background daemon that processes files through the pipeline.

    Usage:
        manager = DaemonManager(store=store, config=config)
        await manager.start()   # Start processing
        await manager.pause()   # Pause processing (files queue up)
        await manager.resume()   # Resume from pause
        await manager.stop()    # Stop completely

    State transitions:
        STOPPED → RUNNING (start)
        RUNNING → PAUSED (pause)
        PAUSED → RUNNING (resume)
        RUNNING → STOPPED (stop)
        PAUSED → STOPPED (stop)
    """

    def __init__(
        self,
        store: StateStore | None = None,
        config: NoctuneConfig | None = None,
        on_state_change: Callable[[DaemonState, DaemonState], None] | None = None,
        notify: bool = True,
    ) -> None:
        self.state = DaemonState.STOPPED
        self._task: asyncio.Task | None = None
        self._store = store
        self._config = config
        self._notify = notify
        self._on_state_change = on_state_change
        self._file_queue: asyncio.Queue[str] = asyncio.Queue()
        self._poll_interval = 5.0  # seconds between polls

    def _transition(self, new_state: DaemonState) -> None:
        """Transition state and fire callback."""
        old_state = self.state
        self.state = new_state
        logger.info("Daemon state: %s → %s", old_state.value, new_state.value)
        if self._on_state_change:
            self._on_state_change(old_state, new_state)

    async def start(self) -> None:
        """Start the daemon — begin processing files."""
        if self.state == DaemonState.RUNNING:
            return
        self._transition(DaemonState.RUNNING)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop(), name="noctune-daemon")
        logger.info("Daemon started")

    async def stop(self) -> None:
        """Stop the daemon completely."""
        if self.state == DaemonState.STOPPED:
            return
        self._transition(DaemonState.STOPPED)
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Daemon stopped")

    async def pause(self) -> None:
        """Pause processing — files are queued but not processed."""
        if self.state == DaemonState.STOPPED:
            return  # Can't pause from stopped
        self._transition(DaemonState.PAUSED)
        logger.info("Daemon paused")

    async def resume(self) -> None:
        """Resume from paused state."""
        if self.state != DaemonState.PAUSED:
            return
        self._transition(DaemonState.RUNNING)
        logger.info("Daemon resumed")

    def add_file(self, file_path: str) -> None:
        """Add a file to the processing queue."""
        self._file_queue.put_nowait(file_path)
        logger.debug("Queued file: %s", file_path)

    async def _run_loop(self) -> None:
        """Main processing loop — polls store and processes files."""
        logger.info("Daemon run loop started")
        try:
            while self.state != DaemonState.STOPPED:
                if self.state == DaemonState.PAUSED:
                    await asyncio.sleep(1.0)
                    continue

                # Process any queued files first
                while not self._file_queue.empty():
                    try:
                        file_path = self._file_queue.get_nowait()
                        await self._process_file(file_path)
                    except asyncio.QueueEmpty:
                        break

                # Poll for discovered files if store is available
                if self._store:
                    discovered = self._store.list_by_state(FileState.DISCOVERED)
                    stable = self._store.list_by_state(FileState.STABLE)
                    pending = discovered + stable
                    for status in pending:
                        await self._process_file(status.file_path)

                # Poll for review items and notify
                if self._store and self._notify:
                    queued = self._store.list_by_state(FileState.QUEUED_FOR_REVIEW)
                    if queued:
                        await self._notify_review(queued)

                await asyncio.sleep(self._poll_interval)

        except asyncio.CancelledError:
            logger.info("Daemon run loop cancelled")
            raise

    async def _process_file(self, file_path: str) -> None:
        """Process a single file through the pipeline.

        This is the hook that connects to the Pipeline class.
        In production, it delegates to Pipeline.process().
        For now, it just logs — the full integration will come when
        Pipeline is wired up to the daemon.
        """
        if not self._store or not self._config:
            logger.warning("No store/config configured, skipping file: %s", file_path)
            return

        try:
            logger.info("Processing: %s", file_path)
            # TODO: Wire up Pipeline.process() here
            # For now, just mark as STABLE (debounce check passed)
            status = self._store.get(file_path)
            if status and status.state == FileState.DISCOVERED:
                self._store.upsert(PipelineStatus(
                    file_path=file_path,
                    state=FileState.STABLE,
                ))
        except Exception:
            logger.exception("Failed to process file: %s", file_path)

    async def _notify_review(self, queued: list[PipelineStatus]) -> None:
        """Send a desktop notification for files needing review."""
        count = len(queued)
        if count == 0:
            return

        try:
            from desktop_notifier import Button, DesktopNotifier, Urgency

            notifier = DesktopNotifier("Noctune")

            message = (
                f"{count} file needs your approval"
                if count == 1
                else f"{count} files need your approval"
            )

            def open_review() -> None:
                """Open browser to the review page."""
                webbrowser.open("http://localhost:8000/review")

            await notifier.send(
                title="Noctune — Review Needed",
                message=f"{message} before tagging",
                urgency=Urgency.Critical,
                buttons=[Button(title="Review Now", on_pressed=open_review)],
                on_clicked=open_review,
            )
            logger.info("Notification sent: %d files in review queue", count)

        except Exception:
            # Notification failures should never break the daemon
            logger.warning("Desktop notification failed (non-critical)")

    @property
    def is_running(self) -> bool:
        return self.state == DaemonState.RUNNING

    @property
    def is_paused(self) -> bool:
        return self.state == DaemonState.PAUSED