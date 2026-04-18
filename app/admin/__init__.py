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
    finally:
        session.close()

    # Merge: DB is source of truth; YAML provides extra metadata when present
    db_by_key = {r.key: r for r in db_resources}
    all_keys = sorted(set(list(yaml_data.keys()) + list(db_by_key.keys())))

    resources_view = []
    for key in all_keys:
        cfg = yaml_data.get(key) or {}
        if not isinstance(cfg, dict):
            cfg = {}
        db_r = db_by_key.get(key)

        resources_view.append({
            "key": key,
            "label": cfg.get("label") or (db_r.label if db_r else key),
            "kind": cfg.get("kind") or (db_r.kind if db_r else "resource"),
            "in_db": key in db_by_key,
        })

    return render_template("ADMIN_UI/resources_list.html", resources=resources_view)


def _load_item_translations(key: str) -> dict:
    """Load fr/en translations for a specific item key from YAML files."""
    result = {}
    for lang in ("fr", "en"):
        path = Path(__file__).resolve().parent.parent / "i18n" / "translations" / f"{lang}.yml"
        if not path.exists():
            result[lang] = {}
            continue
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        item_data = data.get("items", {}).get(key, {})
        result[lang] = item_data
    return result


def _save_item_translations(key: str, translations: dict) -> None:
    """Save fr/en translations for a specific item key into YAML files.

    translations = {"fr": {"label": "...", "description": "..."}, "en": {...}}
    """
    for lang, values in translations.items():
        if not values:
            continue
        path = Path(__file__).resolve().parent.parent / "i18n" / "translations" / f"{lang}.yml"
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        items_section = data.setdefault("items", {})
        item_entry = items_section.setdefault(key, {})
        for field, value in values.items():
            if value is not None:
                item_entry[field] = value

        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False,
                           default_flow_style=False, indent=2)


@admin_bp.get("/resources/<key>/edit")
@admin_bp.post("/resources/<key>/edit")
@admin_required(permission="edit_resources")
def edit_resource(key: str):
    """Edit a resource — reads/writes DB; translations go to fr.yml/en.yml."""
    session = SessionLocal()
    try:
        resource = session.query(ResourceDef).filter(ResourceDef.key == key).first()
        if not resource:
            abort(404)

        translations = _load_item_translations(key)

        if request.method == "POST":
            label = request.form.get("label", "").strip()
            kind = request.form.get("kind", "resource").strip()
            description = request.form.get("description", "").strip() or None
            icon = request.form.get("icon", "").strip() or None
            base_sell_price_raw = request.form.get("base_sell_price", "").strip()
            enabled = request.form.get("enabled") == "on"

            label_fr = request.form.get("label_fr", "").strip()
            label_en = request.form.get("label_en", "").strip()
            desc_fr = request.form.get("desc_fr", "").strip()
            desc_en = request.form.get("desc_en", "").strip()

            if not label and not label_fr:
                return render_template("ADMIN_UI/resource_form.html",
                                       key=key, resource=resource,
                                       translations=translations,
                                       error="Label requis")

            # If translations provided, store the i18n key in DB label
            has_translations = label_fr or label_en
            if has_translations:
                i18n_key = f"items.{key}.label"
                resource.label = i18n_key
                _save_item_translations(key, {
                    "fr": {"label": label_fr or None, "description": desc_fr or None},
                    "en": {"label": label_en or None, "description": desc_en or None},
                })
            elif label:
                resource.label = label

            resource.kind = kind or resource.kind
            resource.description = description
            if icon:
                resource.icon = icon
            if base_sell_price_raw.isdigit():
                resource.base_sell_price = int(base_sell_price_raw)
            resource.enabled = enabled

            session.commit()
            return redirect(url_for("admin.resources_list"))

        return render_template("ADMIN_UI/resource_form.html",
                               key=key, resource=resource, translations=translations)
    finally:
        session.close()


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
    """Edit a land — structured form (no raw JSON for the admin)."""
    lands_data = load_lands_yaml()
    land_config = lands_data.get(key, {})

    # Load available resources for dropdowns
    session = SessionLocal()
    try:
        db_resources = session.query(ResourceDef).filter(
            ResourceDef.enabled == True
        ).order_by(ResourceDef.key).all()
        resource_list = [{"key": r.key, "label": r.label} for r in db_resources]
    finally:
        session.close()

    if request.method == "POST":
        # Basic fields
        land_config["label_fr"] = request.form.get("label_fr", "").strip()
        land_config["label_en"] = request.form.get("label_en", "").strip()
        land_config["enabled"] = request.form.get("enabled") == "on"
        land_config["starting_land"] = request.form.get("starting_land") == "on"

        # Visual
        slot_icon = request.form.get("slot_icon", "").strip()
        logo = request.form.get("logo", "").strip()
        html_desc = request.form.get("html_description", "").strip()
        if slot_icon:
            land_config["slot_icon"] = slot_icon
        if logo:
            land_config["logo"] = logo
        if html_desc:
            land_config["html_description"] = html_desc

        # Settings
        for field, cast in [
            ("slots", int),
            ("additional_slot_base_cost_diams", int),
            ("xp_per_collect", int),
            ("additional_slot_cost_multiplier", float),
        ]:
            raw = request.form.get(field, "").strip()
            if raw:
                try:
                    land_config[field] = cast(raw)
                except ValueError:
                    pass

        # Tools (submitted as JSON blob from the JS editor)
        tools_json = request.form.get("tools_json", "").strip()
        if tools_json:
            try:
                land_config["tools"] = json.loads(tools_json)
            except json.JSONDecodeError:
                return render_template(
                    "ADMIN_UI/land_form.html",
                    key=key, land=land_config,
                    resource_list=resource_list,
                    error="Données outils invalides (JSON malformé)")

        lands_data[key] = land_config
        save_lands_yaml(lands_data)
        return redirect(url_for("admin.lands_list"))

    return render_template("ADMIN_UI/land_form.html",
                           key=key, land=land_config,
                           resource_list=resource_list)


# =============================================================================
# ROUTES: CRAFTS
# =============================================================================

def _load_craft_stations() -> dict:
    """Load craft_stations.yml → {station_key: {label, grids}}"""
    path = Path(current_app.root_path) / "data" / "craft_stations.yml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("stations", {})


def _get_crafts_dict() -> dict:
    """Return crafts as {key: cfg_dict}."""
    data = load_crafts_yaml()
    crafts = data.get("crafts", {})
    if isinstance(crafts, dict):
        return crafts
    # Legacy list format
    return {c["key"]: c for c in crafts if isinstance(c, dict) and "key" in c}


def _save_crafts_dict(crafts_dict: dict) -> None:
    """Persist a crafts dict back to crafts.yml."""
    path = Path(current_app.root_path) / "data" / "crafts.yml"
    header = (
        "# NOTE:\n"
        "#   This file is managed by the admin panel.\n"
        "#   Edit via /admin/crafts/\n\n"
    )
    payload = {"crafts": crafts_dict}
    body = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False,
                          default_flow_style=False, indent=2)
    with path.open("w", encoding="utf-8") as f:
        f.write(header + body)


@admin_bp.get("/crafts/")
@admin_required(permission="edit_crafts")
def crafts_list():
    """List all crafts."""
    crafts_dict = _get_crafts_dict()
    stations = _load_craft_stations()

    crafts_view = []
    for key, cfg in sorted(crafts_dict.items()):
        if not isinstance(cfg, dict):
            cfg = {}
        out = cfg.get("output", {})
        crafts_view.append({
            "key": key,
            "station_key": cfg.get("station_key", "?"),
            "output_key": out.get("key", "?"),
            "output_qty": out.get("quantity", 1),
            "craft_time": cfg.get("craft_time_seconds", "?"),
            "xp_reward": cfg.get("xp_reward", 0),
            "enabled": cfg.get("enabled", True),
        })

    return render_template("ADMIN_UI/crafts_list.html",
                           crafts=crafts_view, stations=stations)


@admin_bp.get("/crafts/<key>/edit")
@admin_bp.post("/crafts/<key>/edit")
@admin_required(permission="edit_crafts")
def edit_craft(key: str):
    """Edit a craft — structured form."""
    crafts_dict = _get_crafts_dict()
    craft = crafts_dict.get(key)
    if craft is None:
        abort(404)

    stations = _load_craft_stations()

    # All resources + items for ingredient dropdowns
    session = SessionLocal()
    try:
        db_resources = session.query(ResourceDef).filter(
            ResourceDef.enabled == True
        ).order_by(ResourceDef.key).all()
        resource_list = [{"key": r.key, "label": r.label} for r in db_resources]
    finally:
        session.close()

    if request.method == "POST":
        craft_json = request.form.get("craft_json", "").strip()
        if not craft_json:
            return render_template("ADMIN_UI/craft_form.html",
                                   key=key, craft=craft,
                                   stations=stations, resource_list=resource_list,
                                   error="Données manquantes")
        try:
            updated = json.loads(craft_json)
        except json.JSONDecodeError as e:
            return render_template("ADMIN_UI/craft_form.html",
                                   key=key, craft=craft,
                                   stations=stations, resource_list=resource_list,
                                   error=f"JSON invalide : {e}")

        updated["key"] = key  # enforce key
        crafts_dict[key] = updated
        _save_crafts_dict(crafts_dict)
        return redirect(url_for("admin.crafts_list"))

    return render_template("ADMIN_UI/craft_form.html",
                           key=key, craft=craft,
                           stations=stations, resource_list=resource_list)


@admin_bp.post("/crafts/new")
@admin_required(permission="edit_crafts")
def create_craft():
    """Create a new empty craft and redirect to its edit page."""
    data = request.get_json() or {}
    key = (data.get("key") or "").strip().lower().replace(" ", "_")

    if not key:
        return jsonify({"ok": False, "error": "Key required"}), 400

    crafts_dict = _get_crafts_dict()
    if key in crafts_dict:
        return jsonify({"ok": False, "error": "Key already exists"}), 400

    crafts_dict[key] = {
        "key": key,
        "station_key": "craft_table_base",
        "output": {"kind": "resource", "key": "", "quantity": 1},
        "recipe": {
            "pattern": ["..."],
            "legend": {},
            "required_table_level": 1,
        },
        "craft_time_seconds": 30,
        "xp_reward": 5,
        "unlock": {"recipe_card_key": f"recipe_{key}", "min_level": 1},
        "enabled": True,
    }
    _save_crafts_dict(crafts_dict)
    return jsonify({"ok": True, "key": key,
                    "redirect": url_for("admin.edit_craft", key=key)})


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


# =============================================================================
# ROUTES: MINI-GAMES
# =============================================================================

from app.models import MiniGameDef, PlayerMiniGameState


def _default_mg_rewards() -> list:
    rewards = []
    for lvl in range(1, 11):
        entry = {
            "win_stop":     {"shards": lvl * 8},
            "win_continue": {"shards": lvl * 4},
        }
        if lvl == 10:
            entry["win_grand"] = {"shards": 50}
        rewards.append(entry)
    return rewards


@admin_bp.get("/minigames/")
@admin_required(permission="view_dashboard")
def minigames_list():
    session = SessionLocal()
    try:
        mgs = session.query(MiniGameDef).order_by(MiniGameDef.min_level).all()
        return render_template("ADMIN_UI/minigames_list.html", minigames=mgs)
    finally:
        session.close()


@admin_bp.post("/minigames/new")
@admin_required(permission="view_dashboard")
def create_minigame():
    data = request.get_json() or {}
    key = (data.get("key") or "").strip().lower().replace(" ", "_")
    if not key:
        return jsonify({"ok": False, "error": "Key required"}), 400

    session = SessionLocal()
    try:
        if session.query(MiniGameDef).filter_by(key=key).first():
            return jsonify({"ok": False, "error": "Key already exists"}), 400
        mg = MiniGameDef(
            key=key,
            name_fr=key,
            name_en=key,
            rewards_json=_default_mg_rewards(),
        )
        session.add(mg)
        session.commit()
        return jsonify({"ok": True, "key": key,
                        "redirect": url_for("admin.edit_minigame", key=key)})
    finally:
        session.close()


@admin_bp.get("/minigames/<key>/edit")
@admin_bp.post("/minigames/<key>/edit")
@admin_required(permission="view_dashboard")
def edit_minigame(key: str):
    session = SessionLocal()
    try:
        mg = session.query(MiniGameDef).filter_by(key=key).first()
        if not mg:
            abort(404)

        # Cards for the dropdown
        cards = session.query(CardDef).order_by(CardDef.key).all()

        # Player stats for this minigame
        total_players = session.query(PlayerMiniGameState)\
            .filter_by(minigame_key=key).count()
        winners = session.query(PlayerMiniGameState)\
            .filter_by(minigame_key=key, has_won_card=True).count()

        if request.method == "POST":
            mg.name_fr = request.form.get("name_fr", "").strip() or mg.name_fr
            mg.name_en = request.form.get("name_en", "").strip() or mg.name_en
            mg.description_fr = request.form.get("description_fr", "").strip() or None
            mg.description_en = request.form.get("description_en", "").strip() or None
            mg.min_level = int(request.form.get("min_level", 5))
            mg.card_key = request.form.get("card_key", "").strip() or None
            mg.card_stock_total = int(request.form.get("card_stock_total", 100))
            mg.card_stock_remaining = int(request.form.get("card_stock_remaining",
                                                           mg.card_stock_remaining))
            mg.free_attempts_per_day = int(request.form.get("free_attempts_per_day", 1))
            mg.extra_attempt_cost_diams = int(request.form.get("extra_attempt_cost_diams", 5))
            mg.enabled = request.form.get("enabled") == "on"

            # Rewards: submitted as JSON
            rewards_raw = request.form.get("rewards_json", "").strip()
            if rewards_raw:
                try:
                    mg.rewards_json = json.loads(rewards_raw)
                except json.JSONDecodeError:
                    return render_template(
                        "ADMIN_UI/minigame_form.html",
                        mg=mg, cards=cards,
                        total_players=total_players, winners=winners,
                        error="Récompenses JSON invalides")

            session.commit()
            return redirect(url_for("admin.minigames_list"))

        return render_template(
            "ADMIN_UI/minigame_form.html",
            mg=mg, cards=cards,
            total_players=total_players, winners=winners,
        )
    finally:
        session.close()


@admin_bp.post("/minigames/<key>/reset-stock")
@admin_required(permission="view_dashboard")
def reset_minigame_stock(key: str):
    """Reset remaining stock to match total."""
    session = SessionLocal()
    try:
        mg = session.query(MiniGameDef).filter_by(key=key).first()
        if not mg:
            abort(404)
        mg.card_stock_remaining = mg.card_stock_total
        session.commit()
        return jsonify({"ok": True, "remaining": mg.card_stock_remaining})
    finally:
        session.close()


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
