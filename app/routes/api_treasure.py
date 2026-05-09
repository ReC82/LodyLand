# =============================================================================
# app/routes/api_treasure.py
# Purpose: API for the Treasure Hunt mini-game.
#
# Endpoints:
#   POST /api/treasure/start  → start (or resume) today's game
#   POST /api/treasure/dig    → dig a cell (consumes 1 shovel)
#   GET  /api/treasure/state  → current game state (no creation)
#
# Rules:
#   - 1 free game per calendar day (UTC)
#   - Requires level >= MIN_LEVEL
#   - Each dig consumes 1 tool_wooden_shovel from PlayerItem
#   - Reward decreases with each dig; minimum 5 shards
# =============================================================================
from __future__ import annotations

import datetime as dt

from flask import Blueprint, jsonify, request

from app.db import SessionLocal
from app.auth import get_current_player
from app.models import Player, TreasureGame, PlayerItem
from app.minigames.treasure_generator import TreasureGenerator

# Icon map for landmark objects — keys match items.yml
_OBJECT_ICONS: dict[str, str] = {
    "flint":       "/static/assets/img/items/resources/flint.png",
    "pearl":       "/static/assets/img/items/resources/pearl.png",
    "stone_chunk": "/static/assets/img/items/resources/stone_chunk.png",
    "seashell":    "/static/assets/img/items/resources/seashell.png",
    "branch":      "/static/assets/img/items/resources/branch.png",
    "starfish":    "/static/assets/img/items/resources/starfish.png",
    "coal":        "/static/assets/img/items/resources/coal.png",
}

bp = Blueprint("treasure", __name__)

SHOVEL_KEY = "tool_wooden_shovel"
MIN_LEVEL = 7


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _shovel_count(session, player: Player) -> int:
    row = (
        session.query(PlayerItem)
        .filter_by(player_id=player.id, item_key=SHOVEL_KEY)
        .first()
    )
    return row.quantity if row else 0


def _compute_reward(grid_size: int, dug_count: int) -> int:
    """More digs = lower reward. Minimum 5 shards."""
    max_reward = grid_size * 8          # 8×8 → 64, 12×12 → 96
    penalty    = (dug_count - 1) * 3   # first dig free
    return max(5, max_reward - penalty)


def _cell_content(state: dict, row: int, col: int) -> str:
    """Return what is at (row, col): 'treasure', 'object:<key>', or 'empty'."""
    t = state["treasure"]
    if row == t["row"] and col == t["col"]:
        return "treasure"
    for obj in state["objects"]:
        if obj["row"] == row and obj["col"] == col:
            return f"object:{obj['key']}"
    return "empty"


def _serialize_game(game: TreasureGame, shovel_count: int) -> dict:
    """
    Client-facing game state.
    Treasure position is only revealed once status == 'won'.
    """
    state     = game.game_state_json
    grid_size = state["grid_size"]

    # Reveal the content of every already-dug cell
    dug_revealed = []
    for cell in state.get("dug", []):
        r, c    = cell[0], cell[1]
        content = _cell_content(state, r, c)
        # Safety: hide treasure content in active games (shouldn't occur)
        if game.status == "active" and content == "treasure":
            content = "empty"
        dug_revealed.append({"row": r, "col": c, "content": content})

    # One clue revealed per dig
    all_clues      = state["clues"]
    revealed_count = min(game.dug_count, len(all_clues))
    revealed_clues = all_clues[:revealed_count]
    total_clues    = len(all_clues)

    # Enrich objects with their resolved icon URL
    objects_with_icons = [
        {**obj, "icon": _OBJECT_ICONS.get(obj["key"], "")}
        for obj in state["objects"]
    ]

    result: dict = {
        "status":        game.status,
        "grid_size":     grid_size,
        "objects":       objects_with_icons,   # visible landmarks with icons
        "clues":         revealed_clues,     # only revealed clues
        "total_clues":   total_clues,        # so the UI can show locked slots
        "dug":           dug_revealed,
        "dug_count":     game.dug_count,
        "shovel_count":  shovel_count,
        "game_date":     game.game_date.isoformat(),
    }

    if game.status == "won":
        result["treasure_pos"]  = state["treasure"]
        result["reward_shards"] = game.reward_shards

    return result


def _get_today_game(session, player: Player) -> TreasureGame | None:
    today = dt.date.today()
    return (
        session.query(TreasureGame)
        .filter_by(player_id=player.id, game_date=today)
        .first()
    )


def _create_game(session, player: Player) -> TreasureGame:
    today = dt.date.today()
    # Seed is deterministic per player+date so the game is reproducible
    seed  = int(f"{player.id}{today.strftime('%Y%m%d')}")
    state = TreasureGenerator(seed=seed).generate()

    game = TreasureGame(
        player_id=player.id,
        game_date=today,
        game_state_json=state,
        status="active",
        dug_count=0,
    )
    session.add(game)
    session.flush()
    return game


# ---------------------------------------------------------------------------
# POST /api/treasure/start
# ---------------------------------------------------------------------------
@bp.post("/treasure/start")
def treasure_start():
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401
        if player.level < MIN_LEVEL:
            return jsonify({"ok": False, "error": "level_required",
                            "min_level": MIN_LEVEL}), 403

        game = _get_today_game(session, player)
        created = game is None

        if created:
            game = _create_game(session, player)

        session.commit()

        return jsonify({
            "ok":      True,
            "created": created,
            "state":   _serialize_game(game, _shovel_count(session, player)),
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        session.close()


# ---------------------------------------------------------------------------
# POST /api/treasure/dig
# ---------------------------------------------------------------------------
@bp.post("/treasure/dig")
def treasure_dig():
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        body = request.get_json(silent=True) or {}
        row  = body.get("row")
        col  = body.get("col")
        if row is None or col is None:
            return jsonify({"ok": False, "error": "missing_params"}), 400

        try:
            row, col = int(row), int(col)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "invalid_params"}), 400

        game = _get_today_game(session, player)
        if not game:
            return jsonify({"ok": False, "error": "no_active_game"}), 404
        if game.status != "active":
            return jsonify({"ok": False, "error": "game_over"}), 400

        state     = game.game_state_json
        grid_size = state["grid_size"]

        # Bounds check
        if not (0 <= row < grid_size and 0 <= col < grid_size):
            return jsonify({"ok": False, "error": "out_of_bounds"}), 400

        # Already dug?
        if [row, col] in state.get("dug", []):
            return jsonify({"ok": False, "error": "already_dug"}), 400

        # Cannot dig an object cell (objects are landmarks, not diggable)
        for obj in state["objects"]:
            if obj["row"] == row and obj["col"] == col:
                return jsonify({"ok": False, "error": "object_cell"}), 400

        # Check & consume shovel
        shovel_row = (
            session.query(PlayerItem)
            .filter_by(player_id=player.id, item_key=SHOVEL_KEY)
            .first()
        )
        if not shovel_row or shovel_row.quantity < 1:
            return jsonify({"ok": False, "error": "no_shovel"}), 400

        shovel_row.quantity -= 1

        # Update dug list (copy to force SQLAlchemy change detection)
        new_dug = list(state.get("dug", [])) + [[row, col]]
        game.game_state_json = {**state, "dug": new_dug}
        game.dug_count       = len(new_dug)

        # Determine result
        content       = _cell_content(state, row, col)
        reward_shards = None

        if content == "treasure":
            game.status       = "won"
            game.finished_at  = dt.datetime.utcnow()
            reward_shards     = _compute_reward(grid_size, game.dug_count)
            game.reward_shards = reward_shards
            player.shards     += reward_shards

        session.commit()

        return jsonify({
            "ok":           True,
            "result":       content,          # "empty" | "treasure"
            "reward_shards": reward_shards,
            "shovel_count": shovel_row.quantity,
            "state":        _serialize_game(game, shovel_row.quantity),
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        session.close()


# ---------------------------------------------------------------------------
# GET /api/treasure/state
# ---------------------------------------------------------------------------
@bp.get("/treasure/state")
def treasure_state():
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        game = _get_today_game(session, player)

        if not game:
            return jsonify({
                "ok":          True,
                "game":        None,
                "shovel_count": _shovel_count(session, player),
            })

        return jsonify({
            "ok":   True,
            "game": _serialize_game(game, _shovel_count(session, player)),
        })

    except Exception as e:
        session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        session.close()
