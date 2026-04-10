# app/routes/api_misc.py
from flask import Blueprint, jsonify, request
from app.auth import get_current_player
from app.db import SessionLocal
from app.models import Player
from app.progression import apply_xp_and_level_up, xp_required_for, MAX_LEVEL


bp = Blueprint("misc", __name__)


# -----------------------------------------------------------------
# Dev UI
# -----------------------------------------------------------------
@bp.get("/ui")
def dev_ui():
    return bp.send_static_file("ui/index.html")


@bp.get("/health")
def health():
    """Simple health endpoint used by tests."""
    return jsonify({"status": "ok"})


# -----------------------------------------------------------------
# DEV ONLY — Set player level instantly
# -----------------------------------------------------------------
@bp.post("/dev/set-level")
def dev_set_level():
    """
    DEV ONLY.
    Instantly set the current player's level (and XP) to the requested level.
    All rewards for intermediate levels are applied.

    Body: { "level": 10 }
    """
    data = request.get_json(silent=True) or {}
    target = data.get("level")

    if target is None:
        return jsonify({"error": "level_required"}), 400
    try:
        target = int(target)
    except (ValueError, TypeError):
        return jsonify({"error": "level_invalid"}), 400

    if target < 1 or target > MAX_LEVEL:
        return jsonify({"error": "level_out_of_range", "max": MAX_LEVEL}), 400

    player_id = data.get("player_id")

    with SessionLocal() as s:
        if player_id is not None:
            p = s.get(Player, int(player_id))
        else:
            p = get_current_player(s)
        if not p:
            return jsonify({"error": "player_required"}), 401

        # XP needed to be exactly at target level
        target_xp = xp_required_for(target)

        # Force XP and let apply_xp_and_level_up handle rewards
        p.xp = target_xp
        _, _, rewards = apply_xp_and_level_up(s, p, 0)

        s.commit()
        s.refresh(p)

        return jsonify({
            "ok": True,
            "level": p.level,
            "xp": p.xp,
            "rewards_applied": rewards,
        })
