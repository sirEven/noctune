"""Path probing — discover source and destination directories.

Probes the local filesystem and remote filesystem to suggest
likely source_dir, dest_dir, and Navidrome music folder paths.

No LLM needed — just filesystem checks, Docker inspect, and reading Navidrome's config.

Key design principle: the probe gathers FACTS, not opinions.
It discovers what exists, how Docker maps paths, and which device/filesystem
a path lives on. The user decides what's right for their setup.

A 400GB microSD is a perfectly valid music store. A named Docker volume
might be exactly what the user wants. We present the facts; the user chooses.
"""

from __future__ import annotations

import json
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


# --- Remote path probing via SSH ---

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

    detail = stderr.strip() or stdout.strip() or f"exit code {rc}"
    return False, f"SSH failed: {detail}"


def _get_filesystem_info(
    host: str, user: str, port: int, path: str, password: str = "",
) -> dict[str, str]:
    """Get filesystem info for a path on the remote machine.

    Uses df to find: device, mount point, filesystem type, total size, used%.
    Returns dict with keys: device, mount_point, fstype, size, used_pct, on_root.
    """
    # df -P for POSIX output, --output=device,target,fstype,size,pcent
    rc, stdout, _ = _ssh_command(
        host, user, port,
        f"df -P --output=source,target,fstype,size,pcent '{path}' 2>/dev/null",
        password=password,
    )
    if rc != 0 or not stdout.strip():
        return {}

    lines = stdout.strip().splitlines()
    if len(lines) < 2:
        return {}

    # Parse: Filesystem Mounted on Type Size Use%
    fields = lines[1].split()
    if len(fields) < 5:
        return {}

    device = fields[0]
    mount_point = fields[1]
    fstype = fields[2]
    size = fields[3]
    used_pct = fields[4].rstrip("%")

    # Check if this is the root device
    on_root = mount_point == "/"

    return {
        "device": device,
        "mount_point": mount_point,
        "fstype": fstype,
        "size": size,
        "used_pct": used_pct,
        "on_root": on_root,
    }


def _docker_inspect_mounts(
    host: str, user: str, port: int, container_id: str, password: str = "",
) -> list[dict]:
    """Get mount info from a Docker container via SSH.

    Returns a list of dicts with keys:
      - type: "bind" or "volume"
      - source: host path (for bind) or volume name (for volume)
      - destination: container path
      - name: volume name (for named volumes)
      - rw: read-write flag
    """
    rc, stdout, _ = _ssh_command(
        host, user, port,
        f"docker inspect {container_id} --format='{{{{json .Mounts}}}}'",
        password=password,
    )
    if rc != 0 or not stdout.strip():
        return []

    try:
        mounts_raw = json.loads(stdout.strip())
    except json.JSONDecodeError:
        rc, stdout, _ = _ssh_command(
            host, user, port,
            f"docker inspect {container_id}",
            password=password,
        )
        if rc != 0 or not stdout.strip():
            return []
        try:
            inspect_data = json.loads(stdout.strip())
            if isinstance(inspect_data, list) and len(inspect_data) > 0:
                mounts_raw = inspect_data[0].get("Mounts", [])
            else:
                return []
        except (json.JSONDecodeError, IndexError, KeyError):
            return []

    if not isinstance(mounts_raw, list):
        return []

    result = []
    for mount in mounts_raw:
        mount_type = mount.get("Type", "unknown")
        source = mount.get("Source", "")
        destination = mount.get("Destination", "")
        rw = mount.get("RW", True)
        result.append({
            "type": mount_type,
            "source": source,
            "destination": destination,
            "name": mount.get("Name", ""),
            "rw": rw,
        })

    return result


def _find_container_music_folder(
    host: str, user: str, port: int, container_id: str, password: str = "",
) -> str | None:
    """Get ND_MUSICFOLDER from a running Navidrome container."""
    rc, stdout, _ = _ssh_command(
        host, user, port,
        f"docker exec {container_id} env 2>/dev/null | grep ND_MUSICFOLDER",
        password=password,
    )
    if rc == 0 and stdout.strip():
        for line in stdout.splitlines():
            if "ND_MUSICFOLDER" in line:
                return line.split("=", 1)[-1].strip()
    return None


def _find_container_config_musicfolder(
    host: str, user: str, port: int, container_id: str, password: str = "",
) -> str | None:
    """Get MusicFolder from navidrome.toml inside a container."""
    rc, stdout, _ = _ssh_command(
        host, user, port,
        f"docker exec {container_id} cat /data/navidrome.toml 2>/dev/null | grep MusicFolder",
        password=password,
    )
    if rc == 0 and stdout.strip():
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("MusicFolder") or line.startswith("MusicFolder ="):
                return line.split("=", 1)[-1].strip().strip('"').strip("'")
    return None


def probe_remote_paths(
    host: str, user: str, port: int = 22, password: str = "",
) -> dict:
    """Probe the remote machine for likely Navidrome music folder paths.

    Gathers factual context about each path:
    - Whether Navidrome runs in Docker or bare-metal
    - Container ↔ host path mappings (for Docker)
    - Device and filesystem info (which disk, how big, how full)
    - Whether the path is on the root device or a separate mount

    No judgments — the user decides what's right for their setup.

    Returns:
      {
        "navidrome_type": "docker" | "bare_metal" | "not_found",
        "music_folder": [
          {
            "path": "/data/music",           # host path (what Noctune uses for rsync/SSH)
            "container_path": "/music",       # what Navidrome sees (None if bare-metal)
            "source": "docker_env_resolved",  # how we found it
            "label": "...",                   # human-readable explanation
            "recommended": True,             # best guess based on source authority
            "exists": True,
            "device": "/dev/sda1",           # filesystem device
            "mount_point": "/data",           # mount point
            "fstype": "ext4",                 # filesystem type
            "size": "234G",                   # total size
            "used_pct": "45",                 # used percentage
            "on_root": False,                 # True if on root device (typically OS disk)
            "mount_type": "bind",            # "bind" | "volume" | None
          },
          ...
        ],
        "error": None | "error message"
      }
    """
    ssh_ok, ssh_msg = _ssh_available(host, user, port, password)
    if not ssh_ok:
        return {"music_folder": [], "navidrome_type": "unknown", "error": ssh_msg}

    navidrome_type = "not_found"
    candidates: list[dict] = []
    seen_host_paths: set[str] = set()
    best_priority = 99

    PRIORITY = {
        "docker_env_resolved": 0,
        "docker_bind": 1,
        "docker_env_container": 2,
        "docker_config_resolved": 3,
        "docker_config_container": 4,
        "navidrome_config": 5,
        "docker_volume": 6,
        "common_path": 7,
    }

    LABELS = {
        "docker_env_resolved": "Navidrome env (ND_MUSICFOLDER) resolved to host path",
        "docker_bind": "Docker bind mount — host directory mounted into container",
        "docker_env_container": "Navidrome env (ND_MUSICFOLDER) — container path only, host path unknown",
        "docker_config_resolved": "Navidrome config (MusicFolder) resolved to host path",
        "docker_config_container": "Navidrome config (MusicFolder) — container path, host path unknown",
        "docker_volume": "Docker named volume — managed by Docker",
        "navidrome_config": "Navidrome config file MusicFolder setting",
        "common_path": "Path exists on disk — not verified as Navidrome's",
    }

    def add_candidate(
        host_path: str,
        source: str,
        container_path: str | None = None,
        mount_type: str | None = None,
        exists: bool = True,
    ) -> None:
        """Add a candidate path with device/filesystem context."""
        nonlocal best_priority
        if host_path in seen_host_paths:
            for c in candidates:
                if c["path"] == host_path:
                    if PRIORITY.get(source, 99) < PRIORITY.get(c["source"], 99):
                        c["source"] = source
                        c["label"] = LABELS.get(source, source)
                        c["container_path"] = container_path or c.get("container_path")
                        c["mount_type"] = mount_type or c.get("mount_type")
                    return
        seen_host_paths.add(host_path)

        is_recommended = PRIORITY.get(source, 99) < best_priority
        if is_recommended:
            for c in candidates:
                c["recommended"] = False
            best_priority = PRIORITY.get(source, 99)

        # Gather device/filesystem context
        fs_info = {}
        if exists:
            fs_info = _get_filesystem_info(host, user, port, host_path, password)

        candidates.append({
            "path": host_path,
            "container_path": container_path,
            "exists": exists,
            "source": source,
            "label": LABELS.get(source, source),
            "recommended": is_recommended,
            "mount_type": mount_type,
            **fs_info,  # device, mount_point, fstype, size, used_pct, on_root
        })

    # --- Step 1: Find Navidrome Docker container ---
    container_music_path: str | None = None
    container_id = ""

    rc, stdout, _ = _ssh_command(
        host, user, port,
        "docker ps --filter name=navidrome --format '{{.ID}}'",
        password=password,
    )
    if rc == 0 and stdout.strip():
        navidrome_type = "docker"
        container_id = stdout.strip().split()[0]
        container_music_path = _find_container_music_folder(host, user, port, container_id, password)
        if not container_music_path:
            container_music_path = _find_container_config_musicfolder(host, user, port, container_id, password)

    # --- Step 2: Get Docker mount info ---
    bind_map: dict[str, str] = {}  # container_path → host_path
    mounts: list[dict] = []
    if container_id:
        mounts = _docker_inspect_mounts(host, user, port, container_id, password)
        for mount in mounts:
            if mount["type"] == "bind":
                bind_map[mount["destination"]] = mount["source"]

    # --- Step 3: Resolve container ND_MUSICFOLDER to host path ---
    if container_music_path:
        if container_music_path in bind_map:
            host_path = bind_map[container_music_path]
            add_candidate(host_path, "docker_env_resolved", container_path=container_music_path, mount_type="bind")
        else:
            # Check if it's a named volume
            volume_mount = None
            for m in mounts:
                if m["destination"] == container_music_path and m["type"] == "volume":
                    volume_mount = m
                    break

            if volume_mount:
                # Named volume — find the real disk path
                volume_name = volume_mount.get("name", "")
                rc, stdout, _ = _ssh_command(
                    host, user, port,
                    f"docker volume inspect {volume_name} --format '{{{{.Mountpoint}}}}' 2>/dev/null",
                    password=password,
                )
                disk_path = stdout.strip() if rc == 0 and stdout.strip() else f"/var/lib/docker/volumes/{volume_name}/_data"
                add_candidate(disk_path, "docker_volume", container_path=container_music_path, mount_type="volume")
            else:
                # Can't resolve — bare container path
                add_candidate(container_music_path, "docker_env_container", container_path=container_music_path)

    # --- Step 4: Add bind mounts that look like music directories ---
    for container_path, host_path in bind_map.items():
        if host_path in seen_host_paths:
            continue
        if any(kw in host_path.lower() for kw in ("music", "data", "media")):
            add_candidate(host_path, "docker_bind", container_path=container_path, mount_type="bind")

    # --- Step 5: Named volumes that look like music ---
    for mount in mounts:
        if mount["type"] == "volume" and mount.get("name"):
            if container_music_path and mount["destination"] == container_music_path:
                continue  # Already handled in step 3
            name = mount["name"].lower()
            dest = mount["destination"].lower()
            if any(kw in name for kw in ("music", "data", "media")) or any(kw in dest for kw in ("music", "data", "media")):
                volume_name = mount.get("name", "")
                rc, stdout, _ = _ssh_command(
                    host, user, port,
                    f"docker volume inspect {volume_name} --format '{{{{.Mountpoint}}}}' 2>/dev/null",
                    password=password,
                )
                disk_path = stdout.strip() if rc == 0 and stdout.strip() else f"/var/lib/docker/volumes/{volume_name}/_data"
                add_candidate(disk_path, "docker_volume", container_path=mount["destination"], mount_type="volume")

    # --- Step 6: Bare-metal Navidrome config ---
    for config_path in REMOTE_NAVIDROME_CONFIG_PATHS:
        rc, stdout, _ = _ssh_command(host, user, port, f"cat {config_path} 2>/dev/null", password=password)
        if rc == 0 and "MusicFolder" in stdout:
            navidrome_type = "bare_metal"
            for line in stdout.splitlines():
                line = line.strip()
                if line.startswith("MusicFolder") or line.startswith("MusicFolder ="):
                    value = line.split("=", 1)[-1].strip().strip('"').strip("'")
                    if value in bind_map:
                        add_candidate(bind_map[value], "docker_config_resolved", container_path=value, mount_type="bind")
                    else:
                        add_candidate(value, "navidrome_config")

    # --- Step 7: Common paths as fallback ---
    for path in REMOTE_MUSIC_CANDIDATES:
        if path in seen_host_paths:
            continue
        rc, _, _ = _ssh_command(host, user, port, f"test -d {path} && echo yes", password=password)
        add_candidate(path, "common_path", exists=rc == 0)

    # Sort: recommended first, then by priority, then alphabetically
    candidates.sort(key=lambda c: (
        not c.get("recommended", False),
        PRIORITY.get(c["source"], 99),
        c["path"],
    ))

    return {"music_folder": candidates, "navidrome_type": navidrome_type}


def probe_navidrome_connection(url: str, username: str, password: str) -> dict[str, str | bool]:
    """Test if Navidrome is reachable and auth works.

    Returns {reachable, auth_ok, version, error}.
    """
    import httpx

    if not url:
        return {"reachable": False, "auth_ok": False, "version": "", "error": "No Navidrome URL configured — enter the URL in settings first"}

    try:
        client = httpx.Client(timeout=10.0)
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