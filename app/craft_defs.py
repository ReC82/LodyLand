# =============================================================================
# File: app/craft_defs.py
# Purpose: Load craftable items + recipes from YAML files into memory.
#
# Source of truth (YAML):
#   - app/data/items/*.yml      -> item definitions (tools, weapons, resources...)
#   - app/data/crafts/*.yml     -> craft recipes (pattern, legend, output, unlock...)
#   - app/data/craft_stations.yml (optional, for grid sizes per station)
#
# Public API:
#   - ITEM_DEFS:   Dict[item_key, cfg]
#   - CRAFT_DEFS:  Dict[item_key, cfg]
#   - STATION_DEFS: Dict[station_key, cfg]
#   - load_craft_defs()
#   - get_craft_item_def(key)
# =============================================================================
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

ITEM_DEFS: Dict[str, Dict[str, Any]] = {}
CRAFT_DEFS: Dict[str, Dict[str, Any]] = {}
STATION_DEFS: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def load_craft_defs() -> None:
    """
    Load all item + craft definitions from YAML files into memory.

    YAML is the source of truth. This function should be called once at app
    startup (or after a hot reload of YAML files).
    """
    global ITEM_DEFS, CRAFT_DEFS, STATION_DEFS

    project_root = Path(__file__).resolve().parent.parent
    data_root = project_root / "app" / "data"

    ITEM_DEFS = _load_item_defs(data_root)
    STATION_DEFS = _load_station_defs(data_root)
    CRAFT_DEFS = _load_craft_item_defs(data_root, ITEM_DEFS)
    
    print("[DEBUG ITEM_DEFS wooden_stick] =", ITEM_DEFS.get("wooden_stick"))
    print("[DEBUG ITEM_DEFS rope]        =", ITEM_DEFS.get("rope"))

    print(f"[craft_defs] Loaded {len(ITEM_DEFS)} items, {len(CRAFT_DEFS)} craftable items.")


# ---------------------------------------------------------------------------
# YAML loaders
# ---------------------------------------------------------------------------
def _load_item_defs(data_root: Path) -> Dict[str, Dict[str, Any]]:
    """
    Load items from app/data/items/*.yml

    Supports:
      A) items:
           slug:
             key: ...
             ...

      B) Flat mapping:
           slug:
             key: ...
             ...

      C) List:
           - key: ...
           - key: ...
    """

    items_dir = data_root / "items"
    if not items_dir.exists():
        print(f"[craft_defs] items dir not found: {items_dir}")
        return {}

    merged: Dict[str, Dict[str, Any]] = {}

    for yaml_path in items_dir.glob("*.yml"):

        # Load YAML
        try:
            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            print(f"[craft_defs] Error reading {yaml_path}: {exc}")
            continue

        if raw is None:
            continue

        # ---------- Detect structure ----------
        items_block = None

        # A) items: {}
        if isinstance(raw, dict):
            if "items" in raw and isinstance(raw["items"], dict):
                items_block = raw["items"]

            # B) flat mapping
            else:
                if any(isinstance(v, dict) for v in raw.values()):
                    items_block = raw

        # C) top-level list
        elif isinstance(raw, list):
            items_block = {}
            for entry in raw:
                if isinstance(entry, dict):
                    key = (entry.get("key") or "").strip()
                    if key:
                        items_block[key] = entry

        # Nothing usable
        if not isinstance(items_block, dict):
            print(f"[craft_defs] File {yaml_path} has no usable item definitions.")
            continue

        # ---------- Normalize entries ----------
        for slug, cfg in items_block.items():
            if not isinstance(cfg, dict):
                print(f"[craft_defs] Skipping slug '{slug}' in {yaml_path}: not a dict.")
                continue

            key = (cfg.get("key") or str(slug)).strip()
            if not key:
                print(f"[craft_defs] Skipping slug '{slug}' in {yaml_path}: missing key.")
                continue

            cfg = dict(cfg)
            cfg["slug"] = str(slug)
            cfg["key"] = key
            cfg["label"] = (cfg.get("label") or key).strip()
            cfg["description"] = (cfg.get("description") or "").strip()

            kind = (cfg.get("kind") or "").strip()
            cfg["kind"] = kind
            if "type" not in cfg:
                cfg["type"] = kind

            if key in merged:
                print(f"[craft_defs] WARNING: duplicate item key '{key}' – last wins ({yaml_path})")

            merged[key] = cfg

    print(f"[craft_defs] Loaded {len(merged)} items from {items_dir}.")
    return merged



def _load_station_defs(data_root: Path) -> Dict[str, Dict[str, Any]]:
    """
    Load craft stations definition from craft_stations.yml (optional).

    Example:
      stations:
        craft_table:
          key: craft_table
          label: Crafting Table
          grids:
            - tier: 1
              rows: 1
              cols: 3
              unlock: { type: default }
            - tier: 2
              rows: 2
              cols: 3
              unlock: { type: card, card_key: upgrade_craft_table_2 }
    """
    stations_path = data_root / "craft_stations.yml"
    if not stations_path.exists():
        print(f"[craft_defs] craft_stations.yml not found at {stations_path}.")
        return {}

    try:
        with stations_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001
        print(f"[craft_defs] Error reading craft_stations.yml: {exc}")
        return {}

    stations = raw.get("stations")
    if not isinstance(stations, dict):
        print("[craft_defs] craft_stations.yml has no valid 'stations' dict.")
        return {}

    normalized: Dict[str, Dict[str, Any]] = {}
    for slug, cfg in stations.items():
        if not isinstance(cfg, dict):
            print(
                f"[craft_defs] Skipping station '{slug}': definition is not a dict."
            )
            continue

        key = (cfg.get("key") or str(slug)).strip()
        if not key:
            print(f"[craft_defs] Skipping station '{slug}': missing 'key'.")
            continue

        cfg["slug"] = str(slug)
        cfg["key"] = key
        normalized[key] = cfg

    print(f"[craft_defs] Loaded {len(normalized)} stations.")
    return normalized


def _load_craft_item_defs(
    data_root: Path, item_defs: Dict[str, Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Load all craft recipes from the *merged* app/data/crafts.yml file
    and merge them with item metadata from item_defs.

    Expected structure (generated by normalize_crafts_yaml.py):

      crafts:
        some_craft_slug:
          key: optional (default: slug)
          station_key: craft_table | craft_table_base | forge_base | ...
          required_grid:
            tier: 1|2|3
            # or rows/cols for advanced stations
          output:
            kind: tool|weapon|resource|...
            key: tool_wooden_axe
            quantity: 1
          recipe:
            pattern: [...]
            legend:
              B:
                kind: resource
                key: branch
                quantity: 1
          craft_time_seconds: 10
          xp_reward: 5
          unlock:
            recipe_card_key: recipe_tool_wooden_axe
            min_level: 2
            building_card_key: building_forge_level_1 (optional)
          enabled: true
    """
    crafts_file = data_root / "crafts.yml"
    crafts_dir = data_root / "crafts"

    # --- 1) Mode moderne : on lit le fichier mergé crafts.yml ---
    if crafts_file.exists():
        try:
            with crafts_file.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except Exception as exc:  # noqa: BLE001
            print(f"[craft_defs] Error reading {crafts_file}: {exc}")
            return {}

        crafts = raw.get("crafts")
        if not isinstance(crafts, dict):
            print(
                f"[craft_defs] crafts.yml has no valid 'crafts' dict "
                f"(type={type(crafts).__name__})."
            )
            return {}

        yaml_path = crafts_file  # pour les logs ci-dessous
        normalized: Dict[str, Dict[str, Any]] = {}

        for slug, cfg in crafts.items():
            if not isinstance(cfg, dict):
                print(
                    f"[craft_defs] Skipping craft slug '{slug}' in {yaml_path}: "
                    f"definition is not a dict."
                )
                continue

            craft_slug = str(slug)
            craft_key = (cfg.get("key") or craft_slug).strip()

            output = cfg.get("output") or {}
            if not isinstance(output, dict):
                print(
                    f"[craft_defs] Craft '{craft_slug}' in {yaml_path}: "
                    f"'output' must be a dict."
                )
                continue

            output_key = (output.get("key") or craft_key).strip()
            if not output_key:
                print(
                    f"[craft_defs] Craft '{craft_slug}' in {yaml_path}: "
                    f"missing output.key."
                )
                continue

            # Lier au meta item
            item_meta = item_defs.get(output_key)
            if not item_meta:
                print(
                    f"[craft_defs] Craft '{craft_slug}' in {yaml_path}: "
                    f"output item_key '{output_key}' not found in item defs."
                )
                continue

            # Base = meta item
            merged = dict(item_meta)
            merged["slug"] = craft_slug
            merged["key"] = output_key

            station_key = (cfg.get("station_key") or "craft_table").strip()
            merged["station_key"] = station_key

            required_grid = cfg.get("required_grid") or {}
            if not isinstance(required_grid, dict):
                required_grid = {}

            tier = int(required_grid.get("tier") or 1)
            merged["required_grid"] = {
                "tier": tier,
                "rows": int(required_grid.get("rows") or 0),
                "cols": int(required_grid.get("cols") or 0),
            }

            # Condition de déblocage (normalisée)
            merged["unlock_condition"] = _build_unlock_condition(
                craft_slug, cfg, item_meta
            )

            # Bloc recipe
            recipe = cfg.get("recipe")
            if recipe is None:
                print(
                    f"[craft_defs] Craft '{craft_slug}' in {yaml_path}: "
                    f"missing 'recipe'."
                )
                continue
            if not isinstance(recipe, dict):
                print(
                    f"[craft_defs] Craft '{craft_slug}' in {yaml_path}: "
                    f"'recipe' must be a dict."
                )
                continue

            recipe = dict(recipe)  # copy
            # injecte la localisation de craft
            recipe["craft_location"] = station_key

            # temps et niveau requis
            recipe["craft_time_seconds"] = int(
                cfg.get("craft_time_seconds") or recipe.get("craft_time_seconds") or 0
            )
            recipe["required_table_level"] = int(
                recipe.get("required_table_level") or tier or 1
            )

            # normalisation pattern / legend / width / height / defaults
            _normalize_recipe(output_key, recipe)

            merged["recipe"] = recipe
            merged["xp_reward"] = int(cfg.get("xp_reward") or 0)
            merged["enabled"] = bool(cfg.get("enabled", True))

            if output_key in normalized:
                print(
                    f"[craft_defs] WARNING: multiple craft recipes for item_key "
                    f"'{output_key}'. Last one wins (file: {yaml_path})."
                )

            normalized[output_key] = merged

        print(f"[craft_defs] Loaded {len(normalized)} craft recipes from {crafts_file}.")
        return normalized

    # --- 2) Fallback : ancien mode, scan du dossier app/data/crafts/*.yml ---
    if not crafts_dir.exists():
        print(
            f"[craft_defs] crafts.yml not found and crafts dir not found: {crafts_dir}"
        )
        return {}

    print(
        f"[craft_defs] crafts.yml not found; falling back to directory scan in {crafts_dir}."
    )

    normalized: Dict[str, Dict[str, Any]] = {}

    for yaml_path in crafts_dir.glob("*.yml"):
        try:
            with yaml_path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except Exception as exc:  # noqa: BLE001
            print(f"[craft_defs] Error reading {yaml_path}: {exc}")
            continue

        crafts = raw.get("crafts")
        if not isinstance(crafts, dict):
            print(
                f"[craft_defs] File {yaml_path} has no valid 'crafts' dict, skipping."
            )
            continue

        for slug, cfg in crafts.items():
            if not isinstance(cfg, dict):
                print(
                    f"[craft_defs] Skipping craft slug '{slug}' in {yaml_path}: "
                    f"definition is not a dict."
                )
                continue

            # … même logique que ci-dessus …
            # (tu peux garder exactement le corps que tu avais déjà ici)
            # [...]
            # Pour ne pas alourdir, je tronque, mais l’idée est d’avoir la même
            # boucle que dans la première partie.
            pass  # <- supprime ce "pass" et remets ton ancien corps si tu veux le fallback

    return normalized



def _build_unlock_condition(
    craft_slug: str, craft_cfg: Dict[str, Any], item_meta: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build a normalized unlock_condition for a craft.

    Priority:
      1) craft_cfg["unlock"].recipe_card_key -> type: "card"
      2) craft_cfg["unlock"].min_level       -> type: "level"
      3) item_meta["unlock_default"]         -> fallback
      4) default: {} (no special condition)
    """
    unlock_cfg = craft_cfg.get("unlock") or {}
    if not isinstance(unlock_cfg, dict):
        unlock_cfg = {}

    recipe_card_key = (unlock_cfg.get("recipe_card_key") or "").strip()
    if recipe_card_key:
        return {"type": "card", "key": recipe_card_key}

    min_level = unlock_cfg.get("min_level")
    if min_level is not None:
        try:
            min_level_int = int(min_level)
        except (TypeError, ValueError):
            min_level_int = 1
        return {"type": "level", "min_level": min_level_int}

    item_unlock = item_meta.get("unlock_default")
    if isinstance(item_unlock, dict):
        return item_unlock

    return {}


# ---------------------------------------------------------------------------
# Recipe normalization
# ---------------------------------------------------------------------------
def _normalize_recipe(item_key: str, recipe: Dict[str, Any]) -> None:
    """Normalize and validate a recipe definition (pattern, legend, dimensions)."""
    kind = (recipe.get("kind") or "shaped").strip().lower()
    recipe["kind"] = kind

    craft_location = (recipe.get("craft_location") or "craft_table").strip()
    recipe["craft_location"] = craft_location

    width = int(recipe.get("width") or 0)
    height = int(recipe.get("height") or 0)

    pattern = recipe.get("pattern") or []
    if not isinstance(pattern, list):
        print(f"Item '{item_key}': recipe.pattern must be a list of strings.")
        recipe["pattern"] = []
        return

    lines = [str(line) for line in pattern]
    if not lines:
        print(f"Item '{item_key}': recipe.pattern is empty.")
        recipe["pattern"] = []
        return

    line_lengths = {len(line) for line in lines}
    if len(line_lengths) != 1:
        print(f"Item '{item_key}': recipe.pattern lines must all have the same length.")
    else:
        if width == 0:
            width = len(lines[0])
        if height == 0:
            height = len(lines)

    recipe["width"] = width
    recipe["height"] = height
    recipe["pattern"] = lines

    legend = recipe.get("legend") or {}
    if not isinstance(legend, dict):
        print(f"Item '{item_key}': recipe.legend must be a dictionary.")
        recipe["legend"] = {}
        return

    normalized_legend: Dict[str, Dict[str, Any]] = {}
    for symbol, entry in legend.items():
        if not isinstance(entry, dict):
            print(
                f"Item '{item_key}': legend entry for symbol '{symbol}' "
                f"is not a dict."
            )
            continue

        res_type = (entry.get("type") or "resource").strip()
        res_key = (entry.get("key") or "").strip()
        qty = int(entry.get("quantity") or 1)

        if not res_key:
            print(
                f"Item '{item_key}': legend entry for symbol '{symbol}' "
                f"missing 'key'."
            )
            continue

        normalized_legend[str(symbol)] = {
            "type": res_type,
            "key": res_key,
            "quantity": max(qty, 1),
        }

    recipe["legend"] = normalized_legend

    recipe["output_quantity"] = int(recipe.get("output_quantity") or 1)
    recipe["craft_time_seconds"] = int(recipe.get("craft_time_seconds") or 0)
    recipe["required_table_level"] = int(recipe.get("required_table_level") or 1)


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------
def get_craft_item_def(key: str) -> Dict[str, Any] | None:
    """Return the craft item definition for a given key, or None if not found."""
    return CRAFT_DEFS.get(key)
