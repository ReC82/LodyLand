import yaml
from pathlib import Path
from sqlalchemy import delete
from .db import SessionLocal
from .models import ResourceDef

DATA_PATH = Path(__file__).parent / "data" / "resources.yml"

def reseed_resources():
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Missing {DATA_PATH}")

    payload = yaml.safe_load(DATA_PATH.read_text(encoding="utf-8")) or {}
    items = payload.get("resources", [])

    with SessionLocal() as s:
        s.execute(delete(ResourceDef))  # reset soft
        for it in items:
            s.add(ResourceDef(
                key=it["key"],
                label=it.get("label", it["key"].title()),
                base_cooldown=int(it.get("base_cooldown", 10)),
                base_sell_price=int(it.get("base_sell_price", 1)),
                unlock_min_level=int(it.get("unlock_min_level", 0)),
                enabled=bool(it.get("enabled", True)),
            ))
        s.commit()
        return len(items)
