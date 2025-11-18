# app/routes/api_players.py
from flask import Blueprint, jsonify, request
from app.db import SessionLocal
from app.models import Player, ResourceStock, ResourceDef
from app.progression import next_threshold
from app.economy import list_prices
from app.auth import get_current_player 

bp = Blueprint("shop", __name__) 

def _round_qty(q, digits: int = 2) -> float:
    if q is None:
        q = 0.0
    return round(float(q), digits)

# -----------------------------------------------------------------
# Prices & selling
# -----------------------------------------------------------------
@bp.get("/prices")
def get_prices():
    return jsonify({"prices": list_prices()})

# -----------------------------------------------------------------
# Vendre une ressource contre des coins
# -----------------------------------------------------------------
@bp.post("/sell")
def sell():
    """
    Vendre une ressource du joueur contre des coins.

    JSON attendu :
    {
      "resource": "branch",
      "qty": 2,
      "playerId": 1   # optionnel : pour les tests / DEV UI
    }
    """
    data = request.get_json(silent=True) or {}

    resource = (data.get("resource") or "").strip()
    qty = data.get("qty")
    player_id = data.get("playerId")

    # --- Validation basique -------------------------------------------------
    if not resource:
        return jsonify({"error": "invalid_payload", "detail": "missing_resource"}), 400

    try:
        qty = int(qty)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_payload", "detail": "invalid_qty"}), 400

    if qty <= 0:
        return jsonify({"error": "invalid_payload", "detail": "qty_must_be_positive"}), 400

    with SessionLocal() as s:
        # 1) On essaie d'abord via le cookie (GAME_UI)
        p: Player | None = get_current_player(s)

        # 2) Sinon, on accepte playerId (tests + Debug UI)
        if not p and player_id is not None:
            try:
                pid_int = int(player_id)
            except (TypeError, ValueError):
                return jsonify({"error": "invalid_payload", "detail": "invalid_playerId"}), 400
            p = s.get(Player, pid_int)

        if not p:
            return jsonify({"error": "not_authenticated"}), 401

        # Stock du joueur
        rs: ResourceStock | None = (
            s.query(ResourceStock)
            .filter_by(player_id=p.id, resource=resource)
            .first()
        )
        if not rs or rs.qty < qty:
            return jsonify({"error": "not_enough_stock"}), 400

        # Prix unitaire : ResourceDef.base_sell_price (fallback = 1)
        rd: ResourceDef | None = (
            s.query(ResourceDef)
            .filter_by(key=resource)
            .first()
        )
        unit_price: int = rd.base_sell_price if rd and rd.base_sell_price is not None else 1

        # Calcul du gain + mise à jour
        rs.qty -= qty
        gain = unit_price * qty
        p.coins = (p.coins or 0) + gain

        s.commit()
        s.refresh(rs)
        s.refresh(p)

        return jsonify(
            {
                "ok": True,
                "sold": {                      # 👈 structure attendue par les tests
                    "resource": resource,
                    "qty": qty,
                    "gain": gain,
                    "unit_price": unit_price,
                },
                "stock": {
                    "resource": rs.resource,
                    "qty": _round_qty(rs.qty),
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
            }
        ), 200