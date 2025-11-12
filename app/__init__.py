# =============================================================================
# File: app/__init__.py
# Purpose: Minimal Flask app using SQLite via SQLAlchemy (with simple read routes).
# =============================================================================
from flask import Flask, jsonify, request, make_response, session
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

# HELPERS
from .db import SessionLocal, init_db
from .models import Player, Tile, ResourceStock
from .progression import level_for_xp, next_threshold, XP_PER_COLLECT
from .economy import get_price, list_prices



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
            return jsonify({
            "id": p.id, "name": p.name,
            "level": p.level, "coins": p.coins, "diams": p.diams, "xp": p.xp,
            "next_xp": next_threshold(p.level)
            })
            
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
        s = SessionLocal()
        name = (request.get_json() or {}).get("name")
        if not name:
            s.close()
            return jsonify({"error": "name_required"}), 400

        existing = s.query(Player).filter_by(name=name).first()
        if existing:
            p = existing
            resp = jsonify({
                "id": p.id, "name": p.name,
                "level": p.level, "coins": p.coins, "diams": p.diams, "xp": p.xp
            })
            s.close()
            return resp, 200

        p = Player(name=name)
        s.add(p); s.commit()
        resp = jsonify({
        "id": p.id, "name": p.name,
        "level": p.level, "coins": p.coins, "diams": p.diams, "xp": p.xp,
        "next_xp": next_threshold(p.level)
        })
        s.close()
        return resp

    @app.post("/api/tiles/unlock")
    def unlock_tile():
        """Unlock a tile for the current player (cookie) or explicit playerId.
        Body: {"resource":"wood"}  (playerId optional; cookie fallback)
        """
        data = request.get_json(silent=True) or {}
        resource = (data.get("resource") or "").strip().lower()
        player_id = data.get("playerId")  # may be None

        if not resource:
            return jsonify({"error": "resource_required"}), 400

        with SessionLocal() as s:
            # If playerId missing, try cookie
            if not player_id:
                me = _get_current_player(s)
                if not me:
                    return jsonify({"error": "player_required"}), 400
                player_id = me.id

            # Validate player
            p = s.get(Player, int(player_id))
            if not p:
                return jsonify({"error": "player_not_found"}), 404

            # Create unlocked tile
            t = Tile(player_id=p.id, resource=resource, locked=False, cooldown_until=None)
            s.add(t)
            s.commit()
            s.refresh(t)

            return jsonify({
                "id": t.id,
                "playerId": t.player_id,
                "resource": t.resource,
                "locked": t.locked,
                "cooldown_until": t.cooldown_until
            }), 200


    @app.post("/api/collect")
    def collect():
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
            cd = t.cooldown_until
            if cd is not None and cd.tzinfo is None:
                cd = cd.replace(tzinfo=timezone.utc)

            if cd and cd > now:
                return jsonify({"error": "on_cooldown", "until": cd.isoformat()}), 409

            # cooldown
            next_cd = now + timedelta(seconds=10)
            t.cooldown_until = next_cd

            # XP + Level
            level_up = False
            p = s.get(Player, t.player_id)
            if p:
                p.xp = (p.xp or 0) + XP_PER_COLLECT  # <- 1 XP par collecte (comme demandé)
                old_level = p.level or 0
                new_level = level_for_xp(p.xp)
                if new_level > old_level:
                    p.level = new_level
                    level_up = True

            # Inventory +1
            if t.resource:
                rs = (s.query(ResourceStock)
                        .filter_by(player_id=t.player_id, resource=t.resource)
                        .first())
                if not rs:
                    rs = ResourceStock(player_id=t.player_id, resource=t.resource, qty=0)
                    s.add(rs)
                rs.qty += 1

            s.commit()
            return jsonify({
                "ok": True,
                "next": next_cd.isoformat(),
                "player": {
                    "id": p.id, "name": p.name,
                    "xp": p.xp, "level": p.level,
                    "next_xp": next_threshold(p.level)  # IMPORTANT pour la barre
                },
                "level_up": level_up
            })


    @app.get("/api/inventory")
    def get_inventory():
        """Return current player's inventory from cookie."""
        with SessionLocal() as s:
            me = _get_current_player(s)
            if not me:
                return jsonify({"error": "not_authenticated"}), 401
            rows = (
                s.query(ResourceStock)
                .filter_by(player_id=me.id)
                .order_by(ResourceStock.resource.asc())
                .all()
            )
            payload = [{"resource": r.resource, "qty": r.qty} for r in rows]
            return jsonify(payload)
            
    @app.get("/api/levels")
    def list_levels():
        """Return thresholds per level and short tips."""
        from .progression import LEVEL_THRESHOLDS
        data = [{"level": i, "xp_required": xp} for i, xp in enumerate(LEVEL_THRESHOLDS)]
        return jsonify({"thresholds": data})
    
    # ---- DEV UI (static debug page) ---------------------------------------------
    @app.get("/ui")
    def dev_ui():
        # Serve the minimal debug UI from /static/ui/index.html
        return app.send_static_file("ui/index.html")

    @app.post("/api/register")
    def register():
        """Create a player (if not exists) and set a 'player_id' cookie."""
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "name_required"}), 400

        with SessionLocal() as s:
            p = s.query(Player).filter_by(name=name).first()
            if not p:
                p = Player(name=name)  # xp/level defaults via model
                s.add(p); s.commit(); s.refresh(p)

            resp = make_response(jsonify({
            "id": p.id, "name": p.name,
            "level": p.level, "coins": p.coins, "diams": p.diams, "xp": p.xp,
            "next_xp": next_threshold(p.level)
            }))
            
            # HttpOnly: true (non accessible JS), SameSite=Lax (OK pour même domaine)
            resp.set_cookie("player_id", str(p.id), httponly=True, samesite="Lax", max_age=60*60*24*365)
            return resp, 200


    @app.post("/api/login")
    def login():
        """Login by id or name and set the 'player_id' cookie."""
        data = request.get_json(silent=True) or {}
        pid = data.get("id")
        name = (data.get("name") or "").strip()

        with SessionLocal() as s:
            p = None
            if pid:
                try:
                    p = s.get(Player, int(pid))
                except Exception:
                    p = None
            if not p and name:
                p = s.query(Player).filter_by(name=name).first()
            if not p:
                return jsonify({"error": "player_not_found"}), 404

            resp = make_response(jsonify({
            "id": p.id, "name": p.name,
            "level": p.level, "coins": p.coins, "diams": p.diams, "xp": p.xp,
            "next_xp": next_threshold(p.level)
            }))
            
            resp.set_cookie("player_id", str(p.id), httponly=True, samesite="Lax", max_age=60*60*24*365)
            return resp, 200


    @app.post("/api/logout")
    def logout():
        """Clear 'player_id' cookie."""
        resp = make_response(jsonify({"ok": True}))
        resp.set_cookie("player_id", "", max_age=0)
        return resp, 200


    @app.get("/api/me")
    def whoami():
        """Return current player from cookie (or 401)."""
        with SessionLocal() as s:
            p = _get_current_player(s)
            if not p:
                return jsonify({"error": "not_authenticated"}), 401
            return jsonify({
            "id": p.id, "name": p.name,
            "level": p.level, "coins": p.coins, "diams": p.diams, "xp": p.xp,
            "next_xp": next_threshold(p.level)
            })


    # -----------------------------------------------------------------------------
    # Cookie-based auth helpers (MVP)
    # -----------------------------------------------------------------------------
    def _get_current_player(session):
        """Return Player from 'player_id' cookie if present, else None."""
        pid = request.cookies.get("player_id")
        if not pid:
            return None
        try:
            pid = int(pid)
        except ValueError:
            return None
        return session.get(Player, pid)

    @app.get("/api/prices")
    def get_prices():
        """Return current NPC prices (MVP: fixed)."""
        return jsonify({"prices": list_prices()})
    
    @app.post("/api/sell")
    def sell_resources():
        """Sell resources to NPC for coins.
        Body: {"resource":"wood", "qty": 3, "playerId": 1 (optional)}
        - If playerId absent, fallback to cookie.
        """
        data = request.get_json(silent=True) or {}
        resource = (data.get("resource") or "").strip().lower()
        qty = int(data.get("qty") or 0)
        player_id = data.get("playerId")  # optional

        if not resource:
            return jsonify({"error": "resource_required"}), 400
        if qty <= 0:
            return jsonify({"error": "qty_invalid"}), 400

        with SessionLocal() as s:
            # Resolve player
            if player_id:
                me = s.get(Player, int(player_id))
            else:
                me = _get_current_player(s)

            if not me:
                return jsonify({"error": "not_authenticated"}), 401

            price = get_price(resource)
            if price <= 0:
                return jsonify({"error": "unknown_resource"}), 400

            rs = (
                s.query(ResourceStock)
                .filter_by(player_id=me.id, resource=resource)
                .first()
            )
            if not rs or rs.qty < qty:
                return jsonify({"error": "not_enough_stock", "have": rs.qty if rs else 0}), 400

            rs.qty -= qty
            gain = qty * price
            me.coins = (me.coins or 0) + gain

            s.commit()
            return jsonify({
                "ok": True,
                "sold": {"resource": resource, "qty": qty, "unit_price": price, "gain": gain},
                "player": {
                    "id": me.id, "name": me.name,
                    "coins": me.coins, "diams": me.diams,
                    "xp": me.xp, "level": me.level,
                    "next_xp": next_threshold(me.level),
                },
                "stock": {"resource": resource, "qty": rs.qty},
            }), 200


    return app

