# app/routes/api_players.py
from flask import Blueprint, jsonify, request
from app.db import SessionLocal
from app.models import Player, ResourceStock
from app.auth import get_current_player

bp = Blueprint("indeventory", __name__) 



# -----------------------------------------------------------------
# Inventory
# -----------------------------------------------------------------
@bp.get("/inventory")
def get_inventory():
    """Return current player's inventory from cookie."""
    with SessionLocal() as s:
        me = get_current_player(s)
        if not me:
            return jsonify({"error": "not_authenticated"}), 401
        rows = (
            s.query(ResourceStock)
            .filter_by(player_id=me.id)
            .order_by(ResourceStock.resource.asc())
            .all()
        )
        payload = [
            {"resource": r.resource, "qty": r.qty} for r in rows
        ]
        return jsonify(payload)