#!/usr/bin/env python
"""
normalize_lands_yaml.py

Bridge script pour les lands de LodyLand.

Objectif :
  - Scanner app/data/lands/*.yml
  - Fusionner toutes les définitions en un seul fichier :
        app/data/lands.yml

Format d'entrée attendu (app/data/lands/*.yml) :

  beach:
    key: land_beach
    ...
  forest:
    card_key: land_forest
    ...
  lake:
    key: land_lake
    ...

OU éventuellement :

  lands:
    beach:
      ...
    forest:
      ...

Dans tous les cas, le fichier généré app/data/lands.yml est *plat* :

  beach:
    ...
  forest:
    ...
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
# .../app/data/lands/normalize_lands_yaml.py
DATA_ROOT = THIS_FILE.parents[2] / "data"    # app/data
LANDS_ROOT = DATA_ROOT / "lands"             # app/data/lands
OUTPUT_FILE = DATA_ROOT / "lands.yml"        # app/data/lands.yml


# ---------------------------------------------------------------------------
# Reporter (simplifié, même pattern que pour les items)
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
        if not msg.startswith("⚠"):
            msg = "⚠ " + msg
        self.warnings.append(msg)
        if not self.json_mode:
            print(msg)

    def error(self, msg: str) -> None:
        if not msg.startswith("❌"):
            msg = "❌ " + msg
        self.errors.append(msg)
        if not self.json_mode:
            print(msg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_lands_from_file(path: Path, rep: Reporter) -> Dict[str, Dict[str, Any]]:
    """
    Charge les lands d’un fichier YAML.

    - Si le fichier contient un bloc 'lands', on l’utilise en priorité :
        lands:
          beach: {...}
          forest: {...}

    - Sinon on considère que le fichier est déjà un mapping plat :
        beach: {...}
        forest: {...}

    Retourne : { slug: cfg }
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"ERROR in YAML syntax: {path}\n{e}") from e

    if data is None:
        rep.info(f"    ↳ (empty YAML in {path}, skipped)")
        return {}

    if not isinstance(data, dict):
        raise ValueError(
            f"Invalid top-level structure in {path}: expected a mapping, "
            f"got {type(data).__name__}."
        )

    # Préférence pour un bloc "lands", sinon mapping plat
    lands_block = data.get("lands")
    if lands_block is None:
        lands_block = data

    if not isinstance(lands_block, dict):
        raise ValueError(
            f"Invalid 'lands' structure in {path}: expected a dict, got "
            f"{type(lands_block).__name__}."
        )

    result: Dict[str, Dict[str, Any]] = {}

    for slug, cfg in lands_block.items():
        if not isinstance(cfg, dict):
            raise ValueError(
                f"Land '{slug}' in {path} must be a dict, got {type(cfg).__name__}."
            )

        # slug = 'beach', 'forest', 'lake', 'village', ...
        # On NE TOUCHE PAS au contenu de 'key' si déjà présent.
        # On se contente de le remplir si absent, avec le slug.
        if "key" not in cfg or cfg.get("key") in (None, ""):
            cfg["key"] = str(slug)

        result[str(slug)] = cfg

    return result


def _collect_all_lands(rep: Reporter) -> Dict[str, Dict[str, Any]]:
    """
    Scan app/data/lands/*.yml et retourne l’ensemble des lands :

        { slug: cfg }
    """
    if not LANDS_ROOT.exists():
        raise SystemExit(f"❌ lands root folder not found: {LANDS_ROOT}")

    all_lands: Dict[str, Dict[str, Any]] = {}

    rep.info(f"\nScanning land YAML under: {LANDS_ROOT}\n")

    for path in sorted(LANDS_ROOT.glob("*.yml")):
        # Ignore backups
        if path.name.endswith(".bak"):
            continue
        # Évite de se charger soi-même par accident
        if path.name.startswith("normalize_"):
            continue

        rep.info(f"  • Loading {path}")

        fragment = _load_lands_from_file(path, rep)

        if not fragment:
            rep.info(f"    ↳ (no lands found in {path}, skipped)")
            continue

        for slug, cfg in fragment.items():
            if slug in all_lands:
                rep.warn(
                    f"WARNING: duplicate land slug '{slug}' from {path} "
                    f"(overwriting previous definition)."
                )
            all_lands[slug] = cfg

        rep.info(f"    ↳ {len(fragment)} land(s) loaded")

    rep.info(f"\n→ Collected {len(all_lands)} land(s) in total.\n")
    return all_lands


def _lands_to_yaml_text(all_lands: Dict[str, Dict[str, Any]]) -> str:
    """
    Convertit le dict global {slug: cfg} en texte YAML pour lands.yml.

    Forme cible :

        # NOTE: ...
        beach:
          key: land_beach
          ...
        forest:
          ...
    """
    lines: List[str] = []
    lines.append("# NOTE:")
    lines.append("#   This file is GENERATED by app/data/lands/normalize_lands_yaml.py.")
    lines.append("#   Do NOT edit this file by hand.")
    lines.append("#   Edit land definitions in app/data/lands/*.yml instead.")
    lines.append("")

    # On dump directement le mapping plat
    yaml_block = yaml.dump(all_lands, sort_keys=False, allow_unicode=True)
    lines.append(yaml_block.rstrip())

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
    lands: Dict[str, Dict[str, Any]] = {}
    structural_error_msg: str | None = None

    try:
        lands = _collect_all_lands(rep)
        if not lands:
            rep.warn("No lands found at all, nothing to write.")
    except SystemExit as e:
        ok = False
        structural_error_msg = str(e)
    except Exception as e:  # noqa: BLE001
        ok = False
        structural_error_msg = str(e)

    if not ok and structural_error_msg:
        rep.error(structural_error_msg)

    land_count = len(lands)

    # Écriture de lands.yml
    if ok and lands:
        yaml_text = _lands_to_yaml_text(lands)
        rep.info(f"→ Will write {land_count} land(s) to {OUTPUT_FILE}")

        # Backup si fichier existant
        if OUTPUT_FILE.exists():
            backup = OUTPUT_FILE.with_suffix(".yml.bak")
            backup.write_text(
                OUTPUT_FILE.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            rep.info(f"Backup created: {backup}")

        OUTPUT_FILE.write_text(yaml_text, encoding="utf-8")
        rep.info(f"✓ lands.yml generated at {OUTPUT_FILE}\n")
    elif ok and not lands:
        rep.warn("No lands found; lands.yml will not be updated.")

    report = {
        "script": "normalize_lands_yaml.py",
        "ok": bool(ok and (structural_error_msg is None)),
        "output_file": str(OUTPUT_FILE),
        "land_count": land_count,
        "errors": rep.errors if structural_error_msg or rep.errors else [],
        "warnings": rep.warnings,
        "infos": rep.infos,
    }

    if json_mode:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        if not report["ok"]:
            print("\n❌ === ERROR ===")
            for msg in rep.errors:
                print("  -", msg)
            print("\n✖ Generation aborted due to errors.\n")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
