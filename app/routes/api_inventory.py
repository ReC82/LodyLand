# app/routes/api_inventory.py
from flask import Blueprint, jsonify, request
from app.db import SessionLocal
from app.models import Player, ResourceStock, PlayerItem  # <-- PlayerItem added
from app.auth import get_current_player

bp = Blueprint("inventory", __name__)  # name is only an internal identifier

def _round_qty(q, digits: int = 2) -> float:
    """Return a float rounded to a fixed number of decimals for JSON."""
    if q is None:
        q = 0.0
    return round(float(q), digits)

# -----------------------------------------------------------------
# Inventory - resources
# -----------------------------------------------------------------
@bp.get("/inventory")
def get_inventory():
    """Return current player's resource inventory from cookie."""
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
            {"resource": r.resource, "qty": _round_qty(r.qty)} for r in rows
        ]
        return jsonify(payload)

# -----------------------------------------------------------------
# Inventory - crafted items (sticks, tools, etc.)
# -----------------------------------------------------------------
@bp.get("/inventory/items")
def get_items_inventory():
    """Return current player's crafted items inventory from cookie."""
    with SessionLocal() as s:
        me = get_current_player(s)
        if not me:
            return jsonify({"error": "not_authenticated"}), 401

        # Fetch all PlayerItem rows for this player
        rows = (
            s.query(PlayerItem)
            .filter_by(player_id=me.id)
            .order_by(PlayerItem.item_key.asc())
            .all()
        )

        # Build clean JSON payload
        payload = [
            {
                "item_key": it.item_key,
                "quantity": int(it.quantity or 0),
            }
            for it in rows
        ]

        return jsonify(payload)
