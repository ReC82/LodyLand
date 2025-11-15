# File: app/seed.py
# Purpose: Charger la config des ressources depuis data/resources.yaml
#          et faire l'upsert dans la table ResourceDef.

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .db import SessionLocal
from .models import ResourceDef

log = logging.getLogger(__name__)

# Emplacement par défaut du YAML

CONFIG_PATH = (
    Path(__file__)
    .resolve()
    .parent        # app/
    / "data"
    / "resources.yml"   # et pas parent.parent / resources.yaml
)

def _default_resources() -> List[Dict[str, Any]]:
  """Fallback si le YAML est manquant ou invalide."""
  return [
      {
          "key": "branch",
          "label": "Branches",
          "base_cooldown": 5,
          "base_sell_price": 1,
          "unlock_min_level": 0,
          "enabled": True,
          "icon": "/static/img/resources/branch.png",
          "description": "Une branche tombée d'un arbre.",
          "unlock_description": "Toujours accessible (niveau 0).",
      },
      {
          "key": "palm_leaf",
          "label": "Palm Leaf",
          "base_cooldown": 6,
          "base_sell_price": 1,
          "unlock_min_level": 0,
          "enabled": True,
          "icon": "/static/img/resources/palm_leaf.png",
          "description": "Une large feuille de palmier, utile pour tisser ou se protéger du soleil.",
          "unlock_description": "Toujours accessible (niveau 0).",
      },
      {
          "key": "stone",
          "label": "Stone",
          "base_cooldown": 8,
          "base_sell_price": 1,
          "unlock_min_level": 2,
          "enabled": True,
          "icon": "/static/img/resources/small_stone.png",
          "description": "Un caillou solide, base de tous les outils sérieux.",
          "unlock_description": "Débloqué au niveau 2.",
      },
      {
          "key": "wood",
          "label": "Wood",
          "base_cooldown": 10,
          "base_sell_price": 2,
          "unlock_min_level": 0,
          "enabled": True,
          "icon": "/static/img/resources/palm_wood.png",
          "description": "Du bois de palmier, ressource de base pour construire et crafter.",
          "unlock_description": "Toujours accessible (niveau 0).",
      },
  ]


def load_resources_config(path: Path | None = None) -> List[Dict[str, Any]]:
    """Charge la config YAML des ressources.

    Retourne une liste de dicts prêts à être upsert en DB.
    En cas de problème, on retourne un set de ressources par défaut.
    """
    path = path or CONFIG_PATH

    if not path.exists():
        log.warning("resources.yaml introuvable (%s), utilisation des defaults.", path)
        return _default_resources()

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        log.error("Erreur lors du chargement de %s: %s", path, e)
        return _default_resources()

    items = raw.get("resources") or []
    if not isinstance(items, list):
        log.error("resources.yaml: 'resources' n'est pas une liste, utilisation des defaults.")
        return _default_resources()

    cleaned: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue

        key = (it.get("key") or "").strip().lower()
        if not key:
            continue

        cleaned.append(
            {
                "key": key,
                "label": it.get("label") or key,
                "base_cooldown": int(it.get("base_cooldown") or 10),
                "base_sell_price": int(it.get("base_sell_price") or 1),
                "unlock_min_level": int(it.get("unlock_min_level") or 0),
                "enabled": bool(it.get("enabled", True)),

                # Front needs these:
                "icon": it.get("icon") or "/static/assets/img/resources/default.png",
                "description": it.get("description") or "",

                # Nice human readable text (used by API for /tiles):
                "unlock_description": it.get("unlock_description") or None,

                # Raw structured rules (JSON column):
                "unlock_rules": it.get("unlock_rules") or None,
            }
        )

    if not cleaned:
        log.warning("resources.yaml ne contient aucune ressource valide, utilisation des defaults.")
        return _default_resources()

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
                row = ResourceDef(**d)
                s.add(row)
                changed += 1
            else:
                row.label = d["label"]
                row.base_cooldown = d["base_cooldown"]
                row.base_sell_price = d["base_sell_price"]
                row.unlock_min_level = d["unlock_min_level"]
                row.enabled = d["enabled"]

                # New fields
                row.icon = d.get("icon", row.icon)
                row.description = d.get("description", row.description)
                row.unlock_description = d.get("unlock_description", row.unlock_description)
                row.unlock_rules = d.get("unlock_rules")

                changed += 1

        s.commit()
        return changed


def ensure_resources_seeded() -> None:
  """Assure que la table ResourceDef est alignée avec le YAML.

  Appelée au démarrage de l'app (create_app).
  """
  cfg = load_resources_config()
  n = _upsert_resources(cfg)
  log.info("ensure_resources_seeded: %s ressources upsertées.", n)


def reseed_resources() -> int:
  """Endpoint 'dev' pour reseeder.

  Pour l'instant, on fait la même chose que ensure_resources_seeded
  et on retourne le nombre de lignes touchées.
  """
  cfg = load_resources_config()
  return _upsert_resources(cfg)
