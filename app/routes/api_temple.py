# =============================================================================
# File: app/routes/api_temple.py
# Purpose: Server-side logic for the Temple mini-game (daily run, traps, moves)
# Notes:
# - Client never receives trap positions.
# - Only server validates moves and updates lives/progress.
# - Coherent with other APIs: uses SessionLocal() + get_current_player(s)
# - Broken tiles are persisted server-side (multi-device/refresh safe)
# =============================================================================

from __future__ import annotations

import datetime as dt
import random
from typing import Any

from flask import Blueprint, jsonify, request

from app.db import SessionLocal
from app.models import TempleRun, Player
from app.auth import get_current_player

bp = Blueprint("temple", __name__)  # prefix handled in register_routes()

ROWS = 8
COLS = 10
DAILY_LIVES = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def _generate_traps() -> dict[str, list[int]]:
    """
    Generate traps for the whole board.
    Rule: row_from_bottom 1 has 1 trap, row_from_bottom 2 has 2 traps, ... up to 8.
    Stored as dict with string keys to keep JSON stable.
    """
    traps: dict[str, list[int]] = {}
    for row_from_bottom in range(1, ROWS + 1):
        k = row_from_bottom
        cols = random.sample(range(COLS), k=k)
        traps[str(row_from_bottom)] = sorted(cols)
    return traps


def _get_or_create_today_run(session, player_id: int) -> TempleRun:
    today = _utc_today()

    run = (
        session.query(TempleRun)
        .filter(TempleRun.player_id == player_id, TempleRun.day == today)
        .first()
    )
    if run:
        # Defensive defaults (in case older rows existed before broken_tiles was added)
        if run.traps is None:
            run.traps = _generate_traps()
        if getattr(run, "broken_tiles", None) is None:
            run.broken_tiles = []
        return run

    run = TempleRun(
        player_id=player_id,
        day=today,
        lives=DAILY_LIVES,
        progress_row=0,
        traps=_generate_traps(),
        broken_tiles=[],  # NEW: persist broken tiles per day
    )
    session.add(run)
    session.flush()
    return run


def _get_player_for_temple(session) -> Player | None:
    """
    Dev-friendly player loader:
    - Uses existing cookie auth via get_current_player(session)
    - Fallback: ?player_id= for testing without re-leveling (temporary)
    """
    player = get_current_player(session)
    if player:
        return player

    pid = request.args.get("player_id")
    if pid:
        try:
            pid_int = int(pid)
            return session.query(Player).filter(Player.id == pid_int).first()
        except ValueError:
            return None

    return None


def _normalize_broken_tiles(value: Any) -> list[dict]:
    """
    Ensure broken_tiles is always a list of objects:
      [{ "row_from_bottom": int, "col": int }, ...]
    """
    if not isinstance(value, list):
        return []

    out: list[dict] = []
    for it in value:
        if not isinstance(it, dict):
            continue
        rfb = it.get("row_from_bottom")
        col = it.get("col")
        if not isinstance(rfb, int) or not isinstance(col, int):
            continue
        if rfb < 1 or rfb > ROWS:
            continue
        if col < 0 or col >= COLS:
            continue
        out.append({"row_from_bottom": rfb, "col": col})
    return out


def _is_tile_already_broken(run: TempleRun, row_from_bottom: int, col: int) -> bool:
    bt = _normalize_broken_tiles(getattr(run, "broken_tiles", []))
    for it in bt:
        if it["row_from_bottom"] == row_from_bottom and it["col"] == col:
            return True
    return False


def _mark_tile_broken(run: TempleRun, row_from_bottom: int, col: int) -> None:
    bt = _normalize_broken_tiles(getattr(run, "broken_tiles", []))
    for it in bt:
        if it["row_from_bottom"] == row_from_bottom and it["col"] == col:
            run.broken_tiles = bt
            return
    bt.append({"row_from_bottom": row_from_bottom, "col": col})
    run.broken_tiles = bt


def _public_state(run: TempleRun) -> dict:
    return {
        "lives": int(run.lives or 0),
        "progress_row": int(run.progress_row or 0),
        "broken_tiles": _normalize_broken_tiles(getattr(run, "broken_tiles", [])),
    }


# ---------------------------------------------------------------------------
# Public state endpoint (no traps)
# ---------------------------------------------------------------------------

@bp.get("/state")
def temple_state():
    """
    Returns public state needed by the client (no traps).
    Includes broken_tiles for persistence across refresh/devices.
    """
    with SessionLocal() as s:
        player = _get_player_for_temple(s)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        run = _get_or_create_today_run(s, player.id)
        s.commit()

        return jsonify(
            {
                "ok": True,
                "rows": ROWS,
                "cols": COLS,
                **_public_state(run),
            }
        )


# ---------------------------------------------------------------------------
# Step endpoint (lateral reveal)
# ---------------------------------------------------------------------------

@bp.post("/step")
def temple_step():
    """
    Reveal/attempt a specific tile on the CURRENT row by stepping laterally.

    Client sends:
      { "row_from_bottom": int, "col": int }

    Server decides:
    - refuses if already finished / no lives
    - refuses if tile already broken
    - checks if tile is a trap in that row
    - if trap: lives-- and persist broken tile
    - if safe: no progress change (progress is only via /advance)
    """
    data = request.get_json(silent=True) or {}
    row_from_bottom = data.get("row_from_bottom", None)
    col = data.get("col", None)

    if not isinstance(row_from_bottom, int) or row_from_bottom < 1 or row_from_bottom > ROWS:
        return jsonify({"ok": False, "error": "invalid_row"}), 400
    if not isinstance(col, int) or col < 0 or col >= COLS:
        return jsonify({"ok": False, "error": "invalid_column"}), 400

    with SessionLocal() as s:
        player = _get_player_for_temple(s)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        run = _get_or_create_today_run(s, player.id)

        if int(run.lives or 0) <= 0:
            return jsonify(
                {
                    "ok": True,
                    "result": "no_lives",
                    "row_from_bottom": row_from_bottom,
                    "col": col,
                    **_public_state(run),
                }
            )

        if int(run.progress_row or 0) >= ROWS:
            return jsonify(
                {
                    "ok": True,
                    "result": "already_finished",
                    "row_from_bottom": row_from_bottom,
                    "col": col,
                    **_public_state(run),
                }
            )

        # Optional safety: only allow stepping on the player's current row
        # Current row from bottom is progress_row (if progress_row==0, player is at start/outside)
        current_row_from_bottom = int(run.progress_row or 0)
        if current_row_from_bottom <= 0:
            return jsonify(
                {
                    "ok": True,
                    "result": "not_in_grid",
                    "row_from_bottom": row_from_bottom,
                    "col": col,
                    **_public_state(run),
                }
            )

        if row_from_bottom != current_row_from_bottom:
            return jsonify(
                {
                    "ok": True,
                    "result": "wrong_row",
                    "row_from_bottom": row_from_bottom,
                    "col": col,
                    **_public_state(run),
                }
            )

        if _is_tile_already_broken(run, row_from_bottom, col):
            return jsonify(
                {
                    "ok": True,
                    "result": "already_broken",
                    "row_from_bottom": row_from_bottom,
                    "col": col,
                    **_public_state(run),
                }
            )

        traps_for_row = (run.traps or {}).get(str(row_from_bottom), [])
        is_trap = col in traps_for_row

        if is_trap:
            run.lives = max(0, int(run.lives or 0) - 1)
            _mark_tile_broken(run, row_from_bottom, col)
            s.commit()
            return jsonify(
                {
                    "ok": True,
                    "result": "trap",
                    "row_from_bottom": row_from_bottom,
                    "col": col,
                    **_public_state(run),
                }
            )

        # safe step: no progress change
        s.commit()
        return jsonify(
            {
                "ok": True,
                "result": "safe",
                "row_from_bottom": row_from_bottom,
                "col": col,
                **_public_state(run),
            }
        )


# ---------------------------------------------------------------------------
# Advance endpoint
# ---------------------------------------------------------------------------

@bp.post("/advance")
def temple_advance():
    """
    Attempt to advance to the next row (from bottom), with chosen column.
    Client sends:
      { "col": int }

    Server decides:
    - which row is being attempted (progress_row + 1)
    - refuses if tile already broken
    - whether it's a trap
    - updates lives / progress / broken_tiles
    """
    data = request.get_json(silent=True) or {}
    col = data.get("col", None)

    if not isinstance(col, int) or col < 0 or col >= COLS:
        return jsonify({"ok": False, "error": "invalid_column"}), 400

    with SessionLocal() as s:
        player = _get_player_for_temple(s)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        run = _get_or_create_today_run(s, player.id)

        # Cannot advance if already finished or no lives
        if int(run.lives or 0) <= 0:
            return jsonify(
                {
                    "ok": True,
                    "result": "no_lives",
                    "lives": int(run.lives or 0),
                    "progress_row": int(run.progress_row or 0),
                    "broken_tiles": _normalize_broken_tiles(getattr(run, "broken_tiles", [])),
                }
            )

        if int(run.progress_row or 0) >= ROWS:
            return jsonify(
                {
                    "ok": True,
                    "result": "already_finished",
                    "lives": int(run.lives or 0),
                    "progress_row": int(run.progress_row or 0),
                    "broken_tiles": _normalize_broken_tiles(getattr(run, "broken_tiles", [])),
                }
            )

        # The row being attempted now (from bottom): 1..ROWS
        attempt_row = int(run.progress_row or 0) + 1

        # Block already broken tiles (authoritative)
        if _is_tile_already_broken(run, attempt_row, col):
            return jsonify(
                {
                    "ok": True,
                    "result": "already_broken",
                    "attempt_row": attempt_row,
                    "col": col,
                    **_public_state(run),
                }
            )

        traps_for_row = (run.traps or {}).get(str(attempt_row), [])
        is_trap = col in traps_for_row

        if is_trap:
            run.lives = max(0, int(run.lives or 0) - 1)
            _mark_tile_broken(run, attempt_row, col)
            s.commit()
            return jsonify(
                {
                    "ok": True,
                    "result": "trap",
                    "attempt_row": attempt_row,
                    "col": col,
                    **_public_state(run),
                }
            )

        # Safe => progress increases
        run.progress_row = int(run.progress_row or 0) + 1
        s.commit()

        finished = int(run.progress_row or 0) >= ROWS

        return jsonify(
            {
                "ok": True,
                "result": "safe",
                "attempt_row": attempt_row,
                "col": col,
                "finished": bool(finished),
                **_public_state(run),
            }
        )


# ---------------------------------------------------------------------------
# DEV ONLY — Reset Temple run for testing
# ---------------------------------------------------------------------------

@bp.post("/dev/reset")
def temple_dev_reset():
    """
    DEV ONLY.
    Resets today's Temple run for the current player:
    - lives back to DAILY_LIVES
    - progress_row = 0
    - regenerate traps
    - clear broken_tiles
    """
    with SessionLocal() as s:
        player = get_current_player(s)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        today = _utc_today()

        run = (
            s.query(TempleRun)
            .filter(
                TempleRun.player_id == player.id,
                TempleRun.day == today,
            )
            .first()
        )

        if not run:
            run = TempleRun(
                player_id=player.id,
                day=today,
                lives=DAILY_LIVES,
                progress_row=0,
                traps=_generate_traps(),
                broken_tiles=[],
            )
            s.add(run)
        else:
            run.lives = DAILY_LIVES
            run.progress_row = 0
            run.traps = _generate_traps()
            run.broken_tiles = []

        s.commit()

        return jsonify(
            {
                "ok": True,
                "message": "Temple run reset (DEV)",
                **_public_state(run),
            }
        )
