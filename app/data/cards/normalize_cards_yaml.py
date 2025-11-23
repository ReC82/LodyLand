"""
normalize_cards_yaml.py

Strict validator + merger for LodyLand cards.

Goals:
  - Load ALL .yml fragments in app/data/cards/
  - Validate each card strictly (required fields)
  - If ANY structural issue is found → STOP and print clear errors
  - If all cards are valid → write merged cards.yml

Extras:
  - Empty files (or files with only comments) are ignored.
  - For each card, we check that card_image exists on disk (under app/static/...).
    * If missing → warning + added to missing_card_images.txt
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any, Dict, List, Tuple
from collections import defaultdict

# Root where fragment YAML files live
CARDS_ROOT = Path("app/data/cards")
# Final merged file
OUTPUT_FILE = Path("app/data/cards.yml")
# Where to write missing images report
MISSING_IMAGES_FILE = CARDS_ROOT / "missing_card_images.txt"

# Root of the project (for resolving /static/ paths)
PROJECT_ROOT = Path("app")  # on part du principe que tu lances depuis la racine du projet


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

# Shop fields required inside shop:
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

    Special:
      - Empty file or file with only comments → returns [] (ignored).
    """
    text = path.read_text(encoding="utf-8")

    try:
        data = yaml.safe_load(text)
    except Exception as e:
        raise ValueError(f"❌ ERROR in YAML syntax: {path}\n{e}")

    # Empty file or only comments → ignore
    if data is None:
        return []

    # Format B: { "cards": [ ... ] }
    if isinstance(data, dict):
        raw_cards = data.get("cards")
        if raw_cards is None:
            # Dict sans clé "cards" → on considère qu'il n'y a pas de cartes
            return []
        if not isinstance(raw_cards, list):
            raise ValueError(
                f"❌ Invalid file structure in {path}: 'cards:' must contain a list"
            )
        return [c for c in raw_cards if isinstance(c, dict)]

    # Format A: [ {...}, {...} ]
    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict)]

    # Unknown structure → vraie erreur
    raise ValueError(
        f"❌ Invalid YAML structure in {path}: expected a dict(cards=…) or a list"
    )


# ---------------------------------------------------------------------------
# Image resolution helper
# ---------------------------------------------------------------------------

def resolve_card_image_path(card_image: str) -> Path:
    """
    Resolve the filesystem path of a card_image value.

    Convention:
      - card_image: "/static/assets/img/cards/foo.png"
        -> PROJECT_ROOT / "static/assets/img/cards/foo.png"
    """
    img = card_image.strip()

    # If it starts with /static/, we strip the leading slash and prefix with app/
    if img.startswith("/"):
        img = img.lstrip("/")  # "static/assets/img/cards/foo.png"

    # On suppose que tout ce qui vient de YAML est relatif à app/
    return PROJECT_ROOT / img


# ---------------------------------------------------------------------------
# Validation system
# ---------------------------------------------------------------------------

def validate_card(
    card: Dict[str, Any],
    source_file: Path,
    missing_images: List[Tuple[str, str, Path, Path]],
) -> None:
    """
    Validate required fields for each card.
    Raise ValueError with a clear message if something is wrong structurally.

    For images:
      - If image file does not exist → add to missing_images + print warning.
    """
    key = card.get("key", "<missing>")

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in card:
            raise ValueError(
                f"❌ Missing field '{field}' in card '{key}' (file: {source_file})"
            )

    # Validate shop block
    shop = card.get("shop")
    if not isinstance(shop, dict):
        raise ValueError(
            f"❌ 'shop' block invalid for card '{key}' (file: {source_file})"
        )

    for field in REQUIRED_SHOP_FIELDS:
        if field not in shop:
            raise ValueError(
                f"❌ Missing field 'shop.{field}' in card '{key}' (file: {source_file})"
            )

    # Validate prices
    prices = shop.get("prices")
    if not isinstance(prices, list):
        raise ValueError(
            f"❌ shop.prices must be a list in card '{key}' (file: {source_file})"
        )

    for p in prices:
        if not isinstance(p, dict):
            raise ValueError(
                f"❌ Invalid price entry in card '{key}' (file: {source_file})"
            )
        if "coins" not in p or "diams" not in p or "resources" not in p:
            raise ValueError(
                f"❌ Each price entry must contain coins/diams/resources "
                f"in card '{key}' (file: {source_file})"
            )

    # Validate card_image existence on disk (warning only)
    card_image = card.get("card_image")
    if isinstance(card_image, str) and card_image.strip():
        fs_path = resolve_card_image_path(card_image)
        if not fs_path.exists():
            print(
                f"⚠ WARNING: image file not found for card '{key}' "
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

    lines = ["cards:", ""]

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

def main():
    all_cards: List[Dict[str, Any]] = []
    missing_images: List[Tuple[str, str, Path, Path]] = []

    print(f"\nScanning YAML under: {CARDS_ROOT}\n")

    for path in CARDS_ROOT.rglob("*.yml"):
        # Skip script and final output
        if path.name in ("normalize_cards_yaml.py", OUTPUT_FILE.name):
            continue
        if path.name.endswith(".bak"):
            continue
        if "debug" in path.parts:
            continue

        print(f"  • Loading {path}")

        cards = load_fragment_cards(path)

        if not cards:
            print(f"    ↳ (no cards found in {path}, skipped)")
            continue

        # Validate each card
        for c in cards:
            validate_card(c, path, missing_images)

        all_cards.extend(cards)
        print(f"    ↳ {len(cards)} card(s) loaded and validated")

    if not all_cards:
        print("\n⚠ No cards found at all, nothing to write.\n")
        return

    print(f"\n✓ All cards structurally validated successfully ({len(all_cards)} total)\n")

    # Backup if needed
    if OUTPUT_FILE.exists():
        backup = OUTPUT_FILE.with_suffix(".yml.bak")
        backup.write_text(OUTPUT_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Backup created: {backup}")

    # Write new merged file
    yaml_text = build_merged_yaml(all_cards)
    OUTPUT_FILE.write_text(yaml_text, encoding="utf-8")

    print(f"✓ cards.yml generated: {OUTPUT_FILE}")

    # Handle missing images report
    if missing_images:
        print(f"\n⚠ {len(missing_images)} image(s) missing. Writing report to {MISSING_IMAGES_FILE}…")
        lines: List[str] = []
        for key, card_image, fs_path, source_file in missing_images:
            lines.append(
                f"card_key={key} | card_image={card_image} | "
                f"resolved_path={fs_path} | source_file={source_file}"
            )
        MISSING_IMAGES_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"⚠ Missing images report written to: {MISSING_IMAGES_FILE}")
    else:
        print("\n✓ All card_image files exist on disk.\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\n❌ === ERROR ===")
        print(e)
        print("\n✖ Merge aborted due to errors.\n")
