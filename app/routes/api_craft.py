# =============================================================================
# File: app/routes/api_craft.py
# Purpose: Craft API endpoints (list available recipes for current player).
# =============================================================================
from __future__ import annotations

from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from app.craft_defs import CRAFT_DEFS
from app.db import SessionLocal
from app.models import Player, PlayerCard, ResourceDef, PlayerItem, ResourceStock  # adapte si les noms diffèrent
from app.quests.service import on_item_crafted

bp = Blueprint("craft", __name__)
# ---------------------------------------------------------------------------
# Helpers: player + cards
# ---------------------------------------------------------------------------
def _get_current_player(session) -> Player | None:
    """Resolve current player from cookie or query param."""
    # Try playerId in query string (fallback)
    player_id = request.args.get("playerId")

    # Otherwise from cookie (normal flow)
    if not player_id:
        player_id = request.cookies.get("player_id")

    if not player_id:
        return None

    try:
        pid = int(player_id)
    except ValueError:
        return None

    return session.get(Player, pid)


def _player_has_card(session, player_id: int, card_key: str) -> bool:
    """Return True if player owns a given card."""
    if not card_key:
        return False

    q = (
        session.query(PlayerCard)
        .filter(
            PlayerCard.player_id == player_id,
            PlayerCard.card_key == card_key,
        )
    )

    return session.query(q.exists()).scalar()  # True / False


def _compute_craft_table_level(session, player: Player) -> int:
    """
    Compute the craft table level for a player based on owned cards.

    Adjust this logic when you create real cards like:
    - craft_base
    - craft_upgrade_1
    - craft_upgrade_2
    """
    level = 1

    # Base craft table (3 slots)
    if _player_has_card(session, player.id, "craft_base"):
        level = max(level, 1)

    # First upgrade
    if _player_has_card(session, player.id, "craft_upgrade_1"):
        level = max(level, 2)

    # Second upgrade, etc...
    if _player_has_card(session, player.id, "craft_upgrade_2"):
        level = max(level, 3)

    return level


def _is_item_unlocked_for_player(
    session, player: Player, item_cfg: Dict[str, Any], table_level: int
) -> bool:
    """Check unlock_condition + table level."""
    recipe = item_cfg.get("recipe")
    if not recipe:
        # Not craftable (no recipe)
        return False

    # Check craft table level
    required_table_level = int(recipe.get("required_table_level") or 1)
    if table_level < required_table_level:
        return False

    # Check unlock_condition on the item
    unlock = item_cfg.get("unlock_condition") or {}
    if not unlock:
        # No condition => unlocked
        return True

    cond_type = (unlock.get("type") or "").lower()
    cond_key = (unlock.get("key") or "").strip()

    if cond_type == "card":
        return _player_has_card(session, player.id, cond_key)

    if cond_type == "level":
        # Example if you store level on the Player model
        min_level = int(unlock.get("min_level") or 1)
        player_level = int(getattr(player, "level", 1))
        return player_level >= min_level

    # Other types can be added later: quest, achievement, etc.
    return True

def _compute_required_resources(recipe: Dict[str, Any], times: int = 1) -> Dict[str, int]:
    """
    Compute total required resources for a recipe, multiplied by 'times'.

    Returns:
      { resource_key: total_quantity_required }
    """
    pattern = recipe.get("pattern") or []
    legend = recipe.get("legend") or {}

    counts: Dict[str, int] = {}

    # Count occurrences of each symbol in the pattern
    for line in pattern:
        for ch in str(line):
            if ch == ".":
                continue
            counts[ch] = counts.get(ch, 0) + 1

    required: Dict[str, int] = {}

    # Convert symbol counts to resource requirements via legend
    for symbol, count in counts.items():
        entry = legend.get(symbol)
        if not entry:
            # Symbol in pattern but not in legend -> ignore or log
            print(f"[craft] Symbol '{symbol}' not defined in legend.")
            continue

        res_key = entry.get("key")
        qty_per_slot = int(entry.get("quantity") or 1)
        total = count * qty_per_slot * max(times, 1)

        if not res_key:
            print(f"[craft] Legend entry for symbol '{symbol}' has no resource key.")
            continue

        required[res_key] = required.get(res_key, 0) + total

    return required

def _load_player_resources_map(session, player: Player) -> dict[str, ResourceStock]:
    """
    Load all resources for a player as a map: resource_key -> ResourceStock row.

    resource_key = ResourceStock.resource (ex: "wood", "stone", "stick", ...)
    """
    stocks = (
        session.query(ResourceStock)
        .filter(ResourceStock.player_id == player.id)
        .all()
    )

    res_map: dict[str, ResourceStock] = {}
    for stock in stocks:
        # stock.resource = "wood", "stone", etc.
        res_map[stock.resource] = stock

    return res_map
  

# ---------------------------------------------------------------------------
# Endpoint: list available recipes
# ---------------------------------------------------------------------------
@bp.get("/craft/recipes")
def list_craft_recipes():
    """
    List craftable recipes for the current player and given craft_location.

    Query params:
      - location: "craft_table", "alchemy_table", etc. (default: "craft_table")
      - playerId (optional): override cookie (mainly for debug)

    Response JSON:
    {
      "craft_location": "craft_table",
      "craft_table_level": 1,
      "recipes": [
        {
          "item_key": "item_pearl_necklace",
          "label_fr": "...",
          "label_en": "...",
          "icon": "items/pearl_necklace.png",
          "recipe": {
            "craft_location": "craft_table",
            "width": 5,
            "height": 5,
            "pattern": [...],
            "legend": {...},
            "output_quantity": 1,
            "craft_time_seconds": 10,
            "required_table_level": 2
          }
        },
        ...
      ]
    }
    """
    craft_location = (request.args.get("location") or "craft_table").strip()
    
    with SessionLocal() as session:
        player = _get_current_player(session)
        if not player:
            return jsonify({"error": "not_logged_in"}), 401

        table_level = _compute_craft_table_level(session, player)

        available: List[Dict[str, Any]] = []

        for item_key, cfg in CRAFT_DEFS.items():
            recipe = cfg.get("recipe")
            if not recipe:
                continue

            # Filter by craft_location (craft_table / alchemy_table / kitchen / ...)
            if (recipe.get("craft_location") or "craft_table") != craft_location:
                continue

            # Check conditions (cards, level, table level)
            if not _is_item_unlocked_for_player(session, player, cfg, table_level):
                continue

            # Build a lightweight payload for frontend
            available.append(
                {
                    "item_key": cfg.get("key") or item_key,
                    "label_fr": cfg.get("label_fr"),
                    "label_en": cfg.get("label_en"),
                    "icon": cfg.get("icon"),
                    "type": cfg.get("type"),
                    "category": cfg.get("category"),
                    "recipe": {
                        "craft_location": recipe.get("craft_location"),
                        "width": recipe.get("width"),
                        "height": recipe.get("height"),
                        "pattern": recipe.get("pattern"),
                        "legend": recipe.get("legend"),
                        "output_quantity": recipe.get("output_quantity"),
                        "craft_time_seconds": recipe.get("craft_time_seconds"),
                        "required_table_level": recipe.get("required_table_level"),
                    },
                }
            )
        print("CRAFT_DEFS loaded keys:", list(CRAFT_DEFS.keys()))
        return jsonify(
            {
                "craft_location": craft_location,
                "craft_table_level": table_level,
                "recipes": available,
            }
        )

@bp.post("/craft/perform")
def perform_craft():
    """
    Perform a craft for the current player.

    Expected JSON body:
    {
      "item_key": "tool_wooden_axe",
      "craft_location": "craft_table",   # optional, default: craft_table
      "times": 1                         # optional, default: 1
    }
    """
    data = request.get_json(silent=True) or {}

    item_key = (data.get("item_key") or "").strip()
    craft_location = (data.get("craft_location") or "craft_table").strip()
    times = int(data.get("times") or 1)
    if times < 1:
        times = 1

    if not item_key:
        return jsonify({"error": "item_key_required"}), 400

    item_cfg = CRAFT_DEFS.get(item_key)
    if not item_cfg:
        return jsonify({"error": "unknown_item_key", "item_key": item_key}), 400

    recipe = item_cfg.get("recipe")
    if not recipe:
        return jsonify({"error": "item_not_craftable", "item_key": item_key}), 400

    # Check craft_location
    recipe_location = (recipe.get("craft_location") or "craft_table").strip()
    if recipe_location != craft_location:
        return jsonify(
            {
                "error": "invalid_craft_location",
                "expected": recipe_location,
                "given": craft_location,
            }
        ), 400

    with SessionLocal() as session:
        player = _get_current_player(session)
        if not player:
            return jsonify({"error": "not_logged_in"}), 401

        # Compute player craft table level
        table_level = _compute_craft_table_level(session, player)

        # Check if the item is unlocked for the player
        if not _is_item_unlocked_for_player(session, player, item_cfg, table_level):
            return jsonify({"error": "craft_locked"}), 403

        # Check table level vs recipe requirement
        required_table_level = int(recipe.get("required_table_level") or 1)
        if table_level < required_table_level:
            return jsonify(
                {
                    "error": "craft_table_too_low",
                    "required_table_level": required_table_level,
                    "player_table_level": table_level,
                }
            ), 403

        # Compute required resources
        required = _compute_required_resources(recipe, times=times)
        if not required:
            return jsonify({"error": "invalid_recipe_definition"}), 500

        # Load player resources into a map
        res_map = _load_player_resources_map(session, player)

        # Check if player has enough resources
        missing: Dict[str, int] = {}
        for res_key, needed in required.items():
            pr = res_map.get(res_key)
            current = float(pr.qty) if pr else 0.0
            if current < needed:
                missing[res_key] = needed - int(current)

        if missing:
            return (
                jsonify(
                    {
                        "error": "not_enough_resources",
                        "missing": missing,
                    }
                ),
                400,
            )

        # Deduct resources
        for res_key, needed in required.items():
            pr = res_map.get(res_key)
            if not pr:
                # Should not happen since we checked missing above
                continue
            pr.qty = float(pr.qty) - needed
            if pr.qty < 0:
                pr.qty = 0.0


        # Add crafted item(s) in player_items
        output_qty = int(recipe.get("output_quantity") or 1) * times

        # Find existing PlayerItem or create a new one
        pi = (
            session.query(PlayerItem)
            .filter(
                PlayerItem.player_id == player.id,
                PlayerItem.item_key == item_cfg.get("key"),
            )
            .one_or_none()
        )

        if pi is None:
            pi = PlayerItem(
                player_id=player.id,
                item_key=item_cfg.get("key"),
                quantity=output_qty,
            )
            session.add(pi)
        else:
            pi.quantity = int(pi.quantity) + output_qty
            
        # --- NEW: quest progression for craft_item ---
        on_item_crafted(
            session=session,
            player=player,
            item_key=item_cfg.get("key"),
            quantity=output_qty,
        )

        session.commit()

        # Basic response (on retournera mieux plus tard)
        return jsonify(
            {
                "ok": True,
                "crafted_item": {
                    "item_key": item_cfg.get("key"),
                    "label_fr": item_cfg.get("label_fr"),
                    "label_en": item_cfg.get("label_en"),
                    "quantity": output_qty,
                },
                "craft_location": craft_location,
                "times": times,
            }
        )