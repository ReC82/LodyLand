# app/routes/api_quests.py
from __future__ import annotations

import datetime as dt

from flask import Blueprint, jsonify, request

from app.auth import get_current_player
from app.db import SessionLocal
from app.models import PlayerQuest
from app.progression import next_threshold, apply_xp_and_level_up
from app.quests.service import (
    QUEST_MIN_LEVEL,
    _apply_quest_rewards,
    assign_continuous_quest_if_needed,
    assign_daily_quest_if_needed,
    assign_weekly_quest_if_needed,
    auto_mark_expired_quests,
    serialize_quest,
)

bp = Blueprint("quests", __name__)


# --------------------------------------------------------------------
# GET /api/quests  — quêtes actives organisées par type
# --------------------------------------------------------------------
@bp.get("/quests")
def get_quests():
    with SessionLocal() as s:
        me = get_current_player(s)
        if not me:
            return jsonify({"error": "not_authenticated"}), 401

        # Level gate — quests become available at QUEST_MIN_LEVEL
        if (me.level or 0) < QUEST_MIN_LEVEL:
            return jsonify({
                "locked": True,
                "min_level": QUEST_MIN_LEVEL,
                "daily": [],
                "weekly": [],
                "continuous": [],
            }), 200

        now = dt.datetime.utcnow()

        # Auto-assign + clean up expired quests
        auto_mark_expired_quests(s, me, now=now)
        assign_daily_quest_if_needed(s, me, now=now)
        assign_weekly_quest_if_needed(s, me, now=now)
        assign_continuous_quest_if_needed(s, me, now=now)
        s.commit()

        active = (
            s.query(PlayerQuest)
            .filter(PlayerQuest.player_id == me.id)
            .filter(PlayerQuest.status.in_(["active", "ready"]))
            .order_by(PlayerQuest.started_at.asc())
            .all()
        )

        # Exclude expired quests from the response (belt-and-suspenders)
        now_ts = now
        daily      = [q for q in active if q.quest_type == "daily"
                      and (q.expires_at is None or q.expires_at > now_ts)]
        weekly     = [q for q in active if q.quest_type == "weekly"
                      and (q.expires_at is None or q.expires_at > now_ts)]
        continuous = [q for q in active if q.quest_type == "continuous"]

        return jsonify({
            "daily":      [serialize_quest(q) for q in daily],
            "weekly":     [serialize_quest(q) for q in weekly],
            "continuous": [serialize_quest(q) for q in continuous],
        }), 200


# --------------------------------------------------------------------
# POST /api/quests/claim
# --------------------------------------------------------------------
@bp.post("/quests/claim")
def claim_quest():
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
        me = get_current_player(s)
        if not me:
            return jsonify({"error": "not_authenticated"}), 401

        quest = (
            s.query(PlayerQuest)
            .filter(PlayerQuest.id == quest_id, PlayerQuest.player_id == me.id)
            .one_or_none()
        )

        if not quest:
            return jsonify({"error": "quest_not_found"}), 404

        if any(obj.current_value < obj.target_value for obj in quest.objectives):
            return jsonify({"error": "objectives_not_fulfilled", "status": quest.status}), 400

        if quest.status != "ready":
            return jsonify({"error": "quest_not_ready", "status": quest.status}), 400

        if quest.expires_at is not None and now > quest.expires_at:
            quest.status = "expired"
            quest.completed_at = now
            s.commit()
            return jsonify({"error": "quest_expired"}), 400

        # Apply non-XP rewards (shards, essence) via service helper,
        # then handle XP separately so level-ups are triggered properly.
        rewards = quest.rewards_json or {}
        quest_xp = int(rewards.get("xp", 0) or 0)

        _apply_quest_rewards(me, quest)

        # Re-apply XP through the proper leveling pipeline (undo the direct add first)
        if quest_xp > 0:
            me.xp = float(me.xp or 0) - quest_xp  # undo direct add from _apply_quest_rewards
            level_up, new_level, level_rewards = apply_xp_and_level_up(s, me, quest_xp)
        else:
            level_up, new_level, level_rewards = False, me.level or 0, []

        completed_type = quest.quest_type
        completed_key  = quest.template_key

        quest.status = "completed"
        quest.completed_at = now

        # Auto-assign new continuous quest immediately
        new_quest = None
        if completed_type == "continuous":
            new_quest = assign_continuous_quest_if_needed(
                s, me, exclude_quest_id=quest.id, now=now
            )

        s.commit()
        s.refresh(me)
        s.refresh(quest)

        return jsonify({
            "ok": True,
            "player": {
                "id":      me.id,
                "name":    me.name,
                "level":   me.level,
                "xp":      me.xp,
                "next_xp": next_threshold(me.level),
                "shards":  me.shards,
                "essence": me.essence,
            },
            "level_up":     level_up,
            "new_level":    new_level if level_up else None,
            "level_rewards": level_rewards if level_up else [],
            "quest":     serialize_quest(quest),
            "new_quest": serialize_quest(new_quest) if new_quest else None,
        }), 200
