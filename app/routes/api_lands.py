from flask import Blueprint, jsonify, request
from app.db import SessionLocal
from app.auth import get_current_player
from app.lands import get_player_land_state
from app.models import PlayerLandSlots, PlayerCard, CardDef 
from app.lands import get_land_def 

bp = Blueprint("lands", __name__)

def get_unlocked_lands_for_player(session, player, lang="fr"):
    """Return a list of unlocked lands for a given player."""
    # 1) All cards of the player
    owned_cards = (
        session.query(PlayerCard)
        .filter(PlayerCard.player_id == player.id)
        .all()
    )

    land_card_keys = [
        pc.card_key
        for pc in owned_cards
        if pc.qty > 0
        and isinstance(pc.card_key, str)
        and pc.card_key.startswith("land_")
    ]

    if not land_card_keys:
        return []

    card_defs = (
        session.query(CardDef)
        .filter(CardDef.key.in_(land_card_keys))
        .all()
    )

    lands_payload = []

    for cd in card_defs:
        base_label = getattr(cd, "card_label", cd.key)
        label_fr = getattr(cd, "card_label_fr", None) or base_label
        label_en = getattr(cd, "card_label_en", None) or base_label

        label = label_en if lang == "en" else label_fr

        card_key = cd.key          # ex: land_forest
        land_key = card_key[len("land_"):] if card_key.startswith("land_") else card_key

        # 🔹 On va chercher la définition du land pour récupérer le slot_icon
        land_def = get_land_def(land_key)  # à adapter : dict, objet, etc.
        slot_icon = None
        is_special = False

        if land_def:
            # Ici j’imagine que tu as quelque chose comme land_def["slot_icon"]
            slot_icon = getattr(land_def, "slot_icon", None) or land_def.get("slot_icon")
            # Tag "specials" dans les tags du land (ou de la card si tu préfères)
            tags = set(getattr(land_def, "tags", []) or land_def.get("tags", []) or [])
            is_special = "specials" in tags

        lands_payload.append(
            {
                "card_key": card_key,
                "land_key": land_key,
                "label": label,
                "slot_icon": slot_icon,  # 🔹 utilisé par le template
                "url": f"/land/{land_key}",
                "is_special": is_special,
            }
        )

    lands_payload.sort(key=lambda l: (l["label"] or "").lower())
    return lands_payload

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
                    "essence": player.essence,
                },
                "land_state": land_state,
            }
        ), 200
        
@bp.get("/lands/unlocked")
def list_unlocked_lands():
    """Return all lands unlocked for the current player (based on land_* cards)."""
    with SessionLocal() as s:
        player = get_current_player(s)
        if not player:
            return jsonify({"error": "player_required"}), 401

        lang = (request.accept_languages.best_match(["fr", "en"]) or "fr").lower()
        lands_payload = get_unlocked_lands_for_player(s, player, lang=lang)

        # Pour compatibilité avec ton front actuel (JS)
        return jsonify({"lands": lands_payload}), 200
