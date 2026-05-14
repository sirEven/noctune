"""Test configuration and fixtures."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir() -> Path:
    """Provide a temporary directory for test databases and files."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)