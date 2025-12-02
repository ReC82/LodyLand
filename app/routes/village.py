# app/routes/village.py
from __future__ import annotations

from flask import Blueprint, jsonify, render_template, url_for
from app.db import SessionLocal
from app.models import Player, ResourceStock, ResourceDef
from app.auth import get_current_player
from app.progression import next_threshold
from app.village_shop import get_active_village_offers  # shop logique YAML

bp = Blueprint("village", __name__)  # prefix géré dans register_routes()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_player(session: SessionLocal) -> Player | None:
    """Return current player from cookie (can be None)."""
    return get_current_player(session)


def _round_qty(q, digits: int = 2) -> float:
    """Round quantity for JSON payload (avoid long floats)."""
    if q is None:
        q = 0.0
    return round(float(q), digits)


# ---------------------------------------------------------------------------
# Village pages
# ---------------------------------------------------------------------------

@bp.get("/")
def village_home():
    """Village hub: main NPC grid (quests / market / shop / trades)."""
    with SessionLocal() as s:
        player = _load_player(s)

    land_logo = url_for(
        "static",
        filename="assets/img/lands/village_logo.png",
    )

    return render_template(
        "GAME_UI/lands/village/village_home.html",
        land_logo=land_logo,
        land_label="Le Village",
        player=player,
    )


@bp.get("/market")
def village_market():
    """Village Market page (UI only, resources loaded via /market/resources)."""
    with SessionLocal() as s:
        player = _load_player(s)

    land_logo = url_for(
        "static",
        filename="assets/img/lands/village_logo.png",
    )

    return render_template(
        "GAME_UI/lands/village/village_market.html",
        land_label="Le Marché du village",
        land_logo=land_logo,
        player=player,
    )


@bp.get("/shop")
def village_shop():
    """
    Card & special items shop.

    For now: only passes active offers from village_shop.yml,
    real filtering (non-boost, random weekly, etc.) viendra plus tard.
    """
    with SessionLocal() as s:
        player = _load_player(s)

    offers = get_active_village_offers()

    land_logo = url_for(
        "static",
        filename="assets/img/lands/village_logo.png",
    )

    return render_template(
        "GAME_UI/lands/village/village_shop.html",
        land_label="La Boutique des Raretés",
        land_logo=land_logo,
        player=player,
        offers=offers,
    )


@bp.get("/quests")
def village_quests():
    """Village quests page (storyline + daily + weekly). UI only for now."""
    with SessionLocal() as s:
        player = _load_player(s)

    land_logo = url_for(
        "static",
        filename="assets/img/lands/village_logo.png",
    )

    return render_template(
        "GAME_UI/lands/village/village_quests.html",
        land_label="Quêtes du Village",
        land_logo=land_logo,
        player=player,
    )


@bp.get("/trades")
def village_trades():
    """Village trades page (resource ↔ items/cards). For now: placeholder."""
    with SessionLocal() as s:
        player = _load_player(s)

    land_logo = url_for(
        "static",
        filename="assets/img/lands/village_logo.png",
    )

    return render_template(
        "GAME_UI/lands/village/village_trades.html",
        land_label="Échanges du Village",
        land_logo=land_logo,
        player=player,
    )


# ---------------------------------------------------------------------------
# Market API for this player
# ---------------------------------------------------------------------------

@bp.get("/market/resources")
def api_village_market_resources():
    """
    Return the list of SELLABLE resources for the current player.

    - Uses ResourceStock for real quantities
    - Only keeps qty > 0
    - Uses ResourceDef for label / emoji / base_sell_price
    - If base_sell_price is NULL, fallback = 1 coin (same logic as /api/sell)
    """
    with SessionLocal() as s:
        player: Player | None = get_current_player(s)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        # 1) All resources > 0 for this player
        stocks: list[ResourceStock] = (
            s.query(ResourceStock)
            .filter(
                ResourceStock.player_id == player.id,
                ResourceStock.qty > 0,
            )
            .all()
        )

        if not stocks:
            # No sellable resources, but still return player meta
            return jsonify(
                {
                    "ok": True,
                    "player": {
                        "id": player.id,
                        "name": player.name,
                        "level": player.level,
                        "xp": player.xp,
                        "coins": player.coins,
                        "diams": player.diams,
                        "next_xp": next_threshold(player.level),
                    },
                    "resources": [],
                }
            )

        # 2) Preload ResourceDef for these keys
        keys = [rs.resource for rs in stocks]
        defs: dict[str, ResourceDef] = {
            rd.key: rd
            for rd in s.query(ResourceDef)
            .filter(ResourceDef.key.in_(keys))
            .all()
        }

        rows: list[dict] = []
        for rs in stocks:
            rd = defs.get(rs.resource)

            # Unit price like in /api/sell
            if rd and rd.base_sell_price is not None:
                unit_price = rd.base_sell_price
            else:
                unit_price = 1  # fallback

            # Optional: add a flag in ResourceDef to block some resources from being sold
            # if rd and not rd.can_be_sold:
            #     continue

            label_fr = getattr(rd, "label_fr", None) if rd else None
            label_en = getattr(rd, "label_en", None) if rd else None
            emoji = getattr(rd, "emoji", "") if rd else ""

            rows.append(
                {
                    "resource": rs.resource,
                    "label": label_fr or label_en or rs.resource,
                    "emoji": emoji or "",
                    "qty": _round_qty(rs.qty),
                    "unit_sell_price": unit_price,
                    "total_sell_price": unit_price * int(rs.qty or 0),
                }
            )

        return jsonify(
            {
                "ok": True,
                "player": {
                    "id": player.id,
                    "name": player.name,
                    "level": player.level,
                    "xp": player.xp,
                    "coins": player.coins,
                    "diams": player.diams,
                    "next_xp": next_threshold(player.level),
                },
                "resources": rows,
            }
        )

# ---------------------------------------------------------------------------
# Village Shop — Buy endpoint
# ---------------------------------------------------------------------------

@bp.post("/shop/buy")
def api_village_shop_buy():
    """
    Buy an item/card from the Village Shop.

    Payload expected:
    {
        "offer_key": "xxx"
    }
    """
    from flask import request
    import datetime

    data = request.get_json(silent=True) or {}
    offer_key = data.get("offer_key")

    if not offer_key:
        return jsonify({"ok": False, "error": "missing_offer_key"}), 400

    with SessionLocal() as s:
        player = get_current_player(s)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        # 1) Charger toutes les offres actives (village_shop.yml déjà chargé)
        offers = get_active_village_offers()
        offer = None

        for o in offers:
            key = o.get("offer_key") or o.get("key") or o.get("item_key")
            if key == offer_key:
                offer = o
                break

        if not offer:
            return jsonify({"ok": False, "error": "unknown_offer"}), 404

        # 2) Vérifier le stock global (si défini)
        stock = offer.get("stock")
        if stock is not None and stock <= 0:
            return jsonify({"ok": False, "error": "out_of_stock"}), 400

        # 3) Déterminer prix
        price_coins = offer.get("price_coins") or offer.get("coins") or 0
        price_diams = offer.get("price_diams") or offer.get("diams") or 0

        # 4) Vérifier que le joueur peut payer
        if player.coins < price_coins:
            return jsonify({"ok": False, "error": "not_enough_coins"}), 400

        if player.diams < price_diams:
            return jsonify({"ok": False, "error": "not_enough_diams"}), 400

        # 5) Type d’item (par défaut : card)
        item_type = offer.get("item_type") or "card"
        item_key = offer.get("item_key") or offer_key

        # === Achats selon type ===============================================

        if item_type == "card":
            from app.services.cards import grant_card_to_player

            ok, reason = grant_card_to_player(s, player.id, item_key)
            if not ok:
                return jsonify({"ok": False, "error": reason or "cannot_grant_card"}), 400

        elif item_type == "boost":
            # Exemple minimal (à étendre)
            pass

        else:
            pass

        # 6) Retirer le prix
        player.coins -= price_coins
        player.diams -= price_diams

        # 7) Réduire stock global (si défini)
        if stock is not None:
            offer["stock"] = stock - 1

        s.commit()

        # Recharger le joueur
        s.refresh(player)

        return jsonify({
            "ok": True,
            "offer_key": offer_key,
            "player": {
                "id": player.id,
                "name": player.name,
                "level": player.level,
                "xp": player.xp,
                "coins": player.coins,
                "diams": player.diams
            },
            "item": {
                "item_type": item_type,
                "item_key": item_key
            }
        })
