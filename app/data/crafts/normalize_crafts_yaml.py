#!/usr/bin/env python
"""
normalize_crafts_yaml.py

Validator + merger for LodyLand craft recipes.

Goals:
  - Recursively scan app/data/crafts/ for *.yml fragments
  - Merge all craft definitions into a single app/data/crafts.yml
  - Validate basic structure of each craft
  - Check references:
      * resources used in recipe.legend exist in app/data/items/resources.yml
      * items (output + legend kind=item/tool/weapon/…) exist in app/data/items/*.yml
      * unlock.recipe_card_key exists in app/data/cards.yml
  - If ANY structural issue -> do NOT touch crafts.yml, generate an HTML report
  - Otherwise -> write a fresh crafts.yml with all crafts merged
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import webbrowser
import yaml

# ---------------------------------------------------------------------------
# Root paths
# ---------------------------------------------------------------------------

# Project layout assumption:
#   project_root/
#     app/
#       data/
#         crafts/
#         items/
#         resources.yml  (or items/resources.yml in our case)
#         cards.yml
#
# Script lives in: app/data/crafts/normalize_crafts_yaml.py
THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parents[2]          # app/
DATA_ROOT = PROJECT_ROOT / "data"            # app/data/
CRAFTS_ROOT = DATA_ROOT / "crafts"
OUTPUT_FILE = DATA_ROOT / "crafts.yml"


# ---------------------------------------------------------------------------
# Helpers to load items / resources / cards for validation
# ---------------------------------------------------------------------------

def load_item_keys() -> Dict[str, str]:
    """
    Load all item definitions from app/data/items/*.yml.

    Accepted formats for EACH file under items/*.yml:

    A) Mapping with 'items' block:

       items:
         branch:
           key: branch
           ...
         stick:
           key: stick
           ...

    B) Flat mapping (no 'items' block):

       branch:
         key: branch
         ...
       stick:
         key: stick
         ...

    C) List of dicts:

       - key: branch
         ...
       - key: stick
         ...

    Returns:
      Dict[item_key, source_file_str]
    """
    items_dir = DATA_ROOT / "items"
    result: Dict[str, str] = {}

    if not items_dir.exists():
        print(f"⚠ items dir not found: {items_dir}")
        return result

    for path in items_dir.glob("*.yml"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as e:  # noqa: BLE001
            print(f"❌ ERROR reading items file {path}: {e}")
            raise

        if data is None:
            continue

        items_dict: Dict[str, Dict[str, Any]] = {}

        # Case 1: dict top-level
        if isinstance(data, dict):
            # 1A: explicit 'items' block
            if "items" in data and isinstance(data["items"], dict):
                items_dict = data["items"]
            else:
                # 1B: flat mapping (slug -> cfg)
                if any(isinstance(v, dict) for v in data.values()):
                    items_dict = data
                else:
                    print(
                        f"⚠ File {path} has a dict top-level but no usable items; "
                        f"skipping for item_keys."
                    )
                    continue

        # Case 2: list top-level
        elif isinstance(data, list):
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                key = (entry.get("key") or "").strip()
                if not key:
                    continue
                items_dict[key] = entry

        else:
            print(
                f"⚠ File {path} has unsupported top-level type "
                f"({type(data).__name__}); skipping for item_keys."
            )
            continue

        # Collect item keys
        for slug, cfg in items_dict.items():
            if not isinstance(cfg, dict):
                print(
                    f"⚠ Item '{slug}' in {path} is not a dict; skipping."
                )
                continue

            item_key = (cfg.get("key") or str(slug)).strip()
            if not item_key:
                print(
                    f"⚠ Item '{slug}' in {path} has empty/missing key; skipping."
                )
                continue

            if item_key in result:
                print(
                    f"⚠ WARNING: duplicate item_key '{item_key}' "
                    f"in {path} (already seen in {result[item_key]})"
                )
            result[item_key] = str(path)

    return result


def load_resource_keys() -> Dict[str, str]:
    """
    Load all resource definitions from app/data/items/resources.yml.

    Accepted formats:

    A) Dict + 'resources' list:

       resources:
         - key: branch
           ...
         - key: stick
           ...

    B) Direct list:

       - key: branch
         ...
       - key: stick
         ...

    Returns:
      Dict[resource_key, source_file_str]
    """
    path = DATA_ROOT / "items" / "resources.yml"
    result: Dict[str, str] = {}

    if not path.exists():
        print(f"⚠ resources.yml not found at {path}")
        return result

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        print(f"❌ ERROR reading resources file {path}: {e}")
        raise

    # Case A: dict with 'resources' list
    if isinstance(data, dict):
        resources = data.get("resources") or []
        if not isinstance(resources, list):
            print(
                f"⚠ resources.yml: 'resources' is not a list at top-level "
                f"({path}), resource validation will be limited."
            )
            return result

    # Case B: top-level list
    elif isinstance(data, list):
        resources = data

    else:
        print(
            f"⚠ resources.yml: unexpected structure at top-level ({type(data).__name__}); "
            f"resource validation will be limited."
        )
        return result

    for entry in resources:
        if not isinstance(entry, dict):
            continue
        key = (entry.get("key") or "").strip()
        if not key:
            continue
        if key in result:
            print(
                f"⚠ WARNING: duplicate resource key '{key}' "
                f"in resources.yml (path {path})"
            )
        result[key] = str(path)

    return result


def load_card_keys() -> Dict[str, str]:
    """
    Load all card keys from app/data/cards.yml.

    Accepted formats:

    1) Grouped format (normalize_cards_yaml.py):

       cards:
         access:
           - key: access_craft_table_basic
             ...
         recipes:
           - key: recipe_tool_wooden_axe
             ...

    2) Flat list under 'cards':

       cards:
         - key: access_craft_table_basic
         - key: recipe_tool_wooden_axe

    3) Direct list (no 'cards' key):

       - key: access_craft_table_basic
       - key: recipe_tool_wooden_axe

    If format is unexpected, card validation is disabled (no error).
    """
    path = DATA_ROOT / "cards.yml"
    result: Dict[str, str] = {}

    if not path.exists():
        print(f"⚠ cards.yml not found at {path} (card validation will be limited).")
        return result

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        print(f"❌ ERROR reading cards.yml: {e}")
        raise

    iterable: List[dict] = []

    # Case A: dict top-level
    if isinstance(data, dict):
        cards_root = data.get("cards")

        # A1: grouped dict (access, recipes, ...)
        if isinstance(cards_root, dict):
            for card_type, cards in cards_root.items():
                if not isinstance(cards, list):
                    print(f"⚠ cards.yml: 'cards.{card_type}' is not a list, skipping.")
                    continue
                iterable.extend(cards)

        # A2: flat list under 'cards'
        elif isinstance(cards_root, list):
            iterable = cards_root

        # A3: no 'cards' key
        elif cards_root is None:
            print("⚠ cards.yml: no 'cards' key found; card validation disabled.")
            return {}

        # A4: unexpected type for 'cards'
        else:
            print("⚠ cards.yml: unexpected type for 'cards'; card validation disabled.")
            return {}

    # Case B: direct list
    elif isinstance(data, list):
        iterable = data

    # Case C: unsupported top-level
    else:
        print("⚠ cards.yml: unexpected top-level structure; card validation disabled.")
        return {}

    for card in iterable:
        if not isinstance(card, dict):
            continue
        key = (card.get("key") or "").strip()
        if not key:
            continue
        if key in result:
            print(
                f"⚠ WARNING: duplicate card key '{key}' "
                f"in cards.yml (already collected)"
            )
        result[key] = str(path)

    return result


# ---------------------------------------------------------------------------
# Craft fragment loading + validation
# ---------------------------------------------------------------------------

def load_fragment_crafts(
    path: Path,
    errors: List[Tuple[Path, str, str]],
) -> Dict[str, Dict[str, Any]]:
    """
    Load a craft fragment file.

    Accepted formats:

    A) Legacy format with 'crafts' block:

       crafts:
         some_craft_slug:
           key: ...
           ...

    B) Flat mapping format (used in craft_base/*.yml):

       some_craft_slug:
         key: ...
         ...

    Returns:
      Dict[slug, craft_cfg]
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        # YAML syntax error: we record one error and skip this file
        msg = f"YAML syntax error: {e}"
        errors.append((path, "<file>", msg))
        print(f"    ↳ YAML ERROR in {path}: {e}")
        return {}

    if data is None:
        print(f"    ↳ (empty YAML in {path}, skipped)")
        return {}

    if not isinstance(data, dict):
        msg = (
            f"Invalid top-level structure in {path}: expected a mapping (dict), "
            f"got {type(data).__name__}."
        )
        errors.append((path, "<file>", msg))
        print(f"    ↳ {msg}")
        return {}

    # Format A: explicit 'crafts' block
    if "crafts" in data:
        crafts = data["crafts"]
        if crafts is None:
            print(f"    ↳ (no crafts found in 'crafts' block of {path}, skipped)")
            return {}
        if not isinstance(crafts, dict):
            msg = (
                f"Invalid structure in {path}: 'crafts' must be a dict of slug -> cfg "
                f"(got {type(crafts).__name__})."
            )
            errors.append((path, "<file>", msg))
            print(f"    ↳ {msg}")
            return {}

    # Format B: flat mapping (slug -> cfg)
    else:
        crafts = data

    result: Dict[str, Dict[str, Any]] = {}
    for slug, cfg in crafts.items():
        if not isinstance(cfg, dict):
            msg = (
                f"Craft slug '{slug}' in file {path} must be a dict, "
                f"got {type(cfg).__name__}."
            )
            errors.append((path, str(slug), msg))
            print(f"    ↳ {msg}")
            continue

        result[str(slug)] = cfg

    return result


def validate_craft(
    slug: str,
    craft: Dict[str, Any],
    source_file: Path,
    item_keys: Dict[str, str],
    resource_keys: Dict[str, str],
    card_keys: Dict[str, str],
    warnings: List[str],
    errors: List[Tuple[Path, str, str]],
) -> None:
    """
    Validate a single craft definition.

    Structural errors:
      - missing output block or output.key
      - missing recipe.pattern or recipe.legend
      - recipe.pattern not a list of strings
      - unlock.recipe_card_key missing (every craft must have a recipe card)

    Structural errors are added to `errors` and we skip further checks for
    this craft.

    Warnings (non-blocking):
      - output.key not found in items/resources
      - any legend entry referring to a missing item/resource
      - recipe_card_key not found in cards.yml
      - etc.
    """
    def add_error(msg: str) -> None:
        """Helper to record an error for this craft and stop validation."""
        errors.append((source_file, slug, msg))
        print(f"    ✖ {msg}")

    # Ensure "key" is set (fallback to slug)
    craft_key = (craft.get("key") or slug).strip()
    craft["key"] = craft_key

    # --- Validate output ---
    output = craft.get("output")
    if not isinstance(output, dict):
        add_error("missing or invalid 'output' block.")
        return

    output_key = (output.get("key") or craft_key).strip()
    if not output_key:
        add_error("missing 'output.key'.")
        return

    # --- Validate recipe ---
    recipe = craft.get("recipe")
    if not isinstance(recipe, dict):
        add_error("missing or invalid 'recipe' block.")
        return

    pattern = recipe.get("pattern")
    if not isinstance(pattern, list) or not pattern:
        add_error("'recipe.pattern' must be a non-empty list.")
        return

    if any(not isinstance(row, str) for row in pattern):
        add_error("all 'recipe.pattern' rows must be strings.")
        return

    legend = recipe.get("legend")
    if not isinstance(legend, dict):
        add_error("'recipe.legend' must be a dict.")
        return

    symbols_in_pattern = {ch for row in pattern for ch in row if ch != "."}
    for sym in symbols_in_pattern:
        if sym not in legend:
            add_error(
                f"symbol '{sym}' appears in pattern but is missing from recipe.legend."
            )
            return

    # Validate each legend entry and check references
    for sym, entry in legend.items():
        if not isinstance(entry, dict):
            add_error(f"legend entry for '{sym}' must be a dict.")
            return

        k_kind = (entry.get("kind") or "").strip()
        k_key = (entry.get("key") or "").strip()
        if not k_key:
            add_error(f"legend '{sym}' missing 'key'.")
            return

        qty = entry.get("quantity", 1)
        if isinstance(qty, (int, float)):
            if qty <= 0:
                warnings.append(
                    f"⚠ Craft '{slug}' in {source_file}: legend '{sym}' has "
                    f"non-positive quantity={qty}."
                )
        else:
            warnings.append(
                f"⚠ Craft '{slug}' in {source_file}: legend '{sym}' has "
                f"non-numeric quantity={qty!r}."
            )

        # Reference checks
        if k_kind == "resource":
            if k_key not in resource_keys:
                warnings.append(
                    f"⚠ Craft '{slug}' in {source_file}: legend '{sym}' "
                    f"resource key '{k_key}' not found in resources."
                )
        elif k_kind in ("item", "tool", "weapon", "misc", "consumable"):
            if k_key not in item_keys:
                warnings.append(
                    f"⚠ Craft '{slug}' in {source_file}: legend '{sym}' "
                    f"item key '{k_key}' not found in items."
                )
        else:
            warnings.append(
                f"⚠ Craft '{slug}' in {source_file}: legend '{sym}' has "
                f"unknown kind '{k_kind}'."
            )
    # --- Unlock: every craft must have a recipe card ---
    unlock = craft.get("unlock")
    recipe_card_key = ""

    # Cas 1 : unlock est un dict (format simple)
    if isinstance(unlock, dict):
        recipe_card_key = (unlock.get("recipe_card_key") or "").strip()

    # Cas 2 : unlock est une liste (format "conditions" que tu utilises)
    elif isinstance(unlock, list):
        # On cherche une entrée de type "card" avec un 'key'
        card_entry = None
        for entry in unlock:
            if not isinstance(entry, dict):
                continue
            # convention : type: card + key: recipe_xxx
            if entry.get("type") == "card" and entry.get("key"):
                card_entry = entry
                break

        if card_entry:
            recipe_card_key = (card_entry.get("key") or "").strip()
        else:
            add_error(
                "unlock is a list but contains no card condition "
                "with 'type: card' and 'key: ...'."
            )
            return

    # Cas 3 : rien / type inattendu
    else:
        add_error(
            "missing or invalid 'unlock' block (expected dict or list)."
        )
        return

    if not recipe_card_key:
        add_error("'unlock.recipe_card_key' is required (from dict or card condition).")
        return

    # Check that the recipe card exists (warning only)
    if card_keys and recipe_card_key not in card_keys:
        warnings.append(
            f"⚠ Craft '{slug}' in {source_file}: recipe_card_key '{recipe_card_key}' "
            f"not found in cards.yml."
        )


    # Optional sanity on craft_time_seconds
    ctime = craft.get("craft_time_seconds")
    if ctime is not None and not isinstance(ctime, (int, float)):
        warnings.append(
            f"⚠ Craft '{slug}' in {source_file}: craft_time_seconds is not a number "
            f"({ctime!r})."
        )

    # Output existence check (warning only)
    output_found = False
    if output_key in item_keys:
        output_found = True
    if output_key in resource_keys:
        output_found = True
    if not output_found:
        warnings.append(
            f"⚠ Craft '{slug}' in {source_file}: output key '{output_key}' "
            f"not found in items or resources."
        )


# ---------------------------------------------------------------------------
# Build merged YAML
# ---------------------------------------------------------------------------

def build_merged_yaml(all_crafts: Dict[str, Dict[str, Any]]) -> str:
    """
    Build the final crafts.yml content.

    Structure:
      crafts:
        slug_a: { ... }
        slug_b: { ... }

    Slugs are sorted alphabetically for readability.
    """
    lines: List[str] = []
    lines.append("# NOTE:")
    lines.append("#   This file is GENERATED by app/data/crafts/normalize_crafts_yaml.py.")
    lines.append("#   Do NOT edit this file by hand; edit fragments in app/data/crafts/ instead.")
    lines.append("")
    lines.append("crafts:")
    lines.append("")

    for slug in sorted(all_crafts.keys()):
        cfg = all_crafts[slug]
        dumped = yaml.dump({slug: cfg}, sort_keys=False, allow_unicode=True)
        for line in dumped.splitlines():
            lines.append("  " + line)
        lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# HTML report generation
# ---------------------------------------------------------------------------

def generate_html_report(
    errors: List[Tuple[Path, str, str]],
    warnings: List[str],
    output_path: Path,
) -> None:
    """Generate a simple HTML report for craft validation and open it."""
    html: List[str] = []
    html.append("<!DOCTYPE html>")
    html.append("<html lang='en'><head><meta charset='UTF-8' />")
    html.append("<title>LodyLand — Craft Validation Report</title>")
    html.append(
        """
<style>
body {
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  margin: 20px;
  background: #020617;
  color: #e5e7eb;
}
h1 {
  color: #38bdf8;
}
h2 {
  color: #a5b4fc;
  border-bottom: 1px solid #334155;
  padding-bottom: 4px;
  margin-top: 24px;
}
.error {
  background:#7f1d1d;
  padding:10px;
  margin:10px 0;
  border-left:5px solid #ef4444;
}
.warn {
  background:#78350f;
  padding:10px;
  margin:10px 0;
  border-left:5px solid #f59e0b;
}
.path {
  font-size: 12px;
  opacity: 0.8;
}
.code {
  background:#0f172a;
  padding: 2px 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 13px;
}
.section-summary {
  background:#0f172a;
  padding:8px 10px;
  border-radius:4px;
  margin-bottom:12px;
}
</style>
</head><body>
"""
    )

    html.append("<h1>LodyLand — Craft Validation Report</h1>")

    # Summary
    html.append("<div class='section-summary'>")
    html.append(f"<div>❌ <strong>{len(errors)} structural error(s)</strong></div>")
    html.append(f"<div>⚠️ <strong>{len(warnings)} warning(s)</strong></div>")
    html.append("</div>")

    # Errors section
    html.append(f"<h2>❌ Structural errors ({len(errors)})</h2>")
    if errors:
        for file_path, slug, msg in errors:
            html.append("<div class='error'>")
            html.append(
                f"<div><b>Craft:</b> <span class='code'>{slug}</span></div>"
            )
            html.append(
                f"<div><b>File:</b> <span class='path'>{file_path}</span></div>"
            )
            html.append(f"<div><b>Issue:</b> {msg}</div>")
            html.append("</div>")
    else:
        html.append("<p>No structural errors 🎉</p>")

    # Warnings section
    html.append(f"<h2>⚠️ Warnings ({len(warnings)})</h2>")
    if warnings:
        for w in warnings:
            html.append(f"<div class='warn'>{w}</div>")
    else:
        html.append("<p>No warnings.</p>")

    html.append("</body></html>")

    output_path.write_text("\n".join(html), encoding="utf-8")
    try:
        webbrowser.open(str(output_path))
    except Exception:
        # If opening fails, we just ignore; file is still generated.
        pass


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"\nScanning craft YAML under: {CRAFTS_ROOT}\n")

    if not CRAFTS_ROOT.exists():
        raise SystemExit(f"❌ crafts root folder not found: {CRAFTS_ROOT}")

    # Load reference sets
    item_keys = load_item_keys()
    resource_keys = load_resource_keys()
    card_keys = load_card_keys()

    print(f"→ Loaded {len(item_keys)} item key(s) for validation.")
    print(f"→ Loaded {len(resource_keys)} resource key(s) for validation.")
    print(f"→ Loaded {len(card_keys)} card key(s) for validation.\n")

    all_crafts: Dict[str, Dict[str, Any]] = {}
    warnings: List[str] = []
    errors: List[Tuple[Path, str, str]] = []

    for path in CRAFTS_ROOT.rglob("*.yml"):
        # Skip output file and this script itself
        if path == OUTPUT_FILE:
            continue
        if path.name.endswith(".bak"):
            continue
        if path.name == THIS_FILE.name:
            continue

        print(f"  • Loading {path}")

        fragment = load_fragment_crafts(path, errors)
        if not fragment:
            print(f"    ↳ (no crafts found in {path}, skipped)")
            continue

        for slug, cfg in fragment.items():
            # Validate craft (no raise, but may add to errors)
            validate_craft(
                slug,
                cfg,
                path,
                item_keys,
                resource_keys,
                card_keys,
                warnings,
                errors,
            )

            # Only keep craft if no structural error for this slug
            if any(e[0] == path and e[1] == slug for e in errors):
                continue

            if slug in all_crafts:
                print(
                    f"⚠ WARNING: duplicate craft slug '{slug}' "
                    f"in {path} (overwriting previous definition)."
                )

            all_crafts[slug] = cfg

        print(f"    ↳ {len(fragment)} craft(s) loaded (including invalid ones, if any)")

    # If there are structural errors, DO NOT write crafts.yml
    if errors:
        print(
            f"\n❌ {len(errors)} structural error(s) detected. "
            f"crafts.yml was NOT updated.\n"
        )
        report_path = DATA_ROOT / "craft_validation_report.html"
        generate_html_report(errors, warnings, report_path)
        return

    if not all_crafts:
        print("\n⚠ No crafts found at all, nothing to write.\n")
        report_path = DATA_ROOT / "craft_validation_report.html"
        generate_html_report(errors, warnings, report_path)
        return

    print(f"\n✓ All crafts structurally validated successfully ({len(all_crafts)} total)\n")

    # Backup existing crafts.yml if present
    if OUTPUT_FILE.exists():
        backup = OUTPUT_FILE.with_suffix(".yml.bak")
        backup.write_text(OUTPUT_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Backup created: {backup}")

    # Write new merged crafts.yml
    yaml_text = build_merged_yaml(all_crafts)
    OUTPUT_FILE.write_text(yaml_text, encoding="utf-8")

    print(f"✓ crafts.yml generated: {OUTPUT_FILE}")

    # Generate HTML report even in success (0 errors)
    report_path = DATA_ROOT / "craft_validation_report.html"
    generate_html_report(errors, warnings, report_path)
    print(f"\nℹ HTML report written to: {report_path}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        # This is only for unexpected exceptions (we already handle most cases).
        print("\n❌ === UNEXPECTED ERROR ===")
        print(e)
        print("\n✖ Merge aborted due to unexpected error.\n")
