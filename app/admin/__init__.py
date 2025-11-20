# app/admin/__init__.py
from functools import wraps

from flask import (
    Blueprint, current_app, redirect, 
    url_for, abort, render_template, request)
from app.db import SessionLocal
from app.auth import get_current_player
from app.models import (
    Player,
    PlayerCard,
    CardDef,
    ResourceStock,
    ResourceDef,
)

from pathlib import Path
import yaml

# Blueprint for the admin panel
admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    template_folder="templates",  # templates inside app/admin/templates
    static_folder="static",      # static inside app/admin/static
)

# -------------------------------------------------------------------
# Cards YAML helpers
# -------------------------------------------------------------------

# On part du dossier app/ (parent de app/admin/) → app/data/cards.yml
CARDS_YAML_PATH = Path(__file__).resolve().parents[1] / "data" / "cards.yml"


def load_cards_yaml() -> dict:
    """Charge cards.yml et retourne un dict {key: config_dict}.

    - Si le YAML a la forme:
        { "cards": [ {key: "...", ...}, {...} ] }
      on le convertit en mapping par key.
    - Si c'est déjà un mapping {key: {...}}, on le renvoie tel quel.
    - Sinon on renvoie {}.
    """
    if not CARDS_YAML_PATH.exists():
        return {}

    with CARDS_YAML_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # Cas 1: ton format actuel: {"cards": [ {...}, {...}, ... ]}
    if isinstance(data, dict) and isinstance(data.get("cards"), list):
        mapping: dict[str, dict] = {}
        for card in data["cards"]:
            if not isinstance(card, dict):
                continue
            key = (card.get("key") or "").strip()
            if not key:
                continue
            mapping[key] = card
        return mapping

    # Cas 2: déjà un mapping { "wood_boost_1": {...}, ... }
    if isinstance(data, dict):
        return data

    # Fallback
    return {}



def save_cards_yaml(data: dict) -> None:
    """Écrit tout le mapping de cartes dans cards.yml.

    - Écrase le fichier
    - Dump propre (clé triées, block style)
    """
    CARDS_YAML_PATH.parent.mkdir(parents=True, exist_ok=True)

    with CARDS_YAML_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            allow_unicode=True,
            sort_keys=True,
            default_flow_style=False,
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
    Show player details, unlocked cards, and resource stocks.
    """
    session = SessionLocal()
    try:
        # Load player
        player = session.get(Player, player_id)
        if not player:
            abort(404)

        # Load all PlayerCard rows for this player + CardDef metadata
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

        # Load resource stocks for this player + ResourceDef metadata
        resources = (
            session.query(ResourceStock, ResourceDef)
            .outerjoin(
                ResourceDef,
                ResourceDef.key == ResourceStock.resource,
            )
            .filter(ResourceStock.player_id == player_id)
            .order_by(ResourceDef.label.asc().nulls_last(), ResourceStock.resource.asc())
            .all()
        )

        return render_template(
            "ADMIN_UI/player_detail.html",
            player=player,
            cards=cards,
            resources=resources,
        )
    finally:
        session.close()

@admin_bp.get("/cards")
@admin_required
def cards_list():
    """Liste toutes les cartes issues de cards.yml + statut de synchro DB."""
    # 1) Charger le YAML
    yaml_data = load_cards_yaml()  # {key: cfg_dict}

    # 2) Charger tous les CardDef en DB
    session = SessionLocal()
    try:
        db_cards = session.query(CardDef).all()
        db_by_key = {c.key: c for c in db_cards}
    finally:
        session.close()

    # 3) Construire une vue simplifiée pour le template
    cards_for_view: list[dict] = []

    for key, cfg in sorted(yaml_data.items(), key=lambda item: item[0]):
        if not isinstance(cfg, dict):
            cfg = {}

        label = (
            cfg.get("label_fr")
            or cfg.get("label_en")
            or cfg.get("label")
            or key
        )
        ctype = cfg.get("type", "?")
        rarity = cfg.get("rarity", "-")
        enabled = cfg.get("enabled", True)

        in_db = key in db_by_key

        cards_for_view.append(
            {
                "key": key,
                "label": label,
                "type": ctype,
                "rarity": rarity,
                "enabled": bool(enabled),
                "in_db": in_db,
            }
        )

    # 4) Détecter les cartes présentes en DB mais absentes du YAML
    db_only_cards = [
        c for c in db_cards
        if c.key not in yaml_data
    ]

    return render_template(
        "ADMIN_UI/cards_list.html",
        cards=cards_for_view,
        db_only_cards=db_only_cards,
        yaml_path=str(CARDS_YAML_PATH),
    )
