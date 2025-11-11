# =============================================================================
# File: app/__init__.py
# Purpose: Minimal Flask application setup (Hello World).
# =============================================================================
from flask import Flask, jsonify, request
from datetime import datetime, timedelta

def create_app():
    """Factory that creates and configures the Flask app."""
    app = Flask(__name__)
    
    MEM = {
        "players": {},     # id -> {"id": int, "name": str, "level": int, "coins": int, "diams": int}
        "tiles": {},       # id -> {"id": int, "playerId": int, "resource": str, "locked": bool, "cooldown_until": datetime|None}
        "seq_player": 0,
        "seq_tile": 0,
    }

    @app.route("/")
    def hello():
        return "Hello, world!"
    
    @app.get("/api/health")
    def health():
        """Simple health check to verify server is up."""
        return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})
    
    @app.post("/api/player")
    def create_player():
        """Create a new player with default attributes."""
        data = request.json
        name = data.get("name", "Lloyd")
        
        # Unique name check
        if any(p["name"] == name for p in MEM["players"].values()):
            return jsonify({"error": "name_taken"}), 409
        
        MEM["seq_player"] += 1
        pid = MEM["seq_player"]
        MEM["players"][pid] = {"id": pid, "name": name, "level": 0, "coins": 0, "diams": 0}
        return jsonify(MEM["players"][pid])

    @app.post("/api/tiles/unlock")
    def unlock_tile():
        """Unlock a tile for a player. Body: {"playerId": 1, "resource": "wood"}"""
        
        data = request.get_json(silent=True) or {}
        player_id = data.get("playerId")
        resource = data.get("resource", "wood")
        
        if not player_id or player_id not in MEM["players"]:
            return jsonify({"error": "player_not_found"}), 400

        MEM["seq_tile"] += 1
        tid = MEM["seq_tile"]
        MEM["tiles"][tid] = {
            "id": tid,
            "playerId": player_id,
            "resource": resource,
            "locked": False,
            "cooldown_until": None,
        }
        return jsonify({"ok": True, "tileId": tid})
    
    @app.post("/api/collect")
    def collect():
        """Collect from an unlocked tile if cooldown passed. Body: {"tileId": 1}."""
        data = request.get_json(silent=True) or {}
        tile_id = data.get("tileId")
        if not tile_id or tile_id not in MEM["tiles"]:
            return jsonify({"error": "tile_missing"}), 400

        t = MEM["tiles"][tile_id]
        if t["locked"]:
            return jsonify({"error": "locked"}), 400

        now = datetime.utcnow()
        if t["cooldown_until"] and t["cooldown_until"] > now:
            return jsonify({"error": "on_cooldown", "until": t["cooldown_until"].isoformat()}), 409

        # grant resource (MVP: just acknowledge)
        t["cooldown_until"] = now + timedelta(seconds=10)
        return jsonify({"ok": True, "next": t["cooldown_until"].isoformat()})    



    return app
