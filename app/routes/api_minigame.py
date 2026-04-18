# =============================================================================
# app/routes/api_minigame.py
# Mini-game "Doors" API
# =============================================================================
from __future__ import annotations

import hashlib
import random
import datetime as dt

from flask import Blueprint, jsonify, request
from app.db import SessionLocal
from app.auth import get_current_player
from app.models import Player, MiniGameDef, PlayerMiniGameState, PlayerCard, CardDef

bp = Blueprint("minigame", __name__)

TOTAL_LEVELS = 10
MIN_DOORS = 3

# ---------------------------------------------------------------------------
# Default rewards if not configured in DB
# ---------------------------------------------------------------------------
def _default_rewards() -> list[dict]:
    rewards = []
    for lvl in range(1, TOTAL_LEVELS + 1):
        entry: dict = {
            "win_stop":     {"shards": lvl * 8},
            "win_continue": {"shards": lvl * 4},
        }
        if lvl == TOTAL_LEVELS:
            entry["win_grand"] = {"shards": 50}  # card_key comes from MiniGameDef
        rewards.append(entry)
    return rewards


# ---------------------------------------------------------------------------
# Path generation — deterministic per (player_id, minigame_key)
# ---------------------------------------------------------------------------
def _generate_path(player_id: int, minigame_key: str) -> list[dict]:
    """
    Returns a list of TOTAL_LEVELS dicts:
      {"doors": ["lose", "win_stop", "win_continue"]}  (levels 1-9)
      {"doors": ["lose", "win_stop", "win_grand"]}      (level 10)

    The arrangement is shuffled but always the same for a given player+game.
    All players have equal base chances: each outcome appears exactly once per level.
    """
    seed_str = f"lodyland_mg_{player_id}_{minigame_key}_v1"
    seed = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16) % (2 ** 32)
    rng = random.Random(seed)

    path = []
    for lvl in range(1, TOTAL_LEVELS + 1):
        if lvl == TOTAL_LEVELS:
            door_types = ["lose", "win_stop", "win_grand"]
        else:
            door_types = ["lose", "win_stop", "win_continue"]
        rng.shuffle(door_types)
        path.append({"doors": door_types})

    return path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _reset_daily_if_needed(state: PlayerMiniGameState) -> None:
    today = dt.date.today()
    if state.last_attempt_date != today:
        state.daily_attempts_used = 0
        state.last_attempt_date = today


def _get_or_create_state(
    session, player: Player, mg: MiniGameDef
) -> PlayerMiniGameState:
    state = (
        session.query(PlayerMiniGameState)
        .filter_by(player_id=player.id, minigame_key=mg.key)
        .first()
    )
    if state is None:
        state = PlayerMiniGameState(
            player_id=player.id,
            minigame_key=mg.key,
            path_json=_generate_path(player.id, mg.key),
        )
        session.add(state)
        session.flush()
    return state


def _serialize_state(state: PlayerMiniGameState, mg: MiniGameDef,
                     player: Player) -> dict:
    """Return safe client-facing state (no door outcomes revealed ahead of time)."""
    _reset_daily_if_needed(state)
    free = mg.free_attempts_per_day
    used = state.daily_attempts_used
    can_attempt_free = used < free

    return {
        "minigame_key": mg.key,
        "name_fr": mg.name_fr,
        "name_en": mg.name_en,
        "description_fr": mg.description_fr or "",
        "description_en": mg.description_en or "",
        "min_level": mg.min_level,
        "total_levels": TOTAL_LEVELS,
        "card_key": mg.card_key,
        "card_stock_remaining": mg.card_stock_remaining,
        "extra_attempt_cost_diams": mg.extra_attempt_cost_diams,
        "free_attempts_per_day": free,
        "daily_attempts_used": used,
        "can_attempt_free": can_attempt_free,
        "player_diams": player.essence,
        # Current run
        "in_progress": state.in_progress,
        "current_level": state.current_level,
        # History
        "has_won_card": state.has_won_card,
        "best_level_reached": state.best_level_reached,
        "total_attempts": state.total_attempts,
    }


# ---------------------------------------------------------------------------
# GET /api/minigame/<key>/state
# ---------------------------------------------------------------------------
@bp.get("/minigame/<key>/state")
def minigame_state(key: str):
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        mg = session.query(MiniGameDef).filter_by(key=key, enabled=True).first()
        if not mg:
            return jsonify({"ok": False, "error": "not_found"}), 404

        if player.level < mg.min_level:
            return jsonify({"ok": False, "error": "level_required",
                            "min_level": mg.min_level}), 403

        state = _get_or_create_state(session, player, mg)
        _reset_daily_if_needed(state)
        session.commit()

        return jsonify({"ok": True, "state": _serialize_state(state, mg, player)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        session.close()


# ---------------------------------------------------------------------------
# POST /api/minigame/<key>/start
# ---------------------------------------------------------------------------
@bp.post("/minigame/<key>/start")
def minigame_start(key: str):
    """Start a new attempt (or resume existing one if in_progress)."""
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        mg = session.query(MiniGameDef).filter_by(key=key, enabled=True).first()
        if not mg:
            return jsonify({"ok": False, "error": "not_found"}), 404

        if player.level < mg.min_level:
            return jsonify({"ok": False, "error": "level_required",
                            "min_level": mg.min_level}), 403

        if mg.card_stock_remaining <= 0:
            return jsonify({"ok": False, "error": "stock_exhausted"}), 410

        state = _get_or_create_state(session, player, mg)
        _reset_daily_if_needed(state)

        if state.has_won_card:
            return jsonify({"ok": False, "error": "already_won"}), 409

        # If already mid-run, just return current level (resume)
        if state.in_progress:
            session.commit()
            current_door_data = _current_level_doors(state, mg)
            return jsonify({
                "ok": True,
                "resumed": True,
                "current_level": state.current_level,
                "doors": current_door_data,
                "state": _serialize_state(state, mg, player),
            })

        # Check attempt quota
        use_paid = request.json.get("paid", False) if request.is_json else False
        free = mg.free_attempts_per_day

        if state.daily_attempts_used >= free:
            # Need to pay
            if not use_paid:
                return jsonify({
                    "ok": False,
                    "error": "no_free_attempts",
                    "cost_diams": mg.extra_attempt_cost_diams,
                }), 402
            if player.essence < mg.extra_attempt_cost_diams:
                return jsonify({"ok": False, "error": "not_enough_diams"}), 402
            player.essence -= mg.extra_attempt_cost_diams

        # Start attempt
        state.in_progress = True
        state.current_level = 1
        state.daily_attempts_used += 1
        state.total_attempts += 1

        session.commit()

        current_door_data = _current_level_doors(state, mg)
        return jsonify({
            "ok": True,
            "resumed": False,
            "current_level": 1,
            "doors": current_door_data,
            "state": _serialize_state(state, mg, player),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        session.close()


def _current_level_doors(state: PlayerMiniGameState, mg: MiniGameDef) -> list[dict]:
    """Return door info for current level — no hints, no outcomes, nothing deducible."""
    lvl = state.current_level
    if not state.path_json or lvl < 1 or lvl > TOTAL_LEVELS:
        return []
    level_data = state.path_json[lvl - 1]
    count = len(level_data.get("doors", []))
    # Only send door count — no hint, no reward preview, no outcome
    return [{"index": i} for i in range(count)]


# ---------------------------------------------------------------------------
# POST /api/minigame/<key>/choose
# ---------------------------------------------------------------------------
@bp.post("/minigame/<key>/choose")
def minigame_choose(key: str):
    """Player picks a door. Returns outcome + rewards."""
    data = request.get_json(silent=True) or {}
    door_index = data.get("door")
    if door_index is None or door_index not in (0, 1, 2):
        return jsonify({"ok": False, "error": "invalid_door"}), 400

    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        mg = session.query(MiniGameDef).filter_by(key=key, enabled=True).first()
        if not mg:
            return jsonify({"ok": False, "error": "not_found"}), 404

        state = (
            session.query(PlayerMiniGameState)
            .filter_by(player_id=player.id, minigame_key=key)
            .first()
        )
        if not state or not state.in_progress:
            return jsonify({"ok": False, "error": "no_active_run"}), 409

        lvl = state.current_level
        level_data = state.path_json[lvl - 1]
        outcome = level_data["doors"][door_index]

        rewards = mg.rewards_json or _default_rewards()
        level_rewards = rewards[lvl - 1] if lvl - 1 < len(rewards) else {}

        granted: dict = {}
        next_level: int | None = None
        run_over = False
        won_grand = False

        if outcome == "lose":
            run_over = True
            state.in_progress = False
            state.current_level = 0

        elif outcome in ("win_stop", "win_continue", "win_grand"):
            # Grant rewards
            reward_def = level_rewards.get(outcome, {})
            shards = reward_def.get("shards", 0)
            if shards:
                player.shards += shards
                granted["shards"] = shards

            if outcome == "win_continue" and lvl < TOTAL_LEVELS:
                next_level = lvl + 1
                state.current_level = next_level
                if next_level > state.best_level_reached:
                    state.best_level_reached = next_level

            elif outcome == "win_grand":
                # Grand prize — give card if stock available
                won_grand = True
                run_over = True
                state.in_progress = False
                state.current_level = 0
                state.has_won_card = True
                state.won_card_at = dt.datetime.utcnow()

                if mg.card_key and mg.card_stock_remaining > 0:
                    mg.card_stock_remaining -= 1
                    # Add card to player inventory
                    pc = (
                        session.query(PlayerCard)
                        .filter_by(player_id=player.id, card_key=mg.card_key)
                        .first()
                    )
                    if pc:
                        pc.qty += 1
                    else:
                        session.add(PlayerCard(
                            player_id=player.id,
                            card_key=mg.card_key,
                            qty=1,
                        ))
                    granted["card_key"] = mg.card_key
                    # Fetch card details for victory screen
                    card_def = session.query(CardDef).filter_by(key=mg.card_key).first()
                    if card_def:
                        granted["card_label"] = card_def.card_label
                        granted["card_image"] = card_def.card_image
                        granted["card_rarity"] = card_def.card_rarity

            else:
                # win_stop — or win_continue on final level
                run_over = True
                state.in_progress = False
                state.current_level = 0

        if lvl > state.best_level_reached:
            state.best_level_reached = lvl

        session.commit()

        response = {
            "ok": True,
            "outcome": outcome,
            "door_index": door_index,
            "level": lvl,
            "granted": granted,
            "run_over": run_over,
            "won_grand": won_grand,
            "next_level": next_level,
        }

        if next_level:
            response["doors"] = _current_level_doors(state, mg)

        # Reveal all doors on run end
        if run_over:
            response["revealed_doors"] = level_data["doors"]

        response["state"] = _serialize_state(state, mg, player)
        return jsonify(response)
    except Exception as e:
        import traceback
        traceback.print_exc()
        session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        session.close()
