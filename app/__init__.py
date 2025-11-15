# app/__init__.py
from flask import Flask, jsonify, render_template
from .db import init_db
from .seed import reseed_resources, ensure_resources_seeded
from .seed_cards import seed_cards_from_yaml
from .routes import register_routes
from .frontend import frontend_bp
from .progression import LEVELS

def create_app() -> Flask:
    app = Flask(__name__)

    init_db()
    seed_cards_from_yaml()
    ensure_resources_seeded()
    reseed_resources()
    register_routes(app)
    app.register_blueprint(frontend_bp)

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
