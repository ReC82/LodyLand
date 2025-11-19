from flask import Blueprint, jsonify, request
from app.db import SessionLocal
from app.auth import get_current_player
from app.lands import get_player_land_state
from app.models import PlayerLandSlots, PlayerCard

bp = Blueprint("lands", __name__)

@bp.post("/lands/<land_key>/slots/buy")
def buy_land_slot(land_key):
    """
    Unlock one extra slot for a land.

    Logic:
    - If player has a matching 'free slot' card, consume it and add slot (no diams).
    - Else, pay with diams using next_cost from land_state.
    """
    data = request.get_json(silent=True) or {}

    with SessionLocal() as s:
        player = get_current_player(s)
        if not player:
            return jsonify({"error": "player_required"}), 401

        # État actuel (base + extra + coût du prochain slot)
        state_before = get_player_land_state(s, player.id, land_key)
        cost = state_before["next_cost"]

        # 1) Vérifier s'il existe une carte "free slot" pour ce land
        # Convention: land_<land_key>_free_slot
        free_card_key = f"land_{land_key}_free_slot"
        free_card = (
            s.query(PlayerCard)
            .filter_by(player_id=player.id, card_key=free_card_key)
            .first()
        )

        used_free_card = False

        if free_card and free_card.qty > 0:
            # On consomme la carte gratuite
            free_card.qty -= 1
            if free_card.qty <= 0:
                s.delete(free_card)
            used_free_card = True
        else:
            # Pas de carte → on paie en diams
            if player.diams < cost:
                return jsonify({"error": "not_enough_diams"}), 400
            player.diams -= cost

        # 2) Ajouter le slot (quel que soit le mode de paiement)
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

        # 3) Recalculer l'état du land pour renvoyer au frontend
        land_state = get_player_land_state(s, player.id, land_key)

        # Combien de cartes free slot il reste (pour info HUD / inventaire)
        remaining_free = 0
        if used_free_card:
            # free_card peut avoir été deleted => re-fetch propre
            new_pc = (
                s.query(PlayerCard)
                .filter_by(player_id=player.id, card_key=free_card_key)
                .first()
            )
            remaining_free = new_pc.qty if new_pc else 0

        return jsonify(
            {
                "ok": True,
                "land_key": land_key,
                "used_free_card": used_free_card,
                "remaining_free_cards": remaining_free,
                "player": {
                    "id": player.id,
                    "diams": player.diams,
                },
                "land_state": land_state,
            }
        ), 200