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

# Human-readable labels for source types
SOURCE_LABELS = {
    "docker_env": "Docker env var (ND_MUSICFOLDER) — the path Navidrome actually uses",
    "docker_config": "Docker config file — Navidrome's own MusicFolder setting",
    "navidrome_config": "Navidrome config file — MusicFolder setting",
    "docker_bind": "Docker volume mount — host path bound into the container",
    "common_path": "Common path — exists on disk but not verified as Navidrome's",
}

# Source priority: earlier = more authoritative
SOURCE_PRIORITY = {
    "docker_env": 0,
    "navidrome_config": 1,
    "docker_config": 1,
    "docker_bind": 2,
    "common_path": 3,
}

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
    1. Docker env var ND_MUSICFOLDER (most authoritative)
    2. Navidrome config file MusicFolder setting
    3. Docker volume mounts for music-related binds
    4. Common music directory paths

    Returns candidates with 'source', 'label', and 'recommended' fields.
    The 'recommended' flag marks the best choice based on source priority.
    """
    # First check if SSH works at all
    ssh_ok, ssh_msg = _ssh_available(host, user, port, password)
    if not ssh_ok:
        return {
            "music_folder": [],
            "error": ssh_msg,
        }

    music_candidates: list[dict] = []
    seen_paths: set[str] = set()
    best_source_priority = 99  # track best found so far

    def add_candidate(path: str, source: str, exists: bool = True) -> None:
        """Add a candidate, deduplicating by path. Keep the one with better source priority."""
        nonlocal best_source_priority
        if path in seen_paths:
            # Already seen — check if this source has higher priority
            for c in music_candidates:
                if c["path"] == path:
                    if SOURCE_PRIORITY.get(source, 99) < SOURCE_PRIORITY.get(c["source"], 99):
                        c["source"] = source
                        c["label"] = SOURCE_LABELS.get(source, source)
                    break
            return
        seen_paths.add(path)
        is_recommended = SOURCE_PRIORITY.get(source, 99) < best_source_priority
        if is_recommended:
            # Demote previous recommendations
            for c in music_candidates:
                c["recommended"] = False
            best_source_priority = SOURCE_PRIORITY.get(source, 99)
        music_candidates.append({
            "path": path,
            "exists": exists,
            "source": source,
            "label": SOURCE_LABELS.get(source, source),
            "recommended": is_recommended,
        })

    # 1. Check if Navidrome is running in Docker — get ND_MUSICFOLDER env var
    rc, stdout, _ = _ssh_command(
        host, user, port,
        "docker ps --filter name=navidrome --format '{{.ID}}'",
        password=password,
    )
    container_id = ""
    if rc == 0 and stdout.strip():
        container_id = stdout.strip().split()[0]

        # ND_MUSICFOLDER env var — most authoritative
        rc2, stdout2, _ = _ssh_command(
            host, user, port,
            f"docker exec {container_id} env 2>/dev/null | grep ND_MUSICFOLDER",
            password=password,
        )
        if rc2 == 0 and stdout2.strip():
            for line in stdout2.splitlines():
                if "ND_MUSICFOLDER" in line:
                    value = line.split("=", 1)[-1].strip()
                    add_candidate(value, "docker_env")

        # Config file inside container
        rc3, stdout3, _ = _ssh_command(
            host, user, port,
            f"docker exec {container_id} cat /data/navidrome.toml 2>/dev/null | grep MusicFolder",
            password=password,
        )
        if rc3 == 0 and stdout3.strip():
            for line in stdout3.splitlines():
                line = line.strip()
                if line.startswith("MusicFolder") or line.startswith("MusicFolder ="):
                    value = line.split("=", 1)[-1].strip().strip('"').strip("'")
                    add_candidate(value, "docker_config")

    # 2. Check Docker volume mounts (Binds) for music-related host paths
    rc, stdout, _ = _ssh_command(
        host, user, port,
        "docker inspect navidrome --format='{{range .Mounts}}{{.Source}}:{{.Destination}} {{end}}' 2>/dev/null || "
        "docker ps --filter name=navidrome --format '{{.ID}}' | head -1 | "
        "xargs -r docker inspect --format='{{range .Mounts}}{{.Source}}:{{.Destination}} {{end}}'",
        password=password,
    )
    if rc == 0 and stdout.strip():
        for mount in stdout.strip().split():
            if ":" not in mount:
                continue
            host_path = mount.split(":")[0].strip().strip('"')
            container_path = mount.split(":")[1].strip().strip('"') if ":" in mount else ""
            # Include music/data-related bind mounts
            if any(kw in host_path.lower() for kw in ("music", "data", "media")):
                add_candidate(host_path, "docker_bind")

    # 3. Check Navidrome config files on the host (bare-metal install)
    for config_path in REMOTE_NAVIDROME_CONFIG_PATHS:
        rc, stdout, _ = _ssh_command(host, user, port, f"cat {config_path} 2>/dev/null", password=password)
        if rc == 0 and "MusicFolder" in stdout:
            for line in stdout.splitlines():
                line = line.strip()
                if line.startswith("MusicFolder") or line.startswith("MusicFolder ="):
                    value = line.split("=", 1)[-1].strip().strip('"').strip("'")
                    add_candidate(value, "navidrome_config")

    # 4. Check common paths
    for path in REMOTE_MUSIC_CANDIDATES:
        rc, _, _ = _ssh_command(host, user, port, f"test -d {path} && echo yes", password=password)
        add_candidate(path, "common_path", exists=rc == 0)

    # Sort: recommended first, then by source priority, then by path
    music_candidates.sort(key=lambda c: (not c.get("recommended", False), SOURCE_PRIORITY.get(c["source"], 99), c["path"]))

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