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
