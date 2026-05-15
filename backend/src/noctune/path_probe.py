"""Path probing — suggest likely source and destination directories.

Probes the local filesystem and remote filesystem to suggest
likely source_dir, dest_dir, and Navidrome music folder paths.

No LLM needed — just filesystem checks and reading Navidrome's config.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# --- Local path suggestions ---

LOCAL_SOURCE_CANDIDATES = [
    Path("~/Music/Incoming"),
    Path("~/Music"),
    Path("~/Downloads"),
    Path("~/Music/Downloads"),
    Path("~/Desktop"),
]

LOCAL_DEST_CANDIDATES = [
    Path("~/Music/Processed"),
    Path("~/Music"),
]


def probe_local_paths() -> dict[str, list[dict[str, str | bool]]]:
    """Probe local filesystem for likely source directories.

    Returns a dict with 'source' and 'dest' keys, each containing
    a list of {path, exists, is_dir} candidates.
    """
    source_candidates = []
    for candidate in LOCAL_SOURCE_CANDIDATES:
        expanded = candidate.expanduser()
        source_candidates.append({
            "path": str(candidate),
            "expanded": str(expanded),
            "exists": expanded.exists(),
            "is_dir": expanded.is_dir() if expanded.exists() else False,
        })

    dest_candidates = []
    for candidate in LOCAL_DEST_CANDIDATES:
        expanded = candidate.expanduser()
        dest_candidates.append({
            "path": str(candidate),
            "expanded": str(expanded),
            "exists": expanded.exists(),
            "is_dir": expanded.is_dir() if expanded.exists() else False,
        })

    return {"source": source_candidates, "dest": dest_candidates}


# --- Remote path suggestions via SSH ---

REMOTE_MUSIC_CANDIDATES = [
    "/data/music",
    "/media/music",
    "/mnt/music",
    "/srv/music",
    "/home/music",
]

REMOTE_NAVIDROME_CONFIG_PATHS = [
    "/etc/navidrome/navidrome.toml",
    "/opt/navidrome/navidrome.toml",
    "/var/lib/navidrome/navidrome.toml",
]

# Navidrome Docker config mount paths
DOCKER_CONFIG_CANDIDATES = [
    "/config/navidrome.toml",
]


def _ssh_command(
    host: str, user: str, port: int, command: str,
    password: str = "", timeout: int = 10,
) -> tuple[int, str, str]:
    """Run a command on the remote host via SSH. Returns (returncode, stdout, stderr).

    If password is provided, uses sshpass. Otherwise assumes key-based auth.
    """
    ssh_opts = [
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=5",
        "-o", "BatchMode=yes",  # fail fast if key auth doesn't work
        "-p", str(port),
    ]

    if password:
        # Use sshpass for password-based auth
        result = subprocess.run(
            ["sshpass", "-p", password, "ssh", *ssh_opts, f"{user}@{host}", command],
            capture_output=True, text=True, timeout=timeout,
        )
    else:
        result = subprocess.run(
            ["ssh", *ssh_opts, f"{user}@{host}", command],
            capture_output=True, text=True, timeout=timeout,
        )

    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _ssh_available(host: str, user: str, port: int = 22, password: str = "") -> tuple[bool, str]:
    """Check if SSH connection is possible. Returns (ok, message)."""
    rc, stdout, stderr = _ssh_command(host, user, port, "echo ok", password=password, timeout=10)

    if rc == 0 and "ok" in stdout:
        return True, "SSH connection successful"

    # Decode common errors into friendly messages
    err_lower = stderr.lower()
    if "permission denied" in err_lower or "permission denied" in stdout.lower():
        if password:
            return False, f"SSH auth failed — wrong password for {user}@{host}"
        return False, f"SSH key auth failed for {user}@{host} — no matching key found. Add your public key to the remote machine, or set an SSH password in settings."
    if "connection refused" in err_lower:
        return False, f"Connection refused — SSH not running on {host}:{port}"
    if "connection timed out" in err_lower or "timed out" in err_lower:
        return False, f"Connection timed out — {host}:{port} unreachable. Is the machine online?"
    if "no route to host" in err_lower:
        return False, f"No route to host — {host} is unreachable. Check the IP/hostname."
    if "host key" in err_lower:
        return False, f"Host key verification failed — remove old key for {host} in ~/.ssh/known_hosts"
    if "could not resolve" in err_lower:
        return False, f"Could not resolve hostname — {host} not found"

    # Generic fallback
    detail = stderr.strip() or stdout.strip() or f"exit code {rc}"
    return False, f"SSH failed: {detail}"


def probe_remote_paths(
    host: str, user: str, port: int = 22, password: str = "",
) -> dict:
    """Probe the remote machine for likely Navidrome music folder and config.

    Checks:
    1. Common music directory paths for existence
    2. Navidrome config file for MusicFolder setting
    3. Docker container config mounts
    4. Docker inspect for volume mounts (if running in Docker)
    """
    # First check if SSH works at all
    ssh_ok, ssh_msg = _ssh_available(host, user, port, password)
    if not ssh_ok:
        return {
            "music_folder": [],
            "error": ssh_msg,
        }

    music_candidates = []

    # 1. Check common paths
    for path in REMOTE_MUSIC_CANDIDATES:
        rc, _, _ = _ssh_command(host, user, port, f"test -d {path} && echo yes", password=password)
        music_candidates.append({
            "path": path,
            "exists": rc == 0,
            "source": "common_path",
        })

    # 2. Check Navidrome config files for MusicFolder
    for config_path in REMOTE_NAVIDROME_CONFIG_PATHS:
        rc, stdout, _ = _ssh_command(host, user, port, f"cat {config_path} 2>/dev/null", password=password)
        if rc == 0 and "MusicFolder" in stdout:
            # Extract MusicFolder value
            for line in stdout.splitlines():
                line = line.strip()
                if line.startswith("MusicFolder") or line.startswith("MusicFolder ="):
                    value = line.split("=", 1)[-1].strip().strip('"').strip("'")
                    music_candidates.append({
                        "path": value,
                        "exists": True,  # if it's in config, it presumably exists
                        "source": "navidrome_config",
                    })

    # 3. Check Docker volume mounts for Navidrome container
    rc, stdout, _ = _ssh_command(
        host, user, port,
        "docker inspect navidrome 2>/dev/null | grep -A5 Binds || "
        "docker ps --filter name=navidrome --format '{{.ID}}' | head -1 | "
        "xargs -r docker inspect | grep -A5 Binds",
        password=password,
    )
    if rc == 0 and stdout:
        # Look for /data/music or similar paths in Docker binds
        for line in stdout.splitlines():
            line = line.strip().strip('"').strip(",")
            if "/" in line and ":" in line:
                # Docker bind: "/host/path:/container/path"
                host_path = line.split(":")[0].strip()
                if "music" in host_path.lower() or "data" in host_path.lower():
                    music_candidates.append({
                        "path": host_path,
                        "exists": True,
                        "source": "docker_bind",
                    })

    # 4. Check if Navidrome is running and get its actual data folder
    rc, stdout, _ = _ssh_command(
        host, user, port,
        "docker ps --filter name=navidrome --format '{{.ID}}'",
        password=password,
    )
    if rc == 0 and stdout.strip():
        # Found a running Navidrome container — check its env for ND_MUSICFOLDER
        container_id = stdout.strip().split()[0]
        rc2, stdout2, _ = _ssh_command(
            host, user, port,
            f"docker exec {container_id} env 2>/dev/null | grep ND_MUSICFOLDER || "
            f"docker exec {container_id} cat /data/navidrome.toml 2>/dev/null | grep MusicFolder",
            password=password,
        )
        if rc2 == 0 and stdout2.strip():
            for line in stdout2.splitlines():
                if "ND_MUSICFOLDER" in line:
                    value = line.split("=", 1)[-1].strip()
                    music_candidates.append({
                        "path": value,
                        "exists": True,
                        "source": "docker_env",
                    })
                elif "MusicFolder" in line:
                    value = line.split("=", 1)[-1].strip().strip('"').strip("'")
                    music_candidates.append({
                        "path": value,
                        "exists": True,
                        "source": "docker_config",
                    })

    return {"music_folder": music_candidates}


def probe_navidrome_connection(url: str, username: str, password: str) -> dict[str, str | bool]:
    """Test if Navidrome is reachable and auth works.

    Returns {reachable, auth_ok, version, error}.
    """
    import httpx

    if not url:
        return {"reachable": False, "auth_ok": False, "version": "", "error": "No Navidrome URL configured — enter the URL in settings first"}

    try:
        client = httpx.Client(timeout=10.0)
        # Use token auth
        import hashlib, os
        salt = os.urandom(8).hex()
        token = hashlib.md5((password + salt).encode()).hexdigest()
        params = {
            "u": username, "t": token, "s": salt,
            "v": "1.16.1", "c": "noctune", "f": "json",
        }
        resp = client.get(f"{url.rstrip('/')}/rest/ping.view", params=params)
        data = resp.json().get("subsonic-response", resp.json())
        status = data.get("status", "failed")

        if status == "ok":
            version = data.get("version", "unknown")
            client.close()
            return {"reachable": True, "auth_ok": True, "version": version, "error": ""}

        error = data.get("error", {}).get("message", "Unknown error")
        client.close()
        return {"reachable": True, "auth_ok": False, "version": "", "error": error}

    except httpx.ConnectError:
        return {"reachable": False, "auth_ok": False, "version": "", "error": f"Connection refused — is Navidrome running at {url}?"}
    except httpx.TimeoutException:
        return {"reachable": False, "auth_ok": False, "version": "", "error": f"Connection timeout — {url} didn't respond. Check the URL and that Navidrome is running"}
    except Exception as e:
        return {"reachable": False, "auth_ok": False, "version": "", "error": str(e)}