# =============================================================================
# File: app/routes/api_village_trades.py
# Purpose: API for treasure-based trades in the village.
# =============================================================================

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.db import SessionLocal
from app.auth import get_current_player
from app.trades.village_trades import (
    list_trades_for_player,
    execute_trade_for_player,
)

bp = Blueprint("village_trades", __name__)

# ---------------------------------------------------------------------------
# GET /api/village/trades
# ---------------------------------------------------------------------------
@bp.get("/village/trades")
def api_list_village_trades():
    """
    Liste tous les trades "treasure" disponibles pour le joueur.

    Query params:
      - land (optionnel): slug de land pour filtrer (ex: ?land=forest)
    """
    land = request.args.get("land") or None

    with SessionLocal() as session:
        player = get_current_player(session)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        data = list_trades_for_player(session, player, land_slug=land)
        # data = {"trades": [...], "available_lands": [...]}
        return jsonify({"ok": True, **data})


# ---------------------------------------------------------------------------
# POST /api/village/trades/execute
# ---------------------------------------------------------------------------
@bp.post("/village/trades/execute")
def api_execute_village_trade():
    """
    Exécute un trade treasure pour une carte donnée.

    Body JSON:
      {
        "card_key": "branch_boost_treasure_1"
      }
    """
    payload = request.get_json(silent=True) or {}
    card_key = payload.get("card_key")

    if not card_key:
        return jsonify({"ok": False, "error": "missing_card_key"}), 400

    with SessionLocal() as session:
        player = get_current_player(session)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        ok, result = execute_trade_for_player(session, player, card_key)
        if not ok:
            session.rollback()
            return jsonify({"ok": False, **result}), 400

        session.commit()
        return jsonify({"ok": True, **result})
