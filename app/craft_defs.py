# =============================================================================
# File: app/craft_defs.py
# Purpose: Load craft definitions (items + recipes) from craft.yml into memory.
# =============================================================================
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

# Global dictionary: item_key -> definition
CRAFT_DEFS: Dict[str, Dict[str, Any]] = {}


def load_craft_defs() -> None:
    """Load crafts.yml into the global CRAFT_DEFS dict."""
    global CRAFT_DEFS

    # Determine path to craft.yml (at project root, next to run.py / cards.yml)
    # You can adjust this if your structure is different.
    project_root = Path(__file__).resolve().parent.parent
    yaml_path = project_root /  "app" / "data" / "crafts.yml"

    if not yaml_path.exists():
        print("craft.yml not found, no craft definitions loaded.")
        CRAFT_DEFS = {}
        return

    try:
        with yaml_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001
        print(f"Error while reading craft.yml: {exc}")
        CRAFT_DEFS = {}
        return

    items = raw.get("items")
    if not isinstance(items, dict):
        print("craft.yml does not contain a valid 'items' dictionary.")
        CRAFT_DEFS = {}
        return

    normalized: Dict[str, Dict[str, Any]] = {}

    for slug, cfg in items.items():
        if not isinstance(cfg, dict):
            print(f"Skipping item '{slug}': definition is not a dictionary.")
            continue

        # Ensure there is a 'key', fall back to slug if missing
        key = (cfg.get("key") or str(slug)).strip()
        if not key:
            print(f"Skipping item '{slug}': missing 'key'.")
            continue

        # Inject some helper fields
        cfg["slug"] = str(slug)
        cfg["key"] = key

        # Basic recipe sanity checks (optional, we keep it light for now)
        recipe = cfg.get("recipe")
        if recipe is not None:
            if not isinstance(recipe, dict):
                print(f"Item '{key}': recipe should be a dictionary.")
                cfg["recipe"] = None
            else:
                _normalize_recipe(key, recipe)

        normalized[key] = cfg

    CRAFT_DEFS.clear()          # keep the same dict object
    CRAFT_DEFS.update(normalized)
    print(f"Loaded {len(CRAFT_DEFS)} craft item definitions from craft.yml.")


def _normalize_recipe(item_key: str, recipe: Dict[str, Any]) -> None:
    """Light normalization & validation for a recipe definition."""
    # kind
    kind = (recipe.get("kind") or "shaped").strip().lower()
    recipe["kind"] = kind

    # craft_location with default
    craft_location = (recipe.get("craft_location") or "craft_table").strip()
    recipe["craft_location"] = craft_location

    # width / height
    width = int(recipe.get("width") or 0)
    height = int(recipe.get("height") or 0)

    pattern = recipe.get("pattern") or []
    if not isinstance(pattern, list):
        print(f"Item '{item_key}': recipe.pattern must be a list of strings.")
        recipe["pattern"] = []
        return

    # Ensure all lines are strings and have same length
    pattern_lines = [str(line) for line in pattern]
    if not pattern_lines:
        print(f"Item '{item_key}': recipe.pattern is empty.")
        recipe["pattern"] = []
        return

    line_lengths = {len(line) for line in pattern_lines}
    if len(line_lengths) != 1:
        print(f"Item '{item_key}': recipe.pattern lines must all have the same length.")
    else:
        # If width/height are not set, infer them from the pattern
        if width == 0:
            width = len(pattern_lines[0])
        if height == 0:
            height = len(pattern_lines)

    recipe["width"] = width
    recipe["height"] = height
    recipe["pattern"] = pattern_lines

    # Legend normalization
    legend = recipe.get("legend") or {}
    if not isinstance(legend, dict):
        print(f"Item '{item_key}': recipe.legend must be a dictionary.")
        recipe["legend"] = {}
        return

    # Ensure quantities and keys are properly set
    normalized_legend: Dict[str, Dict[str, Any]] = {}
    for symbol, entry in legend.items():
        if not isinstance(entry, dict):
            print(f"Item '{item_key}': legend entry for symbol '{symbol}' is not a dict.")
            continue

        res_type = (entry.get("type") or "resource").strip()
        res_key = (entry.get("key") or "").strip()
        qty = int(entry.get("quantity") or 1)

        if not res_key:
            print(f"Item '{item_key}': legend entry for symbol '{symbol}' missing 'key'.")
            continue

        normalized_legend[str(symbol)] = {
            "type": res_type,
            "key": res_key,
            "quantity": max(qty, 1),
        }

    recipe["legend"] = normalized_legend

    # Defaults for other fields
    recipe["output_quantity"] = int(recipe.get("output_quantity") or 1)
    recipe["craft_time_seconds"] = int(recipe.get("craft_time_seconds") or 0)
    recipe["required_table_level"] = int(recipe.get("required_table_level") or 1)


def get_craft_item_def(key: str) -> Dict[str, Any] | None:
    """Return the craft item definition for a given key, or None if not found."""
    return CRAFT_DEFS.get(key)
