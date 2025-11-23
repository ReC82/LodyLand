# =============================================================================
# File: app/progression.py
# Purpose: Central XP / level / rewards logic loaded from levels.yml
# =============================================================================
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, List, Tuple

import yaml

# Base XP for one collect action (before XP boost cards)
XP_PER_COLLECT = 1

# Path to levels.yml (project root / app / data / levels.yml)
BASE_DIR = Path(__file__).resolve().parent.parent
LEVELS_FILE = BASE_DIR / "app" / "data" / "levels.yml"


# =============================================================================
# Levels loading
# =============================================================================
def _load_levels_from_yaml() -> Dict[int, dict]:
    """
    Load levels configuration from levels.yml into a dict keyed by level.

    Expected YAML structure:
      levels:
        - level: 1
          xp_required: 10
          rewards:
            - type: "coins"
              amount: 20
            - type: "card"
              card_key: "land_forest"
              amount: 1
    """
    if not LEVELS_FILE.exists():
        # Fallback to old hard-coded thresholds if file is missing
        defaults = [10, 30, 60, 100, 150]
        levels: Dict[int, dict] = {}
        for idx, thr in enumerate(defaults, start=1):
            levels[idx] = {
                "xp_required": thr,
                "rewards": [],
            }
        return levels

    raw = yaml.safe_load(LEVELS_FILE.read_text(encoding="utf-8")) or {}
    levels_list: List[dict] = raw.get("levels", []) or []

    levels: Dict[int, dict] = {}
    for entry in levels_list:
        lvl = int(entry["level"])
        levels[lvl] = {
            "xp_required": int(entry.get("xp_required", 0)),
            "rewards": entry.get("rewards", []) or [],
        }
    return levels


# Global config: all levels loaded from YAML at import time
LEVELS: Dict[int, dict] = _load_levels_from_yaml()
MAX_LEVEL: int = max(LEVELS.keys()) if LEVELS else 0


# =============================================================================
# XP / level helpers
# =============================================================================
def xp_required_for(level: int) -> int:
    """
    Return total XP required to reach the given level.

    If the level is unknown, returns a very high value so that the player
    will never reach it accidentally.
    """
    cfg = LEVELS.get(level)
    if not cfg:
        return 10**9
    return cfg["xp_required"]


def level_for_xp(xp: float | int) -> int:
    """
    Return the level for a given XP value, based on LEVELS thresholds.

    We iterate levels in ascending order and keep the highest one whose
    xp_required is <= current XP.
    """
    lvl = 0
    for level in sorted(LEVELS.keys()):
        if xp >= LEVELS[level]["xp_required"]:
            lvl = level
        else:
            break
    return lvl


def next_threshold(current_level: int) -> int | None:
    """
    Return XP required for the next level, or None if already at max level.
    """
    if not LEVELS or current_level >= MAX_LEVEL:
        return None
    return xp_required_for(current_level + 1)


# =============================================================================
# Reward helpers
# =============================================================================
def _grant_resource(
    session,
    player_id: int,
    resource_key: str,
    amount: float,
) -> None:
    """
    Increase a given resource in ResourceStock for the player.

    If the ResourceStock row does not exist yet, it is created.
    """
    if not resource_key or amount <= 0:
        return

    from .models import ResourceStock  # local import to avoid circular deps

    row = (
        session.query(ResourceStock)
        .filter_by(player_id=player_id, resource=resource_key)
        .one_or_none()
    )

    if not row:
        row = ResourceStock(
            player_id=player_id,
            resource=resource_key,
            qty=0.0,
        )
        session.add(row)

    row.qty = (row.qty or 0.0) + float(amount)


def _grant_card(
    session,
    player_id: int,
    card_key: str,
    amount: int = 1,
) -> None:
    """
    Grant or increase the quantity of a card for the player.

    If the PlayerCard row does not exist yet, it is created.
    """
    if not card_key or amount <= 0:
        return

    from .models import PlayerCard  # local import to avoid circular deps

    row = (
        session.query(PlayerCard)
        .filter_by(player_id=player_id, card_key=card_key)
        .one_or_none()
    )

    if not row:
        row = PlayerCard(
            player_id=player_id,
            card_key=card_key,
            qty=0,
        )
        session.add(row)

    row.qty = (row.qty or 0) + int(amount)


def apply_level_rewards(
    session,
    player,
    new_level: int,
) -> List[Dict]:
    """
    Apply rewards for the given level and return a list of applied rewards.

    Each reward dict returned has the shape:
      {
        "type": "coins" | "diams" | "resource" | "card",
        "amount": ...,
        "key": "...",           # for resource or card
        "label": "...",         # human readable label for UI
        "icon": "/path/to.png", # icon path usable in <img src="...">
        "level": <added later in apply_xp_and_level_up>
      }
    """
    cfg = LEVELS.get(new_level)
    if not cfg:
        return []

    from .models import ResourceDef, CardDef  # local import to avoid circular deps

    rewards_cfg = cfg.get("rewards", []) or []
    applied: List[Dict] = []

    # Cache definitions in memory to avoid repeated queries during a single
    # level-up sequence.
    resource_defs = {
        r.key: r
        for r in session.query(ResourceDef).filter_by(enabled=True).all()
    }
    card_defs = {
        c.key: c
        for c in session.query(CardDef).filter_by(enabled=True).all()
    }

    for r in rewards_cfg:
        r_type = r.get("type")

        # ------------------------------------------------------------------ #
        # Coins rewards
        # ------------------------------------------------------------------ #
        if r_type == "coins":
            amount = int(r.get("amount", 0))
            player.coins = (player.coins or 0) + amount
            applied.append(
                {
                    "type": "coins",
                    "amount": amount,
                    "label": "Coins",
                    # NOTE: icon path for coins in the UI.
                    "icon": "/static/GAME_UI/img/ui/coins.png",
                }
            )

        # ------------------------------------------------------------------ #
        # Diams rewards
        # ------------------------------------------------------------------ #
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

        # ------------------------------------------------------------------ #
        # Resource rewards (give X units of a resource)
        # ------------------------------------------------------------------ #
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

        # ------------------------------------------------------------------ #
        # Card rewards (give X copies of a card)
        # ------------------------------------------------------------------ #
        elif r_type == "card":
            card_key = r.get("card_key") or ""
            amount = int(r.get("amount", 1))
            _grant_card(session, player.id, card_key, amount)

            cd = card_defs.get(card_key)
            # IMPORTANT: CardDef has been refactored. It no longer has `label`
            # / `icon` fields directly. We now use:
            #   - card_label: internal i18n key (or temporary label)
            #   - card_image: icon / artwork path
            label = getattr(cd, "card_label", None) if cd else None
            icon = getattr(cd, "card_image", None) if cd else None

            applied.append(
                {
                    "type": "card",
                    "key": card_key,
                    "amount": amount,
                    "label": label or card_key,
                    "icon": icon,
                }
            )

        # ------------------------------------------------------------------ #
        # TODO: later extend with other reward types if needed
        # ------------------------------------------------------------------ #

    return applied


# =============================================================================
# Apply XP and handle level up
# =============================================================================
def apply_xp_and_level_up(
    session,
    player,
    gained_xp: float,
) -> Tuple[bool, int, List[Dict]]:
    """
    Apply XP to the player, handle level-ups and rewards.

    Returns:
        (level_up, new_level, all_rewards)

        - level_up: True if at least one new level has been reached
        - new_level: final level after applying the XP
        - all_rewards: list of all reward dicts for all levels gained
    """
    if gained_xp <= 0:
        return False, player.level or 0, []

    # Increase player's XP
    player.xp = (player.xp or 0.0) + float(gained_xp)

    old_level = player.level or 0
    new_level = level_for_xp(player.xp)

    # No level up
    if new_level <= old_level:
        return False, old_level, []

    all_rewards: List[Dict] = []

    # If the player jumps multiple levels at once, we apply rewards
    # for each intermediate level (old_level+1 ... new_level).
    for lvl in range(old_level + 1, new_level + 1):
        lvl_rewards = apply_level_rewards(session, player, lvl)
        # Annotate rewards with the level that granted them
        for r in lvl_rewards:
            r["level"] = lvl
        all_rewards.extend(lvl_rewards)

    # Update player's level
    player.level = new_level
    return True, new_level, all_rewards


# =============================================================================
# Debug information at import time (for development)
# =============================================================================
print(f"[progression] LEVELS_FILE = {LEVELS_FILE}")
print(f"[progression] Loaded {len(LEVELS)} levels from YAML")
if 1 in LEVELS:
    print(f"[progression] Level 1 config: {LEVELS[1]}")
else:
    print("[progression] WARNING: level 1 not found in LEVELS")
