# app/data/quests/normalize_quests_yaml.py
"""
Build a single app/data/quests/quests.yml file by scanning all
YAML files inside app/data/quests (subfolders included).

- Input:  app/data/quests/**.yml  (except quests.yml + this script + files starting with "_")
- Output: app/data/quests/quests.yml  with one 'quest_templates' dict

DO NOT EDIT the generated quests.yml by hand.
"""

from __future__ import annotations

from pathlib import Path
import sys
import yaml


# Base dir: app/data/quests
BASE_DIR = Path(__file__).resolve().parent
# Output: app/data/quests/quests.yml
OUTPUT_PATH = BASE_DIR / "quests.yml"


def iter_source_files():
    """Yield all YAML files under app/data/quests/, excluding output and helper files."""
    for path in BASE_DIR.rglob("*.yml"):
        # ignore the generated file
        if path.resolve() == OUTPUT_PATH.resolve():
            continue
        # ignore helper files starting with "_"
        if path.name.startswith("_"):
            continue
        yield path


def main() -> int:
    merged_templates = {}

    for path in iter_source_files():
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            print(f"[normalize_quests] ERROR reading {path}: {exc}", file=sys.stderr)
            continue

        qt_section = raw.get("quest_templates") or {}
        if not isinstance(qt_section, dict):
            print(f"[normalize_quests] {path} has no 'quest_templates' dict, skipped")
            continue

        for yaml_key, tpl in qt_section.items():
            if not isinstance(tpl, dict):
                print(f"[normalize_quests] {path} - quest '{yaml_key}' is not a dict, skipped")
                continue

            template_key = (tpl.get("key") or str(yaml_key)).strip()
            if not template_key:
                print(f"[normalize_quests] {path} - quest '{yaml_key}' has empty key, skipped")
                continue

            if template_key in merged_templates:
                print(
                    f"[normalize_quests] WARNING: duplicate quest key '{template_key}' "
                    f"overwriting previous definition"
                )

            tpl["key"] = template_key
            merged_templates[template_key] = tpl

    # Sort for stable diffs
    merged_templates = dict(sorted(merged_templates.items(), key=lambda kv: kv[0]))

    final_payload = {
        "quest_templates": merged_templates,
    }

    OUTPUT_PATH.write_text(
        yaml.safe_dump(
            final_payload,
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    print(f"[normalize_quests] OK -> {OUTPUT_PATH}")
    print(f"[normalize_quests] Total quests: {len(merged_templates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
