# app/frontend.py
"""
Frontend routes for LodyLand:
- Public pages (home, login, register)
- Lands selection and individual land pages
- Village pages (hub, quests, shop, trades, market)
- Shop pages (main shop)
- Inventory page
"""

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    make_response,
    g,
)
from werkzeug.security import generate_password_hash, check_password_hash

from sqlalchemy import select, func 
from functools import wraps

from .auth import get_current_player
from .db import SessionLocal
from .models import (
    Player,
    Account,
    PlayerCard,
    CardDef,
    LandSlotState,
    PlayerQuest, 
)
from .routes.api_players import _ensure_starting_land_card
from .lands import get_land_def, get_player_land_state

import datetime as dt
from datetime import datetime, timezone
from .village_shop import get_active_village_offers

frontend_bp = Blueprint("frontend", __name__)

# ---------------------------------------------------------------------------
# Helper / decorator: login_required
# ---------------------------------------------------------------------------


def login_required(view_fn):
    """
    Décorateur pour les pages de jeu qui exigent un joueur connecté.

    - Ouvre une session DB
    - Cherche le player via le cookie (get_current_player)
    - Si pas de player -> redirect vers home
    - Si OK -> stocke player + session dans flask.g
    - Appelle la vue sans lui passer d'arguments supplémentaires.
    """

    @wraps(view_fn)
    def wrapper(*args, **kwargs):
        session = SessionLocal()
        try:
            player = get_current_player(session)
            print("[login_required] player =", player)

            if not player:
                print("[login_required] redirect to home")
                session.close()
                return redirect(url_for("frontend.home"))

            # Stocker pour usage dans la vue
            g.player = player
            g.db_session = session

            # La vue ne reçoit pas player/session en arguments
            response = view_fn(*args, **kwargs)
            return response
        finally:
            try:
                session.close()
            except Exception:
                pass

    return wrapper


# ---------------------------------------------------------------------------
# Helpers: validation
# ---------------------------------------------------------------------------


def validate_email(email: str) -> bool:
    """Very basic email format validation."""
    if not email:
        return False
    email = email.strip()
    return "@" in email and "." in email and " " not in email


def validate_password(password: str) -> list[str]:
    """
    Validate password complexity.

    Simple rules for now:
    - minimum 8 characters
    - at least 1 digit
    - at least 1 letter
    """
    errors: list[str] = []
    if len(password) < 8:
        errors.append("Le mot de passe doit contenir au moins 8 caractères.")
    if not any(c.isdigit() for c in password):
        errors.append("Le mot de passe doit contenir au moins un chiffre.")
    if not any(c.isalpha() for c in password):
        errors.append("Le mot de passe doit contenir au moins une lettre.")
    return errors


# ---------------------------------------------------------------------------
# Lands config helper
# ---------------------------------------------------------------------------


def get_land_slots(slug: str, default: int = 6) -> int:
    """
    Return the number of slots for a given land based on lands.yml.

    slug: "forest", "beach", "village", ...
    default: fallback value if config is missing or invalid.
    """
    conf = get_land_def(slug)  # reads app/data/lands.yml via lands.py
    if not isinstance(conf, dict):
        # Unknown land → use default value
        return default

    try:
        return int(conf.get("slots", default))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Home / Play / Shop
# ---------------------------------------------------------------------------


@frontend_bp.route("/")
def home():
    """
    Public home page.

    If the player is already logged in (cookie present), redirect to forest land.
    """
    session = SessionLocal()
    try:
        player = get_current_player(session)
    finally:
        session.close()

    if player is not None:
        # Player already logged in → send to forest land
        return redirect(url_for("frontend.land_page", slug="forest"))

    return render_template("home.html")


@frontend_bp.get("/play")
def play_redirect():
    """Compatibility route: /play simply redirects to home."""
    return redirect(url_for("frontend.home"))


@frontend_bp.route("/shop")
@login_required
def shop():
    """
    Main shop page (resource selling + card shop).
    Le contenu est surtout géré côté JS.
    """
    # player = g.player  # si tu veux l'utiliser dans le template plus tard
    return render_template("GAME_UI/shop/index.html")


# ---------------------------------------------------------------------------
# Lands selection + individual lands
# ---------------------------------------------------------------------------


@frontend_bp.get("/lands")
@login_required
def lands_select():
    """
    Land selection screen.

    Montre UNIQUEMENT les lands débloqués pour le joueur courant,
    en utilisant les cartes "land_*" et les defs de lands.yml
    (pour récupérer slot_icon + tags).
    """
    player = g.player
    session = g.db_session

    # 1) Clés de cartes land_* possédées par le joueur
    owned_land_rows = (
        session.query(PlayerCard.card_key)
        .filter(
            PlayerCard.player_id == player.id,
            PlayerCard.card_key.like("land_%"),
            PlayerCard.qty > 0,
        )
        .all()
    )
    owned_keys = {key for (key,) in owned_land_rows}

    # 2) Toutes les CardDef de type land_* (enabled)
    land_cards = (
        session.query(CardDef)
        .filter(CardDef.key.like("land_%"), CardDef.enabled == True)
        .order_by(CardDef.key.asc())
        .all()
    )

    def make_price_text(cd: CardDef | None) -> str:
        """Build a human-readable price string for a land card."""
        if not cd:
            return ""

        shop_cfg = cd.shop or {}
        prices = shop_cfg.get("prices") or []
        if not prices:
            return "Gratuit"

        first = prices[0] or {}
        parts: list[str] = []

        coins = first.get("coins", 0)
        diams = first.get("diams", 0)
        res_costs: dict = first.get("resources", {}) or {}

        if coins:
            parts.append(f"{coins} 🪙")
        if diams:
            parts.append(f"{diams} 💎")

        for res_key, qty in res_costs.items():
            parts.append(f"{qty} {res_key}")

        if not parts:
            return "Gratuit"

        return " + ".join(parts)

    EMOJI_BY_SLUG = {
        "forest": "🌲",
        "beach": "🏝️",
        "lake": "🏞️",
        "mountain": "⛰️",
        "village": "🏘️",
    }

    all_lands: list[dict] = []

    for cd in land_cards:
        # key = "land_forest" -> slug = "forest"
        slug = cd.key[len("land_") :]

        # URL = route générique /land/<slug>
        try:
            land_url = url_for("frontend.land_page", slug=slug)
            has_route = True
        except Exception:
            land_url = None
            has_route = False

        # 🔹 Conf dans lands.yml pour slot_icon + tags
        conf = get_land_def(slug) or {}  # app/lands.py 
        slot_icon = conf.get("slot_icon")
        tags = conf.get("tags") or []
        is_special = "specials" in tags

        all_lands.append(
            {
                "key": slug,
                "title": cd.card_label or slug.capitalize(),
                "emoji": EMOJI_BY_SLUG.get(slug, "❓"),
                "desc": cd.card_description or "",
                "url": land_url,
                "has_route": has_route,
                "unlocked": cd.key in owned_keys,
                "price_text": make_price_text(cd),
                "slot_icon": slot_icon,
                "is_special": is_special,
            }
        )

    # ✅ On ne garde que les lands débloqués + qui ont une route
    unlocked_lands = [
        l for l in all_lands if l["unlocked"] and l["has_route"]
    ]

    normal_lands = [l for l in unlocked_lands if not l["is_special"]]
    special_lands = [l for l in unlocked_lands if l["is_special"]]

    return render_template(
        "GAME_UI/lands/select.html",
        lands=normal_lands,
        special_lands=special_lands,
    )



@frontend_bp.get("/land/<slug>")
@login_required
def land_page(slug: str):
    """
    Generic land page.

    - For classic "slot" lands (forest, beach, lake, mountain, ...):
      uses lands.yml + LandSlotState to render slots, tools, cooldowns.
    - For special lands like "village": render their own custom template.
    """
    player = g.player
    session = g.db_session

    # -------------------------------
    # Special case: village
    # -------------------------------
    if slug == "village":
        # Si tu veux plus tard vérifier la carte land_village, tu peux le faire ici.
        return render_template("GAME_UI/lands/village/village_home.html")
    
    # -------------------------------
    # Special case: temple
    # -------------------------------
    if slug == "temple":
        return render_template("GAME_UI/lands/temple/temple_home.html")    

    # -------------------------------
    # Config du land via lands.yml
    # -------------------------------
    conf = get_land_def(slug) or {}
    if not conf:
        # Land inconnu -> retour à la sélection
        return redirect(url_for("frontend.lands_select"))

    land_key = conf.get("key") or f"land_{slug}"
    starting_land = bool(conf.get("starting_land", False))

    # Si ce n'est pas un starting_land, on vérifie que le joueur a la carte
    if not starting_land:
        has_access = (
            session.query(PlayerCard)
            .filter(
                PlayerCard.player_id == player.id,
                PlayerCard.card_key == land_key,
                PlayerCard.qty > 0,
            )
            .first()
        )
        if not has_access:
            return redirect(url_for("frontend.lands_select"))

    # -------------------------------
    # État des slots pour ce joueur
    # -------------------------------
    state = get_player_land_state(session, player.id, slug)

    # -------------------------------
    # Logo / label / tools
    # -------------------------------
    land_logo = conf.get("logo")
    land_label = (
        conf.get("label_fr")
        or conf.get("label_en")
        or conf.get("label")
        or slug.capitalize()
    )

    tools_cfg = conf.get("tools") or {}

    # Normalisation pour le template: [{key, label, emoji, requires_item}, ...]
    tools = []
    for key, cfg in tools_cfg.items():
        if not isinstance(cfg, dict):
            continue

        label = cfg.get("label") or key

        if "emoji" in cfg:
            emoji = cfg.get("emoji") or ""
        else:
            emoji = "🤲" if key == "hands" else "🛠️"

        # Priority to explicit requires_item in YAML.
        requires_item = cfg.get("requires_item")
        # Option: si pas de requires_item, on considère que l'item a le même key
        # sauf pour "hands" qui ne demande rien.
        if requires_item is None and key != "hands":
            requires_item = key

        tools.append(
            {
                "key": key,
                "label": label,
                "emoji": emoji,
                "requires_item": requires_item,
            }
        )

    # -------------------------------
    # Carte "Free Slot" (optionnelle)
    # Pattern: land_<slug>_free_slot si tu veux
    # -------------------------------
    free_card_key = f"{land_key}_free_slot"
    has_free_slot_card = (
        session.query(PlayerCard)
        .filter(
            PlayerCard.player_id == player.id,
            PlayerCard.card_key == free_card_key,
            PlayerCard.qty > 0,
        )
        .count()
        > 0
    )

    # -------------------------------
    # Cooldowns par slot (barre verte)
    # -------------------------------
    now = dt.datetime.now(dt.timezone.utc)

    slot_cooldowns: dict[int, dict] = {}
    rows = (
        session.query(LandSlotState)
        .filter_by(player_id=player.id, land_key=slug)
        .all()
    )

    for st in rows:
        cd = st.cooldown_until
        if not cd:
            continue
        if cd.tzinfo is None:
            cd = cd.replace(tzinfo=dt.timezone.utc)
        if cd <= now:
            continue

        tool_key = st.last_tool_key or "hands"
        tool_cfg = tools_cfg.get(tool_key, {})
        duration = int(tool_cfg.get("cooldown_seconds", 0))
        if duration <= 0:
            continue

        slot_cooldowns[st.slot_index] = {
            "until": cd.isoformat(),
            "duration": duration,
        }

    # -------------------------------
    # Rendu du template générique
    # -------------------------------
    return render_template(
        "GAME_UI/lands/land_generic.html",
        # pour le <script> global
        land_key=slug,
        land_label=land_label,
        # pour le header
        land_logo=land_logo,
        # slots & coûts
        state=state,
        has_free_slot_card=has_free_slot_card,
        # outils
        tools=tools,
        # cooldowns par slot
        slot_cooldowns=slot_cooldowns,
    )


# ---------------------------------------------------------------------------
# Village: hub + quests / shop / trades / market
# ---------------------------------------------------------------------------


@frontend_bp.get("/village")
@login_required
def village_home():
    """Village hub: main NPC grid (quests / market / shop / trades)."""
    player = g.player
    land_logo = url_for(
        "static",
        filename="assets/img/lands/village_logo.png",
    )
    return render_template(
        "GAME_UI/lands/village/village_home.html",
        land_logo=land_logo,
        land_label="Le Village",
        player=player,
    )


@frontend_bp.get("/village/market")
@login_required
def village_market():
    """Village Market page (UI only, resources loaded via /village/market/resources)."""
    player = g.player
    land_logo = url_for(
        "static",
        filename="assets/img/lands/village_logo.png",
    )
    return render_template(
        "GAME_UI/lands/village/village_market.html",
        land_label="Le Marché du village",
        land_logo=land_logo,
        player=player,
    )


@frontend_bp.get("/village/quests")
@login_required
def village_quests():
    """Village quests page (storyline + daily + weekly). UI + JS."""
    player = g.player

    # Pour l'instant, les vraies données de quêtes viennent de /api/state
    daily_quest = None
    available_quests: list[dict] = []
    active_quests: list[dict] = []

    return render_template(
        "GAME_UI/lands/village/village_quests.html",  # <-- IMPORTANT
        player=player,
        daily_quest=daily_quest,
        available_quests=available_quests,
        active_quests=active_quests,
    )



@frontend_bp.get("/village/shop")
@login_required
def village_shop():
    """
    Card Shop du village.

    Version SIMPLE : on ignore village_shop.yml et on affiche
    toutes les cartes dont shop.show_in_village_shop == True.
    """
    player = g.player
    session = g.db_session

    # 1) Toutes les CardDef actives
    all_defs = (
        session.query(CardDef)
        .filter(CardDef.enabled == True)
        .order_by(CardDef.key.asc())
        .all()
    )

    shop_items: list[dict] = []

    for cd in all_defs:
        shop_cfg = cd.shop or {}

        # On ne garde que les cartes marquées pour le Card Shop du village
        if not shop_cfg.get("show_in_village_shop"):
            continue

        # --- Prix : on prend la première entrée de shop.prices ---
        prices = shop_cfg.get("prices") or []
        price_cfg = (prices[0] or {}) if prices else {}
        coins_cost = int(price_cfg.get("coins", 0) or 0)
        diams_cost = int(price_cfg.get("diams", 0) or 0)
        res_costs = price_cfg.get("resources") or {}

        # --- Quantité possédée par le joueur ---
        owned_row = (
            session.query(PlayerCard)
            .filter_by(player_id=player.id, card_key=cd.key)
            .first()
        )
        owned_qty = owned_row.qty if owned_row else 0

        # --- Limites d’achat (max_owned) ---
        max_owned = shop_cfg.get("max_owned")
        if max_owned is None:
            max_owned = cd.card_max_owned

        can_buy = True
        cant_buy_reason = ""
        if max_owned is not None and owned_qty >= max_owned:
            can_buy = False
            cant_buy_reason = "Tu as déjà cette carte au maximum."

        # --- Type et catégorie de filtre pour les onglets ---
        raw_type = (cd.card_type or "").lower()
        # very simple mapping for tabs: access / recipe / land / boost / other
        if "recipe" in raw_type:
            filter_type = "recipe"
        elif "access" in raw_type:
            filter_type = "access"
        elif "land" in raw_type:
            filter_type = "land"
        elif "boost" in raw_type:
            filter_type = "boost"
        else:
            filter_type = "other"

        search_text = " ".join(
            [
                cd.card_label or "",
                cd.card_description or "",
                cd.key or "",
                raw_type,
                cd.card_category or "",
            ]
        ).lower()

        # --- Construction de l'item pour le template ---
        shop_items.append(
            {
                "offer_key": cd.key,
                "item_type": "card",
                "label": cd.card_label,
                "title": cd.card_label,
                "description": cd.card_description,
                "rarity": cd.card_rarity,
                "icon": cd.card_image,
                "price_coins": coins_cost,
                "price_diams": diams_cost,
                "price_resources": res_costs,
                "stock": None,
                "limit_until": None,
                "owned_qty": owned_qty,
                "can_buy": can_buy,
                "cant_buy_reason": cant_buy_reason,
                # NEW: used by filters/search
                "card_type": raw_type,
                "filter_type": filter_type,
                "search_text": search_text,
            }
        )

    # Tri par label
    shop_items.sort(key=lambda it: (it.get("label") or it.get("offer_key") or ""))

    return render_template(
        "GAME_UI/lands/village/village_shop.html",
        player=player,
        shop_items=shop_items,
    )


@frontend_bp.get("/village/trades")
@login_required
def village_trades():
    """Village trades page (resource ↔ items/cards). For now: placeholder."""
    player = g.player

    land_logo = url_for(
        "static",
        filename="assets/img/lands/village_logo.png",
    )

    return render_template(
        "GAME_UI/lands/village/village_trades.html",
        land_label="Échanges du Village",
        land_logo=land_logo,
        player=player,
    )


# ---------------------------------------------------------------------------
# Auth: register / login / logout
# ---------------------------------------------------------------------------


@frontend_bp.route("/register", methods=["GET", "POST"])
def register():
    """
    Registration: email + password + confirmation.

    Creates an Account + Player, and gives starting land card(s).
    """
    if request.method == "GET":
        # Just display the form
        return render_template("GAME_UI/auth/register.html", errors=[])

    # POST
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "") or ""
    password_confirm = request.form.get("password_confirm", "") or ""

    errors: list[str] = []

    if not validate_email(email):
        errors.append("Adresse email invalide.")

    if password != password_confirm:
        errors.append("Les mots de passe ne correspondent pas.")

    errors.extend(validate_password(password))

    session = SessionLocal()
    try:
        # Check if email is already used
        existing = session.query(Account).filter_by(email=email).first()
        if existing:
            errors.append("Un compte existe déjà avec cette adresse email.")

        if errors:
            # Redisplay form with errors
            return render_template(
                "GAME_UI/auth/register.html",
                errors=errors,
                email=email,
            )

        # Create Player (in-game profile)
        # For now we use the truncated email as the 'name'
        player_name = email[:50] or "SansNom"
        player = Player(name=player_name)
        session.add(player)
        session.flush()  # to get player.id

        # Create Account
        account = Account(
            email=email,
            password_hash=generate_password_hash(password),
            player_id=player.id,
        )
        session.add(account)

        # Ensure starting land card(s)
        _ensure_starting_land_card(session, player)

        session.commit()

        # Prepare response + player_id cookie
        resp = make_response(redirect(url_for("frontend.land_page", slug="forest")))
        resp.set_cookie(
            "player_id",
            str(player.id),
            httponly=True,
            samesite="Lax",
        )
        return resp

    finally:
        session.close()


@frontend_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Login via email + password.

    Loads the Account and its associated Player, then sets a cookie.
    """
    if request.method == "GET":
        return render_template("GAME_UI/auth/login.html", errors=[])

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "") or ""

    errors: list[str] = []

    if not email or not password:
        errors.append("Email et mot de passe sont requis.")

    session = SessionLocal()
    try:
        account = session.query(Account).filter_by(email=email).first()
        if not account or not check_password_hash(account.password_hash, password):
            errors.append("Email ou mot de passe incorrect.")

        if errors:
            return render_template(
                "GAME_UI/auth/login.html",
                errors=errors,
                email=email,
            )

        # Fetch associated player
        player = account.player
        if not player:
            # Theoretical case: account without player
            errors.append("Aucun profil joueur associé à ce compte.")
            return render_template(
                "GAME_UI/auth/login.html",
                errors=errors,
                email=email,
            )

        # OK → set cookie + redirect to forest land
        resp = make_response(redirect(url_for("frontend.land_page", slug="forest")))
        resp.set_cookie(
            "player_id",
            str(player.id),
            httponly=True,
            samesite="Lax",
        )
        return resp

    finally:
        session.close()


@frontend_bp.route("/logout")
def logout():
    """
    Simple logout: clear player_id cookie and redirect to home.
    """
    resp = make_response(redirect(url_for("frontend.home")))
    resp.set_cookie(
        "player_id",
        "",
        httponly=True,
        samesite="Lax",
        max_age=0,  # expire immediately
    )
    return resp


# ---------------------------------------------------------------------------
# Inventory page
# ---------------------------------------------------------------------------


@frontend_bp.get("/inventory")
@login_required
def inventory_page():
    """
    Inventory page (resources + cards), requires the player to be logged in.
    """
    # player = g.player  # dispo si tu veux
    return render_template("GAME_UI/inventory.html")

# ---------------------------------------------------------------------------
# Profile page
# ---------------------------------------------------------------------------

@frontend_bp.route("/profile")
@login_required
def player_profile():
    """
    Player profile page:
    - Account info (email, registration date, etc.)
    - Player info (pseudo, level, avatar placeholder)
    - Statistics (lands, slots, quests...)
    """

    player = g.player
    account = getattr(player, "account", None)

    # -----------------------
    # Infos de compte
    # -----------------------
    email = getattr(account, "email", "inconnu")
    created_at = getattr(account, "created_at", None)

    # -----------------------
    # Infos joueur
    # -----------------------
    pseudo = (
        getattr(player, "name", None)        # ton modèle Player a 'name'
        or getattr(player, "pseudo", None)
        or getattr(player, "username", None)
    )
    level = getattr(player, "level", 0)

    # -----------------------
    # Statistiques : quêtes, lands, slots
    # -----------------------
    db = SessionLocal()
    try:
        # 1) Quêtes terminées
        stmt_quests_completed = (
            select(func.count())
            .select_from(PlayerQuest)
            .where(
                PlayerQuest.player_id == player.id,
                PlayerQuest.status == "completed",
            )
        )
        quests_completed: int = db.scalar(stmt_quests_completed) or 0

        # 2) Lands débloqués = nombre de land_key distincts
        stmt_lands_unlocked = (
            select(func.count(func.distinct(LandSlotState.land_key)))
            .where(LandSlotState.player_id == player.id)
        )
        lands_unlocked: int = db.scalar(stmt_lands_unlocked) or 0

        # 3) Nombre total de slots = nombre de lignes LandSlotState pour ce joueur
        stmt_total_slots = (
            select(func.count())
            .select_from(LandSlotState)
            .where(LandSlotState.player_id == player.id)
        )
        total_slots: int = db.scalar(stmt_total_slots) or 0

    finally:
        db.close()

    stats = {
        "lands_unlocked": lands_unlocked,
        "total_slots": total_slots,
        "quests_completed": quests_completed,
        "level": level,
    }

    return render_template(
        "GAME_UI/profile/profile.html",
        email=email,
        created_at=created_at,
        pseudo=pseudo,
        level=level,
        stats=stats,
    )