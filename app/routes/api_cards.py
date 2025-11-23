# app/routes/api_players.py
from flask import Blueprint, jsonify, request
from app.db import SessionLocal
from app.models import Player, CardDef, PlayerCard, ResourceStock, PlayerLandSlots
from app.unlock_rules import check_unlock_rules
from app.auth import get_current_player
from app.services.cards import set_player_card_qty, serialize_card_def
from app.lands import get_player_land_state

from app.village_shop import get_village_excluded_card_keys, get_active_village_offers
import datetime as dt

bp = Blueprint("cards", __name__)

def _resolve_player(session, payload: dict) -> Player | None:
    """Resolve player either from explicit playerId or cookie (get_current_player)."""
    player_id = payload.get("playerId")
    if player_id is not None:
        return session.get(Player, int(player_id))
    # fallback cookie
    return get_current_player(session)

@bp.get("/cards")
def list_cards():
    """
    Return all cards with the new data model:
    - categorie
    - rarity
    - gameplay
    - prices[]
    - shop{}
    - buy_rules{}
    - owned_qty

    context param:
    - context=inventory (défaut) : aucune carte cachée
    - context=shop            : on cache les cartes non visibles en boutique
                                + celles vendues au village
    """
    # contexte : "inventory" (par défaut) ou "shop"
    context = (request.args.get("context") or "inventory").lower()
    hide_for_main_shop = context == "shop"

    payload = {"playerId": request.args.get("playerId")}

    with SessionLocal() as s:
        p = _resolve_player(s, payload)
        if not p:
            return jsonify({"error": "player_required"}), 400

        # 1. Toutes les définitions de cartes actives
        all_defs = (
            s.query(CardDef)
            .filter(CardDef.enabled == True)
            .order_by(CardDef.key.asc())
            .all()
        )

        # 2. Cartes vendues actuellement dans le Village
        excluded_village_keys: set[str] = set()
        if hide_for_main_shop:
            excluded_village_keys = get_village_excluded_card_keys(
                dt.datetime.now(dt.timezone.utc)
            )

        visible_defs: list[CardDef] = []
        for cd in all_defs:
            if hide_for_main_shop:
                shop_cfg = cd.shop or {}

                # A) Si show_in_main_shop = false → exclue du shop normal
                if shop_cfg.get("show_in_main_shop") is False:
                    continue

                # B) Si la carte est vendue dans le village → exclue du shop principal
                if cd.key in excluded_village_keys:
                    continue

            visible_defs.append(cd)

        # 3. Quantités possédées par le joueur
        owned_rows = (
            s.query(PlayerCard)
            .filter_by(player_id=p.id)
            .all()
        )
        owned_map = {pc.card_key: pc.qty for pc in owned_rows}

        # 4. Construction du JSON (via le service)
        out = []
        for cd in visible_defs:
            owned_qty = owned_map.get(cd.key, 0)
            out.append(
                serialize_card_def(
                    cd,
                    owned_qty=owned_qty,
                    context=context,  # "inventory" ou "shop"
                )
            )

        return jsonify(out)


@bp.post("/cards/buy")
def buy_card():
    """
    Purchase a card using a selected price option.

    Expected JSON:
    {
      "card_key": "wood_boost_1",
      "price_index": 0,         # required
      "playerId": 1 (optional)  # fallback to cookie
    }
    """
    data = request.get_json(silent=True) or {}

    card_key = (data.get("card_key") or "").strip()
    price_index = data.get("price_index")

    if not card_key:
        return jsonify({"error": "card_key_required"}), 400

    if price_index is None:
        return jsonify({"error": "price_index_required"}), 400

    try:
        price_index = int(price_index)
    except (TypeError, ValueError):
        return jsonify({"error": "price_index_must_be_int"}), 400

    with SessionLocal() as s:
        # Resolve player (explicit playerId or cookie)
        p = _resolve_player(s, data)
        if not p:
            return jsonify({"error": "player_required"}), 400

        # Load card definition
        cd = s.query(CardDef).filter_by(key=card_key, enabled=True).first()
        if not cd:
            return jsonify({"error": "card_not_found_or_disabled"}), 404

        # --- Shop configuration (new schema) ---
        shop_cfg = cd.shop or {}

        # Prices are stored inside shop.prices (list of price options)
        prices = shop_cfg.get("prices") or []
        if not prices:
            return jsonify({"error": "no_price_defined_for_card"}), 500

        # Validate price index
        if price_index < 0 or price_index >= len(prices):
            return jsonify({"error": "invalid_price_index"}), 400

        price_cfg = prices[price_index] or {}

        # --- Buy rules / unlock rules ---
        # buy_rules can be stored in shop.buy_rules or in cd.unlock_rules
        buy_rules = shop_cfg.get("buy_rules") or cd.unlock_rules or {}

        ok, info = check_unlock_rules(p, buy_rules)
        if not ok:
            payload = {"error": info.get("reason", "buy_rules_not_met")}
            payload.update(info)
            return jsonify(payload), 403

        # --- Current owned quantity ---
        owned = (
            s.query(PlayerCard)
            .filter_by(player_id=p.id, card_key=cd.key)
            .first()
        )
        current_qty = owned.qty if owned else 0

        # --- Max owned (card_max_owned or shop.max_owned) ---
        max_owned = shop_cfg.get("max_owned")
        if max_owned is None:
            max_owned = cd.card_max_owned

        if max_owned is not None and current_qty >= max_owned:
            return jsonify({
                "error": "max_owned_reached",
                "max_owned": max_owned,
                "owned_qty": current_qty,
            }), 400

        # --- Global quantity / stock (card_quantity or shop.quantity) ---
        # If quantity is None or 0 => no global stock limit
        quantity = shop_cfg.get("quantity")
        if quantity is None:
            quantity = cd.card_quantity

        if quantity is not None and quantity > 0:
            # Remaining stock for this card (global, not per player)
            remaining = quantity - current_qty
            if remaining <= 0:
                return jsonify({"error": "sold_out"}), 400

        # --- Purchase limit (date) ---
        # Can be in shop.purchase_limit or cd.card_purchase_limit_quantity
        purchase_limit = shop_cfg.get("purchase_limit") or cd.card_purchase_limit_quantity
        if purchase_limit:
            import datetime
            from datetime import timezone

            try:
                limit_dt = datetime.datetime.fromisoformat(purchase_limit)
            except ValueError:
                # Invalid date format in data: treat as expired or ignore?
                return jsonify({"error": "invalid_purchase_limit_format"}), 500

            now = datetime.datetime.now(timezone.utc)
            if now > limit_dt:
                return jsonify({"error": "purchase_expired"}), 400

        # --- Validate payment option ---
        coins_cost = int(price_cfg.get("coins", 0) or 0)
        diams_cost = int(price_cfg.get("diams", 0) or 0)
        res_costs = price_cfg.get("resources") or {}

        # Coins
        if p.coins < coins_cost:
            return jsonify({"error": "not_enough_coins"}), 400

        # Diamonds
        if p.diams < diams_cost:
            return jsonify({"error": "not_enough_diams"}), 400

        # Resources
        for res_key, needed in res_costs.items():
            stock = (
                s.query(ResourceStock)
                .filter_by(player_id=p.id, resource=res_key)
                .first()
            )
            if not stock or stock.qty < needed:
                return jsonify({
                    "error": "not_enough_resource",
                    "resource": res_key,
                    "required": needed,
                }), 400

        # --- Deduct costs ---
        p.coins -= coins_cost
        p.diams -= diams_cost

        for res_key, needed in res_costs.items():
            stock = (
                s.query(ResourceStock)
                .filter_by(player_id=p.id, resource=res_key)
                .first()
            )
            stock.qty -= needed

        # --- Add card to inventory ---
        if owned is None:
            owned = PlayerCard(player_id=p.id, card_key=cd.key, qty=1)
            s.add(owned)
            new_qty = 1
        else:
            owned.qty += 1
            new_qty = owned.qty

        # Optionally update global card_quantity if you want
        # (e.g. decrement cd.card_quantity if you store actual stock at def level)
        # For now we keep it as "static template" and ignore global decrement.

        s.commit()
        s.refresh(p)
        s.refresh(owned)

        # Use serialize_card_def to keep API shape consistent
        card_payload = serialize_card_def(cd, owned_qty=new_qty, context="inventory")

        return jsonify({
            "ok": True,
            "card": card_payload,
            "owned_qty": new_qty,
            "player": {
                "id": p.id,
                "coins": p.coins,
                "diams": p.diams,
            }
        })


@bp.post("/village/shop/buy")
def buy_village_offer():
    """
    Purchase a card from the village shop.

    Expected JSON:
    {
      "offer_key": "village_card_lake_slot_2025w45"
    }
    """
    data = request.get_json(silent=True) or {}
    offer_key = (data.get("offer_key") or "").strip()
    if not offer_key:
        return jsonify({"error": "offer_key_required"}), 400

    today = dt.date.today()

    with SessionLocal() as s:
        # 1) Resolve player via cookie / session
        p = get_current_player(s)
        if not p:
            return jsonify({"error": "player_required"}), 400

        # 2) Find matching active offer
        active_offers = get_active_village_offers(today=today)
        offer = next((o for o in active_offers if o.get("key") == offer_key), None)
        if not offer:
            return jsonify({"error": "offer_not_active"}), 400

        item_type = offer.get("item_type")
        item_key = offer.get("item_key")

        if item_type != "card":
            return jsonify({"error": "unsupported_item_type"}), 400

        if not item_key:
            return jsonify({"error": "offer_missing_item_key"}), 500

        # 3) Associated CardDef
        cd = (
            s.query(CardDef)
            .filter_by(key=item_key, enabled=True)
            .first()
        )
        if not cd:
            return jsonify({"error": "card_not_found_or_disabled"}), 404

        shop_cfg = cd.shop or {}

        # 4) Owned quantity
        owned = (
            s.query(PlayerCard)
            .filter_by(player_id=p.id, card_key=cd.key)
            .first()
        )
        current_qty = owned.qty if owned else 0

        # 4.a) limit_per_player (village_shop.yml)
        limit_per_player = offer.get("limit_per_player")
        if limit_per_player is not None and current_qty >= limit_per_player:
            return jsonify({
                "error": "village_limit_reached",
                "limit_per_player": limit_per_player,
                "owned_qty": current_qty,
            }), 400

        # 4.b) max_owned (cards.yml → shop.max_owned or card_max_owned)
        max_owned = shop_cfg.get("max_owned")
        if max_owned is None:
            max_owned = cd.card_max_owned

        if max_owned is not None and current_qty >= max_owned:
            return jsonify({
                "error": "max_owned_reached",
                "max_owned": max_owned,
                "owned_qty": current_qty,
            }), 400

        # 5) Price from CardDef.shop.prices (we take the first option for now)
        prices = shop_cfg.get("prices") or []
        if not prices:
            return jsonify({"error": "no_price_defined_for_card"}), 500

        price_cfg = prices[0] or {}
        coins_cost = int(price_cfg.get("coins", 0) or 0)
        diams_cost = int(price_cfg.get("diams", 0) or 0)
        res_costs: dict = price_cfg.get("resources") or {}

        # 6) Check currencies
        if p.coins < coins_cost:
            return jsonify({"error": "not_enough_coins"}), 400

        if p.diams < diams_cost:
            return jsonify({"error": "not_enough_diams"}), 400

        # 6.b) Check resources
        for res_key, needed in res_costs.items():
            stock = (
                s.query(ResourceStock)
                .filter_by(player_id=p.id, resource=res_key)
                .first()
            )
            if not stock or stock.qty < needed:
                return jsonify({
                    "error": "not_enough_resource",
                    "resource": res_key,
                    "required": needed,
                }), 400

        # 7) Deduct costs
        p.coins -= coins_cost
        p.diams -= diams_cost

        for res_key, needed in res_costs.items():
            stock = (
                s.query(ResourceStock)
                .filter_by(player_id=p.id, resource=res_key)
                .first()
            )
            stock.qty -= needed

        # 8) Add card
        if owned is None:
            owned = PlayerCard(player_id=p.id, card_key=cd.key, qty=1)
            s.add(owned)
            new_qty = 1
        else:
            owned.qty += 1
            new_qty = owned.qty

        s.commit()
        s.refresh(p)
        s.refresh(owned)

        # Same shape as buy_card, but with offer_key
        card_payload = serialize_card_def(cd, owned_qty=new_qty, context="inventory")

        return jsonify(
            {
                "ok": True,
                "offer_key": offer_key,
                "card": card_payload,
                "owned_qty": new_qty,
                "player": {
                    "id": p.id,
                    "coins": p.coins,
                    "diams": p.diams,
                },
            }
        ), 200

        
@bp.post("/dev/set_card_qty")
def dev_set_card_qty():
    """Admin: set qty of a player card (debug only)."""
    data = request.get_json(silent=True) or {}
    pid = data.get("playerId")
    key = data.get("card_key")
    qty = data.get("qty")

    if pid is None or key is None or qty is None:
        return jsonify({"error": "invalid_payload"}), 400

    try:
        qty = int(qty)
    except ValueError:
        return jsonify({"error": "qty_must_be_int"}), 400

    with SessionLocal() as s:
        pc = set_player_card_qty(s, pid, key, qty)
        s.commit()

        # pc peut être None si qty <= 0 => on renvoie malgré tout ok=True
        return jsonify(
            {
                "ok": True,
                "key": key,
                "qty": qty,
                "note": "deleted" if pc is None and qty <= 0 else "updated_or_created",
            }
        )

