# app/routes/api_quests.py
from __future__ import annotations

import datetime as dt

from flask import Blueprint, jsonify, request

from app.db import SessionLocal
from app.models import Player, PlayerQuest
from app.quests.service import _apply_quest_rewards, serialize_quest

bp = Blueprint("quests", __name__)


# --------------------------------------------------------------------
# Helper local : récupérer le joueur courant via le cookie player_id
# (on le duplique ici pour éviter les imports circulaires)
# --------------------------------------------------------------------
def _get_current_player(session) -> Player | None:
    from flask import request as flask_request

    pid = flask_request.cookies.get("player_id")
    if not pid:
        return None
    try:
        pid = int(pid)
    except ValueError:
        return None
    return session.get(Player, pid)


# --------------------------------------------------------------------
# POST /api/quests/claim
# --------------------------------------------------------------------
@bp.post("/quests/claim")
def claim_quest():
    """
    Permet au joueur de valider une quête en status 'ready'.

    Input JSON:
      {
        "quest_id": 31
      }

    Règles v1:
      - La quête doit appartenir au joueur courant.
      - status doit être 'ready'.
      - Si la quête est expirée, on la marque 'expired' et on refuse.
      - On applique les récompenses (coins, diams) et on passe en 'completed'.
    """
    data = request.get_json(silent=True) or {}
    quest_id = data.get("quest_id")

    if not quest_id:
        return jsonify({"error": "quest_id_required"}), 400

    try:
        quest_id = int(quest_id)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_quest_id"}), 400

    now = dt.datetime.utcnow()

    with SessionLocal() as s:
        me = _get_current_player(s)
        if not me:
            return jsonify({"error": "not_authenticated"}), 401

        quest = (
            s.query(PlayerQuest)
            .filter(
                PlayerQuest.id == quest_id,
                PlayerQuest.player_id == me.id,
            )
            .one_or_none()
        )

        if not quest:
            return jsonify({"error": "quest_not_found"}), 404

        # 1) objectifs vraiment atteints ?
        if any(obj.current_value < obj.target_value for obj in quest.objectives):
            return jsonify(
                {
                    "error": "objectives_not_fulfilled",
                    "status": quest.status,
                }
            ), 400

        # 2) statut prêt ?
        if quest.status != "ready":
            return jsonify(
                {
                    "error": "quest_not_ready",
                    "status": quest.status,
                }
            ), 400

        # 3) expiration ?
        if quest.expires_at is not None and now > quest.expires_at:
            quest.status = "expired"
            quest.completed_at = now
            s.commit()
            return jsonify({"error": "quest_expired"}), 400

        # 👉 Baby step 2 : on NE touche pas encore aux ressources.
        # On applique juste les récompenses (coins / diams)
        _apply_quest_rewards(me, quest)

        quest.status = "completed"
        quest.completed_at = now

        s.commit()
        s.refresh(me)
        s.refresh(quest)

        return jsonify(
            {
                "ok": True,
                "player": {
                    "id": me.id,
                    "name": me.name,
                    "level": me.level,
                    "xp": me.xp,
                    "shards": me.shards,
                    "essence": me.essence,
                },
                "quest": serialize_quest(quest),
            }
        ), 200
