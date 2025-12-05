# File: app/seed.py
# Purpose: Charger la config des ressources à partir de data/items.yml
#          et faire l'upsert dans la table ResourceDef.

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .db import SessionLocal
from .models import ResourceDef

log = logging.getLogger(__name__)

# Emplacement du YAML MERGE (généré par normalize_items_yaml.py)
CONFIG_PATH = (
    Path(__file__)
    .resolve()
    .parent
    / "data"
    / "items.yml"
)


def load_resources_config_from_items(path: Path | None = None) -> List[Dict[str, Any]]:
    """Charge les définitions "ressource-like" depuis items.yml.

    On lit:
      items:
        key_a:
          kind: resource | treasure | ...
          label: ...
          icon: ...
          base_sell_price: ...
          enabled: true/false
          description: ...
          unlock_description: ...

    On ne garde que les items:
      - kind in {"resource", "treasure"}

    Retourne une liste de dicts prêts à être upsert en ResourceDef.
    """
    path = path or CONFIG_PATH

    if not path.exists():
        msg = f"items.yml introuvable ({path}). Tu as bien lancé normalize_items_yaml.py ?"
        log.error(msg)
        raise FileNotFoundError(msg)

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        msg = f"Erreur lors du chargement de {path}: {e}"
        log.error(msg)
        raise RuntimeError(msg)

    items_map = raw.get("items")
    if not isinstance(items_map, dict):
        msg = (
            f"items.yml invalide ({path}): la clé 'items' doit être un mapping "
            f"key -> cfg."
        )
        log.error(msg)
        raise ValueError(msg)

    cleaned: List[Dict[str, Any]] = []
    for key, cfg in items_map.items():
        if not isinstance(cfg, dict):
            continue

        key_normalized = (cfg.get("key") or str(key)).strip().lower()
        if not key_normalized:
            continue

        kind = (cfg.get("kind") or "resource").strip().lower()
        # On ne garde que les "ressources" et "trésors"
        if kind not in {"resource", "treasure"}:
            continue

        base_sell_price = cfg.get("base_sell_price", cfg.get("sell_price", 0))
        try:
            base_sell_price = int(base_sell_price)
        except Exception:
            base_sell_price = 0

        cleaned.append(
            {
                "key": key_normalized,
                "label": cfg.get("label") or key_normalized,
                "base_sell_price": base_sell_price,
                "enabled": bool(cfg.get("enabled", True)),

                # Front needs these:
                "icon": cfg.get("icon") or "/static/assets/img/resources/default.png",
                "description": cfg.get("description") or "",
                "unlock_description": cfg.get("unlock_description") or None,

                # IMPORTANT: kind pour ResourceDef
                "kind": kind,
            }
        )

    if not cleaned:
        msg = f"items.yml ({path}) ne contient aucune ressource (kind=resource/treasure) valide."
        log.error(msg)
        raise RuntimeError(msg)

    return cleaned


def _upsert_resources(config_items: List[Dict[str, Any]]) -> int:
    with SessionLocal() as s:
        existing = s.query(ResourceDef).all()
        by_key = {r.key: r for r in existing}
        changed = 0

        for d in config_items:
            key = d["key"]
            row = by_key.get(key)

            if row is None:
                # Création
                row = ResourceDef(**d)
                s.add(row)
                changed += 1
            else:
                # Mise à jour
                row.label = d["label"]
                row.base_sell_price = d["base_sell_price"]
                row.enabled = d["enabled"]

                # champs front / texte
                row.icon = d.get("icon", row.icon)
                row.description = d.get("description", row.description)
                row.unlock_description = d.get(
                    "unlock_description", row.unlock_description
                )

                # NEW: kind depuis items.yml
                row.kind = d.get("kind", row.kind)

                changed += 1

        s.commit()
        return changed


def ensure_resources_seeded() -> None:
    """Assure que la table ResourceDef est alignée avec items.yml.

    Appelée au démarrage de l'app (create_app).

    ⚠ Si items.yml est manquant ou invalide, une exception est levée
      dans load_resources_config_from_items et le démarrage de l'app échoue clairement.
    """
    cfg = load_resources_config_from_items()
    n = _upsert_resources(cfg)
    log.info("ensure_resources_seeded: %s ressources upsertées depuis items.yml.", n)


def reseed_resources() -> int:
    """Endpoint 'dev' pour reseeder à partir de items.yml."""
    cfg = load_resources_config_from_items()
    return _upsert_resources(cfg)
