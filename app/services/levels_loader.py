# app/services/levels_loader.py
"""
Service to load and cache level definitions from app/data/levels.yml.

This is the single source of truth for:
- xp_required
- level rewards
- story events (intro, dialogs, tutorials, etc.)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# Global in-memory cache
_LEVELS_CACHE: Optional[List[Dict[str, Any]]] = None


def _get_levels_path() -> Path:
    """Return the path to app/data/levels.yml (generated file)."""
    # __file__ = app/services/levels_loader.py
    base_dir = Path(__file__).resolve().parents[1]  # -> app/
    return base_dir / "data" / "levels.yml"


def _load_levels_from_disk() -> List[Dict[str, Any]]:
    """Load levels.yml from disk and return the 'levels' list."""
    path = _get_levels_path()

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    levels = data.get("levels", [])
    if not isinstance(levels, list):
        raise ValueError(f"{path}: top-level 'levels' must be a list")

    # Optional: basic sanity check
    for lvl in levels:
        if not isinstance(lvl, dict):
            raise ValueError(f"{path}: each level entry must be a mapping")
        if "level" not in lvl:
            raise ValueError(f"{path}: level entry without 'level' field")
        # enforce int-level
        lvl["level"] = int(lvl["level"])

    return levels


def get_all_levels(reload: bool = False) -> List[Dict[str, Any]]:
    """
    Return the list of all levels.

    Uses an in-memory cache by default. Pass reload=True to force re-read
    from disk (useful in dev).
    """
    global _LEVELS_CACHE

    if reload or _LEVELS_CACHE is None:
        _LEVELS_CACHE = _load_levels_from_disk()

    return _LEVELS_CACHE


def get_level_def(level_number: int) -> Optional[Dict[str, Any]]:
    """Return a single level definition by its level number, or None."""
    for lvl in get_all_levels():
        if int(lvl.get("level")) == int(level_number):
            return lvl
    return None
