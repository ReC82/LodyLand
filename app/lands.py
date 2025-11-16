# =============================================================================
# File: app/lands.py
# Purpose: Load land definitions from YAML and provide helper functions.
# =============================================================================
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml

_LANDS_CACHE: Optional[Dict[str, Dict[str, Any]]] = None


def _get_lands_path() -> Path:
    """Return the filesystem path to the lands.yml file."""
    # This assumes the file is located at app/data/lands.yml
    return Path(__file__).with_suffix("").parent / "data" / "lands.yml"


def load_lands() -> Dict[str, Dict[str, Any]]:
    """
    Load all land definitions from YAML (and cache them in memory).

    Returns:
        A dictionary where keys are land keys (e.g. "forest") and values
        are the land configuration dictionaries.
    """
    global _LANDS_CACHE

    if _LANDS_CACHE is None:
        path = _get_lands_path()
        if not path.exists():
            raise FileNotFoundError(f"lands.yml not found at: {path}")

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        if not isinstance(data, dict):
            raise ValueError("lands.yml must contain a top-level mapping")

        _LANDS_CACHE = data

    return _LANDS_CACHE

def get_land_def(land_key: str) -> Optional[Dict[str, Any]]:
    """
    Return the configuration dictionary for a given land key.

    Args:
        land_key: The land identifier (e.g. "forest", "beach").

    Returns:
        The land configuration dict, or None if the key is unknown.
    """
    lands = load_lands()
    return lands.get(land_key)

