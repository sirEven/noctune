"""Tests for Navidrome Subsonic API client."""

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from noctune.navidrome import NavidromeClient, SubsonicError
from noctune.models.config import NavidromeConfig


@pytest.fixture
def nav_config() -> NavidromeConfig:
    """Test Navidrome config."""
    return NavidromeConfig(
        url="http://navidrome.test:4533",
        username="testuser",
        password="testpass",
        music_folder="/data/music",
        ssh_host="192.168.1.100",
        ssh_user="testuser",
        ssh_port=22,
    )


@pytest.fixture
def client(nav_config: NavidromeConfig) -> NavidromeClient:
    """Create a NavidromeClient with test config."""
    return NavidromeClient(nav_config)


class TestAuthParams:
    """Token-based auth parameter generation."""

    def test_auth_params_contain_required_fields(self, client: NavidromeClient) -> None:
        params = client._auth_params()
        assert "u" in params
        assert "t" in params
        assert "s" in params
        assert "v" in params
        assert "c" in params
        assert params["u"] == "testuser"
        assert params["v"] == "1.16.1"
        assert params["c"] == "noctune"

    def test_auth_token_is_md5_password_salt(self, client: NavidromeClient) -> None:
        params = client._auth_params()
        expected_token = hashlib.md5(("testpass" + params["s"]).encode()).hexdigest()
        assert params["t"] == expected_token

    def test_auth_salt_is_random_hex(self, client: NavidromeClient) -> None:
        """Each call generates a different salt."""
        params1 = client._auth_params()
        params2 = client._auth_params()
        assert params1["s"] != params2["s"]


class TestSubsonicCalls:
    """Subsonic API endpoint calls with mocked HTTP responses."""

    def test_search_calls_correct_endpoint(self, client: NavidromeClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "subsonic-response": {"status": "ok", "searchResult3": {"song": []}}
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "get", return_value=mock_response) as mock_get:
            result = client.search("radiohead")
            mock_get.assert_called_once()
            call_url = mock_get.call_args[0][0]
            assert "/rest/search3.view" in call_url

    def test_get_album_calls_correct_endpoint(self, client: NavidromeClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "subsonic-response": {"status": "ok", "album": {"id": "al-1", "name": "OK Computer"}}
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "get", return_value=mock_response) as mock_get:
            result = client.get_album("al-1")
            call_url = mock_get.call_args[0][0]
            assert "/rest/getAlbum.view" in call_url

    def test_start_scan_calls_correct_endpoint(self, client: NavidromeClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "subsonic-response": {"status": "ok", "scanStatus": {"scanning": True}}
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "get", return_value=mock_response) as mock_get:
            result = client.start_scan()
            call_url = mock_get.call_args[0][0]
            assert "/rest/startScan.view" in call_url

    def test_api_error_raises_subsonic_error(self, client: NavidromeClient) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "subsonic-response": {
                "status": "failed",
                "error": {"code": 40, "message": "Wrong username or password"},
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._client, "get", return_value=mock_response):
            with pytest.raises(SubsonicError) as exc_info:
                client.search("test")
            assert exc_info.value.code == 40
            assert "Wrong username" in exc_info.value.message


class TestPathResolution:
    """Remote path resolution."""

    def test_resolve_relative_path(self, client: NavidromeClient) -> None:
        abs_path = client.resolve_remote_path("Radiohead/OK Computer/01 - Airbag.flac")
        assert abs_path == "/data/music/Radiohead/OK Computer/01 - Airbag.flac"

    def test_resolve_path_with_special_chars(self, client: NavidromeClient) -> None:
        abs_path = client.resolve_remote_path("AC⏺DC/Back in Black/01 - Thunderstruck.flac")
        assert abs_path == "/data/music/AC⏺DC/Back in Black/01 - Thunderstruck.flac"


class TestRemoteDeletion:
    """SSH-based file and directory deletion."""

    def test_delete_file_calls_ssh_rm(self, client: NavidromeClient) -> None:
        with patch("noctune.navidrome.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            result = client.delete_remote_file("Artist/Album/track.flac")
            assert result is True
            call_args = mock_run.call_args[0][0]
            assert "rm" in call_args
            assert "/data/music/Artist/Album/track.flac" in call_args
            assert any("192.168.1.100" in arg for arg in call_args)

    def test_delete_directory_calls_ssh_rm_rf(self, client: NavidromeClient) -> None:
        with patch("noctune.navidrome.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            result = client.delete_remote_directory("Artist/Album")
            assert result is True
            call_args = mock_run.call_args[0][0]
            assert "rm" in call_args
            assert "-rf" in call_args
            assert "/data/music/Artist/Album" in call_args

    def test_delete_file_failure_raises_runtime_error(self, client: NavidromeClient) -> None:
        with patch("noctune.navidrome.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="Permission denied")
            with pytest.raises(RuntimeError, match="SSH delete failed"):
                client.delete_remote_file("Artist/Album/track.flac")

    def test_delete_file_includes_strict_host_checking(self, client: NavidromeClient) -> None:
        with patch("noctune.navidrome.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            client.delete_remote_file("test.flac")
            call_args = mock_run.call_args[0][0]
            assert "-o" in call_args
            assert "StrictHostKeyChecking=accept-new" in call_args


class TestClose:
    """Client cleanup."""

    def test_close_closes_http_client(self, client: NavidromeClient) -> None:
        with patch.object(client._client, "close") as mock_close:
            client.close()
            mock_close.assert_called_once()