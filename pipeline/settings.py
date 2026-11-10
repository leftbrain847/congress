"""Loads config/settings.yaml, the single home for every tunable."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / "config" / "settings.yaml"


def load(path: Path = SETTINGS_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)
