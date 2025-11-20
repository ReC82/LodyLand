# app/admin/__init__.py
from functools import wraps
import re

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
# Lands YAML helpers
# -------------------------------------------------------------------

LANDS_YAML_PATH = Path(__file__).resolve().parents[1] / "data" / "lands.yml"


def load_lands_yaml() -> dict:
    """Load lands.yml and return a mapping {slug: config_dict}."""
    if not LANDS_YAML_PATH.exists():
        return {}

    with LANDS_YAML_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # Ton format actuel est déjà { "forest": {...}, "beach": {...}, ... }
    if isinstance(data, dict):
        return data

    return {}


def save_lands_yaml(mapping: dict) -> None:
    """Write mapping {slug: config_dict} back to lands.yml with a clean layout."""
    LANDS_YAML_PATH.parent.mkdir(parents=True, exist_ok=True)

    # On garde juste l’ordre trié par slug pour rester stable visuellement
    ordered = {slug: mapping[slug] for slug in sorted(mapping.keys())}

    yaml_str = yaml.safe_dump(
        ordered,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        indent=2,
    )

    with LANDS_YAML_PATH.open("w", encoding="utf-8") as f:
        f.write(yaml_str)


# -------------------------------------------------------------------
# Resources YAML helpers
# -------------------------------------------------------------------

RESOURCES_YAML_PATH = Path(__file__).resolve().parents[1] / "data" / "resources.yml"


def load_resources_yaml() -> dict:
    """
    Charge resources.yml et retourne un dict {key: config_dict}.

    Formats supportés :
    1) format liste (recommandé) :
       resources:
         - key: wood
           label: "Bois"
           ...
         - key: stone
           ...

    2) format mapping :
       wood:
         label: "Bois"
         ...
       stone:
         ...

    Dans les deux cas, on renvoie un mapping {key: cfg}.
    """
    if not RESOURCES_YAML_PATH.exists():
        return {}

    with RESOURCES_YAML_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # Cas 1 : { "resources": [ {...}, {...}, ... ] }
    if isinstance(data, dict) and isinstance(data.get("resources"), list):
        mapping: dict[str, dict] = {}
        for res in data["resources"]:
            if not isinstance(res, dict):
                continue
            key = (res.get("key") or "").strip()
            if not key:
                continue
            mapping[key] = res
        return mapping

    # Cas 2 : déjà un mapping { "wood": {...}, ... }
    if isinstance(data, dict):
        return data

    return {}


def save_resources_yaml(mapping: dict) -> None:
    """
    Écrit le mapping dans resources.yml avec un layout propre.

    mapping attendu :
      { "wood": {...}, "stone": {...}, ... }

    Format fichier :
      resources:
        - key: wood
          ...
        - key: stone
          ...
    """
    RESOURCES_YAML_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Tri par key pour garder un ordre stable
    resources_list: list[dict] = []
    for key in sorted(mapping.keys()):
        cfg = mapping[key] or {}
        if not isinstance(cfg, dict):
            cfg = {}
        cfg = dict(cfg)  # shallow copy
        cfg["key"] = key
        resources_list.append(cfg)

    wrapper = {"resources": resources_list}

    yaml_str = yaml.safe_dump(
        wrapper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        indent=2,
    )

    # Petite aération visuelle : ligne vide avant chaque élément de liste
    yaml_str = yaml_str.replace("\n- ", "\n\n- ")

    with RESOURCES_YAML_PATH.open("w", encoding="utf-8") as f:
        f.write(yaml_str)


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



def save_cards_yaml(mapping: dict) -> None:
    """Write the cards mapping back to cards.yml with a stable, readable layout.

    Expected mapping:
      { "wood_boost_1": {...}, "branch_boost_1": {...}, ... }

    File format:
      cards:
        - key: wood_boost_1
          ...
        - key: branch_boost_1
          ...
    """
    CARDS_YAML_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Build a list of card dicts, each containing its "key" field.
    # We sort by (type, key) to keep a logical, stable order.
    cards_list: list[dict] = []

    def sort_key(item: tuple[str, dict]) -> tuple[str, str]:
        k, cfg = item
        if not isinstance(cfg, dict):
            cfg = {}
        ctype = (cfg.get("type") or "").lower()
        return (ctype, k)

    for key, card_cfg in sorted(mapping.items(), key=sort_key):
        if not isinstance(card_cfg, dict):
            card_cfg = {}

        # Ensure "key" field is present and matches the mapping key
        card_cfg = dict(card_cfg)  # shallow copy
        card_cfg["key"] = key

        cards_list.append(card_cfg)

    wrapper = {"cards": cards_list}

    # Dump once to a string so we can post-process for visual tweaks
    yaml_str = yaml.safe_dump(
        wrapper,
        allow_unicode=True,
        sort_keys=False,          # keep "cards" first
        default_flow_style=False, # block style (multi-line)
        indent=2,                 # 2 spaces indentation
    )

    # Add a blank line between each list item for readability:
    #   - key: ...
    # devient:
    #   (blank line)
    #   - key: ...
    #
    # This is a small cosmetic hack over PyYAML output.
    yaml_str = yaml_str.replace("\n- ", "\n\n- ")

    with CARDS_YAML_PATH.open("w", encoding="utf-8") as f:
        f.write(yaml_str)



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

@admin_bp.route("/cards/<card_key>/edit", methods=["GET", "POST"])
@admin_required
def card_edit(card_key: str):
    """Edit a single card from cards.yml by its key."""
    card_key = (card_key or "").strip()
    if not card_key:
        abort(404)

    # Load mapping {key: cfg}
    mapping = load_cards_yaml()
    card_cfg = mapping.get(card_key)
    if card_cfg is None or not isinstance(card_cfg, dict):
        abort(404)

    errors: list[str] = []
    saved = False

    # Prepare default advanced YAML texts from current config (for GET)
    def dump_yaml_block(value) -> str:
        """Return a compact YAML block for textarea display."""
        if value is None:
            return ""
        try:
            txt = yaml.safe_dump(
                value,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
                indent=2,
            ).strip()
        except Exception:
            return ""
        return txt

    # Defaults from current card config
    gameplay_text_default = dump_yaml_block(card_cfg.get("gameplay"))
    prices_text_default = dump_yaml_block(card_cfg.get("prices"))
    shop_text_default = dump_yaml_block(card_cfg.get("shop"))
    buy_rules_text_default = dump_yaml_block(card_cfg.get("buy_rules"))

    # If POST, use form values (and re-validate)
    if request.method == "POST":
        # ----- Simple scalar fields -----
        label = (request.form.get("label") or "").strip()
        categorie = (request.form.get("categorie") or "").strip()
        description = (request.form.get("description") or "").strip()
        ctype = (request.form.get("type") or "").strip()
        rarity = (request.form.get("rarity") or "").strip()
        icon = (request.form.get("icon") or "").strip()
        enabled_str = request.form.get("enabled")  # "on" or None

        # ----- Advanced YAML text fields -----
        gameplay_text = (request.form.get("gameplay") or "").strip()
        prices_text = (request.form.get("prices") or "").strip()
        shop_text = (request.form.get("shop") or "").strip()
        buy_rules_text = (request.form.get("buy_rules") or "").strip()

        # Basic required validation
        if not label:
            errors.append("Le champ 'Label' est requis.")
        if not ctype:
            errors.append("Le champ 'Type' est requis.")
        # (Tu peux renforcer les règles ici si tu veux)

        # ----- Parse advanced YAML blocks -----
        parsed_gameplay = card_cfg.get("gameplay")
        parsed_prices = card_cfg.get("prices")
        parsed_shop = card_cfg.get("shop")
        parsed_buy_rules = card_cfg.get("buy_rules")

        def parse_yaml_field(text: str, field_name: str):
            """Parse YAML from textarea, return (value, error_msg_or_None)."""
            if not text:
                return None, None  # empty => remove field
            try:
                val = yaml.safe_load(text)
            except yaml.YAMLError as exc:
                return None, f"YAML invalide dans '{field_name}': {exc}"
            return val, None

        # gameplay
        val, err = parse_yaml_field(gameplay_text, "gameplay")
        if err:
            errors.append(err)
        else:
            parsed_gameplay = val

        # prices
        val, err = parse_yaml_field(prices_text, "prices")
        if err:
            errors.append(err)
        else:
            parsed_prices = val

        # shop
        val, err = parse_yaml_field(shop_text, "shop")
        if err:
            errors.append(err)
        else:
            parsed_shop = val

        # buy_rules
        val, err = parse_yaml_field(buy_rules_text, "buy_rules")
        if err:
            errors.append(err)
        else:
            parsed_buy_rules = val

        if not errors:
            # ----- Apply changes to card config -----
            updated = dict(card_cfg)

            # Scalar fields
            updated["key"] = card_key
            updated["label"] = label
            if categorie:
                updated["categorie"] = categorie
            else:
                updated.pop("categorie", None)

            if description:
                updated["description"] = description
            else:
                updated.pop("description", None)

            if ctype:
                updated["type"] = ctype
            else:
                updated.pop("type", None)

            if rarity:
                updated["rarity"] = rarity
            else:
                updated.pop("rarity", None)

            if icon:
                updated["icon"] = icon
            else:
                updated.pop("icon", None)

            updated["enabled"] = bool(enabled_str)

            # Advanced YAML fields: only keep if not None
            if parsed_gameplay is not None:
                updated["gameplay"] = parsed_gameplay
            else:
                updated.pop("gameplay", None)

            if parsed_prices is not None:
                updated["prices"] = parsed_prices
            else:
                updated.pop("prices", None)

            if parsed_shop is not None:
                updated["shop"] = parsed_shop
            else:
                updated.pop("shop", None)

            if parsed_buy_rules is not None:
                updated["buy_rules"] = parsed_buy_rules
            else:
                updated.pop("buy_rules", None)

            # Save in mapping + file
            mapping[card_key] = updated
            save_cards_yaml(mapping)

            card_cfg = updated
            saved = True

            # Après sauvegarde, on veut réafficher le YAML "propre"
            gameplay_text_default = dump_yaml_block(card_cfg.get("gameplay"))
            prices_text_default = dump_yaml_block(card_cfg.get("prices"))
            shop_text_default = dump_yaml_block(card_cfg.get("shop"))
            buy_rules_text_default = dump_yaml_block(card_cfg.get("buy_rules"))

    # GET initial, ou POST avec erreurs / succès
    return render_template(
        "ADMIN_UI/card_edit.html",
        card_key=card_key,
        card=card_cfg,
        errors=errors,
        saved=saved,
        gameplay_text=gameplay_text_default,
        prices_text=prices_text_default,
        shop_text=shop_text_default,
        buy_rules_text=buy_rules_text_default,
    )

@admin_bp.get("/resources")
@admin_required
def resources_list():
    """
    Liste toutes les ressources depuis resources.yml + statut de synchro DB.
    """
    yaml_data = load_resources_yaml()  # {key: cfg}

    session = SessionLocal()
    try:
        db_resources = session.query(ResourceDef).all()
        db_by_key = {r.key: r for r in db_resources}
    finally:
        session.close()

    resources_for_view: list[dict] = []

    for key, cfg in sorted(yaml_data.items(), key=lambda item: item[0]):
        if not isinstance(cfg, dict):
            cfg = {}

        label = (cfg.get("label") or key).strip()
        icon = (cfg.get("icon") or "").strip()
        unlock_min_level = cfg.get("unlock_min_level", 0)
        base_cooldown = cfg.get("base_cooldown", 0.0)
        base_sell_price = cfg.get("base_sell_price", 0)
        enabled = cfg.get("enabled", True)

        in_db = key in db_by_key

        resources_for_view.append(
            {
                "key": key,
                "label": label,
                "icon": icon,
                "unlock_min_level": unlock_min_level,
                "base_cooldown": base_cooldown,
                "base_sell_price": base_sell_price,
                "enabled": bool(enabled),
                "in_db": in_db,
            }
        )

    db_only_resources = [r for r in db_resources if r.key not in yaml_data]

    return render_template(
        "ADMIN_UI/resources_list.html",
        resources=resources_for_view,
        db_only_resources=db_only_resources,
        yaml_path=str(RESOURCES_YAML_PATH),
    )

@admin_bp.route("/resources/<res_key>/edit", methods=["GET", "POST"])
@admin_required
def resource_edit(res_key: str):
    """Éditer une ressource dans resources.yml via son key."""
    res_key = (res_key or "").strip()
    if not res_key:
        abort(404)

    mapping = load_resources_yaml()
    res_cfg = mapping.get(res_key)
    if res_cfg is None or not isinstance(res_cfg, dict):
        abort(404)

    errors: list[str] = []
    saved = False

    # Petit helper pour pré-remplir le YAML dans le textarea
    def dump_yaml_block(value) -> str:
        if value is None:
            return ""
        try:
            txt = yaml.safe_dump(
                value,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
                indent=2,
            ).strip()
        except Exception:
            return ""
        return txt

    # Valeur par défaut pour unlock_rules (si tu en utilises)
    unlock_rules_text_default = dump_yaml_block(res_cfg.get("unlock_rules"))

    if request.method == "POST":
        # Champs simples
        label = (request.form.get("label") or "").strip()
        description = (request.form.get("description") or "").strip()
        icon = (request.form.get("icon") or "").strip()
        unlock_min_level_str = (request.form.get("unlock_min_level") or "").strip()
        base_cooldown_str = (request.form.get("base_cooldown") or "").strip()
        base_sell_price_str = (request.form.get("base_sell_price") or "").strip()
        enabled_str = request.form.get("enabled")  # "on" ou None

        # Champ YAML avancé
        unlock_rules_text = (request.form.get("unlock_rules") or "").strip()

        # Validation basique
        if not label:
            errors.append("Le champ 'Label' est requis.")

        # Conversion numérique
        unlock_min_level = res_cfg.get("unlock_min_level", 0)
        base_cooldown = res_cfg.get("base_cooldown", 0.0)
        base_sell_price = res_cfg.get("base_sell_price", 0)

        if unlock_min_level_str:
            try:
                unlock_min_level = int(unlock_min_level_str)
            except ValueError:
                errors.append("unlock_min_level doit être un entier.")

        if base_cooldown_str:
            try:
                base_cooldown = float(base_cooldown_str)
            except ValueError:
                errors.append("base_cooldown doit être un nombre (float).")

        if base_sell_price_str:
            try:
                base_sell_price = int(base_sell_price_str)
            except ValueError:
                errors.append("base_sell_price doit être un entier.")

        # Parse YAML unlock_rules
        parsed_unlock_rules = res_cfg.get("unlock_rules")

        def parse_yaml_field(text: str, field_name: str):
            if not text:
                return None, None  # vide => supprime la clé
            try:
                val = yaml.safe_load(text)
            except yaml.YAMLError as exc:
                return None, f"YAML invalide dans '{field_name}': {exc}"
            return val, None

        val, err = parse_yaml_field(unlock_rules_text, "unlock_rules")
        if err:
            errors.append(err)
        else:
            parsed_unlock_rules = val

        if not errors:
            # Appliquer les changements
            updated = dict(res_cfg)

            updated["key"] = res_key
            updated["label"] = label

            if description:
                updated["description"] = description
            else:
                updated.pop("description", None)

            if icon:
                updated["icon"] = icon
            else:
                updated.pop("icon", None)

            updated["unlock_min_level"] = unlock_min_level
            updated["base_cooldown"] = base_cooldown
            updated["base_sell_price"] = base_sell_price
            updated["enabled"] = bool(enabled_str)

            # unlock_rules
            if parsed_unlock_rules is not None:
                updated["unlock_rules"] = parsed_unlock_rules
            else:
                updated.pop("unlock_rules", None)

            # Sauvegarde
            mapping[res_key] = updated
            save_resources_yaml(mapping)

            res_cfg = updated
            saved = True
            unlock_rules_text_default = dump_yaml_block(res_cfg.get("unlock_rules"))

    return render_template(
        "ADMIN_UI/resource_edit.html",
        res_key=res_key,
        res=res_cfg,
        errors=errors,
        saved=saved,
        unlock_rules_text=unlock_rules_text_default,
    )
    
@admin_bp.route("/resources/new", methods=["GET", "POST"])
@admin_required
def resource_create():
    """Créer une nouvelle ressource dans resources.yml."""
    mapping = load_resources_yaml()  # {key: cfg}
    errors: list[str] = []
    saved = False

    # Valeurs par défaut pour GET / ou POST avec erreur
    form_defaults = {
        "key": "",
        "label": "",
        "description": "",
        "icon": "",
        "unlock_min_level": "0",
        "base_cooldown": "10.0",
        "base_sell_price": "1",
        "enabled": True,
    }

    if request.method == "POST":
        key = (request.form.get("key") or "").strip()
        label = (request.form.get("label") or "").strip()
        description = (request.form.get("description") or "").strip()
        icon = (request.form.get("icon") or "").strip()
        unlock_min_level_str = (request.form.get("unlock_min_level") or "").strip()
        base_cooldown_str = (request.form.get("base_cooldown") or "").strip()
        base_sell_price_str = (request.form.get("base_sell_price") or "").strip()
        enabled_str = request.form.get("enabled")  # "on" ou None

        # On garde ce que l'utilisateur a saisi
        form_defaults.update(
            {
                "key": key,
                "label": label,
                "description": description,
                "icon": icon,
                "unlock_min_level": unlock_min_level_str or "0",
                "base_cooldown": base_cooldown_str or "10.0",
                "base_sell_price": base_sell_price_str or "1",
                "enabled": bool(enabled_str),
            }
        )

        # ---- Validation de la key ----
        if not key:
            errors.append("Le champ 'Key' est requis.")
        else:
            # On impose un format simple : minuscules, chiffres, underscore (wood, branch, magic_stone...)
            if not re.match(r"^[a-z0-9_]+$", key):
                errors.append(
                    "La key doit contenir uniquement des lettres minuscules, "
                    "chiffres et underscores (ex: wood, magic_stone)."
                )
            if key in mapping:
                errors.append(f"Une ressource avec la key '{key}' existe déjà.")

        if not label:
            errors.append("Le champ 'Label' est requis.")

        # ---- Conversion numérique ----
        unlock_min_level = 0
        base_cooldown = 10.0
        base_sell_price = 1

        if unlock_min_level_str:
            try:
                unlock_min_level = int(unlock_min_level_str)
            except ValueError:
                errors.append("unlock_min_level doit être un entier.")

        if base_cooldown_str:
            try:
                base_cooldown = float(base_cooldown_str)
            except ValueError:
                errors.append("base_cooldown doit être un nombre (float).")

        if base_sell_price_str:
            try:
                base_sell_price = int(base_sell_price_str)
            except ValueError:
                errors.append("base_sell_price doit être un entier.")

        if not errors:
            # ---- Construction de la config YAML minimale ----
            cfg = dict(mapping.get(key) or {})

            cfg["key"] = key
            cfg["label"] = label

            if description:
                cfg["description"] = description
            else:
                cfg.pop("description", None)

            # Si pas d'icon fournie, on met un chemin par défaut cohérent
            cfg["icon"] = icon or f"/static/assets/img/resources/{key}.png"

            cfg["unlock_min_level"] = unlock_min_level
            cfg["base_cooldown"] = base_cooldown
            cfg["base_sell_price"] = base_sell_price
            cfg["enabled"] = bool(enabled_str)

            # Pas d'unlock_rules par défaut (tu pourras en ajouter dans l'édition)
            cfg.pop("unlock_rules", None)

            mapping[key] = cfg
            save_resources_yaml(mapping)
            saved = True

            # Redirection vers la fiche d'édition détaillée
            return redirect(url_for("admin.resource_edit", res_key=key))

    # GET initial ou POST avec erreurs
    return render_template(
        "ADMIN_UI/resource_create.html",
        errors=errors,
        form=form_defaults,
        saved=saved,
    )


@admin_bp.get("/lands")
@admin_required
def lands_list():
    """
    Liste toutes les lands depuis lands.yml (YAML only).
    """
    yaml_data = load_lands_yaml()  # {slug: cfg}

    lands_for_view: list[dict] = []

    for slug, cfg in sorted(yaml_data.items(), key=lambda item: item[0]):
        if not isinstance(cfg, dict):
            cfg = {}

        label_fr = (cfg.get("label_fr") or "").strip()
        label_en = (cfg.get("label_en") or "").strip()
        starting_land = bool(cfg.get("starting_land", False))
        slots = cfg.get("slots", 0)
        slot_icon = (cfg.get("slot_icon") or "").strip()
        logo = (cfg.get("logo") or "").strip()
        base_cost = cfg.get("additional_slot_base_cost_diams", 0)
        multiplier = cfg.get("additional_slot_cost_multiplier", 1.0)

        lands_for_view.append(
            {
                "slug": slug,  # "forest", "beach", ...
                "label_fr": label_fr,
                "label_en": label_en,
                "starting_land": starting_land,
                "slots": slots,
                "slot_icon": slot_icon,
                "logo": logo,
                "base_cost": base_cost,
                "multiplier": multiplier,
            }
        )

    return render_template(
        "ADMIN_UI/lands_list.html",
        lands=lands_for_view,
        yaml_path=str(LANDS_YAML_PATH),
    )

@admin_bp.route("/lands/<land_key>/edit", methods=["GET", "POST"])
@admin_required
def land_edit(land_key: str):
    """Edit a land entry in lands.yml by its slug (forest, beach, ...)."""
    land_key = (land_key or "").strip()
    if not land_key:
        abort(404)

    mapping = load_lands_yaml()
    land_cfg = mapping.get(land_key)
    if land_cfg is None or not isinstance(land_cfg, dict):
        abort(404)

    errors: list[str] = []
    saved = False

    if request.method == "POST":
        label_fr = (request.form.get("label_fr") or "").strip()
        label_en = (request.form.get("label_en") or "").strip()
        starting_land_str = request.form.get("starting_land")  # "on" ou None
        slots_str = (request.form.get("slots") or "").strip()
        slot_icon = (request.form.get("slot_icon") or "").strip()
        logo = (request.form.get("logo") or "").strip()
        base_cost_str = (request.form.get("base_cost") or "").strip()
        multiplier_str = (request.form.get("multiplier") or "").strip()

        if not label_fr and not label_en:
            errors.append("Au moins un label (FR ou EN) est requis.")

        slots = land_cfg.get("slots", 0)
        base_cost = land_cfg.get("additional_slot_base_cost_diams", 0)
        multiplier = land_cfg.get("additional_slot_cost_multiplier", 1.0)

        if slots_str:
            try:
                slots = int(slots_str)
            except ValueError:
                errors.append("slots doit être un entier.")

        if base_cost_str:
            try:
                base_cost = int(base_cost_str)
            except ValueError:
                errors.append("additional_slot_base_cost_diams doit être un entier.")

        if multiplier_str:
            try:
                multiplier = float(multiplier_str)
            except ValueError:
                errors.append("additional_slot_cost_multiplier doit être un nombre (float).")

        if not errors:
            updated = dict(land_cfg)  # copy existing config

            # ⚠️ On ne touche PAS à updated["key"] (ex: "land_forest")
            # on ne la remplace pas par le slug !

            if label_fr:
                updated["label_fr"] = label_fr
            else:
                updated.pop("label_fr", None)

            if label_en:
                updated["label_en"] = label_en
            else:
                updated.pop("label_en", None)

            updated["starting_land"] = bool(starting_land_str)
            updated["slots"] = slots

            if slot_icon:
                updated["slot_icon"] = slot_icon
            else:
                updated.pop("slot_icon", None)

            if logo:
                updated["logo"] = logo
            else:
                updated.pop("logo", None)

            updated["additional_slot_base_cost_diams"] = base_cost
            updated["additional_slot_cost_multiplier"] = multiplier

            mapping[land_key] = updated
            save_lands_yaml(mapping)

            land_cfg = updated
            saved = True

    return render_template(
        "ADMIN_UI/land_edit.html",
        land_key=land_key,
        land=land_cfg,
        errors=errors,
        saved=saved,
    )

@admin_bp.route("/lands/new", methods=["GET", "POST"])
@admin_required
def land_create():
    """Créer un nouveau land dans lands.yml à partir d'un slug."""
    mapping = load_lands_yaml()  # {slug: cfg}
    errors: list[str] = []
    saved = False

    # Valeurs par défaut pour le GET / ou en cas d'erreur POST
    form_defaults = {
        "slug": "",
        "label_fr": "",
        "label_en": "",
        "starting_land": False,
        "slots": "8",
        "slot_icon": "",
        "logo": "",
        "base_cost": "10",
        "multiplier": "1.5",
    }

    if request.method == "POST":
        slug = (request.form.get("slug") or "").strip()
        label_fr = (request.form.get("label_fr") or "").strip()
        label_en = (request.form.get("label_en") or "").strip()
        starting_land_str = request.form.get("starting_land")
        slots_str = (request.form.get("slots") or "").strip()
        slot_icon = (request.form.get("slot_icon") or "").strip()
        logo = (request.form.get("logo") or "").strip()
        base_cost_str = (request.form.get("base_cost") or "").strip()
        multiplier_str = (request.form.get("multiplier") or "").strip()

        # On garde ce que l'utilisateur vient d'encoder pour ré-affichage en cas d'erreur
        form_defaults.update(
            {
                "slug": slug,
                "label_fr": label_fr,
                "label_en": label_en,
                "starting_land": bool(starting_land_str),
                "slots": slots_str or "8",
                "slot_icon": slot_icon,
                "logo": logo,
                "base_cost": base_cost_str or "10",
                "multiplier": multiplier_str or "1.5",
            }
        )

        # ---- Validation slug ----
        if not slug:
            errors.append("Le champ 'Slug' est requis.")
        else:
            # slug en minuscules, lettres, chiffres, underscore
            if not re.match(r"^[a-z0-9_]+$", slug):
                errors.append(
                    "Le slug doit contenir uniquement des lettres minuscules, "
                    "chiffres et underscores (ex: forest, desert_2)."
                )
            if slug in mapping:
                errors.append(f"Un land avec le slug '{slug}' existe déjà.")

        # Au moins un label
        if not label_fr and not label_en:
            errors.append("Au moins un label (FR ou EN) est requis.")

        # ---- Conversion des valeurs numériques ----
        slots = 8
        base_cost = 10
        multiplier = 1.5

        if slots_str:
            try:
                slots = int(slots_str)
            except ValueError:
                errors.append("slots doit être un entier.")
        if base_cost_str:
            try:
                base_cost = int(base_cost_str)
            except ValueError:
                errors.append("base_cost doit être un entier (diams).")
        if multiplier_str:
            try:
                multiplier = float(multiplier_str)
            except ValueError:
                errors.append("multiplier doit être un nombre (float).")

        if not errors:
            # ---- Construction de la config YAML minimale pour le land ----
            key_internal = f"land_{slug}"

            cfg = dict(mapping.get(slug) or {})
            cfg["key"] = key_internal
            cfg["label_fr"] = label_fr or label_en
            cfg["label_en"] = label_en or label_fr
            cfg["starting_land"] = bool(starting_land_str)
            cfg["slots"] = slots

            cfg["slot_icon"] = (
                slot_icon or f"static/assets/img/lands/{slug}_slot.png"
            )
            cfg["logo"] = logo or f"static/assets/img/lands/{slug}_logo.png"

            cfg["additional_slot_base_cost_diams"] = base_cost
            cfg["additional_slot_cost_multiplier"] = multiplier

            cfg.setdefault("tools", {})

            # Sauvegarde du land dans lands.yml
            mapping[slug] = cfg
            save_lands_yaml(mapping)

            # ---- Création automatique de la carte d'accès land_<slug> ----
            try:
                from . import load_cards_yaml, save_cards_yaml  # si helpers dans ce même module
            except ImportError:
                # Si import circulaire, les helpers sont déjà dans ce fichier,
                # donc on peut les appeler directement sans re-import.
                pass

            cards_mapping = load_cards_yaml()
            card_key = key_internal  # ex: "land_mountain"

            if card_key not in cards_mapping:
                # On crée une carte d'accès minimale,
                # que tu pourras affiner ensuite dans l'admin "Cartes".
                card_label = f"Accès {label_fr or label_en or slug.capitalize()}"
                card_description = (
                    f"Débloque le land {label_fr or label_en or slug}."
                )

                card_cfg = {
                    "key": card_key,
                    "categorie": "land",
                    "label": card_label,
                    "description": card_description,
                    "icon": f"/static/assets/img/cards/{card_key}.png",
                    "type": "land_access",
                    "rarity": "uncommon",
                    "gameplay": {
                        "target_land": slug
                    },
                    # Prix par défaut très simple : gratuit pour l'instant.
                    # Tu pourras ajuster dans l'admin des cartes.
                    "prices": [
                        {"coins": 0}
                    ],
                    "shop": {
                        "tradable": False,
                        "giftable": True,
                        "max_owned": 1,
                        "enabled": True,
                    },
                    # "buy_rules": {}  # tu pourras en ajouter si besoin
                }

                cards_mapping[card_key] = card_cfg
                save_cards_yaml(cards_mapping)

            saved = True

            # Redirection vers l'écran d'édition détaillée du land
            return redirect(url_for("admin.land_edit", land_key=slug))


    # GET initial ou POST avec erreurs
    return render_template(
        "ADMIN_UI/land_create.html",
        errors=errors,
        form=form_defaults,
        saved=saved,
    )
