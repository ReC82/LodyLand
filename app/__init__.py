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


def _seed_minigames() -> None:
    """Ensure the default doors mini-game exists in DB."""
    from .db import SessionLocal
    from .models import MiniGameDef

    session = SessionLocal()
    try:
        if session.query(MiniGameDef).filter_by(key="doors_level5").first():
            return
        rewards = []
        for lvl in range(1, 11):
            entry = {
                "win_stop":     {"shards": lvl * 8},
                "win_continue": {"shards": lvl * 4},
            }
            if lvl == 10:
                entry["win_grand"] = {"shards": 50}
            rewards.append(entry)

        mg = MiniGameDef(
            key="doors_level5",
            name_fr="La Salle des Portes",
            name_en="The Door Room",
            description_fr=(
                "Dix niveaux, trois portes. L'une cache la défaite, "
                "une autre une récompense, la troisième… la gloire."
            ),
            description_en=(
                "Ten levels, three doors. One hides defeat, "
                "one a reward, the third… glory."
            ),
            min_level=5,
            card_key=None,          # admin sets this via the panel
            card_stock_total=100,
            card_stock_remaining=100,
            free_attempts_per_day=1,
            extra_attempt_cost_diams=5,
            rewards_json=rewards,
            enabled=True,
        )
        session.add(mg)
        session.commit()
        print("[minigame] Seeded default mini-game: doors_level5")
    except Exception as e:
        print(f"[minigame] Seed error: {e}")
        session.rollback()
    finally:
        session.close()


def _seed_story_events() -> None:
    """
    Import story events from levels.yml into the StoryEventDef table (one-time).
    Also seeds the NpcDef for the villager guide if it doesn't exist.
    Safe to call on every boot — skips if table already has rows.
    """
    from .db import SessionLocal
    from .models import StoryEventDef, NpcDef
    from .progression import LEVELS

    session = SessionLocal()
    try:
        if session.query(StoryEventDef).count() > 0:
            return  # Already seeded

        # Seed the default NPC
        if not session.query(NpcDef).filter_by(key="npc_villager_guide").first():
            session.add(NpcDef(
                key="npc_villager_guide",
                name_fr="Le Guide du Village",
                name_en="The Village Guide",
                portrait="Anna.png",
            ))

        # Import all story events from levels.yml
        count = 0
        for lvl_num, cfg in LEVELS.items():
            events = cfg.get("story_events") or []
            for sort_idx, ev in enumerate(events):
                ev_id = ev.get("id")
                if not ev_id:
                    continue

                # Convert pages: normalize speaker from old format
                raw_pages = ev.get("pages") or []
                pages = []
                for page in raw_pages:
                    speaker_raw = page.get("speaker", "self")
                    # Old format uses "npc_villager_guide" as speaker key
                    if speaker_raw == "self":
                        speaker = "self"
                    else:
                        speaker = f"npc:{speaker_raw}"

                    pages.append({
                        "speaker": speaker,
                        "mood": page.get("mood", ""),
                        "text": page.get("text", {"fr": "", "en": ""}),
                    })

                session.add(StoryEventDef(
                    id=ev_id,
                    level=lvl_num,
                    trigger=ev.get("trigger", "on_level_reached"),
                    land_key=ev.get("land_key"),
                    show_once=ev.get("show_once", True),
                    modal_variant=ev.get("modal_variant", "centered"),
                    pages=pages,
                    quest_start=ev.get("quest_start"),
                    sort_order=sort_idx,
                    enabled=True,
                ))
                count += 1

        session.commit()
        print(f"[story] Seeded {count} story events from levels.yml")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[story] Seed error: {e}")
        session.rollback()
    finally:
        session.close()


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
    _seed_minigames()
    _seed_story_events()
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
