# =============================================================================
# File: app/services/crafts.py
# Purpose: Centralized logic for craftable items & recipes.
#
# This module:
#   - reads definitions from craft_defs.CRAFT_DEFS (YAML source of truth)
#   - applies player context (owned cards, table level, etc.)
#   - returns API-friendly dicts for the frontend.
# =============================================================================
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app import craft_defs
from app.models import Player


def serialize_craft_def(
    item_key: str,
    cfg: Dict[str, Any],
    *,
    player: Player,
    is_unlocked: bool,
    craft_table_level: int,
    location: str = "craft_table",
) -> Dict[str, Any]:
    """
    Transform a raw craft item config (from YAML) into an API-friendly dict.

    This is similar in spirit to serialize_card_def for cards.
    """
    recipe = cfg.get("recipe") or {}
    unlock_cond = cfg.get("unlock_condition") or {}

    label = cfg.get("label") or cfg.get("key") or item_key
    description = cfg.get("description") or ""

    return {
        # identity
        "item_key": item_key,
        "key": item_key,
        "label": label,
        "description": description,
        "icon": cfg.get("icon"),

        # metadata
        "kind": cfg.get("kind"),
        "type": cfg.get("type") or cfg.get("kind"),
        "category": cfg.get("category"),
        "rarity": cfg.get("rarity"),
        "craftable": cfg.get("craftable", True),

        # recipe info
        "recipe": {
            "craft_location": recipe.get("craft_location") or location,
            "width": recipe.get("width"),
            "height": recipe.get("height"),
            "pattern": recipe.get("pattern") or [],
            "legend": recipe.get("legend") or {},
            "output_quantity": recipe.get("output_quantity") or 1,
            "craft_time_seconds": recipe.get("craft_time_seconds") or 0,
            "required_table_level": recipe.get("required_table_level") or 1,
        },

        # unlock info
        "unlock_condition": unlock_cond,
        "is_unlocked": is_unlocked,

        # context
        "craft_table_level": craft_table_level,
        "enabled": cfg.get("enabled", True),
    }


def _player_has_card(session: Session, player_id: int, card_key: str | None) -> bool:
    """Check if player owns at least 1 copy of a card."""
    if not card_key:
        return False

    from app.models import PlayerCard  # local import to avoid circular deps

    count = (
        session.query(PlayerCard)
        .filter_by(player_id=player_id, card_key=card_key)
        .count()
    )
    return count > 0


def is_craft_unlocked_for_player(
    session: Session,
    player: Player,
    cfg: Dict[str, Any],
    *,
    craft_table_level: int,
) -> bool:
    """
    Evaluate whether a given craft is usable by the player right now.

    - checks required_table_level vs craft_table_level
    - checks unlock_condition (card, level, etc.)
    """
    recipe = cfg.get("recipe") or {}
    required_table_level = int(recipe.get("required_table_level") or 1)
    if craft_table_level < required_table_level:
        return False

    unlock = cfg.get("unlock_condition") or {}
    utype = unlock.get("type")

    if utype == "card":
        card_key = unlock.get("key")
        if not _player_has_card(session, player.id, card_key):
            return False

    if utype == "level":
        min_level = int(unlock.get("min_level") or 1)
        if player.level < min_level:
            return False

    # Later you can add more conditions (lands, quests, etc.)
    return True


def list_crafts_for_location(
    session: Session,
    player: Player,
    *,
    location: str,
    craft_table_level: int,
) -> List[Dict[str, Any]]:
    """
    Main entrypoint for the /craft/recipes endpoint.

    Filters CRAFT_DEFS by location and returns serialized crafts for the player.
    """
    results: List[Dict[str, Any]] = []

    for item_key, cfg in craft_defs.CRAFT_DEFS.items():
        recipe = cfg.get("recipe") or {}
        craft_location = (
            recipe.get("craft_location") or cfg.get("station_key") or "craft_table"
        )

        if craft_location != location:
            continue

        is_unlocked = is_craft_unlocked_for_player(
            session=session,
            player=player,
            cfg=cfg,
            craft_table_level=craft_table_level,
        )

        results.append(
            serialize_craft_def(
                item_key=item_key,
                cfg=cfg,
                player=player,
                is_unlocked=is_unlocked,
                craft_table_level=craft_table_level,
                location=location,
            )
        )

    # Simple sort by label for now
    results.sort(key=lambda c: c.get("label") or "")
    return results
