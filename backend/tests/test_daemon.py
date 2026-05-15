"""Tests for the daemon module."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from noctune.daemon import DaemonManager, DaemonState


class TestDaemonState:
    """Tests for DaemonState enum."""

    def test_states_exist(self) -> None:
        assert DaemonState.STOPPED == "stopped"
        assert DaemonState.RUNNING == "running"
        assert DaemonState.PAUSED == "paused"


class TestDaemonManager:
    """Tests for DaemonManager — start/stop/pause lifecycle."""

    async def test_initial_state_is_stopped(self) -> None:
        manager = DaemonManager()
        assert manager.state == DaemonState.STOPPED

    async def test_start_transitions_to_running(self) -> None:
        manager = DaemonManager()
        await manager.start()
        assert manager.state == DaemonState.RUNNING
        await manager.stop()

    async def test_stop_transitions_to_stopped(self) -> None:
        manager = DaemonManager()
        await manager.start()
        await manager.stop()
        assert manager.state == DaemonState.STOPPED

    async def test_pause_transitions_to_paused(self) -> None:
        manager = DaemonManager()
        await manager.start()
        await manager.pause()
        assert manager.state == DaemonState.PAUSED
        await manager.stop()

    async def test_resume_transitions_to_running(self) -> None:
        manager = DaemonManager()
        await manager.start()
        await manager.pause()
        await manager.resume()
        assert manager.state == DaemonState.RUNNING
        await manager.stop()

    async def test_start_when_already_running_is_noop(self) -> None:
        manager = DaemonManager()
        await manager.start()
        await manager.start()  # Should not raise
        assert manager.state == DaemonState.RUNNING
        await manager.stop()

    async def test_stop_when_stopped_is_noop(self) -> None:
        manager = DaemonManager()
        await manager.stop()  # Should not raise
        assert manager.state == DaemonState.STOPPED

    async def test_pause_when_stopped_is_noop(self) -> None:
        manager = DaemonManager()
        await manager.pause()  # Should not raise
        assert manager.state == DaemonState.STOPPED

    async def test_processes_queued_files(self) -> None:
        """Verify the daemon actually processes files through the pipeline."""
        manager = DaemonManager()
        processed: list[str] = []

        async def mock_process(file_path: str) -> None:
            processed.append(file_path)

        manager._process_file = mock_process  # type: ignore[assignment]
        manager.add_file("/music/test.flac")

        await manager.start()
        # Give the event loop a moment to process
        await asyncio.sleep(0.1)
        await manager.stop()

        assert "/music/test.flac" in processed

    async def test_state_callback_fired(self) -> None:
        """Verify state change callbacks are fired."""
        transitions: list[tuple[DaemonState, DaemonState]] = []

        def on_state_change(old: DaemonState, new: DaemonState) -> None:
            transitions.append((old, new))

        manager = DaemonManager(on_state_change=on_state_change)
        await manager.start()
        await manager.stop()

        assert len(transitions) == 2
        assert transitions[0] == (DaemonState.STOPPED, DaemonState.RUNNING)
        assert transitions[1] == (DaemonState.RUNNING, DaemonState.STOPPED)