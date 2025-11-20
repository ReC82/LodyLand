# app/admin/__init__.py
from functools import wraps

from flask import Blueprint, current_app, redirect, url_for, abort
from app.db import SessionLocal
from app.auth import get_current_player   # ✔ TON projet utilise déjà ça

# Blueprint du panel admin
admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
)


def admin_required(view_func):
    """
    Vérifie :
    - Admin panel activé ?
    - Joueur connecté ?
    - Joueur admin ?
    """
    @wraps(view_func)
    def wrapper(*args, **kwargs):

        # 1) Admin panel activé dans create_app()
        if not current_app.config.get("ADMIN_ENABLED", False):
            abort(404)

        session = SessionLocal()
        try:
            player = get_current_player(session)
            # 2) joueur existe ?
            # 3) joueur est admin ?
            if not player or not getattr(player, "is_admin", False):
                return redirect(url_for("frontend.home"))
        finally:
            session.close()

        return view_func(*args, **kwargs)

    return wrapper


@admin_bp.get("/")
@admin_required
def admin_dashboard():
    # Ce sera remplacé par un vrai template au Step 2
    return "<h1>LodyLand Admin Panel</h1><p>✔ Accès admin OK</p>"
