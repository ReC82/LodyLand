# app/__init__.py
from flask import Flask, jsonify, render_template
from .db import init_db
from .seed import reseed_resources, ensure_resources_seeded
from .seed_cards import seed_cards_from_yaml
from .routes import register_routes
from .frontend import frontend_bp
from .progression import LEVELS
from .craft_defs import load_craft_defs
from app.quests.loader import load_quest_templates

from app.admin import admin_bp

def create_app() -> Flask:
    app = Flask(__name__)
    
    # ===== Admin Panel activé en dev =====
    app.config["ADMIN_ENABLED"] = True
    # =====================================    

    init_db()
    seed_cards_from_yaml()
    ensure_resources_seeded()
    reseed_resources()
    load_craft_defs()
    load_quest_templates()
    register_routes(app)

    
    app.register_blueprint(frontend_bp)
    
    # Admin panel
    app.register_blueprint(admin_bp)    

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

    return app
