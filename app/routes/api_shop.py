# app/routes/api_players.py
from flask import Blueprint, jsonify, request
from app.db import SessionLocal
from app.models import Player, ResourceStock, ResourceDef
from app.progression import next_threshold
from app.economy import list_prices
from app.auth import get_current_player 

bp = Blueprint("shop", __name__) 
# -----------------------------------------------------------------
# Prices & selling
# -----------------------------------------------------------------
@bp.get("/prices")
def get_prices():
    return jsonify({"prices": list_prices()})

@bp.post("/sell")
def sell():
    """Sell some resource from the player's inventory."""
    data = request.get_json(silent=True) or {}
    resource = (data.get("resource") or "").strip().lower()
    qty = int(data.get("qty") or 0)
    player_id = data.get("playerId")  # optionnel (tests) ; sinon cookie

    if not resource or qty <= 0:
        return jsonify({"error": "invalid_payload"}), 400

    with SessionLocal() as s:
        # Auth : si playerId fourni (tests), on l'utilise, sinon cookie
        if player_id:
            try:
                p = s.get(Player, int(player_id))
            except Exception:
                p = None
        else:
            p = get_current_player(s)

        if not p:
            return jsonify({"error": "not_authenticated"}), 401

        # Prix unitaire via ResourceDef (fallback = 1)
        rd = s.query(ResourceDef).filter_by(key=resource, enabled=True).first()
        unit_price = rd.base_sell_price if rd else 1

        # Vérifier le stock
        rs = (
            s.query(ResourceStock)
            .filter_by(player_id=p.id, resource=resource)
            .first()
        )
        if not rs or rs.qty < qty:
            return jsonify({"error": "not_enough_stock"}), 400

        # Décrémenter stock + créditer les coins
        rs.qty -= qty
        gain = unit_price * qty
        p.coins = (p.coins or 0) + gain

        s.commit()
        s.refresh(rs)
        s.refresh(p)

        return jsonify({
            "ok": True,
            "sold": {
                "resource": resource,
                "qty": qty,
                "gain": gain,
            },
            "stock": {
                "resource": resource,
                "qty": rs.qty,
            },
            "player": {
                "id": p.id,
                "name": p.name,
                "level": p.level,
                "xp": p.xp,
                "coins": p.coins,
                "diams": p.diams,
                "next_xp": next_threshold(p.level),
            },
        }), 200