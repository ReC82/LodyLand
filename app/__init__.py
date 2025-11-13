# =============================================================================
# File: app/__init__.py
# Purpose: Minimal Flask app using SQLite via SQLAlchemy (with simple read routes).
# =============================================================================
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, make_response, request
from sqlalchemy import select

from .db import SessionLocal, init_db
from .economy import DAILY_REWARD_COINS, list_prices
from .models import Player, ResourceDef, ResourceStock, Tile
from .progression import XP_PER_COLLECT, level_for_xp, next_threshold
from .seed import reseed_resources


# ---------------------------------------------------------------------
# Helpers: resources
# ---------------------------------------------------------------------
def _get_res_def(session, key: str) -> ResourceDef | None:
    if not key:
        return None
    return session.query(ResourceDef).filter_by(key=key, enabled=True).first()


def _seed_resources_if_missing() -> None:
    """Seed (et corrige) les ressources de base.

    - crée les entrées manquantes
    - met à jour celles qui existent déjà (unlock_min_level, prix, etc.)
    """
    defaults = [
        {
            "key": "branch",
            "label": "Branchages",
            "unlock_min_level": 0,
            "base_cooldown": 5,
            "base_sell_price": 1,
            "enabled": True,
        },
        {
            "key": "palm_leaf",
            "label": "Feuilles de palmier",
            "unlock_min_level": 0,
            "base_cooldown": 6,
            "base_sell_price": 1,
            "enabled": True,
        },
        {
            "key": "wood",
            "label": "Bois (palmier)",
            "unlock_min_level": 0,
            "base_cooldown": 10,
            "base_sell_price": 2,
            "enabled": True,
        },
        # 👉 IMPORTANT : ressource qui demande AU MOINS le niveau 2
        {
            "key": "stone",
            "label": "Pierre",
            "unlock_min_level": 2,  # <= utilisée par le test_unlock_requires_min_level
            "base_cooldown": 12,
            "base_sell_price": 3,
            "enabled": True,
        },
    ]

    with SessionLocal() as s:
        existing_rows = s.query(ResourceDef).all()
        existing_by_key = {r.key: r for r in existing_rows}

        for d in defaults:
            row = existing_by_key.get(d["key"])
            if row is None:
                row = ResourceDef(**d)
                s.add(row)
            else:
                row.label = d["label"]
                row.unlock_min_level = d["unlock_min_level"]
                row.base_cooldown = d["base_cooldown"]
                row.base_sell_price = d["base_sell_price"]
                row.enabled = d["enabled"]

        s.commit()


# ---------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------
def create_app() -> Flask:
    """Factory that creates and configures the Flask app."""
    app = Flask(__name__)
    init_db()
    _seed_resources_if_missing()

    # -----------------------------------------------------------------
    # Basic routes
    # -----------------------------------------------------------------
    @app.route("/")
    def hello():
        return "Hello, world!"

    @app.get("/api/health")
    def health():
        return jsonify(
            {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}
        )

    # -----------------------------------------------------------------
    # Players
    # -----------------------------------------------------------------
    @app.get("/api/player/<int:player_id>")
    def get_player(player_id: int):
        """Return a player by id."""
        with SessionLocal() as s:
            p = s.get(Player, player_id)
            if not p:
                return jsonify({"error": "not_found"}), 404
            return jsonify(
                {
                    "id": p.id,
                    "name": p.name,
                    "level": p.level,
                    "coins": p.coins,
                    "diams": p.diams,
                    "xp": p.xp,
                    "next_xp": next_threshold(p.level),
                }
            )

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
            resp = jsonify(
                {
                    "id": p.id,
                    "name": p.name,
                    "level": p.level,
                    "coins": p.coins,
                    "diams": p.diams,
                    "xp": p.xp,
                    "next_xp": next_threshold(p.level),
                }
            )
            s.close()
            return resp, 200

        p = Player(name=name)
        s.add(p)
        s.commit()
        resp = jsonify(
            {
                "id": p.id,
                "name": p.name,
                "level": p.level,
                "coins": p.coins,
                "diams": p.diams,
                "xp": p.xp,
                "next_xp": next_threshold(p.level),
            }
        )
        s.close()
        return resp

    # -----------------------------------------------------------------
    # Tiles
    # -----------------------------------------------------------------
    @app.get("/api/player/<int:player_id>/tiles")
    def list_tiles(player_id: int):
        """Return all tiles for a player."""
        with SessionLocal() as s:
            if not s.get(Player, player_id):
                return jsonify({"error": "player_not_found"}), 404
            rows = (
                s.execute(select(Tile).where(Tile.player_id == player_id))
                .scalars()
                .all()
            )
            data = [
                {
                    "id": t.id,
                    "playerId": t.player_id,
                    "resource": t.resource,
                    "locked": t.locked,
                    "cooldown_until": t.cooldown_until.isoformat()
                    if t.cooldown_until
                    else None,
                }
                for t in rows
            ]
            return jsonify(data)

    @app.post("/api/tiles/unlock")
    def unlock_tile():
        """Unlock a tile for the current player or explicit playerId.

        Body: {"resource":"wood", "playerId": 1 (optional)}
        """
        data = request.get_json(silent=True) or {}
        resource = (data.get("resource") or "").strip().lower()
        player_id = data.get("playerId")

        if not resource:
            return jsonify({"error": "resource_required"}), 400

        with SessionLocal() as s:
            if not player_id:
                me = _get_current_player(s)
                if not me:
                    return jsonify({"error": "player_required"}), 400
                player_id = me.id

            p = s.get(Player, int(player_id))
            if not p:
                return jsonify({"error": "player_not_found"}), 404

            rd = _get_res_def(s, resource)
            if not rd:
                return jsonify(
                    {"error": "resource_unknown_or_disabled"}
                ), 400

            if p.level < rd.unlock_min_level:
                return (
                    jsonify(
                        {
                            "error": "level_too_low",
                            "required": rd.unlock_min_level,
                        }
                    ),
                    403,
                )

            t = Tile(
                player_id=p.id,
                resource=resource,
                locked=False,
                cooldown_until=None,
            )
            s.add(t)
            s.commit()
            s.refresh(t)

            return jsonify({"id": t.id}), 200

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
                return (
                    jsonify(
                        {"error": "on_cooldown", "until": cd.isoformat()}
                    ),
                    409,
                )

            rd = _get_res_def(s, t.resource)
            base_cd = rd.base_cooldown if rd else 10
            next_cd = now + timedelta(seconds=base_cd)
            t.cooldown_until = next_cd

            level_up = False
            p = s.get(Player, t.player_id)
            if p:
                p.xp = (p.xp or 0) + XP_PER_COLLECT
                old_level = p.level or 0
                new_level = level_for_xp(p.xp)
                if new_level > old_level:
                    p.level = new_level
                    level_up = True

            if t.resource:
                rs = (
                    s.query(ResourceStock)
                    .filter_by(
                        player_id=t.player_id, resource=t.resource
                    )
                    .first()
                )
                if not rs:
                    rs = ResourceStock(
                        player_id=t.player_id,
                        resource=t.resource,
                        qty=0,
                    )
                    s.add(rs)
                rs.qty += 1

            s.commit()
            return jsonify(
                {
                    "ok": True,
                    "next": next_cd.isoformat(),
                    "player": {
                        "id": p.id,
                        "name": p.name,
                        "xp": p.xp,
                        "level": p.level,
                        "next_xp": next_threshold(p.level),
                    },
                    "level_up": level_up,
                }
            )

    # -----------------------------------------------------------------
    # Inventory
    # -----------------------------------------------------------------
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
            payload = [
                {"resource": r.resource, "qty": r.qty} for r in rows
            ]
            return jsonify(payload)

    # -----------------------------------------------------------------
    # Levels
    # -----------------------------------------------------------------
    @app.get("/api/levels")
    def list_levels():
        """Return thresholds per level and short tips."""
        from .progression import LEVEL_THRESHOLDS

        data = [
            {"level": i, "xp_required": xp}
            for i, xp in enumerate(LEVEL_THRESHOLDS)
        ]
        return jsonify({"thresholds": data})

    # -----------------------------------------------------------------
    # Dev UI
    # -----------------------------------------------------------------
    @app.get("/ui")
    def dev_ui():
        return app.send_static_file("ui/index.html")

    # -----------------------------------------------------------------
    # Auth: register / login / logout / me
    # -----------------------------------------------------------------
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
                p = Player(name=name)
                s.add(p)
                s.commit()
                s.refresh(p)

            resp = make_response(
                jsonify(
                    {
                        "id": p.id,
                        "name": p.name,
                        "level": p.level,
                        "coins": p.coins,
                        "diams": p.diams,
                        "xp": p.xp,
                        "next_xp": next_threshold(p.level),
                    }
                )
            )
            resp.set_cookie(
                "player_id",
                str(p.id),
                httponly=True,
                samesite="Lax",
                max_age=60 * 60 * 24 * 365,
            )
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

            resp = make_response(
                jsonify(
                    {
                        "id": p.id,
                        "name": p.name,
                        "level": p.level,
                        "coins": p.coins,
                        "diams": p.diams,
                        "xp": p.xp,
                        "next_xp": next_threshold(p.level),
                    }
                )
            )
            resp.set_cookie(
                "player_id",
                str(p.id),
                httponly=True,
                samesite="Lax",
                max_age=60 * 60 * 24 * 365,
            )
            return resp, 200

    @app.post("/api/logout")
    def logout():
        resp = make_response(jsonify({"ok": True}))
        resp.set_cookie("player_id", "", max_age=0)
        return resp, 200

    @app.get("/api/me")
    def whoami():
        with SessionLocal() as s:
            p = _get_current_player(s)
            if not p:
                return jsonify({"error": "not_authenticated"}), 401
            return jsonify(
                {
                    "id": p.id,
                    "name": p.name,
                    "level": p.level,
                    "coins": p.coins,
                    "diams": p.diams,
                    "xp": p.xp,
                    "next_xp": next_threshold(p.level),
                }
            )

    # -----------------------------------------------------------------
    # Helper: cookie-based auth
    # -----------------------------------------------------------------
    def _get_current_player(session):
        pid = request.cookies.get("player_id")
        if not pid:
            return None
        try:
            pid = int(pid)
        except ValueError:
            return None
        return session.get(Player, pid)

    # -----------------------------------------------------------------
    # Prices & selling
    # -----------------------------------------------------------------
    @app.get("/api/prices")
    def get_prices():
        return jsonify({"prices": list_prices()})

    @app.post("/api/sell")
    def sell():
        """Sell some resource from inventory.

        Body: {"resource":"wood","qty":2,"playerId":1?}
        Tests appellent avec playerId explicite.
        """
        data = request.get_json(silent=True) or {}
        resource = (data.get("resource") or "").strip().lower()
        qty = int(data.get("qty") or 0)
        player_id = data.get("playerId")

        if not resource or qty <= 0:
            return jsonify({"error": "invalid_payload"}), 400

        with SessionLocal() as s:
            # Auth: playerId explicite ou cookie
            me = s.get(Player, int(player_id)) if player_id else _get_current_player(s)
            if not me:
                return jsonify({"error": "not_authenticated"}), 401

            rd = _get_res_def(s, resource)
            if not rd:
                return jsonify(
                    {"error": "resource_unknown_or_disabled"}
                ), 400

            rs = (
                s.query(ResourceStock)
                .filter_by(player_id=me.id, resource=resource)
                .first()
            )
            if not rs or rs.qty < qty:
                return jsonify({"error": "insufficient_qty"}), 400

            gain = qty * int(rd.base_sell_price)
            rs.qty -= qty
            me.coins = (me.coins or 0) + gain

            s.commit()
            s.refresh(rs)
            s.refresh(me)

            return (
                jsonify(
                    {
                        "ok": True,
                        "sold": {
                            "resource": resource,
                            "qty": qty,
                            "gain": gain,
                        },
                        "stock": {
                            "resource": resource,
                            "qty": rs.qty,
                        },
                        "player": {
                            "id": me.id,
                            "coins": me.coins,
                        },
                    }
                ),
                200,
            )

    # -----------------------------------------------------------------
    # Daily chest
    # -----------------------------------------------------------------
    @app.post("/api/daily")
    def claim_daily():
        """Claim daily chest (once per UTC day)."""
        with SessionLocal() as s:
            me = _get_current_player(s)
            if not me:
                return jsonify({"error": "not_authenticated"}), 401

            today_utc = datetime.now(timezone.utc).date()
            if me.last_daily == today_utc:
                next_reset = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) + timedelta(days=1)
                return (
                    jsonify(
                        {
                            "error": "already_claimed",
                            "next_at": next_reset.isoformat(),
                        }
                    ),
                    409,
                )

            me.last_daily = today_utc
            me.coins = (me.coins or 0) + DAILY_REWARD_COINS
            s.commit()

            next_reset = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)

            return (
                jsonify(
                    {
                        "ok": True,
                        "reward": DAILY_REWARD_COINS,
                        "player": {
                            "id": me.id,
                            "name": me.name,
                            "coins": me.coins,
                            "diams": me.diams,
                            "xp": me.xp,
                            "level": me.level,
                            "next_xp": next_threshold(me.level),
                        },
                        "next_at": next_reset.isoformat(),
                    }
                ),
                200,
            )

    # -----------------------------------------------------------------
    # Resources listing (for UI + tests)
    # -----------------------------------------------------------------
    @app.get("/api/resources")
    def list_resources():
        with SessionLocal() as s:
            rows = (
                s.query(ResourceDef)
                .filter_by(enabled=True)
                .order_by(ResourceDef.unlock_min_level.asc())
                .all()
            )
            return jsonify(
                [
                    {
                        "key": r.key,
                        "label": r.label,
                        "unlock_min_level": r.unlock_min_level,
                        "base_cooldown": r.base_cooldown,
                        "base_sell_price": r.base_sell_price,
                        "enabled": r.enabled,
                    }
                    for r in rows
                ]
            )

    # -----------------------------------------------------------------
    # Dev reseed endpoint
    # -----------------------------------------------------------------
    @app.post("/api/dev/reseed")
    def dev_reseed():
        try:
            n = reseed_resources()
            return jsonify({"ok": True, "inserted": n})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.get("/api/state")
    def get_state():
        """Retourne l'état complet du joueur courant (pour future UI)."""
        with SessionLocal() as s:
            me = _get_current_player(s)
            if not me:
                return jsonify({"error": "not_authenticated"}), 401

            # Tiles du joueur
            tiles = (
                s.query(Tile)
                .filter_by(player_id=me.id)
                .order_by(Tile.id.asc())
                .all()
            )

            tiles_payload = []
            for t in tiles:
                tiles_payload.append({
                    "id": t.id,
                    "playerId": t.player_id,
                    "resource": t.resource,
                    "locked": t.locked,
                    "cooldown_until": t.cooldown_until.isoformat()
                        if t.cooldown_until else None,
                })

            # Inventaire
            stocks = (
                s.query(ResourceStock)
                .filter_by(player_id=me.id)
                .order_by(ResourceStock.resource.asc())
                .all()
            )
            inventory_payload = [
                {"resource": rs.resource, "qty": rs.qty}
                for rs in stocks
            ]

            # Defs de ressources
            resources_rows = (
                s.query(ResourceDef)
                .filter_by(enabled=True)
                .order_by(ResourceDef.unlock_min_level.asc())
                .all()
            )
            resources_payload = [
                {
                    "key": r.key,
                    "label": r.label,
                    "unlock_min_level": r.unlock_min_level,
                    "base_cooldown": r.base_cooldown,
                    "base_sell_price": r.base_sell_price,
                    "enabled": r.enabled,
                }
                for r in resources_rows
            ]

            return jsonify({
                "player": {
                    "id": me.id,
                    "name": me.name,
                    "level": me.level,
                    "xp": me.xp,
                    "coins": me.coins,
                    "diams": me.diams,
                    "next_xp": next_threshold(me.level),
                },
                "tiles": tiles_payload,
                "inventory": inventory_payload,
                "resources": resources_payload,
            }), 200


    return app
