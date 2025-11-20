# app/admin/__init__.py
from functools import wraps

from flask import Blueprint, current_app, redirect, url_for, abort, render_template, request
from app.db import SessionLocal
from app.auth import get_current_player
from app.models import Player, PlayerCard, CardDef

# Blueprint for the admin panel
admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    template_folder="templates",  # templates inside app/admin/templates
    static_folder="static",      # static inside app/admin/static
)

def admin_required(view_func):
    """
    Ensure:
    - ADMIN_ENABLED config flag is True
    - current player is logged in
    - current player has is_admin == True
    """
    @wraps(view_func)
    def wrapper(*args, **kwargs):

        # 1) Is the admin panel globally enabled?
        if not current_app.config.get("ADMIN_ENABLED", False):
            abort(404)

        session = SessionLocal()
        try:
            player = get_current_player(session)
            if not player or not getattr(player, "is_admin", False):
                # Not admin → redirect back to the game home
                return redirect(url_for("frontend.home"))
        finally:
            session.close()

        return view_func(*args, **kwargs)

    return wrapper


@admin_bp.get("/")
@admin_required
def admin_dashboard():
    """
    Admin home page using a clean HTML layout.
    """
    return render_template("ADMIN_UI/dashboard.html")

@admin_bp.get("/players")
@admin_required
def players_list():
    """
    List players with optional search on name.
    """
    # Get search query from URL: /admin/players?q=...
    search = (request.args.get("q") or "").strip()

    session = SessionLocal()
    try:
        query = session.query(Player)

        # Filter by name if search term provided
        if search:
            like_pattern = f"%{search}%"
            query = query.filter(Player.name.ilike(like_pattern))

        # For now we load all results, later we can add pagination
        players = query.order_by(Player.id.asc()).all()

        return render_template(
            "ADMIN_UI/players_list.html",
            players=players,
            search=search,
        )
    finally:
        session.close()
        
@admin_bp.get("/players/<int:player_id>")
@admin_required
def player_detail(player_id: int):
    """
    Show player details and unlocked cards.
    """
    session = SessionLocal()
    try:
        # Load player
        player = session.get(Player, player_id)
        if not player:
            abort(404)

        # Load all PlayerCard rows for this player
        # and join with CardDef to get label/icon/type
        cards = (
            session.query(PlayerCard, CardDef)
            .outerjoin(
                CardDef,
                CardDef.key == PlayerCard.card_key,
            )
            .filter(PlayerCard.player_id == player_id)
            .order_by(CardDef.label.asc().nulls_last(), PlayerCard.card_key.asc())
            .all()
        )

        return render_template(
            "ADMIN_UI/player_detail.html",
            player=player,
            cards=cards,
        )
    finally:
        session.close()
        