#!/usr/bin/env python3
"""
Normalize all level definition fragments into a single app/data/levels.yml file.

Usage:
    python app/data/levels/normalize_levels_yaml.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml


def load_levels_from_file(path: Path) -> List[Dict[str, Any]]:
    """Load a YAML file and return its 'levels' list.

    - Empty files (or files that parse to empty YAML) are ignored (return []).
    - Non-empty files MUST have a top-level 'levels' key (or we raise).
    """
    text = path.read_text(encoding="utf-8")

    # If the file is completely empty or only whitespace -> ignore it
    if not text.strip():
        return []

    data = yaml.safe_load(text)

    # If YAML is empty (None / {}), we also treat it as "no levels"
    if not data:
        return []

    if "levels" not in data:
        raise ValueError(f"{path}: missing top-level 'levels' key")

    if not isinstance(data["levels"], list):
        raise ValueError(f"{path}: 'levels' must be a list")

    return data["levels"]


def main() -> int:
    # Base directory: where this script lives (app/data/levels)
    base_dir = Path(__file__).resolve().parent

    # Output file (generated) -> app/data/levels.yml
    output_path = base_dir.parent / "levels.yml"

    # Collect all *.yml files in app/data/levels/ (fragments only)
    yaml_files = sorted(base_dir.glob("*.yml"))

    if not yaml_files:
        print("No level fragment files (*.yml) found.", file=sys.stderr)
        return 1

    all_levels: Dict[int, Dict[str, Any]] = {}

    for path in yaml_files:
        
        if path.name == "levels.yml":
            continue
        
        # We never want to read the generated file as a fragment
        if path == output_path:
            continue

        try:
            levels = load_levels_from_file(path)
        except Exception as exc:  # noqa: BLE001
            print(f"Error in {path}: {exc}", file=sys.stderr)
            return 1

        # Empty or "no levels" -> skip silently
        if not levels:
            continue

        for lvl in levels:
            if not isinstance(lvl, dict):
                print(f"{path}: invalid level entry (not a mapping)", file=sys.stderr)
                return 1

            if "level" not in lvl:
                print(f"{path}: level entry without 'level' field", file=sys.stderr)
                return 1

            try:
                level_number = int(lvl["level"])
            except Exception:
                print(f"{path}: 'level' must be an integer: {lvl['level']}", file=sys.stderr)
                return 1

            if level_number in all_levels:
                # You can decide to merge instead, but failing fast is safer.
                print(
                    f"Duplicate definition for level {level_number} "
                    f"(already defined in another file).",
                    file=sys.stderr,
                )
                return 1

            all_levels[level_number] = lvl

    # Build final ordered list of levels
    ordered_levels: List[Dict[str, Any]] = [
        all_levels[n] for n in sorted(all_levels.keys())
    ]

    final_data = {"levels": ordered_levels}

    # Write final YAML
    with output_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            final_data,
            f,
            sort_keys=False,       # keep keys in our order
            allow_unicode=True,    # keep accents
            default_flow_style=False,
        )

    print(f"Generated {output_path} with {len(ordered_levels)} levels.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
