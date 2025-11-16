# app/routes/api_players.py
from flask import Blueprint, jsonify, request
from app.db import SessionLocal
from app.models import Player, CardDef, PlayerCard
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
    Liste les cartes disponibles + combien le joueur en possède.

    Query params:
      - playerId (optionnel)

    Réponse:
      [
        {
          "key": "...",
          "label": "...",
          "type": "resource_boost",
          "target_resource": "wood",
          "price_coins": 50,
          "price_diams": 0,
          "max_owned": 5,
          "enabled": true,
          "owned_qty": 0
        },
        ...
      ]
    """
    payload = {"playerId": request.args.get("playerId")}
    with SessionLocal() as s:
        p = _resolve_player(s, payload)
        if not p:
            return jsonify({"error": "player_required"}), 400

        # Cartes actives
        defs = (
            s.query(CardDef)
            .filter_by(enabled=True)
            .order_by(CardDef.key.asc())
            .all()
        )

        # Cartes du joueur (par key)
        owned_rows = (
            s.query(PlayerCard)
            .filter_by(player_id=p.id)
            .all()
        )
        owned_by_key = {pc.card_key: pc for pc in owned_rows}

        data = []
        for cd in defs:
            pc = owned_by_key.get(cd.key)
            data.append(
                {
                    "key": cd.key,
                    "label": cd.label,
                    "description": cd.description,
                    "icon": cd.icon,
                    "type": cd.type,
                    "target_resource": cd.target_resource,
                    "price_coins": cd.price_coins,
                    "price_diams": cd.price_diams,
                    "max_owned": cd.max_owned,
                    "enabled": cd.enabled,
                    "owned_qty": pc.qty if pc else 0,
                }
            )

        return jsonify(data)

@bp.post("/cards/buy")
def buy_card():
    """
    Achat d'une carte.

    JSON attendu:
      {
        "card_key": "wood_boost_1",
        "playerId": 1   # optionnel si cookie
      }

    Utilise price_coins / price_diams pour débiter le joueur.
    Respecte max_owned si défini.
    """
    data = request.get_json(silent=True) or {}
    card_key = (data.get("card_key") or "").strip()
    if not card_key:
        return jsonify({"error": "card_key_required"}), 400

    with SessionLocal() as s:
        p = _resolve_player(s, data)
        if not p:
            return jsonify({"error": "player_required"}), 400

        cd = s.query(CardDef).filter_by(key=card_key, enabled=True).first()
        if not cd:
            return jsonify({"error": "card_not_found_or_disabled"}), 404

        # Règles d'unlock (niveau, coins, etc.) optionnelles
        ok, info = check_unlock_rules(p, cd.unlock_rules)
        if not ok:
            payload = {"error": info.get("reason", "unlock_conditions_not_met")}
            payload.update(info)
            return jsonify(payload), 403

        # Vérifier le max_owned
        pc = (
            s.query(PlayerCard)
            .filter_by(player_id=p.id, card_key=cd.key)
            .first()
        )

        current_qty = pc.qty if pc else 0
        if cd.max_owned is not None and current_qty >= cd.max_owned:
            return jsonify(
                {
                    "error": "max_owned_reached",
                    "max_owned": cd.max_owned,
                    "owned_qty": current_qty,
                }
            ), 400

        # Vérifier la monnaie (priorité aux coins, sinon diams)
        if cd.price_coins > 0:
            if p.coins < cd.price_coins:
                return jsonify({"error": "not_enough_coins"}), 400
            p.coins -= cd.price_coins

        if cd.price_diams > 0:
            if p.diams < cd.price_diams:
                return jsonify({"error": "not_enough_diams"}), 400
            p.diams -= cd.price_diams

        # Ajouter / incrémenter la PlayerCard
        if pc is None:
            pc = PlayerCard(player_id=p.id, card_key=cd.key, qty=1)
            s.add(pc)
            owned_qty = 1
        else:
            pc.qty += 1
            owned_qty = pc.qty

        s.commit()
        s.refresh(p)
        s.refresh(pc)

        return jsonify(
            {
                "ok": True,
                "card": {
                    "key": cd.key,
                    "label": cd.label,
                    "type": cd.type,
                    "target_resource": cd.target_resource,
                },
                "owned_qty": owned_qty,
                "player": {
                    "id": p.id,
                    "coins": p.coins,
                    "diams": p.diams,
                },
            }
        )
        
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

        