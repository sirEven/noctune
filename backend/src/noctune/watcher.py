"""File watcher with async debounce for stable file detection.

Watches a directory for music file events. When a file appears or changes,
waits for the debounce period to expire before considering it stable and
ready for pipeline processing.
"""

import asyncio
import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# Audio file extensions Noctune processes
VALID_EXTENSIONS: frozenset[str] = frozenset(
    {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac", ".wma", ".opus", ".alac"}
)


class DebouncedWatcher:
    """Debounced file watcher — collects rapid filesystem events and
    emits stable file paths only after a configurable quiet period.

    Uses asyncio timers (not threads) so it integrates cleanly with
    the FastAPI event loop.
    """

    def __init__(self, debounce_seconds: float = 5.0) -> None:
        self.debounce_seconds = debounce_seconds
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self._callbacks: list[Callable[[Path], None]] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def on_stable(self, callback: Callable[[Path], None]) -> None:
        """Register a callback to fire when a file path is deemed stable."""
        self._callbacks.append(callback)

    def _handle_event(self, src_path: str, event_type: str) -> None:
        """Handle a filesystem event — reset the debounce timer for this path.

        Called by the watchdog observer or directly in tests.
        """
        path = Path(src_path)

        # Only process audio files
        if path.suffix.lower() not in VALID_EXTENSIONS:
            return

        logger.debug("File event: %s on %s", event_type, src_path)

        # Cancel existing timer for this path if any
        key = str(path)
        if key in self._timers:
            self._timers[key].cancel()

        # Schedule a new timer
        loop = self._loop or asyncio.get_event_loop()
        handle = loop.call_later(
            self.debounce_seconds,
            self._emit_stable,
            path,
        )
        self._timers[key] = handle

    def _emit_stable(self, path: Path) -> None:
        """Emit a stable event for a path — called when the debounce timer expires."""
        key = str(path)
        self._timers.pop(key, None)

        logger.info("File stable: %s", path)
        for callback in self._callbacks:
            callback(path)

    async def start(self, watch_dir: Path) -> None:
        """Start watching a directory for file changes.

        Uses watchdog's async observer to detect file creation and modification
        events, then debounces them before emitting stable paths.
        """
        self._loop = asyncio.get_event_loop()

        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEvent, FileSystemEventHandler

            class Handler(FileSystemEventHandler):
                def __init__(self, watcher: DebouncedWatcher) -> None:
                    self.watcher = watcher

                def on_created(self, event: FileSystemEvent) -> None:
                    self.watcher._handle_event(event.src_path, "created")  # noqa: SLF001

                def on_modified(self, event: FileSystemEvent) -> None:
                    self.watcher._handle_event(event.src_path, "modified")  # noqa: SLF001

            handler = Handler(self)
            observer = Observer()
            observer.schedule(handler, str(watch_dir), recursive=True)
            observer.start()

            logger.info("Watching %s (debounce: %.1fs)", watch_dir, self.debounce_seconds)

            # Keep running until cancelled
            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                observer.stop()
                observer.join()
                raise

        except ImportError:
            logger.warning("watchdog not installed — file watching disabled")
            raise