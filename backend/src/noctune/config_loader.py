"""YAML config loading for Noctune."""

from pathlib import Path

import yaml

from noctune.models.config import NoctuneConfig


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

    return NoctuneConfig.model_validate(raw)