#!/usr/bin/env python
"""
normalize_cards_yaml.py

Strict validator + merger for LodyLand cards.

Goals:
  - Load ALL .yml fragments in app/data/cards/
  - Validate each card strictly (required fields)
  - If ANY structural issue is found → STOP and report errors
  - If all cards are valid → write merged cards.yml

Extras:
  - Empty files (or files with only comments) are ignored.
  - For each card, we check that card_image exists on disk (under app/static/...).
    * If missing → warning + added to missing_card_images.txt

JSON mode:
  - With --json, output a machine-readable summary for the global runner,
    without console spam.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent        # .../app/data/cards
PROJECT_ROOT = SCRIPT_DIR.parent.parent            # .../app
CARDS_ROOT = SCRIPT_DIR                             # .../app/data/cards

OUTPUT_FILE = PROJECT_ROOT / "data" / "cards.yml"
MISSING_IMAGES_FILE = CARDS_ROOT / "missing_card_images.txt"


# ---------------------------------------------------------------------------
# Reporter (no emojis, ASCII-only)
# ---------------------------------------------------------------------------

class Reporter:
    def __init__(self, json_mode: bool = False) -> None:
        self.json_mode = json_mode
        self.infos: List[str] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []

    def _emit(self, msg: str, kind: str) -> None:
        if kind == "info":
            self.infos.append(msg)
        elif kind == "warn":
            self.warnings.append(msg)
        elif kind == "error":
            self.errors.append(msg)

        if self.json_mode:
            # In JSON mode we do not print anything to stdout,
            # only the final JSON at the end.
            return

        # Normal console mode
        if kind == "error":
            print(msg, file=sys.stderr)
        else:
            print(msg)

    def info(self, msg: str) -> None:
        self._emit(msg, "info")

    def warn(self, msg: str) -> None:
        self._emit("WARNING: " + msg, "warn")

    def error(self, msg: str) -> None:
        self._emit("ERROR: " + msg, "error")


# ---------------------------------------------------------------------------
# REQUIRED FIELDS (strict)
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "key",
    "enabled",
    "card_type",
    "card_category",
    "card_tags",
    "card_label",
    "card_description",
    "card_image",
    "card_rarity",
    "card_gameplay",
    "shop",
    "tradable",
    "giftable",
    "card_quantity",
    "card_purchase_limit_quantity",
    "card_max_owned",
]

REQUIRED_SHOP_FIELDS = [
    "prices",
    "show_in_main_shop",
    "show_in_village_shop",
    "buy_rules",
]


# ---------------------------------------------------------------------------
# Loading YAML fragments
# ---------------------------------------------------------------------------

def load_fragment_cards(path: Path) -> List[Dict[str, Any]]:
    """
    Load YAML file and extract a list of card definitions.

    Supports:
      - Format A: [ {...}, {...} ]
      - Format B: { cards: [ {...} ] }

    Empty file (None) -> [].
    """
    text = path.read_text(encoding="utf-8")

    try:
        data = yaml.safe_load(text)
    except Exception as e:
        raise ValueError(f"ERROR in YAML syntax: {path}\n{e}")

    if data is None:
        return []

    # Format B: { "cards": [ ... ] }
    if isinstance(data, dict):
        raw_cards = data.get("cards")
        if raw_cards is None:
            return []
        if not isinstance(raw_cards, list):
            raise ValueError(
                f"Invalid file structure in {path}: 'cards:' must contain a list"
            )
        return [c for c in raw_cards if isinstance(c, dict)]

    # Format A: [ {...}, {...} ]
    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict)]

    raise ValueError(
        f"Invalid YAML structure in {path}: expected a dict(cards=…) or a list"
    )


# ---------------------------------------------------------------------------
# Image resolution helper
# ---------------------------------------------------------------------------

def resolve_card_image_path(card_image: str) -> Path:
    """
    Resolve the filesystem path of a card_image value.

    Example:
      card_image: "/static/assets/img/cards/foo.png"
      -> PROJECT_ROOT / "static/assets/img/cards/foo.png"
    """
    img = card_image.strip()
    if img.startswith("/"):
        img = img.lstrip("/")
    return PROJECT_ROOT / img


# ---------------------------------------------------------------------------
# Validation system
# ---------------------------------------------------------------------------

def validate_card(
    card: Dict[str, Any],
    source_file: Path,
    missing_images: List[Tuple[str, str, Path, Path]],
    rep: Reporter,
) -> None:
    """
    Validate required fields for each card.

    Structural issues -> raise ValueError with a clear message.
    Missing image -> warning only (tracked in missing_images).
    """
    key = card.get("key", "<missing>")

    # Required top-level fields
    for field in REQUIRED_FIELDS:
        if field not in card:
            raise ValueError(
                f"Missing field '{field}' in card '{key}' (file: {source_file})"
            )

    # shop block
    shop = card.get("shop")
    if not isinstance(shop, dict):
        raise ValueError(
            f"'shop' block invalid for card '{key}' (file: {source_file})"
        )

    for field in REQUIRED_SHOP_FIELDS:
        if field not in shop:
            raise ValueError(
                f"Missing field 'shop.{field}' in card '{key}' (file: {source_file})"
            )

    # prices
    prices = shop.get("prices")
    if not isinstance(prices, list):
        raise ValueError(
            f"shop.prices must be a list in card '{key}' (file: {source_file})"
        )

    for p in prices:
        if not isinstance(p, dict):
            raise ValueError(
                f"Invalid price entry in card '{key}' (file: {source_file})"
            )
        if "coins" not in p or "diams" not in p or "resources" not in p:
            raise ValueError(
                f"Each price entry must contain coins/diams/resources "
                f"in card '{key}' (file: {source_file})"
            )

    # card_image existence (warning only)
    card_image = card.get("card_image")
    if isinstance(card_image, str) and card_image.strip():
        fs_path = resolve_card_image_path(card_image)
        if not fs_path.exists():
            rep.warn(
                f"image file not found for card '{key}' "
                f"(card_image={card_image}, resolved={fs_path})"
            )
            missing_images.append((key, card_image, fs_path, source_file))


# ---------------------------------------------------------------------------
# Grouping + YAML output
# ---------------------------------------------------------------------------

def group_by_card_type(cards: List[Dict[str, Any]]):
    groups = defaultdict(list)
    for c in cards:
        groups[c.get("card_type", "unknown")].append(c)

    preferred_order = [
        "land_access",
        "land_slot",
        "resource_boost",
        "cooldown_boost",
        "land_loot_boost",
        "xp_boost",
        "pack",
    ]

    extras = sorted(t for t in groups.keys() if t not in preferred_order)
    return groups, preferred_order + extras


def card_to_yaml_lines(card: Dict[str, Any]) -> List[str]:
    dumped = yaml.dump(card, sort_keys=False, allow_unicode=True).splitlines()
    first = "- " + dumped[0]
    rest = ["  " + line for line in dumped[1:]]
    return [first] + rest


def build_merged_yaml(cards: List[Dict[str, Any]]) -> str:
    groups, order = group_by_card_type(cards)

    lines: List[str] = []
    lines.append("# NOTE:")
    lines.append("#   This file is GENERATED by app/data/cards/normalize_cards_yaml.py.")
    lines.append("#   Do NOT edit this file by hand; edit fragments in app/data/cards/ instead.")
    lines.append("")
    lines.append("cards:")
    lines.append("")

    for ctype in order:
        items = groups.get(ctype)
        if not items:
            continue

        title = ctype.upper().replace("_", " ")

        lines += [
            "",
            "# ============================================================",
            f"# {title} CARDS",
            f"# card_type: {ctype}",
            "# ============================================================",
            "",
        ]

        for c in sorted(items, key=lambda x: x.get("key", "")):
            lines += card_to_yaml_lines(c)
            lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main(json_mode: bool = False) -> int:
    rep = Reporter(json_mode=json_mode)
    all_cards: List[Dict[str, Any]] = []
    missing_images: List[Tuple[str, str, Path, Path]] = []
    structural_errors: List[str] = []

    rep.info("")
    rep.info(f"Scanning YAML under: {CARDS_ROOT}")
    rep.info("")

    for path in CARDS_ROOT.rglob("*.yml"):
        # Skip script, final output, debug, backups
        if path.name in ("normalize_cards_yaml.py", OUTPUT_FILE.name):
            continue
        if path.name.endswith(".bak"):
            continue
        if "debug" in path.parts:
            continue

        rep.info(f"  • Loading {path}")

        try:
            cards = load_fragment_cards(path)
        except ValueError as e:
            msg = f"{e}"
            structural_errors.append(msg)
            rep.error(msg)
            continue

        if not cards:
            rep.info(f"    -> (no cards found in {path}, skipped)")
            continue

        # Validate each card
        for c in cards:
            try:
                validate_card(c, path, missing_images, rep)
            except ValueError as e:
                msg = f"{e}"
                structural_errors.append(msg)
                rep.error(msg)

        # If there were structural errors for this file, do not include its cards
        if structural_errors and any(str(path) in err for err in structural_errors):
            rep.error(f"    -> structural errors detected in {path}, cards not added.")
            continue

        all_cards.extend(cards)
        rep.info(f"    -> {len(cards)} card(s) loaded and validated")

    if structural_errors:
        rep.error(
            f"\n{len(structural_errors)} structural error(s) detected. "
            "cards.yml was NOT updated.\n"
        )

        if json_mode:
            payload = {
                "script": "normalize_cards_yaml.py",
                "ok": False,
                "errors": structural_errors,
                "warnings": rep.warnings,
                "cards_count": len(all_cards),
                "missing_images_count": len(missing_images),
            }
            print(json.dumps(payload, ensure_ascii=True, indent=2))
        return 1

    if not all_cards:
        rep.warn("No cards found at all, nothing to write.")
        if json_mode:
            payload = {
                "script": "normalize_cards_yaml.py",
                "ok": True,
                "errors": [],
                "warnings": rep.warnings,
                "cards_count": 0,
                "missing_images_count": len(missing_images),
            }
            print(json.dumps(payload, ensure_ascii=True, indent=2))
        return 0

    rep.info(
        f"\nAll cards structurally validated successfully ({len(all_cards)} total)\n"
    )

    # Backup
    if OUTPUT_FILE.exists():
        backup = OUTPUT_FILE.with_suffix(".yml.bak")
        backup.write_text(OUTPUT_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        rep.info(f"Backup created: {backup}")

    # Write merged YAML
    yaml_text = build_merged_yaml(all_cards)
    OUTPUT_FILE.write_text(yaml_text, encoding="utf-8")
    rep.info(f"cards.yml generated: {OUTPUT_FILE}")

    # Missing images report
    if missing_images:
        rep.warn(
            f"{len(missing_images)} image(s) missing. Writing report to {MISSING_IMAGES_FILE}."
        )
        lines: List[str] = []
        for key, card_image, fs_path, source_file in missing_images:
            lines.append(
                f"card_key={key} | card_image={card_image} | "
                f"resolved_path={fs_path} | source_file={source_file}"
            )
        MISSING_IMAGES_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        rep.info(f"Missing images report written to: {MISSING_IMAGES_FILE}")
    else:
        rep.info("All card_image files exist on disk.")

    if json_mode:
        payload = {
            "script": "normalize_cards_yaml.py",
            "ok": True,
            "errors": [],
            "warnings": rep.warnings,
            "cards_count": len(all_cards),
            "missing_images_count": len(missing_images),
        }
        print(json.dumps(payload, ensure_ascii=True, indent=2))

    return 0


if __name__ == "__main__":
    json_mode = "--json" in sys.argv
    try:
        code = main(json_mode=json_mode)
    except Exception as e:  # noqa: BLE001
        # Unexpected error: send something clean for the runner
        if json_mode:
            payload = {
                "script": "normalize_cards_yaml.py",
                "ok": False,
                "errors": [f"UNEXPECTED ERROR: {e}"],
                "warnings": [],
                "cards_count": 0,
                "missing_images_count": 0,
            }
            print(json.dumps(payload, ensure_ascii=True, indent=2))
        else:
            print("\nERROR: unexpected exception in normalize_cards_yaml.py", file=sys.stderr)
            print(e, file=sys.stderr)
        code = 1
    sys.exit(code)
