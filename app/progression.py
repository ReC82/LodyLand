# =============================================================================
# File: app/progression.py
# Purpose: Central XP / level / rewards logic loaded from levels.yaml
# =============================================================================
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List, Tuple

import yaml

# Base XP for one collect action (before boost cards)
XP_PER_COLLECT = 1

# Path to levels.yaml (root of the project)
BASE_DIR = Path(__file__).resolve().parent.parent
LEVELS_FILE = BASE_DIR / "app" / "data" / "levels.yml"


def _load_levels_from_yaml() -> Dict[int, dict]:
    """Load levels configuration from levels.yaml into a dict keyed by level."""
    if not LEVELS_FILE.exists():
        # Fallback to old hard-coded thresholds if file is missing
        defaults = [10, 30, 60, 100, 150]
        levels: Dict[int, dict] = {}
        for idx, thr in enumerate(defaults, start=1):
            levels[idx] = {"xp_required": thr, "rewards": []}
        return levels

    raw = yaml.safe_load(LEVELS_FILE.read_text(encoding="utf-8")) or {}
    levels_list: List[dict] = raw.get("levels", [])

    levels: Dict[int, dict] = {}
    for entry in levels_list:
        lvl = int(entry["level"])
        levels[lvl] = {
            "xp_required": int(entry.get("xp_required", 0)),
            "rewards": entry.get("rewards", []) or [],
        }
    return levels


# Global config: all levels loaded from YAML
LEVELS: Dict[int, dict] = _load_levels_from_yaml()
MAX_LEVEL: int = max(LEVELS.keys()) if LEVELS else 0


def xp_required_for(level: int) -> int:
    """Return total XP required to reach the given level."""
    cfg = LEVELS.get(level)
    if not cfg:
        # Very high value for unknown level
        return 10**9
    return cfg["xp_required"]


def level_for_xp(xp: float | int) -> int:
    """Return the level for a given XP value (based on LEVELS thresholds)."""
    lvl = 0
    for level in sorted(LEVELS.keys()):
        if xp >= LEVELS[level]["xp_required"]:
            lvl = level
        else:
            break
    return lvl


def next_threshold(current_level: int) -> int | None:
    """Return XP required for the next level, or None if already maxed."""
    if not LEVELS or current_level >= MAX_LEVEL:
        return None
    return xp_required_for(current_level + 1)


# -------------------------------------------------------------------------
# Reward helpers
# -------------------------------------------------------------------------
def _grant_resource(session, player_id: int, resource_key: str, amount: float) -> None:
    """Increase a given resource in ResourceStock for the player."""
    if not resource_key or amount <= 0:
        return

    from .models import ResourceStock  # local import to avoid circular deps

    row = (
        session.query(ResourceStock)
        .filter_by(player_id=player_id, resource=resource_key)
        .one_or_none()
    )

    if not row:
        row = ResourceStock(player_id=player_id, resource=resource_key, qty=0.0)
        session.add(row)

    row.qty = (row.qty or 0.0) + float(amount)


def _grant_card(session, player_id: int, card_key: str, amount: int = 1) -> None:
    """Grant or increase quantity of a card for the player."""
    if not card_key or amount <= 0:
        return

    from .models import PlayerCard  # local import to avoid circular deps

    row = (
        session.query(PlayerCard)
        .filter_by(player_id=player_id, card_key=card_key)
        .one_or_none()
    )

    if not row:
        row = PlayerCard(player_id=player_id, card_key=card_key, qty=0)
        session.add(row)

    row.qty = (row.qty or 0) + int(amount)


# Exemple adapté — à mettre dans app/progression.py

def apply_level_rewards(session, player, new_level: int) -> List[Dict]:
    """Apply rewards for the given level and return a list of applied rewards.

    Each reward dict will contain:
    - type: "coins" | "diams" | "resource" | "card"
    - amount
    - key (for resource/card)
    - label (human readable)
    - icon (path used directly in <img src="...">)
    - level (ajouté plus tard dans apply_xp_and_level_up)
    """
    cfg = LEVELS.get(new_level)
    if not cfg:
        return []

    from .models import ResourceDef, CardDef  # local import to avoid circular deps

    rewards = cfg.get("rewards", []) or []
    applied: List[Dict] = []

    # Cache defs pour éviter des queries répétées dans une même montée de niveau
    resource_defs = {
        r.key: r
        for r in session.query(ResourceDef).filter_by(enabled=True).all()
    }
    card_defs = {
        c.key: c
        for c in session.query(CardDef).filter_by(enabled=True).all()
    }

    for r in rewards:
        r_type = r.get("type")

        if r_type == "coins":
            amount = int(r.get("amount", 0))
            player.coins = (player.coins or 0) + amount
            applied.append(
                {
                    "type": "coins",
                    "amount": amount,
                    "label": "Coins",
                    "icon": "/static/GAME_UI/img/ui/coins.png",
                }
            )

        elif r_type == "diams":
            amount = int(r.get("amount", 0))
            player.diams = (player.diams or 0) + amount
            applied.append(
                {
                    "type": "diams",
                    "amount": amount,
                    "label": "Diams",
                    "icon": "/static/GAME_UI/img/ui/diams.png",
                }
            )

        elif r_type == "resource":
            resource_key = r.get("resource_key") or ""
            amount = float(r.get("amount", 0))
            _grant_resource(session, player.id, resource_key, amount)

            rd = resource_defs.get(resource_key)
            applied.append(
                {
                    "type": "resource",
                    "key": resource_key,
                    "amount": amount,
                    "label": rd.label if rd else resource_key,
                    "icon": rd.icon if rd else None,
                }
            )

        elif r_type == "card":
            card_key = r.get("card_key") or ""
            amount = int(r.get("amount", 1))
            _grant_card(session, player.id, card_key, amount)

            cd = card_defs.get(card_key)
            applied.append(
                {
                    "type": "card",
                    "key": card_key,
                    "amount": amount,
                    "label": cd.label if cd else card_key,
                    "icon": cd.icon if cd else None,
                }
            )

        # Later: other reward types

    return applied



def apply_xp_and_level_up(
    session, player, gained_xp: float
) -> Tuple[bool, int, List[Dict]]:
    """Apply XP to the player, handle level-ups and rewards.

    Returns:
        (level_up, new_level)
    """
    if gained_xp <= 0:
        return False, player.level or 0, []

    player.xp = (player.xp or 0.0) + float(gained_xp)

    old_level = player.level or 0
    new_level = level_for_xp(player.xp)

    if new_level <= old_level:
        return False, old_level, []

    all_rewards: List[Dict] = []
    # If player jumps multiple levels at once, we gather everything
    for lvl in range(old_level + 1, new_level + 1):
        lvl_rewards = apply_level_rewards(session, player, lvl)
        # We keep track of which level gave which rewards
        for r in lvl_rewards:
            r["level"] = lvl
        all_rewards.extend(lvl_rewards)

    player.level = new_level
    return True, new_level, all_rewards

# Simple debug at import time (for development only)
print(f"[progression] LEVELS_FILE = {LEVELS_FILE}")
print(f"[progression] Loaded {len(LEVELS)} levels from YAML")
if 1 in LEVELS:
    print(f"[progression] Level 1 config: {LEVELS[1]}")
else:
    print("[progression] WARNING: level 1 not found in LEVELS")