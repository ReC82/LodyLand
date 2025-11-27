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

    Cards:
      - access_craft_table_basic
      - access_craft_table_medium
      - access_craft_table_advanced

    Levels:
      0 = aucune table
      1 = basic   -> 1x3
      2 = medium  -> 2x3
      3 = advanced-> 3x3
    """
    level = 0

    has_basic = _player_has_card(session, player.id, "access_craft_table_basic")
    has_medium = _player_has_card(session, player.id, "access_craft_table_medium")
    has_advanced = _player_has_card(session, player.id, "access_craft_table_advanced")

    # Si le joueur a n'importe quelle carte, au moins niveau 1
    if has_basic or has_medium or has_advanced:
        level = max(level, 1)

    # Medium ou advanced -> au moins niveau 2
    if has_medium or has_advanced:
        level = max(level, 2)

    # Advanced -> niveau 3
    if has_advanced:
        level = max(level, 3)

    return level



def _is_item_unlocked_for_player(
    session,
    player: Player,
    item_cfg: Dict[str, Any],
    craft_table_level: int,
) -> bool:
    """
    Return True if this craft is currently unlocked for the given player.

    - Check required_table_level (linked to grid tier)
    - Then check unlock/unlock_condition (card, level, etc.)
    """
    recipe = item_cfg.get("recipe") or {}
    required_table_level = int(recipe.get("required_table_level") or 1)

    # 1) Table level gate
    if craft_table_level < required_table_level:
        return False

    # 2) Normalized unlock_condition (if craft_defs built it)
    unlock = item_cfg.get("unlock_condition")
    if unlock:
        cond_type = (unlock.get("type") or "").lower()
        cond_key = (unlock.get("key") or unlock.get("card_key") or "").strip()

        if cond_type == "card":
            if not cond_key:
                return True
            return _player_has_card(session, player.id, cond_key)

        if cond_type == "level":
            min_level = int(unlock.get("min_level") or 1)
            player_level = int(getattr(player, "level", 1))
            return player_level >= min_level

        # Other types -> not blocking for now
        return True

    # 3) Raw YAML 'unlock' list (like in pearl_necklace)
    unlock_list = item_cfg.get("unlock") or []
    if not unlock_list:
        # No specific condition -> unlocked
        return True

    # For now: AND over all conditions
    for cond in unlock_list:
        if not isinstance(cond, dict):
            continue
        cond_type = (cond.get("type") or "").lower()

        if cond_type == "card":
            card_key = (cond.get("key") or cond.get("card_key") or "").strip()
            if not card_key:
                continue
            if not _player_has_card(session, player.id, card_key):
                return False

        elif cond_type == "level":
            min_level = int(cond.get("min_level") or 1)
            player_level = int(getattr(player, "level", 1))
            if player_level < min_level:
                return False

        # Other cond types: ignore for now (do not block)

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

def _compute_player_craft_station_keys(session, player: Player) -> list[str]:
    """
    Return the list of station_key accessible for the generic 'craft_table'
    location, based on the player's cards.

    - level 0 : aucune table -> []
    - level 1 : basic        -> ["craft_table_base"]
    - level 2 : medium       -> ["craft_table_base", "craft_table_medium"]
    - level 3 : advanced     -> ["craft_table_base", "craft_table_medium", "craft_table_advanced"]
    """
    level = _compute_craft_table_level(session, player)

    stations: set[str] = set()
    if level >= 1:
        stations.add("craft_table_base")
    if level >= 2:
        stations.add("craft_table_medium")
    if level >= 3:
        stations.add("craft_table_advanced")

    return sorted(stations)

def _extract_recipe_card_keys(item_cfg: Dict[str, Any]) -> set[str]:
    """
    Explore unlock_condition et unlock[] (y compris les noeuds 'and'/'or')
    et renvoie l'ensemble de toutes les card_key/ key de type 'card'.
    """
    keys: set[str] = set()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            cond_type = (node.get("type") or "").lower()

            if cond_type == "card":
                card_key = (node.get("key") or node.get("card_key") or "").strip()
                if card_key:
                    keys.add(card_key)

            # Gérer les noeuds composés: { type: "and"/"or", conditions: [...] }
            subconds = node.get("conditions")
            if isinstance(subconds, list):
                for sub in subconds:
                    _walk(sub)

        elif isinstance(node, list):
            for sub in node:
                _walk(sub)

    # 1) unlock_condition normalisé
    unlock_cond = item_cfg.get("unlock_condition")
    if unlock_cond:
        _walk(unlock_cond)

    # 2) liste 'unlock' brute depuis les YAML
    unlock_list = item_cfg.get("unlock")
    if unlock_list:
        _walk(unlock_list)

    return keys


def _extract_recipe_card_keys(item_cfg: Dict[str, Any]) -> list[str]:
    """
    Inspecte strictement la liste YAML brute 'unlock' et renvoie
    la liste des clés de cartes de recette (type: card).
    """
    keys: list[str] = []

    unlock_list = item_cfg.get("unlock") or []
    if not isinstance(unlock_list, list):
        return keys

    for cond in unlock_list:
        if not isinstance(cond, dict):
            continue
        cond_type = (cond.get("type") or "").lower()
        if cond_type != "card":
            continue

        card_key = (cond.get("key") or cond.get("card_key") or "").strip()
        if card_key:
            keys.append(card_key)

    return keys

def _item_requires_recipe_card(item_cfg: Dict[str, Any]) -> bool:
    unlock_cond = item_cfg.get("unlock_condition")

    if isinstance(unlock_cond, dict):
        return (unlock_cond.get("type") == "card")

    return False

def _recipe_card_flags_for_item(
    session,
    player: Player,
    item_cfg: Dict[str, Any],
) -> tuple[bool, bool]:
    """
    Returns:
      (requires_recipe_card, has_recipe_card)
    based on the normalized 'unlock_condition' built by craft_defs.
    """
    requires = False
    has = False

    unlock_cond = item_cfg.get("unlock_condition") or {}
    if isinstance(unlock_cond, dict):
        cond_type = (unlock_cond.get("type") or "").lower()
        if cond_type == "card":
            requires = True
            card_key = (unlock_cond.get("key") or "").strip()
            if card_key:
                has = _player_has_card(session, player.id, card_key)

    return requires, has



def _player_has_recipe_card_for_item(session, player, item_cfg):
    unlock_cond = item_cfg.get("unlock_condition")

    if isinstance(unlock_cond, dict) and unlock_cond.get("type") == "card":
        card_key = unlock_cond.get("key")
        if card_key:
            return _player_has_card(session, player.id, card_key)

    return False





# ---------------------------------------------------------------------------
# GET /api/craft/recipes
# ---------------------------------------------------------------------------
@bp.get("/craft/recipes")
def list_craft_recipes():
    """
    List all craft recipes available for the given location.

    Front envoie:
      GET /api/craft/recipes?location=craft_table

    On traduit "craft_table" côté back en plusieurs station_key
    (craft_table_base / medium / advanced) en fonction des cartes du joueur.
    """
    craft_location = (request.args.get("location") or "craft_table").strip()

    # On autorise éventuellement ?playerId=... en GET, mais en général
    # on passe par le cookie -> get_current_player
    payload: Dict[str, Any] = request.args.to_dict()

    with SessionLocal() as session:
        player = _resolve_player(session, payload)
        if not player:
            return jsonify({"error": "not_logged_in"}), 401

        recipes: list[dict[str, Any]] = []

        # Niveau de table (0 / 1 / 2 / 3)
        craft_table_level = _compute_craft_table_level(session, player)

        # ----------------- mapping station_key autorisées -----------------
        if craft_location == "craft_table":
            # On convertit 'craft_table' en station_key réelles
            allowed_locations = set(_compute_player_craft_station_keys(session, player))
            # compat rétro: si certaines recettes ont craft_location="craft_table"
            allowed_locations.add("craft_table")
        else:
            # autre station: forge_level_1, etc.
            allowed_locations = {craft_location}
        # ------------------------------------------------------------------

        print("[craft] list_craft_recipes() location=", craft_location)
        print("[craft] allowed_locations =", allowed_locations)
        
        print("=== DEBUG CRAFT_DEFS ENTRY ===")
        print("ITEM KEYS:", list(craft_defs.CRAFT_DEFS.keys()))
        print("pearl_necklace unlock =", craft_defs.CRAFT_DEFS.get("pearl_necklace", {}).get("unlock"))
        print("pearl_necklace unlock_condition =", craft_defs.CRAFT_DEFS.get("pearl_necklace", {}).get("unlock_condition"))
        print("=================================")        

        for item_key, cfg in craft_defs.CRAFT_DEFS.items():
            recipe = cfg.get("recipe")
            if not isinstance(recipe, dict):
                continue

            recipe_location = (
                recipe.get("craft_location")
                or cfg.get("craft_location")
                or cfg.get("station_key")
                or "craft_table"
            )

            # 1) Filtre station: on NE montre pas les recettes d'une station
            #    que le joueur n'a pas encore (pas de craft_table_advanced sans la carte).
            if craft_location == "craft_table":
                if recipe_location not in allowed_locations:
                    continue
            else:
                if recipe_location != craft_location:
                    continue

            # 2) Flags recette
            requires_recipe_card, has_recipe_card = _recipe_card_flags_for_item(
                session, player, cfg
            )

            # 3) Calculer si cette recette est débloquée (table + level + carte, etc.)
            is_unlocked = _is_item_unlocked_for_player(
                session=session,
                player=player,
                item_cfg=cfg,
                craft_table_level=craft_table_level,
            )

            # 4) Label / recipe details
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

                    # Pour l'UI
                    "is_unlocked": is_unlocked,
                    "requires_recipe_card": requires_recipe_card,
                    "has_recipe_card": has_recipe_card,

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



        # petit tri par label pour un affichage stable
        recipes.sort(key=lambda r: r.get("label") or "")

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

    recipe = item_cfg.get("recipe") or {}
    if not recipe:
        return jsonify({"error": "item_not_craftable", "item_key": item_key}), 400

    recipe_location = (recipe.get("craft_location") or "craft_table").strip()

    # IMPORTANT :
    # - "craft_table" (côté UI) = alias générique pour toutes les tables de craft
    #   (craft_table_base, craft_table_medium, craft_table_advanced, craft_table).
    # - On ne bloque donc PAS si craft_location == "craft_table".
    # - On ne bloque que si l'appel spécifie un lieu *plus précis* qui ne correspond pas.
    if craft_location != "craft_table" and recipe_location != craft_location:
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
