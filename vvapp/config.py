"""Loads config.yaml and environment secrets."""
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(name: str, required: bool = True, default: str = "") -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(
            f"Missing secret/environment variable {name}. "
            f"Add it in GitHub > Settings > Secrets and variables > Actions."
        )
    return value
