# =============================================================================
# File: seed_cards.py
# Purpose: Load cards.yml (new format) → populate card_defs table
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
        for cfg in cards:
            key = cfg["key"]

            # Delete existing row (dev reset)
            existing = s.query(CardDef).filter_by(key=key).first()
            if existing:
                s.delete(existing)
                s.commit()

            cd = CardDef(
                key=key,
                label=cfg["label"],
                description=cfg.get("description"),
                icon=cfg.get("icon"),

                type=cfg.get("type", "").strip() or "generic",

                target_resource=cfg.get("target_resource"),
                target_building=cfg.get("target_building"),

                max_owned=cfg.get("max_owned"),
                enabled=cfg.get("enabled", True),
                unlock_rules=cfg.get("unlock_rules"),

                categorie=cfg.get("categorie"),
                rarity=cfg.get("rarity"),

                gameplay=cfg.get("gameplay"),
                prices=cfg.get("prices"),
                shop=cfg.get("shop"),
                buy_rules=cfg.get("buy_rules"),
            )

            s.add(cd)
            s.commit()

        print(f"✓ Loaded {len(cards)} cards from cards.yml")