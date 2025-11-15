# app/seed_cards.py
# Safe card seeding: never crash when cards.yml is missing (CI)

from __future__ import annotations

import logging
from pathlib import Path
import yaml

from .db import SessionLocal
from .models import CardDef

log = logging.getLogger(__name__)


def seed_cards_from_yaml() -> int:
    """
    Charge app/data/cards.yml si présent.
    IMPORTANT :
    - En CI (GitHub Actions), le fichier n'existe pas → NE DOIT PAS planter.
    - En local, si cards.yml existe → seed normal.
    - Retourne le nombre de cartes detectées, même si aucun insert.
    """

    # ✔️ Chemin correct : app/data/cards.yml
    yaml_path = (
        Path(__file__).resolve().parent   # app/
        / "data"
        / "cards.yml"
    )

    # ✔️ Si le fichier n'existe pas (cas CI) → on skip
    if not yaml_path.exists():
        log.warning("cards.yml not found (%s) – skipping card seeding.", yaml_path)
        return 0

    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        log.error("Failed to load cards.yml: %s", e)
        return 0

    cards = raw.get("cards", [])
    if not isinstance(cards, list):
        log.error("cards.yml: 'cards' must be a list.")
        return 0

    # ✔️ Si aucun élément → rien à faire
    if not cards:
        log.info("cards.yml contains no cards (empty list).")
        return 0

    # ✔️ Seed réel
    with SessionLocal() as s:
        existing = {c.key: c for c in s.query(CardDef).all()}

        for d in cards:
            key = d["key"]
            row = existing.get(key)

            if row is None:
                # nouvelle carte
                row = CardDef(**d)
                s.add(row)
            else:
                # update idempotent
                row.label = d.get("label", row.label)
                row.description = d.get("description", row.description)
                row.icon = d.get("icon", row.icon)
                row.type = d.get("type", row.type)
                row.target_resource = d.get("target_resource", row.target_resource)
                row.target_building = d.get("target_building", row.target_building)
                row.price_coins = d.get("price_coins", row.price_coins)
                row.price_diams = d.get("price_diams", row.price_diams)
                row.max_owned = d.get("max_owned", row.max_owned)
                row.enabled = d.get("enabled", row.enabled)
                row.unlock_rules = d.get("unlock_rules", row.unlock_rules)

        s.commit()

    log.info("Cards seeded successfully: %d entries.", len(cards))
    return len(cards)
