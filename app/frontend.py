# app/frontend.py
"""
Frontend routes for LodyLand:
- Public pages (home, login, register)
- Lands selection and individual land pages
- Shop pages (main shop + village shop)
- Inventory page
"""

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    make_response,
)
from werkzeug.security import generate_password_hash, check_password_hash

from .auth import get_current_player
from .db import SessionLocal
from .models import Player, Account, PlayerCard, CardDef
from .routes.api_players import _ensure_starting_land_card
from .lands import get_land_def, get_player_land_state

import datetime as dt
from .village_shop import get_active_village_offers

from pathlib import Path
import yaml

frontend_bp = Blueprint("frontend", __name__)

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
        return redirect(url_for("frontend.land_forest"))

    return render_template("home.html")


@frontend_bp.get("/play")
def play_redirect():
    """Compatibility route: /play simply redirects to home."""
    return redirect(url_for("frontend.home"))


@frontend_bp.route("/shop")
def shop():
    """Main shop page (resource selling + card shop)."""
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))
    finally:
        session.close()
    # For now, the page is mostly driven by JS
    return render_template("GAME_UI/shop/index.html")


# ---------------------------------------------------------------------------
# Lands selection + individual lands
# ---------------------------------------------------------------------------


@frontend_bp.get("/lands")
def lands_select():
    """
    Land selection screen.

    Shows all available land access cards (land_*) and which ones are unlocked
    for the current player.
    """
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))

        # 1) Land access cards owned by the player (keys like "land_forest")
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

        # 2) All enabled CardDef with key starting by land_*
        land_cards = (
            session.query(CardDef)
            .filter(CardDef.key.like("land_%"), CardDef.enabled == True)
            .order_by(CardDef.key.asc())
            .all()
        )

        def make_price_text(cd: CardDef | None) -> str:
            """
            Build a human-readable price string for a land card.

            Uses the first price option from cd.shop["prices"] if present.
            """
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

            # Simple display for resource costs, e.g. "100 wood"
            for res_key, qty in res_costs.items():
                parts.append(f"{qty} {res_key}")

            if not parts:
                return "Gratuit"

            return " + ".join(parts)

        # Optional: small emoji mapping per land (purely cosmetic)
        EMOJI_BY_SLUG = {
            "forest": "🌲",
            "beach": "🏝️",
            "village": "🏘️",
            # "desert": "🏜️", etc. when you add more
        }

        lands: list[dict] = []
        for cd in land_cards:
            # key = "land_forest" -> slug = "forest"
            slug = cd.key[len("land_") :]

            # Try to resolve frontend.land_<slug> route
            endpoint = f"frontend.land_{slug}"
            try:
                land_url = url_for(endpoint)
                has_route = True
            except Exception:
                land_url = None
                has_route = False

            lands.append(
                {
                    "key": slug,
                    "title": cd.card_label or slug.capitalize(),
                    "emoji": EMOJI_BY_SLUG.get(slug, "❓"),
                    "desc": cd.card_description or "",
                    "url": land_url,
                    "has_route": has_route,
                    "unlocked": cd.key in owned_keys,
                    "price_text": make_price_text(cd),
                }
            )

    finally:
        session.close()

    return render_template("GAME_UI/lands/select.html", lands=lands)


@frontend_bp.get("/land/forest")
def land_forest():
    """
    Forest land page.

    Renders slots state for the player + free slot card usage info.
    """
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))

        # Land state (base_slots, extra_slots, total_slots, next_cost, slot_icon, ...)
        state = get_player_land_state(session, player.id, "forest")

        # Land config (logo + label) from lands.yml
        conf = get_land_def("forest") or {}
        land_logo = conf.get("logo")  # e.g. "static/assets/img/lands/forest_logo.png"
        land_label = conf.get("label_fr") or conf.get("label_en") or "Forêt"

        # Does the player have a "Forest Free Slot" card?
        free_card_key = "land_forest_free_slot"
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

        return render_template(
            "GAME_UI/lands/forest.html",
            state=state,
            has_free_slot_card=has_free_slot_card,
            land_logo=land_logo,
            land_label=land_label,
        )
    finally:
        session.close()


@frontend_bp.get("/land/beach")
def land_beach():
    """
    Beach land page.

    Requires the player to own the land_beach card, otherwise redirects to /lands.
    """
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))

        # Check that player owns the beach access card
        has_beach = (
            session.query(PlayerCard)
            .filter(
                PlayerCard.player_id == player.id,
                PlayerCard.card_key == "land_beach",
                PlayerCard.qty > 0,
            )
            .first()
        )
        if not has_beach:
            # Redirect to lands selection
            return redirect(url_for("frontend.lands_select"))

        # Land state (slots + cost of next slot for this player on this land)
        state = get_player_land_state(session, player.id, "beach")

        # Land config (logo + label) from lands.yml
        conf = get_land_def("beach") or {}
        land_logo = conf.get("logo")  # e.g. "static/assets/img/lands/beach_logo.png"
        land_label = conf.get("label_fr") or conf.get("label_en") or "Plage"

        # Does the player have a "Beach Free Slot" card?
        free_card_key = "land_beach_free_slot"
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

        return render_template(
            "GAME_UI/lands/beach.html",
            state=state,
            has_free_slot_card=has_free_slot_card,
            land_logo=land_logo,
            land_label=land_label,
        )
    finally:
        session.close()


@frontend_bp.get("/land/lake")
def land_lake():
    """
    Lake land page.

    Requires the player to own the land_lake card, otherwise redirects to /lands.
    """
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))

        # Check that player owns the lake access card
        has_lake = (
            session.query(PlayerCard)
            .filter(
                PlayerCard.player_id == player.id,
                PlayerCard.card_key == "land_lake",
                PlayerCard.qty > 0,
            )
            .first()
        )
        if not has_lake:
            return redirect(url_for("frontend.lands_select"))

        # Land state (base slots + bonuses + next slot cost)
        state = get_player_land_state(session, player.id, "lake")

        # Land config (logo + label) from lands.yml
        conf = get_land_def("lake") or {}
        land_logo = conf.get("logo")  # e.g. "static/assets/img/lands/lake_logo.png"
        land_label = conf.get("label_fr") or conf.get("label_en") or "Lac"

        # Does the player have a "Lake Free Slot" card?
        free_card_key = "land_lake_free_slot"
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

        return render_template(
            "GAME_UI/lands/lake.html",
            state=state,
            has_free_slot_card=has_free_slot_card,
            land_logo=land_logo,
            land_label=land_label,
        )
    finally:
        session.close()


@frontend_bp.get("/land/village")
def land_village():
    """
    Village land page.

    For now, no specific card check; later we can require land_village card.
    """
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))
        # Optional: later, check for land_village card here.
        return render_template("GAME_UI/lands/village/village.html")
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Village: quests / shop / trades
# ---------------------------------------------------------------------------


@frontend_bp.get("/village/quests")
def village_quests():
    """Display the village quest NPC screen (daily + available quests)."""
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))

        # For now, we don't load real quests from DB.
        # We'll just render a static UI that we'll wire later.
        daily_quest = None
        available_quests: list[dict] = []
        active_quests: list[dict] = []

        return render_template(
            "GAME_UI/lands/village/quests.html",
            player=player,
            daily_quest=daily_quest,
            available_quests=available_quests,
            active_quests=active_quests,
        )
    finally:
        session.close()


@frontend_bp.get("/village/shop")
def village_shop():
    """
    Display the special village shop with limited items, loaded from YAML.

    This uses village_shop.yml to find active offers, then links them to CardDef.
    """
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))

        today = dt.date.today()
        offers = get_active_village_offers(today)

        shop_items: list[dict] = []

        for o in offers:
            if o.get("item_type") != "card":
                # For now we only support card offers
                continue

            card_key = o.get("item_key")
            if not card_key:
                continue

            cd = (
                session.query(CardDef)
                .filter(CardDef.key == card_key, CardDef.enabled == True)
                .first()
            )
            if not cd:
                continue

            # Shop configuration from card definition
            shop_cfg = cd.shop or {}

            # Take first price from card definition (shop.prices)
            prices = shop_cfg.get("prices") or []
            price_cfg = (prices[0] or {}) if prices else {}
            coins_cost = int(price_cfg.get("coins", 0) or 0)
            diams_cost = int(price_cfg.get("diams", 0) or 0)
            res_costs = price_cfg.get("resources") or {}

            # How many does the player already own?
            owned_row = (
                session.query(PlayerCard)
                .filter_by(player_id=player.id, card_key=cd.key)
                .first()
            )
            owned_qty = owned_row.qty if owned_row else 0

            # Purchase limits
            limit_per_player = o.get("limit_per_player")
            max_owned = shop_cfg.get("max_owned")
            can_buy_reasons: list[str] = []

            # Limit specific to the village offer
            if limit_per_player is not None and owned_qty >= limit_per_player:
                can_buy_reasons.append(
                    f"Tu as déjà acheté cette offre ({owned_qty}/{limit_per_player})."
                )

            # Global card max_owned
            if max_owned is not None and owned_qty >= max_owned:
                can_buy_reasons.append(
                    "Tu as déjà atteint le nombre maximum pour cette carte."
                )

            # Currency checks
            if player.coins < coins_cost:
                can_buy_reasons.append("Tu n'as pas assez de coins.")
            if player.diams < diams_cost:
                can_buy_reasons.append("Tu n'as pas assez de diams.")

            # (later we can also check resource costs in reasons)

            can_buy = len(can_buy_reasons) == 0
            cant_buy_reason = can_buy_reasons[0] if can_buy_reasons else ""

            # Format end date for UI
            end_str = o.get("end_date")
            end_date_fmt = None
            if end_str:
                try:
                    end_date = dt.date.fromisoformat(end_str)
                    end_date_fmt = end_date.strftime("%d/%m/%Y")
                except Exception:
                    end_date_fmt = None

            shop_items.append(
                {
                    "offer_key": o.get("key"),
                    "villager": o.get("villager"),
                    "label": cd.card_label,
                    "description": cd.card_description,
                    "rarity": cd.card_rarity,
                    "price_coins": coins_cost,
                    "price_diams": diams_cost,
                    "price_resources": res_costs,
                    "stock": o.get("stock_global"),
                    "limit_until": end_date_fmt,
                    "owned_qty": owned_qty,
                    "can_buy": can_buy,
                    "cant_buy_reason": cant_buy_reason,
                }
            )

        # Group by villager, then label
        shop_items.sort(
            key=lambda it: ((it.get("villager") or ""), it.get("label") or "")
        )

        return render_template(
            "GAME_UI/lands/village/shop.html",
            player=player,
            shop_items=shop_items,
        )
    finally:
        session.close()


@frontend_bp.get("/village/trades")
def village_trades():
    """
    Display the village trading NPC screen.

    For now this is demo-only data for the UI; real data will come from YAML/DB.
    """
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))

        # Demo trades only for UI; real data will come from YAML/DB later.
        trade_offers: list[dict] = [
            {
                "key": "demo_trade_wood_to_rope",
                "label": "Bois contre corde (DEMO)",
                "description": "Échange quelques branches contre une corde utile pour le craft.",
                "give": {"branch": 5},
                "receive": {"item_rope": 1},
                "limit_per_day": 3,
                "limit_per_rotation": None,
            },
            {
                "key": "demo_trade_mushroom_to_card",
                "label": "Champignons contre carte Forêt (DEMO)",
                "description": "Échange beaucoup de champignons contre une carte slot supplémentaire en Forêt.",
                "give": {"mushroom": 20},
                "receive": {"card_forest_free_slot": 1},
                "limit_per_day": 1,
                "limit_per_rotation": None,
            },
            {
                "key": "demo_trade_pearl_to_boost",
                "label": "Perles contre Boost Lac (DEMO)",
                "description": "Échange des perles rares contre un boost spécial au Lac.",
                "give": {"pearl": 3},
                "receive": {"boost_lake_x2": 1},
                "limit_per_day": None,
                "limit_per_rotation": 1,
            },
        ]

        return render_template(
            "GAME_UI/lands/village/trades.html",
            player=player,
            trade_offers=trade_offers,
        )
    finally:
        session.close()


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
        resp = make_response(redirect(url_for("frontend.land_forest")))
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
        resp = make_response(redirect(url_for("frontend.land_forest")))
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
def inventory_page():
    """
    Inventory page (resources + cards), requires the player to be logged in.
    """
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))

        return render_template("GAME_UI/inventory.html")
    finally:
        session.close()
