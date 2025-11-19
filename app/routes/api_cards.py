# app/routes/api_players.py
from flask import Blueprint, jsonify, request
from app.db import SessionLocal
from app.models import Player, CardDef, PlayerCard, ResourceStock
from app.unlock_rules import check_unlock_rules
from app.auth import get_current_player
from app.services.cards import set_player_card_qty

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
    """
    payload = {"playerId": request.args.get("playerId")}

    with SessionLocal() as s:
        p = _resolve_player(s, payload)
        if not p:
            return jsonify({"error": "player_required"}), 400

        defs = (
            s.query(CardDef)
            .filter(CardDef.enabled == True)
            .order_by(CardDef.key.asc())
            .all()
        )

        owned_rows = (
            s.query(PlayerCard)
            .filter_by(player_id=p.id)
            .all()
        )
        owned_map = {pc.card_key: pc.qty for pc in owned_rows}

        out = []
        for cd in defs:
            out.append({
                "key": cd.key,
                "label": cd.label,
                "description": cd.description,
                "icon": cd.icon,

                "categorie": cd.categorie,
                "rarity": cd.rarity,
                "type": cd.type,

                "gameplay": cd.gameplay or {},
                "prices": cd.prices or [],
                "shop": cd.shop or {},
                "buy_rules": cd.buy_rules or {},

                "enabled": cd.enabled,
                "owned_qty": owned_map.get(cd.key, 0),
            })

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

    with SessionLocal() as s:
        p = _resolve_player(s, data)
        if not p:
            return jsonify({"error": "player_required"}), 400

        cd = s.query(CardDef).filter_by(key=card_key, enabled=True).first()
        if not cd:
            return jsonify({"error": "card_not_found_or_disabled"}), 404

        shop = cd.shop or {}
        prices = cd.prices or []

        # --- Validate price index ---
        if price_index < 0 or price_index >= len(prices):
            return jsonify({"error": "invalid_price_index"}), 400

        price_cfg = prices[price_index]

        # --- Check buy rules ---
        ok, info = check_unlock_rules(p, cd.buy_rules)
        if not ok:
            payload = {"error": info.get("reason", "buy_rules_not_met")}
            payload.update(info)
            return jsonify(payload), 403

        # --- Max owned ---
        owned = (
            s.query(PlayerCard)
            .filter_by(player_id=p.id, card_key=cd.key)
            .first()
        )
        current_qty = owned.qty if owned else 0

        max_owned = shop.get("max_owned")
        if max_owned is not None and current_qty >= max_owned:
            return jsonify({
                "error": "max_owned_reached",
                "max_owned": max_owned,
                "owned_qty": current_qty
            }), 400

        # --- Quantity (global stock) ---
        quantity = shop.get("quantity", 0)
        if quantity > 0:
            # We must ensure this card still has stock
            remaining = quantity - current_qty
            if remaining <= 0:
                return jsonify({"error": "sold_out"}), 400

        # --- Purchase limit (date) ---
        purchase_limit = shop.get("purchase_limit")
        if purchase_limit:
            import datetime
            from datetime import timezone

            limit_dt = datetime.datetime.fromisoformat(purchase_limit)
            now = datetime.datetime.now(timezone.utc)

            if now > limit_dt:
                return jsonify({"error": "purchase_expired"}), 400

        # --- Validate payment option ---
        coins_cost = price_cfg.get("coins", 0)
        diams_cost = price_cfg.get("diams", 0)
        res_costs = price_cfg.get("resources", {})

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
                    "required": needed
                }), 400

        # --- Deduct costs ---
        p.coins -= coins_cost
        p.diams -= diams_cost

        # Deduct resources
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

        s.commit()
        s.refresh(p)
        s.refresh(owned)

        return jsonify({
            "ok": True,
            "card": {
                "key": cd.key,
                "label": cd.label,
                "categorie": cd.categorie,
            },
            "owned_qty": new_qty,
            "player": {
                "id": p.id,
                "coins": p.coins,
                "diams": p.diams,
            }
        })
        
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

        