from flask import Blueprint, jsonify, request
from app.db import SessionLocal
from app.auth import get_current_player
from app.lands import get_player_land_state
from app.models import PlayerLandSlots

bp = Blueprint("lands", __name__)

@bp.post("/lands/<land_key>/slots/buy")
def buy_slot(land_key):
    data = request.get_json(silent=True) or {}

    with SessionLocal() as s:
        player = get_current_player(s)
        if not player:
            return jsonify({"error": "player_required"}), 401

        state = get_player_land_state(s, player.id, land_key)
        cost = state["next_cost"]

        if player.diams < cost:
            return jsonify({"error": "not_enough_diams"}), 400

        # payer
        player.diams -= cost

        # enregistrer
        pls = (
            s.query(PlayerLandSlots)
            .filter_by(player_id=player.id, land_key=land_key)
            .first()
        )
        if not pls:
            pls = PlayerLandSlots(player_id=player.id, land_key=land_key, extra_slots=1)
            s.add(pls)
        else:
            pls.extra_slots += 1

        s.commit()
        # recalcul state
        new_state = get_player_land_state(s, player.id, land_key)

        return jsonify({
            "ok": True,
            "player": {"diams": player.diams},
            "land_state": new_state,
        })
