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

            cd = CardDef(
                key=key,
                enabled=cfg.get("enabled", True),

                card_type=cfg.get("card_type"),
                card_category=cfg.get("card_category"),
                card_tags=cfg.get("card_tags"),

                card_label=cfg.get("card_label"),
                card_description=cfg.get("card_description"),
                card_image=cfg.get("card_image"),
                card_rarity=cfg.get("card_rarity"),

                card_gameplay=cfg.get("card_gameplay"),
                shop=cfg.get("shop"),

                tradable=cfg.get("tradable", False),
                giftable=cfg.get("giftable", True),
                card_quantity=cfg.get("card_quantity", 0),
                card_purchase_limit_quantity=cfg.get("card_purchase_limit_quantity"),
                card_max_owned=cfg.get("card_max_owned"),

                unlock_rules=cfg.get("unlock_rules"),
            )
            s.add(cd)
            s.commit()

        print(f"✓ Loaded {len(cards)} cards from cards.yml")
