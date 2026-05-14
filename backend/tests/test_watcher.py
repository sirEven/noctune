"""Tests for the file watcher with debounce."""

import asyncio
from pathlib import Path

from noctune.watcher import DebouncedWatcher
from noctune.models.config import NoctuneConfig


class TestDebouncedWatcher:
    """Tests for DebouncedWatcher debounce logic."""

    async def test_single_event_emits_after_debounce(self) -> None:
        watcher = DebouncedWatcher(debounce_seconds=0.05)
        stable_paths: list[Path] = []
        watcher.on_stable(lambda p: stable_paths.append(p))

        watcher._handle_event("/music/test.flac", "created")
        await asyncio.sleep(0.15)

        assert len(stable_paths) == 1
        assert stable_paths[0] == Path("/music/test.flac")

    async def test_rapid_events_emit_once(self) -> None:
        watcher = DebouncedWatcher(debounce_seconds=0.05)
        stable_paths: list[Path] = []
        watcher.on_stable(lambda p: stable_paths.append(p))

        for _ in range(5):
            watcher._handle_event("/music/test.flac", "modified")
            await asyncio.sleep(0.01)

        await asyncio.sleep(0.15)

        assert len(stable_paths) == 1
        assert stable_paths[0] == Path("/music/test.flac")

    async def test_different_files_tracked_separately(self) -> None:
        watcher = DebouncedWatcher(debounce_seconds=0.05)
        stable_paths: list[Path] = []
        watcher.on_stable(lambda p: stable_paths.append(p))

        watcher._handle_event("/music/a.flac", "created")
        watcher._handle_event("/music/b.flac", "created")
        await asyncio.sleep(0.15)

        assert len(stable_paths) == 2
        paths = {str(p) for p in stable_paths}
        assert "/music/a.flac" in paths
        assert "/music/b.flac" in paths

    async def test_callback_receives_correct_path(self) -> None:
        watcher = DebouncedWatcher(debounce_seconds=0.05)
        results: list[str] = []
        watcher.on_stable(lambda p: results.append(f"stable:{p}"))

        watcher._handle_event("/music/album/01 - Track.flac", "created")
        await asyncio.sleep(0.15)

        assert len(results) == 1
        assert "01 - Track.flac" in results[0]

    async def test_debounce_timer_resets_on_new_event(self) -> None:
        watcher = DebouncedWatcher(debounce_seconds=0.1)
        stable_paths: list[Path] = []
        watcher.on_stable(lambda p: stable_paths.append(p))

        watcher._handle_event("/music/test.flac", "created")
        await asyncio.sleep(0.05)  # Not enough time
        watcher._handle_event("/music/test.flac", "modified")  # Resets timer
        await asyncio.sleep(0.05)  # Not enough time again

        assert len(stable_paths) == 0  # Should not have fired yet

        await asyncio.sleep(0.1)  # Now enough time after reset
        assert len(stable_paths) == 1