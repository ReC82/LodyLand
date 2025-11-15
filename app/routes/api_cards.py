# app/routes/api_players.py
from flask import Blueprint, jsonify, request
from app.db import SessionLocal
from app.models import Player, CardDef, PlayerCard
from app.unlock_rules import check_unlock_rules


bp = Blueprint("cards", __name__)

@bp.get("/shop/cards")
def list_shop_cards():
    with SessionLocal() as s:
        # TODO: récupérer le player courant (cookie) ou playerId querystring
        # pour l'instant : mocked / à adapter
        player_id = request.args.get("playerId", type=int)
        p = s.get(Player, player_id) if player_id else None

        cards = s.query(CardDef).filter_by(enabled=True).all()
        out = []

        for c in cards:
            can_buy = False
            reason = None

            if p:
                ok, details = check_unlock_rules(p, c.unlock_rules)
                if not ok:
                    reason = details.get("reason", "unlock_conditions_not_met")
                else:
                    can_buy = True  # côté shop : conditions remplies
            else:
                reason = "player_required"

            out.append({
                "key": c.key,
                "label": c.label,
                "description": c.description,
                "icon": c.icon,
                "price_coins": c.price_coins,
                "price_diams": c.price_diams,
                "can_buy": can_buy,
                "reason": reason,
            })

        return jsonify(out)

@bp.post("/api/shop/cards/buy")
def buy_card():
    data = request.get_json(silent=True) or {}
    card_key = (data.get("card") or "").strip()
    player_id = data.get("playerId")

    if not card_key or not player_id:
        return jsonify({"error": "payload_invalid"}), 400

    with SessionLocal() as s:
        p = s.get(Player, int(player_id))
        if not p:
            return jsonify({"error": "player_not_found"}), 404

        c = s.query(CardDef).filter_by(key=card_key, enabled=True).first()
        if not c:
            return jsonify({"error": "card_not_found"}), 404

        # max_owned
        if c.max_owned is not None:
            existing = (
                s.query(PlayerCard)
                .filter_by(player_id=p.id, card_key=c.key)
                .first()
            )
            if existing and existing.qty >= c.max_owned:
                return jsonify({"error": "max_owned_reached"}), 409

        # règles d’unlock (lvl, etc.)
        ok, details = check_unlock_rules(p, c.unlock_rules)
        if not ok:
            payload = {"error": details.get("reason", "unlock_conditions_not_met")}
            payload.update(details)
            return jsonify(payload), 403

        # coût
        if p.coins < c.price_coins or p.diams < c.price_diams:
            return jsonify({"error": "not_enough_currency"}), 403

        p.coins -= c.price_coins
        p.diams -= c.price_diams

        # ajout carte
        pc = (
            s.query(PlayerCard)
            .filter_by(player_id=p.id, card_key=c.key)
            .first()
        )
        if not pc:
            pc = PlayerCard(player_id=p.id, card_key=c.key, qty=1)
            s.add(pc)
        else:
            pc.qty += 1

        s.commit()

        return jsonify({
            "ok": True,
            "player": {
                "id": p.id,
                "coins": p.coins,
                "diams": p.diams,
            },
            "card": {
                "key": c.key,
                "qty": pc.qty,
            },
        }), 200