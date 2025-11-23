# app/routes/api_craft.py
# =============================================================================
# Craft API endpoints:
# - GET  /api/craft/recipes   -> list available recipes
# - POST /api/craft/perform   -> perform a craft
# =============================================================================
from __future__ import annotations

from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from app import craft_defs
from app.db import SessionLocal
from app.models import Player, PlayerCard, ResourceStock, PlayerItem
from app.auth import get_current_player
from app.quests.service import on_item_crafted

bp = Blueprint("craft", __name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_player(session, payload: dict) -> Player | None:
    """Resolve player either from explicit playerId or cookie (get_current_player)."""
    player_id = payload.get("playerId")
    if player_id is not None:
        try:
            return session.get(Player, int(player_id))
        except (TypeError, ValueError):
            return None
    # fallback cookie / auth normal
    return get_current_player(session)


def _player_has_card(session, player_id: int, card_key: str) -> bool:
    """Return True if player owns a given card."""
    if not card_key:
        return False

    count = (
        session.query(PlayerCard)
        .filter_by(player_id=player_id, card_key=card_key)
        .count()
    )
    return count > 0


def _compute_craft_table_level(session, player: Player) -> int:
    """
    Compute the craft table level for a player based on owned cards.

    For now we keep:
      - craft_base
      - craft_upgrade_1
      - craft_upgrade_2
    """
    level = 1

    if _player_has_card(session, player.id, "craft_base"):
        level = max(level, 1)

    if _player_has_card(session, player.id, "craft_upgrade_1"):
        level = max(level, 2)

    if _player_has_card(session, player.id, "craft_upgrade_2"):
        level = max(level, 3)

    return level


def _is_item_unlocked_for_player(
    session,
    player: Player,
    item_cfg: dict[str, Any],
    craft_table_level: int,
) -> bool:
    """
    Check if a craft is unlocked for a given player.

    - Vérifie d'abord le niveau de table requis (recipe.required_table_level).
    - Puis, s'il y a une condition d'unlock (unlock_condition),
      vérifie par ex. une carte de recette ou un niveau minimum.
    """
    recipe = item_cfg.get("recipe") or {}
    required_table_level = int(recipe.get("required_table_level") or 1)

    # 1) niveau de table
    if craft_table_level < required_table_level:
        return False

    # 2) conditions d'unlock (optionnelles)
    unlock = item_cfg.get("unlock_condition") or {}
    if not unlock:
        return True  # pas de condition -> débloqué

    cond_type = (unlock.get("type") or "").lower()
    cond_key = (unlock.get("key") or "").strip()

    if cond_type == "card":
        # ex: key = "recipe_tool_wooden_axe"
        return _player_has_card(session, player.id, cond_key)

    if cond_type == "level":
        min_level = int(unlock.get("min_level") or 1)
        player_level = int(getattr(player, "level", 1))
        return player_level >= min_level

    # Unknown condition type -> pour l'instant, on ne bloque pas
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

    for line in pattern:
        for ch in str(line):
            if ch == ".":
                continue
            counts[ch] = counts.get(ch, 0) + 1

    required: Dict[str, int] = {}

    for symbol, count in counts.items():
        entry = legend.get(symbol)
        if not entry:
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
    """Load all resources for a player as a map: resource_key -> ResourceStock row."""
    stocks = (
        session.query(ResourceStock)
        .filter(ResourceStock.player_id == player.id)
        .all()
    )

    return {s.resource: s for s in stocks}


# ---------------------------------------------------------------------------
# GET /api/craft/recipes
# ---------------------------------------------------------------------------
@bp.get("/craft/recipes")
def list_craft_recipes():
    """
    List craftable recipes for the current player and given craft_location.

    Query params:
      - location: "craft_table", "craft_table_base", "forge", ...
      - playerId (optionnel) : override cookie (debug)

    Réponse JSON:
    {
      "craft_location": "craft_table",
      "craft_table_level": 1,
      "recipes": [
        {
          "item_key": "tool_wooden_axe",
          "label": "Wooden Axe",
          "icon": "...",
          "kind": "tool",
          "category": "...",
          "recipe": {
            "pattern": ["BBS"],
            "legend": {...},
            "output_quantity": 1,
            "craft_time_seconds": 8,
            "required_table_level": 1
          }
        }
      ]
    }
    """
    craft_location = (request.args.get("location") or "craft_table").strip()

    # On récupère playerId (si passé en param) pour être cohérent avec api_cards
    payload = {"playerId": request.args.get("playerId")}

    with SessionLocal() as session:
        player = _resolve_player(session, payload)
        if not player:
            return jsonify({"error": "not_logged_in"}), 401

        # TODO: brancher plus tard sur un vrai calcul de niveau de table
        craft_table_level = 1

        recipes: list[dict[str, Any]] = []

        print("[craft] list_craft_recipes() location=", craft_location)
        print("[craft] CRAFT_DEFS keys:", list(craft_defs.CRAFT_DEFS.keys()))

        # Niveau de table réel (avec cartes craft_base, craft_upgrade_1, craft_upgrade_2)
        craft_table_level = _compute_craft_table_level(session, player)

        for item_key, cfg in craft_defs.CRAFT_DEFS.items():
            recipe = cfg.get("recipe")
            if not isinstance(recipe, dict):
                continue

            # 1) Déterminer la station de craft réelle de cette recette
            recipe_location = (
                recipe.get("craft_location")
                or cfg.get("craft_location")
                or cfg.get("station_key")
                or "craft_table"
            )

            # 2) Filtrer par station / location
            if recipe_location != craft_location:
                continue

            # 3) Calculer si cette recette est débloquée pour le joueur
            is_unlocked = _is_item_unlocked_for_player(
                session=session,
                player=player,
                item_cfg=cfg,
                craft_table_level=craft_table_level,
            )

            # 4) Préparer les données pour le front
            label = cfg.get("label") or cfg.get("key") or item_key

            pattern = recipe.get("pattern") or []
            legend = recipe.get("legend") or {}

            output_quantity = int(recipe.get("output_quantity") or 1)
            craft_time_seconds = int(recipe.get("craft_time_seconds") or 0)
            required_table_level = int(recipe.get("required_table_level") or 1)

            recipes.append(
                {
                    "item_key": cfg.get("key") or item_key,
                    "label": label,
                    "icon": cfg.get("icon"),
                    "kind": cfg.get("kind") or cfg.get("type"),
                    "category": cfg.get("category"),
                    "is_unlocked": is_unlocked,  # 👈 super important pour l’UI
                    "recipe": {
                        "craft_location": recipe_location,
                        "pattern": pattern,
                        "legend": legend,
                        "output_quantity": output_quantity,
                        "craft_time_seconds": craft_time_seconds,
                        "required_table_level": required_table_level,
                    },
                }
            )

        print("[craft] list_craft_recipes ->", len(recipes), "recipes")

        return jsonify(
            {
                "craft_location": craft_location,
                "craft_table_level": craft_table_level,
                "recipes": recipes,
            }
        )


        print("[craft] list_craft_recipes ->", len(recipes), "recipes")


        return jsonify(
            {
                "craft_location": craft_location,
                "craft_table_level": craft_table_level,
                "recipes": recipes,
            }
        )



# ---------------------------------------------------------------------------
# POST /api/craft/perform
# ---------------------------------------------------------------------------
@bp.post("/craft/perform")
def perform_craft():
    """
    Perform a craft for the current player.

    POST /api/craft/perform
    {
      "item_key": "tool_wooden_axe",
      "craft_location": "craft_table",
      "times": 1,
      "playerId": 1
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

    item_cfg = craft_defs.CRAFT_DEFS.get(item_key)
    if not item_cfg:
        return jsonify({"error": "unknown_item_key", "item_key": item_key}), 400

    recipe = item_cfg.get("recipe")
    if not recipe:
        return jsonify({"error": "item_not_craftable", "item_key": item_key}), 400

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
        player = _resolve_player(session, data)
        if not player:
            return jsonify({"error": "player_required"}), 400

        table_level = _compute_craft_table_level(session, player)

        if not _is_item_unlocked_for_player(session, player, item_cfg, table_level):
            return jsonify({"error": "craft_locked"}), 403

        required_table_level = int(recipe.get("required_table_level") or 1)
        if table_level < required_table_level:
            return jsonify(
                {
                    "error": "craft_table_too_low",
                    "required_table_level": required_table_level,
                    "player_table_level": table_level,
                }
            ), 403

        required = _compute_required_resources(recipe, times=times)
        if not required:
            return jsonify({"error": "invalid_recipe_definition"}), 500

        res_map = _load_player_resources_map(session, player)

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
                continue
            pr.qty = float(pr.qty) - needed
            if pr.qty < 0:
                pr.qty = 0.0

        # Add crafted item(s)
        output_qty = int(recipe.get("output_quantity") or 1) * times

        pi = (
            session.query(PlayerItem)
            .filter_by(player_id=player.id, item_key=item_cfg.get("key"))
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

        # Quest hook
        on_item_crafted(
            session=session,
            player=player,
            item_key=item_cfg.get("key"),
            quantity=output_qty,
        )

        session.commit()

        return jsonify(
            {
                "ok": True,
                "crafted_item": {
                    "item_key": item_cfg.get("key"),
                    "label": item_cfg.get("label"),
                    "quantity": output_qty,
                },
                "craft_location": craft_location,
                "times": times,
            }
        )
