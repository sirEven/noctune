"""Navidrome Subsonic API client for browsing and deleting from the remote library.

Uses the Subsonic REST API (http://www.subsonic.org/pages/api.jsp)
to query Navidrome for library contents and trigger rescans.

Auth uses token-based authentication: token = md5(password + salt).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

import httpx

from noctune.models.config import NavidromeConfig


class SubsonicError(Exception):
    """Error from the Subsonic API."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"Subsonic error {code}: {message}")


class NavidromeClient:
    """Client for Navidrome's Subsonic-compatible REST API.

    Provides library browsing, search, and scan triggering.
    Combined with SSH for file deletion on the remote server.
    """

    API_VERSION = "1.16.1"
    CLIENT_NAME = "noctune"

    def __init__(self, config: NavidromeConfig) -> None:
        self._config = config
        self._base_url = config.url.rstrip("/")
        self._client = httpx.Client(timeout=30.0)

    def _auth_params(self) -> dict[str, str]:
        """Generate token auth parameters (md5(password + salt))."""
        salt = os.urandom(8).hex()
        token = hashlib.md5(
            (self._config.password + salt).encode()
        ).hexdigest()
        return {
            "u": self._config.username,
            "t": token,
            "s": salt,
            "v": self.API_VERSION,
            "c": self.CLIENT_NAME,
        }

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call a Subsonic REST endpoint and return the JSON response."""
        url = f"{self._base_url}/rest/{endpoint}"
        all_params = {**self._auth_params(), "f": "json"}
        if params:
            all_params.update(params)
        resp = self._client.get(url, params=all_params)
        resp.raise_for_status()
        data = resp.json()
        subsonic = data.get("subsonic-response", data)
        status = subsonic.get("status", "failed")
        if status == "failed":
            error = subsonic.get("error", {})
            raise SubsonicError(
                error.get("code", -1),
                error.get("message", "Unknown error"),
            )
        return subsonic

    # --- Browsing ---

    def search(self, query: str, song_count: int = 20, album_count: int = 10, artist_count: int = 5) -> dict[str, Any]:
        """Search the library. Returns searchResult3 with artists, albums, songs."""
        return self._get("search3.view", {
            "query": query,
            "artistCount": artist_count,
            "albumCount": album_count,
            "songCount": song_count,
        })

    def get_artists(self) -> dict[str, Any]:
        """List all artists (ID3 organized)."""
        return self._get("getArtists.view")

    def get_artist(self, artist_id: str) -> dict[str, Any]:
        """Get artist details + album list."""
        return self._get("getArtist.view", {"id": artist_id})

    def get_album(self, album_id: str) -> dict[str, Any]:
        """Get album details + song list. Songs include 'path' field."""
        return self._get("getAlbum.view", {"id": album_id})

    def get_song(self, song_id: str) -> dict[str, Any]:
        """Get a single song by ID. Includes 'path' field."""
        return self._get("getSong.view", {"id": song_id})

    def get_album_list(self, ltype: str = "alphabeticalByName", offset: int = 0, size: int = 50) -> dict[str, Any]:
        """List albums by type (newest, alphabetialByName, etc.)."""
        return self._get("getAlbumList2.view", {
            "type": ltype,
            "offset": offset,
            "size": size,
        })

    # --- Scanning ---

    def start_scan(self) -> dict[str, Any]:
        """Trigger a library rescan."""
        return self._get("startScan.view")

    def get_scan_status(self) -> dict[str, Any]:
        """Check scan status."""
        return self._get("getScanStatus.view")

    def wait_for_scan(self, timeout: float = 60.0, interval: float = 2.0) -> bool:
        """Poll scan status until scanning is complete. Returns True if finished."""
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self.get_scan_status()
            scanning = result.get("scanStatus", {}).get("scanning", False)
            if not scanning:
                return True
            time.sleep(interval)
        return False

    # --- File operations via SSH ---

    def resolve_remote_path(self, relative_path: str) -> str:
        """Convert a Navidrome relative path to an absolute path on the Pi."""
        return str(Path(self._config.music_folder) / relative_path)

    def delete_remote_file(self, relative_path: str) -> bool:
        """Delete a file on the remote server via SSH.

        Args:
            relative_path: Path relative to Navidrome's music folder root.

        Returns:
            True if deletion succeeded.
        """
        abs_path = self.resolve_remote_path(relative_path)
        result = subprocess.run(
            [
                "ssh",
                "-o", "StrictHostKeyChecking=accept-new",
                "-p", str(self._config.ssh_port),
                f"{self._config.ssh_user}@{self._config.ssh_host}",
                "rm", "--", abs_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"SSH delete failed: {result.stderr}")
        return True

    def delete_remote_directory(self, relative_path: str) -> bool:
        """Delete a directory (e.g. an entire album) on the remote server via SSH.

        Args:
            relative_path: Path relative to Navidrome's music folder root.

        Returns:
            True if deletion succeeded.
        """
        abs_path = self.resolve_remote_path(relative_path)
        result = subprocess.run(
            [
                "ssh",
                "-o", "StrictHostKeyChecking=accept-new",
                "-p", str(self._config.ssh_port),
                f"{self._config.ssh_user}@{self._config.ssh_host}",
                "rm", "-rf", "--", abs_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"SSH delete directory failed: {result.stderr}")
        return True

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()