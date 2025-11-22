"""
normalize_cards_yaml.py

Utility to migrate/normalize LodyLand cards YAML to the new schema:
- card_type / card_category / card_tags
- card_* fields (label, description, image, rarity, gameplay)
- shop structure (prices + flags)
- root-level tradable / giftable / quantity / limits
"""

import yaml
from copy import deepcopy
from pathlib import Path
from collections import defaultdict

# Adjust this path if needed
CARDS_PATH = Path("cards.yml")  # ou Path("cards.yml")


def load_cards():
    """Load current cards.yml and return the list of cards."""
    with CARDS_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("cards", [])


def infer_category(card_type: str) -> str | None:
    """Infer card_category from card_type."""
    if card_type in ("land_access", "land_slot"):
        return "land"
    if card_type in ("resource_boost", "cooldown_boost", "xp_boost", "land_loot_boost"):
        return "boost"
    return None


def build_tags(key: str | None, gameplay: dict | None) -> list[str]:
    """Create simple tags from key + gameplay (land/resource)."""
    tags = set()

    gp = gameplay or {}
    if isinstance(gp, dict):
        for k, v in gp.items():
            if isinstance(v, dict):
                for kk in ("target_land", "land", "resource_key", "target_resource"):
                    if kk in v and v[kk]:
                        tags.add(str(v[kk]))
            else:
                if k in ("target_land", "land", "resource_key", "target_resource") and v:
                    tags.add(str(v))

    if key:
        if key.startswith("land_"):
            tags.add("land")
        for name in ("forest", "beach", "lake", "desert", "cave", "mountain", "farm", "village"):
            if name in key:
                tags.add(name)

    return sorted(tags)


def normalize_card(old_card: dict) -> dict:
    """Transform one old card dict into the new schema."""
    c = deepcopy(old_card)

    new = {}

    # --- basic fields ---
    new["key"] = c.get("key")
    enabled = c.get("enabled", c.get("shop", {}).get("enabled", True))
    new["enabled"] = bool(enabled)

    card_type = c.get("type")
    new["card_type"] = card_type
    new["card_category"] = infer_category(card_type)

    gameplay = c.get("gameplay") or {}
    new["card_tags"] = build_tags(new["key"], gameplay)

    # We keep current human-readable labels for now
    new["card_label"] = c.get("label")
    new["card_description"] = c.get("description")
    new["card_image"] = c.get("icon")
    new["card_rarity"] = c.get("rarity")

    new["card_gameplay"] = gameplay

    # --- shop and prices ---
    shop = c.get("shop") or {}
    root_buy_rules = c.get("buy_rules", None)
    buy_rules = shop.get("buy_rules", root_buy_rules)

    raw_prices = c.get("prices", [])
    normalized_prices = []

    for p in raw_prices:
        if p is None:
            continue
        coins = p.get("coins", 0)
        diams = p.get("diams", 0)
        resources = p.get("resources", {})
        if resources is None:
            resources = {}
        normalized_prices.append(
            {
                "coins": coins,
                "diams": diams,
                "resources": resources,
            }
        )

    if not normalized_prices:
        normalized_prices = [{"coins": 0, "diams": 0, "resources": {}}]

    new["shop"] = {
        "prices": normalized_prices,
        "show_in_main_shop": shop.get("show_in_main_shop", False),
        "show_in_village_shop": shop.get("show_in_village_shop", False),
        "buy_rules": buy_rules,
    }

    # --- economy / limits ---
    new["tradable"] = shop.get("tradable", False)
    new["giftable"] = shop.get("giftable", True)

    new["card_quantity"] = shop.get("quantity", 0)
    new["card_purchase_limit_quantity"] = shop.get("purchase_limit", None)
    new["card_max_owned"] = shop.get("max_owned", 1)

    return new


def group_by_type(cards: list[dict]):
    """Group cards by card_type for nice sections in YAML."""
    groups_def = [
        ("land_access", "LAND ACCESS CARDS", "Cards that unlock new lands"),
        ("land_slot", "LAND SLOT CARDS", "Cards that add extra slots on lands"),
        ("cooldown_boost", "COOLDOWN BOOST CARDS", "Cards that reduce cooldown on resources"),
        ("resource_boost", "RESOURCE BOOST CARDS", "Cards that increase harvested amount for a resource"),
        ("land_loot_boost", "LAND LOOT BOOST CARDS", "Cards that boost loot on a specific land"),
        ("xp_boost", "XP BOOST CARDS", "Cards that boost XP gained"),
    ]
    groups = defaultdict(list)
    for c in cards:
        groups[c.get("card_type")].append(c)
    return groups_def, groups


def card_to_yaml_lines(card: dict) -> list[str]:
    """Dump one card as a YAML list item with '- ' prefix."""
    dumped = yaml.dump(card, sort_keys=False, allow_unicode=True).splitlines()
    if not dumped:
        return []
    first = "- " + dumped[0]
    rest = ["  " + line for line in dumped[1:]]
    return [first] + rest


def build_yaml_text(cards: list[dict]) -> str:
    """Build the final YAML text with sections and all cards."""
    groups_def, groups = group_by_type(cards)

    lines: list[str] = []
    lines.append("cards:")
    lines.append("")

    for gid, title, desc in groups_def:
        group_cards = sorted(
            (c for c in groups.get(gid, []) if c.get("card_type") == gid),
            key=lambda c: (c.get("card_category") or "", c.get("key") or "")
        )
        if not group_cards:
            continue

        lines.append("")
        lines.append("# ============================================================")
        lines.append(f"# {title}")
        lines.append(f"# {desc}")
        lines.append(f"# card_type: {gid}")
        if gid in ("land_access", "land_slot"):
            lines.append("# card_category: land")
        elif gid in ("resource_boost", "cooldown_boost", "xp_boost", "land_loot_boost"):
            lines.append("# card_category: boost")
        lines.append("# ============================================================")
        lines.append("")

        for card in group_cards:
            lines.extend(card_to_yaml_lines(card))
            lines.append("")

    return "\n".join(lines) + "\n"


def main():
    """Main entry point for normalization script."""
    original_cards = load_cards()
    normalized_cards = [normalize_card(c) for c in original_cards]
    yaml_text = build_yaml_text(normalized_cards)

    # Backup
    backup_path = CARDS_PATH.with_suffix(".yml.bak")
    backup_path.write_text(CARDS_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    # Write new file
    CARDS_PATH.write_text(yaml_text, encoding="utf-8")

    print(f"Done. Normalized cards written to {CARDS_PATH}")
    print(f"Backup created at {backup_path}")


if __name__ == "__main__":
    main()
