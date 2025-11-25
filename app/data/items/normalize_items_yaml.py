#!/usr/bin/env python
"""
normalize_items_yaml.py

Bridge script for LodyLand items → legacy resources.yml.

Goals:
  - Scan app/data/items/*.yml
  - Collect all items with kind: resource
  - Generate app/data/resources.yml in the LEGACY format used by:
      - ResourceDef / seed_resources_from_yaml()
  - DO NOT touch craft/item logic (that's handled elsewhere)

Expected item structure (in app/data/items/*.yml):

  items:
    branch:
      key: branch
      kind: resource
      label: Branch
      description: A small branch...
      icon: /static/assets/img/resources/branch.png
      unlock_min_level: 0
      base_cooldown: 10.0
      base_sell_price: 2
      enabled: true
      unlock_description: Always available at level 0.

Only items with `kind: resource` are exported to resources.yml.

Extra:
  - With the flag --json, this script outputs a JSON report instead of
    human logs. This is used by a global “normalize_all” runner.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import json
import sys

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

THIS_FILE = Path(__file__).resolve()
# .../app/data/items/normalize_items_yaml.py
DATA_ROOT = THIS_FILE.parents[2] / "data"          # app/data
ITEMS_ROOT = DATA_ROOT / "items"                   # app/data/items
OUTPUT_FILE = DATA_ROOT / "resources.yml"          # app/data/resources.yml


# ---------------------------------------------------------------------------
# Small reporter helper (collect logs + control printing)
# ---------------------------------------------------------------------------

class Reporter:
    def __init__(self, json_mode: bool = False) -> None:
        self.json_mode = json_mode
        self.infos: List[str] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def info(self, msg: str) -> None:
        self.infos.append(msg)
        if not self.json_mode:
            print(msg)

    def warn(self, msg: str) -> None:
        # normalise en "⚠ ..." pour cohérence
        if not msg.startswith("⚠"):
            msg = "⚠ " + msg
        self.warnings.append(msg)
        if not self.json_mode:
            print(msg)

    def error(self, msg: str) -> None:
        # normalise en "❌ ..." pour cohérence
        if not msg.startswith("❌"):
            msg = "❌ " + msg
        self.errors.append(msg)
        if not self.json_mode:
            print(msg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_items_from_file(path: Path, rep: Reporter) -> Dict[str, Dict[str, Any]]:
    """
    Load items from a YAML file.

    Accepted formats:

    A) Standard:

       items:
         slug_a:
           key: ...
           kind: resource
           ...
         slug_b:
           ...

    B) Flat dict (fallback):

       slug_a:
         key: ...
         kind: resource
         ...
       slug_b:
         ...

    Returns a dict { item_key: cfg }.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"ERROR in YAML syntax: {path}\n{e}")

    if data is None:
        rep.info(f"    ↳ (empty YAML in {path}, skipped)")
        return {}

    if not isinstance(data, dict):
        raise ValueError(
            f"Invalid top-level structure in {path}: expected a mapping, "
            f"got {type(data).__name__}."
        )

    # Preferred: "items" block
    items_block = data.get("items")
    if items_block is None:
        # Fallback: consider the whole mapping as slug -> cfg
        items_block = data

    if not isinstance(items_block, dict):
        raise ValueError(
            f"Invalid 'items' structure in {path}: expected a dict, got "
            f"{type(items_block).__name__}."
        )

    result: Dict[str, Dict[str, Any]] = {}

    for slug, cfg in items_block.items():
        if not isinstance(cfg, dict):
            raise ValueError(
                f"Item '{slug}' in {path} must be a dict, got {type(cfg).__name__}."
            )

        key = (cfg.get("key") or str(slug)).strip()
        if not key:
            raise ValueError(
                f"Item '{slug}' in {path} has an empty or missing key."
            )

        if key in result:
            rep.warn(
                f"WARNING: duplicate item key '{key}' in {path} "
                f"(already collected from another entry in the same file)."
            )

        result[key] = cfg

    return result


def _collect_all_items(rep: Reporter) -> Dict[str, Dict[str, Any]]:
    """
    Scan app/data/items/*.yml and return all items as a single dict:

      { item_key: cfg }
    """
    if not ITEMS_ROOT.exists():
        raise SystemExit(f"❌ items root folder not found: {ITEMS_ROOT}")

    all_items: Dict[str, Dict[str, Any]] = {}

    rep.info(f"\nScanning item YAML under: {ITEMS_ROOT}\n")

    for path in sorted(ITEMS_ROOT.glob("*.yml")):
        # Skip backup files if any
        if path.name.endswith(".bak"):
            continue

        rep.info(f"  • Loading {path}")

        try:
            fragment = _load_items_from_file(path, rep)
        except ValueError as e:
            # Re-raise so that main() can mark this as a structural error
            raise

        if not fragment:
            rep.info(f"    ↳ (no items found in {path}, skipped)")
            continue

        for key, cfg in fragment.items():
            if key in all_items:
                rep.warn(
                    f"WARNING: duplicate item key '{key}' from {path} "
                    f"(overwriting previous definition)."
                )
            all_items[key] = cfg

        rep.info(f"    ↳ {len(fragment)} item(s) loaded")

    rep.info(f"\n→ Collected {len(all_items)} item(s) in total.\n")
    return all_items


def _build_legacy_resource_entry(item_key: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a single resource entry for legacy resources.yml from an item cfg.

    Legacy format expects fields:
      key, label, description, icon,
      unlock_min_level, base_cooldown, base_sell_price,
      enabled, unlock_description
    """
    label = (cfg.get("label") or item_key).strip()
    description = cfg.get("description") or ""
    icon = cfg.get("icon") or ""

    # Default values for legacy fields
    unlock_min_level = int(cfg.get("unlock_min_level") or 0)
    base_cooldown = float(cfg.get("base_cooldown") or 10.0)
    # We accept either base_sell_price or sell_price
    base_sell_price = cfg.get("base_sell_price", cfg.get("sell_price", 0))

    try:
        base_sell_price = int(base_sell_price)
    except Exception:
        base_sell_price = 0

    enabled = bool(cfg.get("enabled", True))
    unlock_description = cfg.get("unlock_description") or ""

    entry = {
        "key": item_key,
        "label": label,
        "base_cooldown": base_cooldown,
        "base_sell_price": base_sell_price,
        "unlock_min_level": unlock_min_level,
        "enabled": enabled,
        "icon": icon,
    }

    if description:
        entry["description"] = description
    if unlock_description:
        entry["unlock_description"] = unlock_description

    return entry


def _build_resources_yaml(all_items: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Create the list of legacy resources from collected items.

    Only items with kind: resource are exported.
    """
    resources: List[Dict[str, Any]] = []

    for key, cfg in sorted(all_items.items()):
        kind = (cfg.get("kind") or "").strip().lower()
        if kind != "resource":
            continue
        entry = _build_legacy_resource_entry(key, cfg)
        resources.append(entry)

    return resources


def _resources_to_yaml_text(resources: List[Dict[str, Any]]) -> str:
    """
    Convert a list of resources to the final YAML text for resources.yml.
    """
    lines: List[str] = []
    lines.append("# NOTE:")
    lines.append("#   This file is GENERATED by app/data/items/normalize_items_yaml.py.")
    lines.append("#   Do NOT edit this file by hand.")
    lines.append("#   Edit item definitions in app/data/items/*.yml instead.")
    lines.append("")
    lines.append("resources:")
    lines.append("")

    yaml_block = yaml.dump(resources, sort_keys=False, allow_unicode=True)
    for line in yaml_block.splitlines():
        if not line.strip():
            lines.append(line)
        else:
            lines.append("  " + line)

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    json_mode = "--json" in argv
    rep = Reporter(json_mode=json_mode)

    ok = True
    resources: List[Dict[str, Any]] = []
    structural_error_msg: str | None = None

    try:
        all_items = _collect_all_items(rep)
        if not all_items:
            rep.warn("No items found at all, nothing to write.")
            resources = []
        else:
            resources = _build_resources_yaml(all_items)

    except SystemExit as e:
        # Hard stop (e.g., missing ITEMS_ROOT)
        ok = False
        structural_error_msg = str(e)
    except Exception as e:
        ok = False
        structural_error_msg = str(e)

    if not ok:
        if structural_error_msg:
            rep.error(structural_error_msg)

    resource_count = len(resources)

    # If everything is OK and we have resources, write the file
    if ok and resources:
        yaml_text = _resources_to_yaml_text(resources)
        rep.info(f"→ Will write {resource_count} resource(s) to {OUTPUT_FILE}")

        # Backup existing file if any
        if OUTPUT_FILE.exists():
            backup = OUTPUT_FILE.with_suffix(".yml.bak")
            backup.write_text(OUTPUT_FILE.read_text(encoding="utf-8"), encoding="utf-8")
            rep.info(f"Backup created: {backup}")

        OUTPUT_FILE.write_text(yaml_text, encoding="utf-8")
        rep.info(f"✓ resources.yml generated at {OUTPUT_FILE}\n")
    elif ok and not resources:
        # Pas d’erreur structurelle, mais rien à écrire
        rep.warn("No resource-type items found; resources.yml will not be updated.")

    # Build JSON report (for --json mode or future aggregator)
    report = {
        "script": "normalize_items_yaml.py",
        "ok": bool(ok and (structural_error_msg is None)),
        "output_file": str(OUTPUT_FILE),
        "resource_count": resource_count,
        "errors": rep.errors if structural_error_msg or rep.errors else [],
        "warnings": rep.warnings,
        "infos": rep.infos,
    }

    if json_mode:
        # Pure JSON output, no extra noise
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        # Human-friendly error footer
        if not report["ok"]:
            print("\n❌ === ERROR ===")
            for msg in rep.errors:
                print("  -", msg)
            print("\n✖ Generation aborted due to errors.\n")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
