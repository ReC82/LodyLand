# =============================================================================
# File: app/__init__.py
# Purpose: Minimal Flask app using SQLite via SQLAlchemy (with simple read routes).
# =============================================================================
from flask import Flask, jsonify, request
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

# HELPERS
from .db import SessionLocal, init_db
from .models import Player, Tile
from .progression import level_for_xp, next_threshold


def create_app():
    """Factory that creates and configures the Flask app."""
    app = Flask(__name__)
    init_db()

    @app.route("/")
    def hello():
        return "Hello, world!"

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})

    # --- NEW: read a player by id ------------------------------------------------
    @app.get("/api/player/<int:player_id>")
    def get_player(player_id: int):
        """Return a player by id."""
        with SessionLocal() as s:
            p = s.get(Player, player_id)
            if not p:
                return jsonify({"error": "not_found"}), 404
            return jsonify({"id": p.id, "name": p.name, "level": p.level, "coins": p.coins, "diams": p.diams, "xp": p.xp})

    # --- NEW: list tiles for a player -------------------------------------------
    @app.get("/api/player/<int:player_id>/tiles")
    def list_tiles(player_id: int):
        """Return all tiles for a player."""
        with SessionLocal() as s:
            # Fast check player exists
            if not s.get(Player, player_id):
                return jsonify({"error": "player_not_found"}), 404
            rows = s.execute(select(Tile).where(Tile.player_id == player_id)).scalars().all()
            data = [{
                "id": t.id,
                "playerId": t.player_id,
                "resource": t.resource,
                "locked": t.locked,
                "cooldown_until": t.cooldown_until.isoformat() if t.cooldown_until else None,
            } for t in rows]
            return jsonify(data)

    @app.post("/api/player")
    def create_player():
        """Create a simple player. Body: {"name": "Lloyd"}."""
        data = request.get_json(silent=True) or {}
        name = data.get("name", "player1")
        with SessionLocal() as s:
            exists = s.execute(select(Player).where(Player.name == name)).scalar_one_or_none()
            if exists:
                return jsonify({"error": "name_taken"}), 409
            p = Player(name=name)
            s.add(p)
            s.commit()
            s.refresh(p)
            return jsonify({"id": p.id, "name": p.name, "level": p.level, "coins": p.coins, "diams": p.diams, "xp": p.xp})


    @app.post("/api/tiles/unlock")
    def unlock_tile():
        """Unlock a tile for a player. Body: {"playerId": 1, "resource": "wood"}"""
        data = request.get_json(silent=True) or {}
        player_id = data.get("playerId")
        resource = data.get("resource", "wood")
        if not player_id:
            return jsonify({"error": "playerId_required"}), 400

        with SessionLocal() as s:
            p = s.get(Player, player_id)
            if not p:
                return jsonify({"error": "player_not_found"}), 400
            t = Tile(player_id=player_id, resource=resource, locked=False, cooldown_until=None)
            s.add(t)
            s.commit()
            s.refresh(t)
            return jsonify({"ok": True, "tileId": t.id})

    @app.post("/api/collect")
    def collect():
        """Collect from an unlocked tile if cooldown passed. Body: {"tileId": 1}."""
        data = request.get_json(silent=True) or {}
        tile_id = data.get("tileId")
        if not tile_id:
            return jsonify({"error": "tileId_required"}), 400

        with SessionLocal() as s:
            t = s.get(Tile, tile_id)
            if not t:
                return jsonify({"error": "tile_missing"}), 400
            if t.locked:
                return jsonify({"error": "locked"}), 400
            now = datetime.now(timezone.utc)
            if t.cooldown_until and t.cooldown_until > now:
                return jsonify({"error": "on_cooldown", "until": t.cooldown_until.isoformat()}), 409
            t.cooldown_until = now + timedelta(seconds=10)
            
            # ADD PLAYER XP
            p = s.get(Player, t.player_id)
            if p:
                # MVP: +10 XP per successful collect
                p.xp = (p.xp or 0) + 10

                # Recompute level from xp
                old_level = p.level or 0
                new_level = level_for_xp(p.xp)
                if new_level > old_level:
                    p.level = new_level
                    level_up = True
            
            s.commit()
            return jsonify({
                "ok": True,
                "next": t.cooldown_until.isoformat(),
                "player": {
                    "id": p.id,
                    "xp": p.xp,
                    "level": p.level,
                    "next_xp": next_threshold(p.level)  # None if max
                },
                "level_up": level_up
            })
            
    @app.get("/api/levels")
    def list_levels():
        """Return thresholds per level and short tips."""
        from .progression import LEVEL_THRESHOLDS
        data = [{"level": i, "xp_required": xp} for i, xp in enumerate(LEVEL_THRESHOLDS)]
        return jsonify({"thresholds": data})

    return app

