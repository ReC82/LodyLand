# app/routes/api_skills.py
from __future__ import annotations

from flask import Blueprint, jsonify

from app.auth import get_current_player
from app.db import SessionLocal
from app.services.skill_engine import get_all_player_skills

bp = Blueprint("skills", __name__)


@bp.get("/skills")
def skills_list():
    """Return all skills for the current player."""
    with SessionLocal() as s:
        player = get_current_player(s)
        if not player:
            return jsonify({"error": "player_required"}), 401
        skills = get_all_player_skills(player.id, session=s)
    return jsonify({"ok": True, "skills": skills})
