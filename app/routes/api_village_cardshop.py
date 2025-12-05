# =============================================================================
# File: app/routes/api_village_cardshop.py
# Purpose: Dedicated API for the Village Card Shop (cardshop).
# =============================================================================

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.db import SessionLocal
from app.auth import get_current_player
from app.village_shop import get_active_village_offers
from app.services.cards import grant_card_to_player

bp = Blueprint("village_cardshop", __name__)

# ---------------------------------------------------------------------------
# POST /api/village/cardshop/buy
# ---------------------------------------------------------------------------

@bp.post("/village/cardshop/buy")
def api_village_cardshop_buy():
    """
    Buy an item/card from the Village Card Shop.

    Expected JSON:
    {
        "offer_key": "xxx"
    }
    """
    data = request.get_json(silent=True) or {}
    offer_key = data.get("offer_key")

    if not offer_key:
        return jsonify({"ok": False, "error": "missing_offer_key"}), 400

    with SessionLocal() as session:
        player = get_current_player(session)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        # 1) Load active offers from village_shop.yml
        offers = get_active_village_offers()
        offer = None

        for o in offers:
            key = o.get("offer_key") or o.get("key") or o.get("item_key")
            if key == offer_key:
                offer = o
                break

        if not offer:
            return jsonify({"ok": False, "error": "unknown_offer"}), 404

        # 2) Global stock check (if defined)
        stock = offer.get("stock")
        if stock is not None and stock <= 0:
            return jsonify({"ok": False, "error": "out_of_stock"}), 400

        # 3) Price
        price_coins = offer.get("price_coins") or offer.get("coins") or 0
        price_diams = offer.get("price_diams") or offer.get("diams") or 0

        # 4) Check player can pay
        if player.coins < price_coins:
            return jsonify({"ok": False, "error": "not_enough_coins"}), 400

        if player.diams < price_diams:
            return jsonify({"ok": False, "error": "not_enough_diams"}), 400

        # 5) Item type (default: card)
        item_type = offer.get("item_type") or "card"
        item_key = offer.get("item_key") or offer_key

        # === Purchase handling ==============================================
        if item_type == "card":
            # Use the existing card service to grant the card
            ok, reason = grant_card_to_player(session, player.id, item_key)
            if not ok:
                return jsonify(
                    {"ok": False, "error": reason or "cannot_grant_card"}
                ), 400

        elif item_type == "boost":
            # TODO: implement boost acquisition later
            pass
        else:
            # Unknown type for now
            pass

        # 6) Deduct price
        player.coins -= price_coins
        player.diams -= price_diams

        # 7) Decrease global stock (if defined)
        if stock is not None:
            offer["stock"] = stock - 1

        session.commit()
        session.refresh(player)

        return jsonify(
            {
                "ok": True,
                "offer_key": offer_key,
                "player": {
                    "id": player.id,
                    "name": player.name,
                    "level": player.level,
                    "xp": player.xp,
                    "coins": player.coins,
                    "diams": player.diams,
                },
                "item": {
                    "item_type": item_type,
                    "item_key": item_key,
                },
            }
        )
