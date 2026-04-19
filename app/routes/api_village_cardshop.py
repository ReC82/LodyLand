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
from app.models import CardDef, PlayerCard
from app.progression import next_threshold

bp = Blueprint("village_cardshop", __name__)

# Cartes d'accès craft ordonnées du plus bas au plus haut niveau.
# Un joueur ne peut posséder qu'une seule de ces cartes à la fois.
# Acheter un niveau supérieur retire automatiquement la carte du niveau précédent.
CRAFT_ACCESS_GROUP: list[str] = [
    "access_craft_table_basic",
    "access_craft_table_medium",
    "access_craft_table_advanced",
]


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

        # 2) Prix : coins → shards, diams → essence (voir Player.coins/diams properties)
        prices = shop_cfg.get("prices") or []
        price_cfg = (prices[0] or {}) if prices else {}
        price_shards = int(price_cfg.get("coins", 0) or 0)   # "coins" dans le YAML = shards en DB
        price_essence = int(price_cfg.get("diams", 0) or 0)  # "diams" dans le YAML = essence en DB
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

        # Check buy_rules: prerequisite card ownership
        buy_rules = shop_cfg.get("buy_rules") or {}
        requires_card = buy_rules.get("requires_card")
        if requires_card:
            has_prereq = (
                session.query(PlayerCard)
                .filter_by(player_id=player.id, card_key=requires_card)
                .count()
            ) > 0
            if not has_prereq:
                # Trouver le label lisible de la carte prérequise
                req_cd = session.query(CardDef).filter_by(key=requires_card).first()
                req_label = req_cd.card_label if req_cd else requires_card.replace("_", " ").title()
                return jsonify({
                    "ok": False,
                    "error": "prerequisite_card_required",
                    "requires_card": requires_card,
                    "requires_card_label": req_label,
                }), 400

        # Vérification groupe craft access : on ne peut pas acheter une carte
        # si on possède déjà une carte de niveau supérieur du même groupe.
        if offer_key in CRAFT_ACCESS_GROUP:
            current_tier = CRAFT_ACCESS_GROUP.index(offer_key)
            for higher_key in CRAFT_ACCESS_GROUP[current_tier + 1:]:
                owns_higher = (
                    session.query(PlayerCard)
                    .filter_by(player_id=player.id, card_key=higher_key)
                    .count()
                ) > 0
                if owns_higher:
                    higher_cd = session.query(CardDef).filter_by(key=higher_key).first()
                    higher_label = higher_cd.card_label if higher_cd else higher_key.replace("_", " ").title()
                    return jsonify({
                        "ok": False,
                        "error": "craft_access_already_upgraded",
                        "owns_higher_card": higher_key,
                        "owns_higher_card_label": higher_label,
                    }), 400

        # (optionnel) Ressources requises -> à implémenter plus tard
        if res_costs:
            # TODO: vérifier les ressources du joueur
            pass

        # 4) Vérifier les fonds du joueur
        if player.shards < price_shards:
            return jsonify({"ok": False, "error": "not_enough_coins"}), 400

        if player.essence < price_essence:
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

        # 6) Groupe craft access : retirer les cartes de niveau inférieur
        if offer_key in CRAFT_ACCESS_GROUP:
            current_tier = CRAFT_ACCESS_GROUP.index(offer_key)
            for lower_key in CRAFT_ACCESS_GROUP[:current_tier]:
                lower_row = (
                    session.query(PlayerCard)
                    .filter_by(player_id=player.id, card_key=lower_key)
                    .first()
                )
                if lower_row:
                    session.delete(lower_row)

        # 7) Déduction du prix
        player.shards -= price_shards
        player.essence -= price_essence

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
                    "next_xp": next_threshold(player.level),
                    "shards": player.shards,
                    "essence": player.essence,
                    "coins": player.shards,
                    "diams": player.essence,
                },
                "item": {
                    "item_type": item_type,
                    "item_key": item_key,
                },
            }
        )
