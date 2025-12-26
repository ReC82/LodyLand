# app/services/xp.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from app.progression import next_threshold, xp_required_for, LEVELS, MAX_LEVEL
from app.models import Player

@dataclass
class LevelUpResult:
    old_level: int
    new_level: int
    level_rewards: List[dict]  # format déjà utilisé par /api/levels (normalized)

def _normalize_level_rewards(level: int) -> List[dict]:
    # Ici vous pouvez réutiliser exactement la logique de /levels,
    # ou mieux: extraire un helper commun "normalize_rewards(cfg, session)".
    cfg = (LEVELS or {}).get(level, {}) or {}
    rewards_cfg = cfg.get("rewards", []) or []

    # Minimal: renvoyer brut ou normalisé partiellement.
    # Recommandé: normaliser au même format que /api/levels.
    normalized = []
    for r in rewards_cfg:
        normalized.append(r)  # à remplacer par normalisation complète
    return normalized

def grant_xp(session, player: Player, amount: float, reason: str = "") -> Dict[str, Any]:
    """
    Ajoute de l'XP et gère la montée de niveau.
    Retourne un payload uniforme:
      {
        "player": {...},
        "rewards": {
            "level_up": true/false,
            "old_level": ...,
            "new_level": ...,
            "level_rewards": [...]
        } | None
      }
    """
    if amount is None:
        amount = 0
    amount = float(amount)
    if amount <= 0:
        return {
            "player": _player_payload(player),
            "rewards": None
        }

    old_level = int(player.level or 0)
    old_xp = float(player.xp or 0.0)

    # Appliquer XP
    player.xp = old_xp + amount

    # Calcul level-ups (loop si plusieurs niveaux)
    new_level = old_level
    level_up_rewards_acc = []

    while new_level < MAX_LEVEL:
        # seuil du niveau suivant
        next_lvl = new_level + 1
        thr = xp_required_for(next_lvl)
        if player.xp < thr:
            break

        # level up
        new_level = next_lvl
        player.level = new_level

        # rewards du niveau
        level_up_rewards_acc.extend(_normalize_level_rewards(new_level))

    # Important: commit laissé au caller (route métier)
    rewards_payload = None
    if new_level != old_level:
        rewards_payload = {
            "level_up": True,
            "old_level": old_level,
            "new_level": new_level,
            "level_rewards": level_up_rewards_acc,
        }

    return {
        "player": _player_payload(player),
        "rewards": rewards_payload,
    }

def _player_payload(p: Player) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "coins": p.coins,
        "diams": p.diams,
        "level": p.level,
        "xp": p.xp,
        "next_xp": next_threshold(p.level),
    }
