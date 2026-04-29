# =============================================================================
# File: seed_cards.py
# Purpose: Load cards.yml (new card_* format) → populate card_defs table
# =============================================================================
from __future__ import annotations

import yaml
from pathlib import Path

from app.db import SessionLocal
from app.models import CardDef

CARDS_FILE = Path("app/data/cards.yml")


def seed_cards_from_yaml() -> None:
    """Load cards.yml (new format) and sync card_defs table (dev mode)."""
    if not CARDS_FILE.exists():
        print("cards.yml missing → skipping card seed")
        return

    with CARDS_FILE.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    cards = raw.get("cards") or []
    if not cards:
        print("⚠ cards.yml contains no cards")
        return

    with SessionLocal() as s:
        # En dev, on efface tout et on recrée proprement
        s.query(CardDef).delete()
        s.commit()

        for cfg in cards:
            key = cfg["key"]

            # Support both short field names (type, label, rarity…) used by the
            # admin YAML format and the legacy card_* prefixed names.
            def _f(short: str, long: str | None = None, default=None):
                """Read short name first, fall back to long (card_*) name."""
                v = cfg.get(short)
                if v is None and long:
                    v = cfg.get(long)
                return v if v is not None else default

            label = (_f("label_fr") or _f("label") or _f("card_label") or key)
            desc  = _f("description_fr") or _f("description") or _f("card_description")
            ctype = _f("type") or _f("card_type") or "unknown"

            cd = CardDef(
                key=key,
                enabled=cfg.get("enabled", True),

                card_type=ctype,
                card_category=_f("category", "card_category"),
                card_tags=_f("tags", "card_tags"),

                card_label=label,
                card_description=desc,
                card_image=_f("image", "card_image"),
                card_rarity=_f("rarity", "card_rarity"),

                card_gameplay=_f("gameplay", "card_gameplay"),
                shop=cfg.get("shop"),

                tradable=cfg.get("tradable", False),
                giftable=cfg.get("giftable", True),
                card_quantity=cfg.get("card_quantity", 0),
                card_purchase_limit_quantity=cfg.get("card_purchase_limit_quantity"),
                card_max_owned=cfg.get("card_max_owned"),

                unlock_rules=_f("unlock_rules"),
            )
            s.add(cd)
            s.commit()

        print(f"✓ Loaded {len(cards)} cards from cards.yml")
