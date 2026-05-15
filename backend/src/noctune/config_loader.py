"""YAML config loading for Noctune."""

from pathlib import Path

import yaml

from noctune.models.config import NoctuneConfig, RemoteConfig


def load_config(path: Path = Path("~/.noctune/config.yaml")) -> NoctuneConfig:
    """Load Noctune configuration from a YAML file.

    If the file doesn't exist, returns defaults.
    Expands ~ in source_dir, converts dest_dir to Path,
    and validates against the NoctuneConfig Pydantic model.
    """
    resolved = Path(path).expanduser()

    if not resolved.exists():
        # Return defaults — the daemon/scan commands will use config from CLI
        from noctune.models.config import LLMConfig
        return NoctuneConfig(
            source_dir=Path("~/Music/Incoming").expanduser(),
            llm=LLMConfig(),
        )

    with open(resolved) as f:
        raw = yaml.safe_load(f) or {}

    # Expand ~ in source_dir before Pydantic validation
    if "source_dir" in raw:
        raw["source_dir"] = Path(raw["source_dir"]).expanduser()
    if "dest_dir" in raw:
        raw["dest_dir"] = Path(raw["dest_dir"])

    # Handle legacy flat keys: dest_host/dest_user -> remote.host/remote.user
    if "remote" not in raw:
        remote_data: dict = {}
        # Migrate dest_host/dest_user from flat config
        if "dest_host" in raw:
            remote_data["host"] = raw.pop("dest_host")
        if "dest_user" in raw:
            remote_data["user"] = raw.pop("dest_user")
        # Migrate navidrome.ssh_* from flat config
        nav_raw = raw.get("navidrome", {})
        if isinstance(nav_raw, dict):
            if "ssh_host" in nav_raw:
                remote_data["host"] = nav_raw.pop("ssh_host")
            if "ssh_user" in nav_raw:
                remote_data["user"] = nav_raw.pop("ssh_user")
            if "ssh_password" in nav_raw:
                remote_data["password"] = nav_raw.pop("ssh_password")
            if "ssh_port" in nav_raw:
                remote_data["port"] = nav_raw.pop("ssh_port")
        if remote_data:
            raw["remote"] = remote_data

    return NoctuneConfig.model_validate(raw)