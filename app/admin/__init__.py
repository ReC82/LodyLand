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
    NpcDef,
    StoryEventDef,
    SkillDef,
    PlayerSkill,
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

@admin_bp.get("/resources/print")
@admin_required(permission="edit_resources")
def resources_print():
    """Printable artist reference sheet for all resources."""
    import os
    session = SessionLocal()
    try:
        db_resources = session.query(ResourceDef).order_by(ResourceDef.key).all()
    finally:
        session.close()

    # Load all translations at once
    translations = {}
    for lang in ("fr", "en"):
        path = Path(__file__).resolve().parent.parent / "i18n" / "translations" / f"{lang}.yml"
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            translations[lang] = data.get("items", {})
        else:
            translations[lang] = {}

    items_img_dir = Path(__file__).resolve().parent.parent / "static" / "assets" / "img" / "items"

    def find_image(key):
        """Find image in items subfolders."""
        for sub in ("resources", "treasures", "tools", "misc", "weapons"):
            p = items_img_dir / sub / f"{key}.png"
            if p.exists():
                return f"/static/assets/img/items/{sub}/{key}.png"
        return None

    resources_view = []
    for r in db_resources:
        fr_data = translations["fr"].get(r.key, {})
        en_data = translations["en"].get(r.key, {})
        label_fr = fr_data.get("label") if isinstance(fr_data, dict) else None
        label_en = en_data.get("label") if isinstance(en_data, dict) else None
        # Fallback to DB label if no i18n entry
        if not label_fr and r.label and not r.label.startswith("items."):
            label_fr = r.label
        resources_view.append({
            "key": r.key,
            "label_fr": label_fr or r.key,
            "label_en": label_en or "",
            "kind": r.kind,
            "image": find_image(r.key),
        })

    return render_template("ADMIN_UI/resources_print.html", resources=resources_view)


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


# =============================================================================
# Levels Management
# =============================================================================

LEVELS_FILE = Path(__file__).parent.parent / "data" / "levels.yml"

REWARD_TYPES = [
    ("shards",   "🪙 Shards"),
    ("essence",  "💎 Essence"),
    ("card",     "🃏 Carte"),
    ("resource", "📦 Ressource"),
]


def _load_levels_yaml() -> list:
    """Return raw YAML list (preserving all fields)."""
    if not LEVELS_FILE.exists():
        return []
    raw = yaml.safe_load(LEVELS_FILE.read_text(encoding="utf-8")) or {}
    return raw.get("levels", []) or []


def _save_levels_yaml(levels_list: list) -> None:
    """Write levels list back to YAML, reload the progression module."""
    LEVELS_FILE.write_text(
        yaml.dump({"levels": levels_list}, allow_unicode=True,
                  sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    # Hot-reload progression globals
    import app.progression as prog
    prog.LEVELS = prog._load_levels_from_yaml()
    prog.MAX_LEVEL = max(prog.LEVELS.keys()) if prog.LEVELS else 0


@admin_bp.get("/levels/")
@admin_required(permission="view_dashboard")
def levels_list():
    levels = _load_levels_yaml()
    session = SessionLocal()
    try:
        cards = session.query(CardDef).filter_by(enabled=True).order_by(CardDef.key).all()
        resources = session.query(ResourceDef).filter_by(enabled=True).order_by(ResourceDef.key).all()
    finally:
        session.close()
    return render_template("ADMIN_UI/levels_list.html",
                           levels=levels, cards=cards, resources=resources,
                           reward_types=REWARD_TYPES)


@admin_bp.post("/levels/save")
@admin_required(permission="view_dashboard")
def levels_save():
    """Save full levels payload (JSON body) back to YAML."""
    data = request.get_json(silent=True)
    if not data or "levels" not in data:
        return jsonify({"ok": False, "error": "Invalid payload"}), 400

    # Load current YAML to preserve story_events, system_unlocks
    current = {int(l["level"]): l for l in _load_levels_yaml()}

    merged = []
    for entry in data["levels"]:
        lvl_num = int(entry.get("level", 0))
        existing = current.get(lvl_num, {"level": lvl_num})
        existing["xp_required"] = int(entry.get("xp_required", 0))
        existing["rewards"] = entry.get("rewards", [])
        merged.append(existing)

    # Keep levels that weren't in the payload (shouldn't happen, but safe)
    sent_nums = {int(e["level"]) for e in data["levels"]}
    for lvl_num, existing in current.items():
        if lvl_num not in sent_nums:
            merged.append(existing)

    merged.sort(key=lambda l: int(l["level"]))
    _save_levels_yaml(merged)
    return jsonify({"ok": True})


@admin_bp.post("/levels/new")
@admin_required(permission="view_dashboard")
def level_new():
    """Add a new level."""
    data = request.get_json(silent=True) or {}
    lvl_num = int(data.get("level", 0))
    if lvl_num < 0:
        return jsonify({"ok": False, "error": "Invalid level"}), 400

    levels = _load_levels_yaml()
    existing_nums = {int(l["level"]) for l in levels}
    if lvl_num in existing_nums:
        return jsonify({"ok": False, "error": f"Level {lvl_num} already exists"}), 400

    levels.append({"level": lvl_num, "xp_required": 0, "rewards": [],
                   "story_events": [], "system_unlocks": []})
    levels.sort(key=lambda l: int(l["level"]))
    _save_levels_yaml(levels)
    return jsonify({"ok": True})


@admin_bp.post("/levels/<int:lvl_num>/delete")
@admin_required(permission="view_dashboard")
def level_delete(lvl_num: int):
    levels = _load_levels_yaml()
    levels = [l for l in levels if int(l["level"]) != lvl_num]
    _save_levels_yaml(levels)
    return jsonify({"ok": True})


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


# =============================================================================
# NPC Management
# =============================================================================

def _get_pnj_portraits() -> list[str]:
    """List portrait filenames from the pnj/villagers folder."""
    pnj_dir = Path(__file__).parent.parent / "static" / "assets" / "img" / "pnj" / "villagers"
    if not pnj_dir.exists():
        return []
    return sorted(
        f.name for f in pnj_dir.iterdir()
        if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
    )


def _get_player_moods() -> list[str]:
    """List player mood image filenames from the players/defaults folder."""
    pl_dir = Path(__file__).parent.parent / "static" / "assets" / "img" / "ui" / "players" / "defaults"
    if not pl_dir.exists():
        return []
    return sorted(
        f.stem for f in pl_dir.iterdir()
        if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
    )


@admin_bp.get("/npcs/")
@admin_required(permission="view_dashboard")
def npcs_list():
    session = SessionLocal()
    try:
        npcs = session.query(NpcDef).order_by(NpcDef.key).all()
        return render_template("ADMIN_UI/npcs_list.html", npcs=npcs)
    finally:
        session.close()


@admin_bp.post("/npcs/new")
@admin_required(permission="view_dashboard")
def create_npc():
    data = request.get_json() or {}
    key = (data.get("key") or "").strip().lower().replace(" ", "_")
    if not key:
        return jsonify({"ok": False, "error": "Key required"}), 400
    if not key.startswith("npc_"):
        key = "npc_" + key

    session = SessionLocal()
    try:
        if session.query(NpcDef).filter_by(key=key).first():
            return jsonify({"ok": False, "error": "Key already exists"}), 400
        npc = NpcDef(key=key, name_fr=key, name_en=key)
        session.add(npc)
        session.commit()
        return jsonify({"ok": True, "key": key,
                        "redirect": url_for("admin.edit_npc", key=key)})
    finally:
        session.close()


@admin_bp.get("/npcs/<key>/edit")
@admin_bp.post("/npcs/<key>/edit")
@admin_required(permission="view_dashboard")
def edit_npc(key: str):
    session = SessionLocal()
    try:
        npc = session.query(NpcDef).filter_by(key=key).first()
        if not npc:
            abort(404)

        portraits = _get_pnj_portraits()

        if request.method == "POST":
            npc.name_fr = request.form.get("name_fr", "").strip() or npc.name_fr
            npc.name_en = request.form.get("name_en", "").strip() or npc.name_en
            portrait = request.form.get("portrait", "").strip()
            npc.portrait = portrait if portrait else None
            npc.enabled = request.form.get("enabled") == "on"
            session.commit()
            return redirect(url_for("admin.npcs_list"))

        return render_template("ADMIN_UI/npc_form.html", npc=npc, portraits=portraits)
    finally:
        session.close()


@admin_bp.post("/npcs/<key>/delete")
@admin_required(permission="view_dashboard")
def delete_npc(key: str):
    session = SessionLocal()
    try:
        npc = session.query(NpcDef).filter_by(key=key).first()
        if not npc:
            abort(404)
        session.delete(npc)
        session.commit()
        return jsonify({"ok": True})
    finally:
        session.close()


# =============================================================================
# Story Event Management
# =============================================================================

TRIGGERS = [
    ("on_first_login", "Premier login"),
    ("on_level_reached", "Niveau atteint"),
    ("on_land_unlocked", "Terre débloquée"),
    ("on_enter_land", "Entrée dans une terre"),
]

MODAL_VARIANTS = [
    ("full", "Plein écran (full)"),
    ("centered", "Centré (centered)"),
    ("toast", "Toast (toast)"),
]


@admin_bp.get("/story/")
@admin_required(permission="view_dashboard")
def story_list():
    session = SessionLocal()
    try:
        events = (
            session.query(StoryEventDef)
            .order_by(StoryEventDef.level, StoryEventDef.sort_order, StoryEventDef.id)
            .all()
        )
        # Group by level
        by_level: dict = {}
        for ev in events:
            by_level.setdefault(ev.level, []).append(ev)

        return render_template("ADMIN_UI/story_list.html",
                               by_level=by_level,
                               sorted_levels=sorted(by_level.keys()))
    finally:
        session.close()


@admin_bp.post("/story/new")
@admin_required(permission="view_dashboard")
def create_story_event():
    data = request.get_json() or {}
    ev_id = (data.get("id") or "").strip().lower().replace(" ", "_")
    if not ev_id:
        return jsonify({"ok": False, "error": "ID required"}), 400
    level = int(data.get("level", 0))

    session = SessionLocal()
    try:
        if session.query(StoryEventDef).filter_by(id=ev_id).first():
            return jsonify({"ok": False, "error": "ID already exists"}), 400
        ev = StoryEventDef(
            id=ev_id,
            level=level,
            trigger="on_level_reached",
            pages=[],
        )
        session.add(ev)
        session.commit()
        return jsonify({"ok": True, "id": ev_id,
                        "redirect": url_for("admin.edit_story_event", ev_id=ev_id)})
    finally:
        session.close()


@admin_bp.get("/story/<ev_id>/edit")
@admin_bp.post("/story/<ev_id>/edit")
@admin_required(permission="view_dashboard")
def edit_story_event(ev_id: str):
    session = SessionLocal()
    try:
        ev = session.query(StoryEventDef).filter_by(id=ev_id).first()
        if not ev:
            abort(404)

        npcs = session.query(NpcDef).filter_by(enabled=True).order_by(NpcDef.key).all()
        player_moods = _get_player_moods()
        portraits = _get_pnj_portraits()
        error = None

        if request.method == "POST":
            ev.level = int(request.form.get("level", 0))
            ev.trigger = request.form.get("trigger", "on_level_reached")
            ev.land_key = request.form.get("land_key", "").strip() or None
            ev.show_once = request.form.get("show_once") == "on"
            ev.modal_variant = request.form.get("modal_variant", "centered")
            ev.sort_order = int(request.form.get("sort_order", 0))
            ev.enabled = request.form.get("enabled") == "on"

            quest_key = request.form.get("quest_key", "").strip()
            ev.quest_start = {"quest_key": quest_key} if quest_key else None

            pages_raw = request.form.get("pages_json", "[]").strip()
            try:
                ev.pages = json.loads(pages_raw)
            except json.JSONDecodeError:
                error = "Pages JSON invalides"

            if not error:
                session.commit()
                return redirect(url_for("admin.story_list"))

        return render_template(
            "ADMIN_UI/story_form.html",
            ev=ev,
            npcs=npcs,
            player_moods=player_moods,
            portraits=portraits,
            triggers=TRIGGERS,
            modal_variants=MODAL_VARIANTS,
            error=error,
        )
    finally:
        session.close()


@admin_bp.get("/story/export")
@admin_required(permission="view_dashboard")
def export_story():
    """Export all story events as JSON or YAML download."""
    import io
    from flask import make_response
    fmt = request.args.get("fmt", "json").lower()

    session = SessionLocal()
    try:
        events = (
            session.query(StoryEventDef)
            .order_by(StoryEventDef.level, StoryEventDef.sort_order, StoryEventDef.id)
            .all()
        )
        npcs = {n.key: {"name_fr": n.name_fr, "name_en": n.name_en, "portrait": n.portrait}
                for n in session.query(NpcDef).all()}

        data = {
            "npcs": npcs,
            "story_events": [
                {
                    "id": ev.id,
                    "level": ev.level,
                    "trigger": ev.trigger,
                    "land_key": ev.land_key,
                    "show_once": ev.show_once,
                    "modal_variant": ev.modal_variant,
                    "sort_order": ev.sort_order,
                    "enabled": ev.enabled,
                    "quest_start": ev.quest_start,
                    "pages": ev.pages or [],
                }
                for ev in events
            ],
        }

        if fmt == "yaml":
            content = yaml.dump(data, allow_unicode=True, sort_keys=False,
                                default_flow_style=False)
            resp = make_response(content)
            resp.headers["Content-Type"] = "text/yaml; charset=utf-8"
            resp.headers["Content-Disposition"] = "attachment; filename=story_events.yaml"
        else:
            content = json.dumps(data, ensure_ascii=False, indent=2)
            resp = make_response(content)
            resp.headers["Content-Type"] = "application/json; charset=utf-8"
            resp.headers["Content-Disposition"] = "attachment; filename=story_events.json"

        return resp
    finally:
        session.close()


@admin_bp.post("/story/<ev_id>/delete")
@admin_required(permission="view_dashboard")
def delete_story_event(ev_id: str):
    session = SessionLocal()
    try:
        ev = session.query(StoryEventDef).filter_by(id=ev_id).first()
        if not ev:
            abort(404)
        session.delete(ev)
        session.commit()
        return jsonify({"ok": True})
    finally:
        session.close()


# =============================================================================
# Skills Management
# =============================================================================

SKILL_CATEGORIES = [
    ("resource", "Ressource"),
    ("land",     "Terre"),
    ("craft",    "Artisanat"),
]

BONUS_TYPES = [
    ("double_drop",          "Double drop (%)",             50),
    ("cooldown_reduction",   "Réduction cooldown (s)",      30),
    ("craft_time_reduction", "Réduction temps craft (%)",   50),
    ("instant_craft_chance", "Craft instantané (%)",        30),
    ("xp_bonus",             "Bonus XP (%)",               100),
    ("shard_chance",         "Chance shards (%)",           30),
]


@admin_bp.get("/skills/")
@admin_required(permission="view_dashboard")
def skills_list():
    session = SessionLocal()
    try:
        skills = session.query(SkillDef).order_by(SkillDef.category, SkillDef.key).all()
        # Count players with each skill
        skill_player_counts = {}
        for sk in skills:
            cnt = session.query(PlayerSkill).filter_by(skill_key=sk.key).filter(PlayerSkill.level > 0).count()
            skill_player_counts[sk.key] = cnt
        return render_template("ADMIN_UI/skills_list.html",
                               skills=skills,
                               skill_player_counts=skill_player_counts,
                               categories=SKILL_CATEGORIES)
    finally:
        session.close()


@admin_bp.get("/skills/<key>/edit")
@admin_bp.post("/skills/<key>/edit")
@admin_required(permission="view_dashboard")
def edit_skill(key: str):
    session = SessionLocal()
    try:
        skill = session.query(SkillDef).filter_by(key=key).first()
        if not skill:
            abort(404)
        error = None
        if request.method == "POST":
            skill.name_fr = request.form.get("name_fr", "").strip() or skill.name_fr
            skill.name_en = request.form.get("name_en", "").strip() or skill.name_en
            skill.category = request.form.get("category", skill.category)
            skill.subject_key = request.form.get("subject_key", "").strip() or None
            skill.enabled = request.form.get("enabled") == "on"
            levels_raw = request.form.get("levels_json", "[]")
            try:
                skill.levels = json.loads(levels_raw)
            except json.JSONDecodeError:
                error = "JSON des niveaux invalide."
            if not error:
                session.commit()
                return redirect(url_for("admin.skills_list"))
        return render_template("ADMIN_UI/skill_form.html",
                               skill=skill,
                               categories=SKILL_CATEGORIES,
                               bonus_types=BONUS_TYPES,
                               error=error)
    finally:
        session.close()


@admin_bp.post("/skills/new")
@admin_required(permission="view_dashboard")
def create_skill():
    data = request.get_json() or {}
    key = (data.get("key") or "").strip().lower().replace(" ", "_")
    if not key:
        return jsonify({"ok": False, "error": "Clé requise"}), 400
    if not key.startswith("skill_"):
        key = "skill_" + key
    session = SessionLocal()
    try:
        if session.query(SkillDef).filter_by(key=key).first():
            return jsonify({"ok": False, "error": "Clé déjà utilisée"}), 400
        sk = SkillDef(key=key, name_fr=key, name_en=key,
                      category=data.get("category", "resource"),
                      subject_key=data.get("subject_key") or None,
                      levels=[])
        session.add(sk)
        session.commit()
        return jsonify({"ok": True, "key": key,
                        "redirect": url_for("admin.edit_skill", key=key)})
    finally:
        session.close()


@admin_bp.post("/skills/<key>/delete")
@admin_required(permission="view_dashboard")
def delete_skill(key: str):
    session = SessionLocal()
    try:
        sk = session.query(SkillDef).filter_by(key=key).first()
        if not sk:
            abort(404)
        session.query(PlayerSkill).filter_by(skill_key=key).delete()
        session.delete(sk)
        session.commit()
        return jsonify({"ok": True})
    finally:
        session.close()


@admin_bp.post("/skills/<key>/toggle")
@admin_required(permission="view_dashboard")
def toggle_skill(key: str):
    session = SessionLocal()
    try:
        sk = session.query(SkillDef).filter_by(key=key).first()
        if not sk:
            abort(404)
        sk.enabled = not sk.enabled
        session.commit()
        return jsonify({"ok": True, "enabled": sk.enabled})
    finally:
        session.close()


# =============================================================================
# Tools Management
# =============================================================================

_TOOLS_IMG_DIR = Path(__file__).resolve().parent.parent / "static" / "assets" / "img" / "items" / "tools"
_TOOLS_IMG_URL_BASE = "/static/assets/img/items/tools/"
_ALLOWED_IMG_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _tool_image_path(key: str) -> Path:
    return _TOOLS_IMG_DIR / f"{key}.png"


def _tool_image_url(key: str) -> str | None:
    # Try exact key first (e.g. tool_wooden_axe.png)
    if _tool_image_path(key).exists():
        return f"{_TOOLS_IMG_URL_BASE}{key}.png"
    # Try without tool_ prefix (e.g. wooden_axe.png)
    short = key[5:] if key.startswith("tool_") else key
    short_path = _TOOLS_IMG_DIR / f"{short}.png"
    if short_path.exists():
        return f"{_TOOLS_IMG_URL_BASE}{short}.png"
    return None


def _save_tool_image(file_storage, key: str) -> str:
    """
    Crop & resize uploaded image to square (512×512 PNG).
    Returns the URL path of the saved image.
    Raises ValueError on bad file type.
    """
    from PIL import Image
    import io

    ext = Path(file_storage.filename).suffix.lower()
    if ext not in _ALLOWED_IMG_EXTENSIONS:
        raise ValueError(f"Extension non autorisée : {ext}")

    raw = file_storage.read()
    img = Image.open(io.BytesIO(raw)).convert("RGBA")

    # Square crop (centre)
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top  = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.resize((512, 512), Image.LANCZOS)

    _TOOLS_IMG_DIR.mkdir(parents=True, exist_ok=True)
    dest = _tool_image_path(key)
    img.save(dest, "PNG", optimize=True)
    return f"{_TOOLS_IMG_URL_BASE}{key}.png"


def _get_all_tools(session) -> list:
    """
    Return all tools by merging:
      1. items.yml  — keys starting with tool_  (source of truth for existing tools)
      2. ResourceDef DB — kind='tool' OR key LIKE 'tool_%' (admin-created tools)
      3. i18n translations (fr.yml / en.yml)
    """
    # ── Load items.yml ────────────────────────────────────────────────────────
    items_yml_path = Path(__file__).resolve().parent.parent / "data" / "items.yml"
    yaml_tools: dict = {}
    if items_yml_path.exists():
        with items_yml_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        all_items = raw.get("items", raw)
        yaml_tools = {k: v for k, v in all_items.items()
                      if isinstance(v, dict) and k.startswith("tool_")}

    # ── Load DB rows (kind=tool OR key prefix tool_) ──────────────────────────
    db_rows = (
        session.query(ResourceDef)
        .filter(
            (ResourceDef.kind == "tool") |
            ResourceDef.key.like("tool_%")
        )
        .order_by(ResourceDef.key)
        .all()
    )
    db_by_key = {r.key: r for r in db_rows}

    # ── Load i18n translations ────────────────────────────────────────────────
    translations: dict = {}
    for lang in ("fr", "en"):
        path = Path(__file__).resolve().parent.parent / "i18n" / "translations" / f"{lang}.yml"
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            translations[lang] = data.get("items", {})
        else:
            translations[lang] = {}

    # ── Merge: union of YAML + DB keys ───────────────────────────────────────
    all_keys = sorted(set(list(yaml_tools.keys()) + list(db_by_key.keys())))

    result = []
    for key in all_keys:
        yaml_cfg = yaml_tools.get(key, {})
        db_row   = db_by_key.get(key)
        fr_data  = translations["fr"].get(key) or {}
        en_data  = translations["en"].get(key) or {}

        # Label resolution: i18n > yaml > db
        label_fr = (fr_data.get("label") if isinstance(fr_data, dict) else None) \
                   or yaml_cfg.get("label") \
                   or (db_row.label if db_row and db_row.label and "." not in db_row.label else None) \
                   or key
        label_en = (en_data.get("label") if isinstance(en_data, dict) else None) \
                   or yaml_cfg.get("label", "")

        # Icon: DB > yaml > auto-detect
        icon = (db_row.icon if db_row else None) or yaml_cfg.get("icon")

        # image_url: check actual file on disk (stripping tool_ prefix for filename)
        image_url = _tool_image_url(key)
        # Also try the yaml icon path if file exists
        if not image_url and yaml_cfg.get("icon"):
            image_url = yaml_cfg["icon"]

        result.append({
            "key": key,
            "label_fr": label_fr,
            "label_en": label_en,
            "description_fr": (fr_data.get("description") if isinstance(fr_data, dict) else None)
                               or yaml_cfg.get("description", ""),
            "icon": icon,
            "image_url": image_url,
            "base_sell_price": (db_row.base_sell_price if db_row else None)
                                or yaml_cfg.get("base_sell_price", 0),
            "enabled": (db_row.enabled if db_row else yaml_cfg.get("enabled", True)),
            "in_db": key in db_by_key,
        })
    return result


@admin_bp.get("/tools/")
@admin_required(permission="edit_resources")
def tools_list():
    session = SessionLocal()
    try:
        tools = _get_all_tools(session)
        return render_template("ADMIN_UI/tools_list.html", tools=tools)
    finally:
        session.close()


@admin_bp.get("/tools/print")
@admin_required(permission="edit_resources")
def tools_print():
    session = SessionLocal()
    try:
        tools = _get_all_tools(session)
        return render_template("ADMIN_UI/tools_print.html", tools=tools)
    finally:
        session.close()


@admin_bp.post("/tools/new")
@admin_required(permission="edit_resources")
def create_tool():
    data = request.get_json() or {}
    key = (data.get("key") or "").strip().lower().replace(" ", "_")
    label_fr = (data.get("label_fr") or "").strip()
    label_en = (data.get("label_en") or "").strip()

    if not key:
        return jsonify({"ok": False, "error": "Clé requise"}), 400
    if not label_fr:
        return jsonify({"ok": False, "error": "Nom FR requis"}), 400

    session = SessionLocal()
    try:
        if session.query(ResourceDef).filter_by(key=key).first():
            return jsonify({"ok": False, "error": "Clé déjà utilisée"}), 400

        # Save to DB
        tool = ResourceDef(
            key=key,
            label=f"items.{key}.label",
            kind="tool",
            base_sell_price=0,
            enabled=True,
        )
        session.add(tool)
        session.commit()

        # Save i18n
        _save_item_translations(key, {
            "fr": {"label": label_fr},
            "en": {"label": label_en or label_fr},
        })

        return jsonify({"ok": True, "key": key,
                        "redirect": url_for("admin.edit_tool", key=key)})
    finally:
        session.close()


@admin_bp.get("/tools/<key>/edit")
@admin_bp.post("/tools/<key>/edit")
@admin_required(permission="edit_resources")
def edit_tool(key: str):
    session = SessionLocal()
    try:
        tool = session.query(ResourceDef).filter_by(key=key, kind="tool").first()
        if not tool:
            abort(404)

        translations = _load_item_translations(key)
        error = None
        success = None

        if request.method == "POST":
            action = request.form.get("action", "save")

            # ── Image upload ──────────────────────────────────────────────────
            if action == "upload_image":
                img_file = request.files.get("image")
                if not img_file or not img_file.filename:
                    error = "Aucun fichier sélectionné."
                else:
                    try:
                        url = _save_tool_image(img_file, key)
                        tool.icon = url
                        session.commit()
                        success = f"Image enregistrée ({url})"
                    except ValueError as e:
                        error = str(e)
                    except Exception as e:
                        error = f"Erreur : {e}"

            # ── Save metadata ─────────────────────────────────────────────────
            else:
                label_fr = request.form.get("label_fr", "").strip()
                label_en = request.form.get("label_en", "").strip()
                desc_fr  = request.form.get("desc_fr", "").strip()
                desc_en  = request.form.get("desc_en", "").strip()
                base_sell_price_raw = request.form.get("base_sell_price", "").strip()
                tool.enabled = request.form.get("enabled") == "on"

                if not label_fr:
                    error = "Nom FR requis."
                else:
                    tool.label = f"items.{key}.label"
                    _save_item_translations(key, {
                        "fr": {"label": label_fr, "description": desc_fr or None},
                        "en": {"label": label_en or label_fr, "description": desc_en or None},
                    })
                    if base_sell_price_raw.isdigit():
                        tool.base_sell_price = int(base_sell_price_raw)
                    session.commit()
                    if not error:
                        return redirect(url_for("admin.tools_list"))

        # Reload translations after potential save
        translations = _load_item_translations(key)
        image_url = _tool_image_url(key)
        return render_template("ADMIN_UI/tool_form.html",
                               tool=tool, key=key,
                               translations=translations,
                               image_url=image_url,
                               error=error, success=success)
    finally:
        session.close()


@admin_bp.post("/tools/<key>/delete")
@admin_required(permission="edit_resources")
def delete_tool(key: str):
    session = SessionLocal()
    try:
        tool = session.query(ResourceDef).filter_by(key=key, kind="tool").first()
        if not tool:
            abort(404)
        session.delete(tool)
        session.commit()
        # Optionally remove image
        img = _tool_image_path(key)
        if img.exists():
            img.unlink()
        return jsonify({"ok": True})
    finally:
        session.close()
