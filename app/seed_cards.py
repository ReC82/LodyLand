import yaml
from pathlib import Path
from .db import SessionLocal
from .models import CardDef

def seed_cards_from_yaml():
    yaml_path = Path(__file__).with_suffix("") / ".." / "data" / "cards.yml"
    with yaml_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    cards = raw.get("cards", [])

    with SessionLocal() as s:
        existing = {c.key: c for c in s.query(CardDef).all()}

        for d in cards:
            key = d["key"]
            row = existing.get(key)
            if row is None:
                row = CardDef(**d)
                s.add(row)
            else:
                # mise à jour "idempotente"
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
