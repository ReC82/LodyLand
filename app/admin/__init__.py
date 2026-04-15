# app/admin/__init__.py
"""
Comprehensive admin panel module for LodyLand game.
- Role-based access control (super_admin, admin, artist)
- Routes for users, resources, lands, crafts, cards
- YAML file management helpers
"""
from functools import wraps
import re
import json
from pathlib import Path
from datetime import datetime

from flask import (
    Blueprint, current_app, redirect,
    url_for, abort, render_template, request, jsonify)
from app.db import SessionLocal
from app.auth import get_current_player
from app.models import (
    Player,
    PlayerCard,
    CardDef,
    ResourceStock,
    ResourceDef,
    Account,
)

import yaml

# Blueprint for the admin panel
admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    template_folder="templates",
    static_folder="static",
)

# =============================================================================
# ROLE DEFINITIONS & PERMISSIONS
# =============================================================================

ADMIN_ROLES = {
    "super_admin": {
        "label": "Super Admin",
        "permissions": ["view_dashboard", "view_users", "manage_roles", "edit_resources",
                       "edit_lands", "edit_crafts", "edit_cards"]
    },
    "admin": {
        "label": "Admin",
        "permissions": ["view_dashboard", "view_users", "edit_resources",
                       "edit_lands", "edit_crafts", "edit_cards"]
    },
    "artist": {
        "label": "Artist",
        "permissions": ["upload_images", "edit_cards"]
    }
}


def _get_player_role(player: Player) -> str | None:
    """Get the admin role of a player."""
    if not player or not player.is_admin:
        return None
    return player.admin_role or "admin"


def _has_permission(player: Player, permission: str) -> bool:
    """Check if player has a specific permission."""
    role = _get_player_role(player)
    if not role or role not in ADMIN_ROLES:
        return False
    return permission in ADMIN_ROLES[role]["permissions"]


def admin_required(view_func=None, permission=None):
    """
    Decorator for admin-required routes.
    - Checks ADMIN_ENABLED config
    - Verifies player is logged in and is_admin=True
    - If permission specified, checks that too
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_app.config.get("ADMIN_ENABLED", False):
                abort(404)

            session = SessionLocal()
            try:
                player = get_current_player(session)
                if not player or not getattr(player, "is_admin", False):
                    return redirect(url_for("frontend.home"))

                if permission and not _has_permission(player, permission):
                    abort(403)
            finally:
                session.close()

            return func(*args, **kwargs)
        return wrapper

    if view_func is None:
        return decorator
    else:
        return decorator(view_func)


# =============================================================================
# YAML FILE HELPERS
# =============================================================================

def _get_yaml_path(filename: str) -> Path:
    """Get absolute path to a YAML file in app/data/"""
    return Path(current_app.root_path) / "data" / filename


def load_yaml_file(filename: str) -> dict:
    """Load a YAML file and return as dict."""
    path = _get_yaml_path(filename)
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml_file(filename: str, data: dict) -> None:
    """Save dict to YAML file."""
    path = _get_yaml_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            indent=2,
        )


# =============================================================================
# RESOURCES YAML HELPERS
# =============================================================================

def load_resources_yaml() -> dict:
    """Load resources.yml and return {key: config_dict}."""
    data = load_yaml_file("resources.yml")

    # Handle both list and mapping formats
    if isinstance(data, dict) and isinstance(data.get("resources"), list):
        mapping = {}
        for res in data["resources"]:
            if not isinstance(res, dict):
                continue
            key = (res.get("key") or "").strip()
            if key:
                mapping[key] = res
        return mapping

    return data if isinstance(data, dict) else {}


def save_resources_yaml(mapping: dict) -> None:
    """Save resources mapping to YAML."""
    resources_list = []
    for key in sorted(mapping.keys()):
        cfg = dict(mapping.get(key) or {})
        cfg["key"] = key
        resources_list.append(cfg)

    wrapper = {"resources": resources_list}
    yaml_str = yaml.safe_dump(wrapper, allow_unicode=True, sort_keys=False,
                              default_flow_style=False, indent=2)
    yaml_str = yaml_str.replace("\n- ", "\n\n- ")

    path = _get_yaml_path("resources.yml")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(yaml_str)


# =============================================================================
# CARDS YAML HELPERS
# =============================================================================

def load_cards_yaml() -> dict:
    """Load cards.yml and return {key: config_dict}."""
    data = load_yaml_file("cards.yml")

    if isinstance(data, dict) and isinstance(data.get("cards"), list):
        mapping = {}
        for card in data["cards"]:
            if not isinstance(card, dict):
                continue
            key = (card.get("key") or "").strip()
            if key:
                mapping[key] = card
        return mapping

    return data if isinstance(data, dict) else {}


def save_cards_yaml(mapping: dict) -> None:
    """Save cards mapping to YAML."""
    cards_list = []

    def sort_key(item):
        k, cfg = item
        if not isinstance(cfg, dict):
            cfg = {}
        ctype = (cfg.get("type") or "").lower()
        return (ctype, k)

    for key, card_cfg in sorted(mapping.items(), key=sort_key):
        cfg = dict(card_cfg or {})
        cfg["key"] = key
        cards_list.append(cfg)

    wrapper = {"cards": cards_list}
    yaml_str = yaml.safe_dump(wrapper, allow_unicode=True, sort_keys=False,
                              default_flow_style=False, indent=2)
    yaml_str = yaml_str.replace("\n- ", "\n\n- ")

    path = _get_yaml_path("cards.yml")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(yaml_str)


# =============================================================================
# LANDS YAML HELPERS
# =============================================================================

def load_lands_yaml() -> dict:
    """Load lands.yml and return {key: config_dict}."""
    data = load_yaml_file("lands.yml")
    return data if isinstance(data, dict) else {}


def save_lands_yaml(mapping: dict) -> None:
    """Save lands mapping to YAML."""
    ordered = {slug: mapping[slug] for slug in sorted(mapping.keys())}
    save_yaml_file("lands.yml", ordered)


# =============================================================================
# CRAFTS YAML HELPERS
# =============================================================================

def load_crafts_yaml() -> dict:
    """Load crafts.yml and return data."""
    return load_yaml_file("crafts.yml")


def save_crafts_yaml(data: dict) -> None:
    """Save crafts data to YAML."""
    save_yaml_file("crafts.yml", data)


# =============================================================================
# ROUTES: DASHBOARD
# =============================================================================

@admin_bp.get("/")
@admin_required(permission="view_dashboard")
def admin_dashboard():
    """Admin dashboard homepage."""
    session = SessionLocal()
    try:
        player_count = session.query(Player).count()
        admin_count = session.query(Player).filter(Player.is_admin == True).count()
        resource_count = session.query(ResourceDef).count()
        card_count = session.query(CardDef).count()

        stats = {
            "players": player_count,
            "admins": admin_count,
            "resources": resource_count,
            "cards": card_count,
        }
    finally:
        session.close()

    return render_template("ADMIN_UI/dashboard.html", stats=stats)


# =============================================================================
# ROUTES: USERS / PLAYERS
# =============================================================================

@admin_bp.get("/users/")
@admin_required(permission="view_users")
def users_list():
    """List all users with search."""
    search = (request.args.get("q") or "").strip()

    session = SessionLocal()
    try:
        query = session.query(Player)

        if search:
            like_pattern = f"%{search}%"
            query = query.filter(Player.name.ilike(like_pattern))

        players = query.order_by(Player.id.asc()).all()
        return render_template("ADMIN_UI/users_list.html", players=players, search=search)
    finally:
        session.close()


@admin_bp.get("/users/<int:player_id>")
@admin_required(permission="view_users")
def user_detail(player_id: int):
    """Show user details."""
    session = SessionLocal()
    try:
        player = session.get(Player, player_id)
        if not player:
            abort(404)

        account = session.query(Account).filter(Account.player_id == player_id).first()

        cards = (
            session.query(PlayerCard, CardDef)
            .outerjoin(CardDef, CardDef.key == PlayerCard.card_key)
            .filter(PlayerCard.player_id == player_id)
            .order_by(CardDef.card_label.asc().nulls_last())
            .all()
        )

        resources = (
            session.query(ResourceStock, ResourceDef)
            .outerjoin(ResourceDef, ResourceDef.key == ResourceStock.resource)
            .filter(ResourceStock.player_id == player_id)
            .order_by(ResourceDef.label.asc().nulls_last())
            .all()
        )

        return render_template(
            "ADMIN_UI/user_detail.html",
            player=player,
            account=account,
            cards=cards,
            resources=resources,
        )
    finally:
        session.close()


@admin_bp.post("/users/<int:player_id>/role")
@admin_required(permission="manage_roles")
def set_user_role(player_id: int):
    """Set user admin role (super_admin only)."""
    data = request.get_json() or {}
    new_role = (data.get("role") or "").strip()

    if new_role and new_role not in ADMIN_ROLES:
        return jsonify({"ok": False, "error": "Invalid role"}), 400

    session = SessionLocal()
    try:
        player = session.get(Player, player_id)
        if not player:
            abort(404)

        player.is_admin = bool(new_role)
        player.admin_role = new_role or None
        session.commit()

        return jsonify({"ok": True, "role": new_role})
    finally:
        session.close()


# =============================================================================
# ROUTES: RESOURCES
# =============================================================================

@admin_bp.get("/resources/")
@admin_required(permission="edit_resources")
def resources_list():
    """List all resources."""
    yaml_data = load_resources_yaml()

    session = SessionLocal()
    try:
        db_resources = session.query(ResourceDef).all()
        db_by_key = {r.key: r for r in db_resources}
    finally:
        session.close()

    resources_view = []
    for key, cfg in sorted(yaml_data.items()):
        if not isinstance(cfg, dict):
            cfg = {}

        resources_view.append({
            "key": key,
            "label": cfg.get("label", key),
            "kind": cfg.get("kind", "resource"),
            "in_db": key in db_by_key,
        })

    return render_template("ADMIN_UI/resources_list.html", resources=resources_view)


@admin_bp.get("/resources/<key>/edit")
@admin_bp.post("/resources/<key>/edit")
@admin_required(permission="edit_resources")
def edit_resource(key: str):
    """Edit a resource (GET form, POST save)."""
    yaml_data = load_resources_yaml()
    resource_config = yaml_data.get(key, {})

    if request.method == "POST":
        # Update resource config
        label = request.form.get("label", "").strip()
        kind = request.form.get("kind", "resource").strip()

        if not label:
            return render_template("ADMIN_UI/resource_form.html",
                                 key=key, resource=resource_config, error="Label required")

        resource_config["label"] = label
        resource_config["kind"] = kind
        yaml_data[key] = resource_config
        save_resources_yaml(yaml_data)

        return redirect(url_for("admin.resources_list"))

    return render_template("ADMIN_UI/resource_form.html", key=key, resource=resource_config)


@admin_bp.post("/resources/")
@admin_required(permission="edit_resources")
def create_resource():
    """Create a new resource."""
    data = request.get_json() or {}
    key = (data.get("key") or "").strip().lower()
    label = (data.get("label") or "").strip()

    if not key or not label:
        return jsonify({"ok": False, "error": "Key and label required"}), 400

    yaml_data = load_resources_yaml()
    if key in yaml_data:
        return jsonify({"ok": False, "error": "Key already exists"}), 400

    yaml_data[key] = {
        "key": key,
        "label": label,
        "kind": data.get("kind", "resource"),
    }
    save_resources_yaml(yaml_data)

    return jsonify({"ok": True, "key": key})


# =============================================================================
# ROUTES: LANDS
# =============================================================================

@admin_bp.get("/lands/")
@admin_required(permission="edit_lands")
def lands_list():
    """List all lands."""
    lands_data = load_lands_yaml()

    lands_view = []
    for key, cfg in sorted(lands_data.items()):
        if not isinstance(cfg, dict):
            cfg = {}

        lands_view.append({
            "key": key,
            "label": cfg.get("label", key),
            "description": cfg.get("description", ""),
            "enabled": cfg.get("enabled", True),
        })

    return render_template("ADMIN_UI/lands_list.html", lands=lands_view)


@admin_bp.get("/lands/<key>/edit")
@admin_bp.post("/lands/<key>/edit")
@admin_required(permission="edit_lands")
def edit_land(key: str):
    """Edit a land (GET form, POST save with JSON support)."""
    lands_data = load_lands_yaml()
    land_config = lands_data.get(key, {})

    if request.method == "POST":
        label = request.form.get("label", "").strip()
        description = request.form.get("description", "").strip()
        enabled = request.form.get("enabled") == "on"

        # Try to parse JSON data if provided
        json_data_str = request.form.get("json_data", "").strip()
        if json_data_str:
            try:
                extra_data = json.loads(json_data_str)
                land_config.update(extra_data)
            except json.JSONDecodeError:
                return render_template("ADMIN_UI/land_form.html",
                                     key=key, land=land_config,
                                     error="Invalid JSON data")

        land_config["label"] = label
        land_config["description"] = description
        land_config["enabled"] = enabled

        lands_data[key] = land_config
        save_lands_yaml(lands_data)

        return redirect(url_for("admin.lands_list"))

    json_data = json.dumps({k: v for k, v in land_config.items()
                           if k not in ["label", "description", "enabled"]}, indent=2)

    return render_template("ADMIN_UI/land_form.html",
                         key=key, land=land_config, json_data=json_data)


# =============================================================================
# ROUTES: CRAFTS
# =============================================================================

@admin_bp.get("/crafts/")
@admin_required(permission="edit_crafts")
def crafts_list():
    """List all crafts."""
    crafts_data = load_crafts_yaml()

    # Handle both list and mapping formats
    crafts_list_view = []
    if isinstance(crafts_data, dict):
        if isinstance(crafts_data.get("crafts"), list):
            crafts_list_view = crafts_data.get("crafts", [])
        else:
            crafts_list_view = [{"key": k, **v} if isinstance(v, dict) else {"key": k}
                               for k, v in crafts_data.items()]

    return render_template("ADMIN_UI/crafts_list.html", crafts=crafts_list_view)


@admin_bp.post("/crafts/")
@admin_required(permission="edit_crafts")
def create_craft():
    """Create or update a craft."""
    data = request.get_json() or {}
    key = (data.get("key") or "").strip()

    if not key:
        return jsonify({"ok": False, "error": "Key required"}), 400

    crafts_data = load_crafts_yaml()

    # Ensure we have a list format
    if not isinstance(crafts_data, dict) or "crafts" not in crafts_data:
        crafts_data = {"crafts": []}

    craft_list = crafts_data.get("crafts", [])

    # Find or create craft entry
    existing = next((c for c in craft_list if c.get("key") == key), None)
    if existing:
        existing.update({k: v for k, v in data.items() if k != "key"})
    else:
        craft_entry = {"key": key}
        craft_entry.update({k: v for k, v in data.items() if k != "key"})
        craft_list.append(craft_entry)

    save_crafts_yaml(crafts_data)
    return jsonify({"ok": True, "key": key})


# =============================================================================
# ROUTES: CARDS
# =============================================================================

@admin_bp.get("/cards/")
@admin_required(permission="edit_cards")
def cards_list():
    """List all cards."""
    yaml_data = load_cards_yaml()

    session = SessionLocal()
    try:
        db_cards = session.query(CardDef).all()
        db_by_key = {c.key: c for c in db_cards}
    finally:
        session.close()

    cards_view = []
    for key, cfg in sorted(yaml_data.items()):
        if not isinstance(cfg, dict):
            cfg = {}

        cards_view.append({
            "key": key,
            "label": cfg.get("label") or cfg.get("label_fr") or key,
            "type": cfg.get("type", "?"),
            "rarity": cfg.get("rarity", "-"),
            "enabled": cfg.get("enabled", True),
            "in_db": key in db_by_key,
        })

    return render_template("ADMIN_UI/cards_list.html", cards=cards_view)


@admin_bp.post("/cards/")
@admin_required(permission="edit_cards")
def create_card():
    """Create or update a card."""
    data = request.get_json() or {}
    key = (data.get("key") or "").strip()

    if not key:
        return jsonify({"ok": False, "error": "Key required"}), 400

    yaml_data = load_cards_yaml()

    card_data = yaml_data.get(key, {})
    card_data.update({k: v for k, v in data.items()})
    card_data["key"] = key

    yaml_data[key] = card_data
    save_cards_yaml(yaml_data)

    return jsonify({"ok": True, "key": key})


# =============================================================================
# ROUTES: ROLES MANAGEMENT (super_admin only)
# =============================================================================

@admin_bp.get("/roles/manage")
@admin_required(permission="manage_roles")
def manage_roles():
    """Manage admin roles (super_admin only)."""
    session = SessionLocal()
    try:
        admins = session.query(Player).filter(Player.is_admin == True).all()
    finally:
        session.close()

    return render_template("ADMIN_UI/roles_list.html", admins=admins, roles=ADMIN_ROLES)


# Keep old routes for backward compatibility
@admin_bp.get("/players")
@admin_required(permission="view_users")
def players_list():
    """Legacy route - redirects to new path."""
    return redirect(url_for("admin.users_list"))


@admin_bp.get("/players/<int:player_id>")
@admin_required(permission="view_users")
def player_detail(player_id: int):
    """Legacy route - use user_detail instead."""
    return redirect(url_for("admin.user_detail", player_id=player_id))
