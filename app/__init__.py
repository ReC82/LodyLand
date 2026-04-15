# app/__init__.py
import os
import secrets

from flask import Flask, jsonify, render_template
from .db import init_db
from .seed import reseed_resources, ensure_resources_seeded
from .seed_cards import seed_cards_from_yaml
from .routes import register_routes
from .frontend import frontend_bp
from .progression import LEVELS
from .craft_defs import load_craft_defs
from app.quests.loader import load_quest_templates
from app.i18n import init_i18n, register_i18n_helpers

from app.admin import admin_bp

from .extensions import limiter

def create_app() -> Flask:
    app = Flask(__name__)
        
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    
    # ⬇️ AJOUTER ÇA : Désactiver le cache Jinja en dev
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    # dans create_app(), après register_routes(app)
    # ===== Admin Panel activé en dev =====
    app.config["ADMIN_ENABLED"] = True
    # =====================================    
    limiter.init_app(app)
    init_db()
    init_i18n()
    register_i18n_helpers(app)

    seed_cards_from_yaml()
    ensure_resources_seeded()
    reseed_resources()
    load_craft_defs()
    load_quest_templates()
    register_routes(app)

    
    app.register_blueprint(frontend_bp)
    
    # Admin panel
    app.register_blueprint(admin_bp)

    # ── Theme context processor ────────────────────────────────────
    @app.context_processor
    def inject_theme():
        from flask import g
        player = getattr(g, "player", None)
        theme = getattr(player, "theme", "default") if player else "default"
        # Whitelist to avoid injection
        valid = {"default", "light", "monochrome", "medieval", "fantasy", "emerald"}
        if theme not in valid:
            theme = "light"
        return {"current_theme": theme}

    @app.context_processor
    def inject_current_player():
        """Inject current_player into all templates."""
        from flask import g
        from .db import SessionLocal
        from .auth import get_current_player as get_player_from_session

        player = getattr(g, "player", None)
        if player is None:
            session = SessionLocal()
            try:
                player = get_player_from_session(session)
                if player:
                    g.player = player
            finally:
                session.close()

        return {"current_player": player}

    @app.get("/")
    def index():
        # UI joueur
        return render_template("GAME_UI/index.html")

    @app.get("/ui")
    def debug_ui():
        # UI dev
        return render_template("DEV_UI/index.html")

    @app.get("/api/levels")
    def list_levels():
        data = [
            {"level": i, "xp_required": xp}
            for i, xp in enumerate(LEVELS)
        ]
        return jsonify({"thresholds": data})

    @app.post("/api/dev/reseed")
    def dev_reseed():
        try:
            n = reseed_resources()
            return jsonify({"ok": True, "inserted": n})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    #print("=== URL MAP ===")
    #print(app.url_map)

    return app
