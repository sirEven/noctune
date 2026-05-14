"""YAML config loading for Noctune."""

from pathlib import Path

import yaml

from noctune.models.config import NoctuneConfig


def load_config(path: Path) -> NoctuneConfig:
    """Load Noctune configuration from a YAML file.

    Expands ~ in source_dir, converts dest_dir to Path,
    and validates against the NoctuneConfig Pydantic model.
    """
    with open(path) as f:
        raw = yaml.safe_load(f)

    # Expand ~ in source_dir before Pydantic validation
    if "source_dir" in raw:
        raw["source_dir"] = Path(raw["source_dir"]).expanduser()
    if "dest_dir" in raw:
        raw["dest_dir"] = Path(raw["dest_dir"])

    return NoctuneConfig.model_validate(raw)