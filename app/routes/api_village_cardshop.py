# =============================================================================
# File: app/routes/api_village_cardshop.py
# Purpose: Dedicated API for the Village Card Shop (cardshop).
# Version SIMPLE : s'aligne sur frontend /village/shop
# en utilisant CardDef + shop.show_in_village_shop.
# =============================================================================

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.db import SessionLocal
from app.auth import get_current_player
from app.services.cards import grant_card_to_player
from app.models import CardDef, PlayerCard  # 👈 important

bp = Blueprint("village_cardshop", __name__)


# ---------------------------------------------------------------------------
# POST /api/village/cardshop/buy
# ---------------------------------------------------------------------------

@bp.post("/village/cardshop/buy")
def api_village_cardshop_buy():
    """
    Buy an item/card from the Village Card Shop (version SIMPLE).

    Expected JSON:
    {
        "offer_key": "xxx"  # correspond à CardDef.key
    }
    """
    data = request.get_json(silent=True) or {}
    offer_key = data.get("offer_key")

    if not offer_key:
        return jsonify({"ok": False, "error": "missing_offer_key"}), 400

    with SessionLocal() as session:
        # 0) Auth
        player = get_current_player(session)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        # 1) Retrouver la CardDef correspondant à offer_key
        cd: CardDef | None = (
            session.query(CardDef)
            .filter(
                CardDef.enabled == True,
                CardDef.key == offer_key,
            )
            .first()
        )

        if not cd:
            # Aucune carte avec cette clé
            return jsonify({"ok": False, "error": "unknown_offer"}), 404

        shop_cfg = cd.shop or {}
        # On ne permet l'achat que si la carte est marquée pour le village shop
        if not shop_cfg.get("show_in_village_shop"):
            return jsonify({"ok": False, "error": "unknown_offer"}), 404

        # 2) Prix : même logique que dans frontend.village_shop()
        prices = shop_cfg.get("prices") or []
        price_cfg = (prices[0] or {}) if prices else {}
        price_coins = int(price_cfg.get("shards", 0) or 0)
        price_diams = int(price_cfg.get("essence", 0) or 0)
        res_costs = price_cfg.get("resources") or {}

        # 3) Quantité possédée + max_owned
        owned_row = (
            session.query(PlayerCard)
            .filter_by(player_id=player.id, card_key=cd.key)
            .first()
        )
        owned_qty = owned_row.qty if owned_row else 0

        max_owned = shop_cfg.get("max_owned")
        if max_owned is None:
            max_owned = cd.card_max_owned

        if max_owned is not None and owned_qty >= max_owned:
            return jsonify(
                {"ok": False, "error": "max_owned_reached"}
            ), 400

        # (optionnel) Ressources requises -> à implémenter plus tard
        if res_costs:
            # TODO: vérifier les ressources du joueur
            pass

        # 4) Vérifier les coins/diams du joueur
        if player.coins < price_coins:
            return jsonify({"ok": False, "error": "not_enough_coins"}), 400

        if player.diams < price_diams:
            return jsonify({"ok": False, "error": "not_enough_diams"}), 400

        # 5) Item type : ici, uniquement des cartes
        item_type = "card"
        item_key = cd.key  # == offer_key

        # === Purchase handling ==============================================
        # On utilise grant_card_to_player comme pour les autres cartes
        ok, reason = grant_card_to_player(session, player.id, item_key)
        if not ok:
            return jsonify(
                {"ok": False, "error": reason or "cannot_grant_card"}
            ), 400

        # 6) Déduction du prix
        player.coins -= price_coins
        player.diams -= price_diams

        session.commit()
        session.refresh(player)

        # 7) Réponse JSON pour mettre à jour le HUD côté client
        return jsonify(
            {
                "ok": True,
                "offer_key": offer_key,
                "player": {
                    "id": player.id,
                    "name": player.name,
                    "level": player.level,
                    "xp": player.xp,
                    "shards": player.shards,
                    "essence": player.essence,
                },
                "item": {
                    "item_type": item_type,
                    "item_key": item_key,
                },
            }
        )
