# app/frontend.py
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

from pathlib import Path
import yaml

frontend_bp = Blueprint("frontend", __name__)

# ----------------- Helpers validation -----------------

def validate_email(email: str) -> bool:
    """Very basic email format validation."""
    if not email:
        return False
    email = email.strip()
    return "@" in email and "." in email and " " not in email


def validate_password(password: str) -> list[str]:
    """
    Validate password complexity.
    Règles simples pour commencer :
    - min 8 caractères
    - au moins 1 chiffre
    - au moins 1 lettre
    """
    errors: list[str] = []
    if len(password) < 8:
        errors.append("Le mot de passe doit contenir au moins 8 caractères.")
    if not any(c.isdigit() for c in password):
        errors.append("Le mot de passe doit contenir au moins un chiffre.")
    if not any(c.isalpha() for c in password):
        errors.append("Le mot de passe doit contenir au moins une lettre.")
    return errors

# ----------------- Lands config helper -----------------

def get_land_slots(slug: str, default: int = 6) -> int:
    """
    Retourne le nombre de slots pour un land donné à partir de lands.yml.
    slug : "forest", "beach", "village", ...
    default : valeur de secours si la config est absente ou invalide.
    """
    conf = get_land_def(slug)  # lit app/data/lands.yml via lands.py
    if not isinstance(conf, dict):
        # Land inconnu -> valeur par défaut
        return default

    try:
        return int(conf.get("slots", default))
    except (TypeError, ValueError):
        return default


@frontend_bp.route("/")
def home():
    """Page d'accueil publique. Si le joueur est connecté, on le redirige vers la forêt."""
    session = SessionLocal()
    try:
        player = get_current_player(session)
    finally:
        session.close()

    if player is not None:
        # Joueur déjà connecté → on l'envoie sur la forêt
        return redirect(url_for("frontend.land_forest"))

    return render_template("home.html")


@frontend_bp.get("/play")
def play_redirect():
    """Compatibilité : /play redirige vers /."""
    return redirect(url_for("frontend.home"))

@frontend_bp.route("/shop")
def shop():
    """Page boutique joueur (vente ressources + achat cartes)."""
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))
    finally:
        session.close()        
    # Pour le moment, la page sera majoritairement pilotée par JS
    return render_template("GAME_UI/shop/index.html")

@frontend_bp.get("/lands")
def lands_select():
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))

        # 1) Cartes d'accès land_* possédées par le joueur
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

        # 2) Tous les CardDef de type land_* (activés)
        land_cards = (
            session.query(CardDef)
            .filter(CardDef.key.like("land_%"), CardDef.enabled == True)
            .order_by(CardDef.key.asc())
            .all()
        )

        def make_price_text(cd: CardDef | None) -> str:
            if not cd:
                return ""

            # New multi-price format: we only display the first option for now.
            prices = cd.prices or []
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

        # Optionnel : petit mapping d’emoji par land (juste cosmétique)
        EMOJI_BY_SLUG = {
            "forest": "🌲",
            "beach": "🏝️",
            "village": "🏘️",
            # "desert": "🏜️", etc. quand tu en ajoutes
        }

        lands: list[dict] = []
        for cd in land_cards:
            # key = "land_forest" -> slug = "forest"
            slug = cd.key[len("land_") :]

            # On tente de trouver la route frontend.land_<slug>
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
                    "title": cd.label or slug.capitalize(),
                    "emoji": EMOJI_BY_SLUG.get(slug, "❓"),
                    "desc": cd.description or "",
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
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))

        # État du land (base_slots, extra_slots, total_slots, next_cost, slot_icon, ...)
        state = get_player_land_state(session, player.id, "forest")

        # Config du land (pour logo + label) depuis lands.yml
        conf = get_land_def("forest") or {}
        land_logo = conf.get("logo")  # "static/assets/img/lands/forest_logo.png"
        land_label = conf.get("label_fr") or conf.get("label_en") or "Forêt"

        # Le joueur possède-t-il une carte free slot pour la forêt ?
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
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))

        # Vérifier que le joueur possède bien la carte d'accès à la plage
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
            # On le renvoie sur l’écran de sélection des lands
            return redirect(url_for("frontend.lands_select"))

        # Slots + coût du prochain slot pour CE joueur sur CE land
        state = get_player_land_state(session, player.id, "beach")
        
                # Config du land (pour logo + label) depuis lands.yml
        conf = get_land_def("beach") or {}
        land_logo = conf.get("logo")  # "static/assets/img/lands/beach_logo.png"
        land_label = conf.get("label_fr") or conf.get("label_en") or "Plage"

        # Possède-t-il une carte "Beach Free Slot" ?
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
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))

        # Vérifier la carte d'accès au lac
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

        # État du land (slots de base + bonus + coût prochain slot)
        state = get_player_land_state(session, player.id, "lake")
        
                # Config du land (pour logo + label) depuis lands.yml
        conf = get_land_def("lake") or {}
        land_logo = conf.get("logo")  # "static/assets/img/lands/lake_logo.png"
        land_label = conf.get("label_fr") or conf.get("label_en") or "Lac"

        # Possède-t-il une carte Lake Free Slot ?
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
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))
        # Optionnel : check carte land_desert ici
        return render_template("GAME_UI/lands/village/village.html")
    finally:
        session.close()
        
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
    """Display the special village shop with limited items (UI only for now)."""
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))

        # For now, we use static demo items.
        # Later this will be loaded from YAML / DB with rotations.
        shop_items: list[dict] = [
            {
                "key": "demo_boost_forest_x2",
                "label": "Boost Forêt x2 (DEMO)",
                "description": "Double temporairement tes gains de ressources en Forêt.",
                "rarity": "rare",
                "price_coins": 250,
                "price_diams": 0,
                "stock": 3,
            },
            {
                "key": "demo_card_lake_free_slot",
                "label": "Carte: Emplacement Lac +1 (DEMO)",
                "description": "Ajoute un emplacement de récolte sur le Lac.",
                "rarity": "epic",
                "price_coins": 0,
                "price_diams": 5,
                "stock": 1,
            },
            {
                "key": "demo_recipe_rope",
                "label": "Recette: Corde (DEMO)",
                "description": "Débloque la recette de fabrication de corde.",
                "rarity": "uncommon",
                "price_coins": 120,
                "price_diams": 0,
                "stock": 999,  # 'Illimité' côté UI
            },
        ]

        shop_rotation_label = "Rotation de démonstration (UI only)"

        return render_template(
            "GAME_UI/lands/village/shop.html",
            player=player,
            shop_items=shop_items,
            shop_rotation_label=shop_rotation_label,
        )
    finally:
        session.close()    
        
@frontend_bp.get("/village/trades")
def village_trades():
    """Display the village trading NPC screen (UI only for now)."""
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
        

@frontend_bp.route("/register", methods=["GET", "POST"])
def register():
    """Inscription : email + mot de passe + confirmation. Crée un Account + Player."""
    if request.method == "GET":
        # Affiche juste le formulaire
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
        # Vérifier si email déjà utilisé
        existing = session.query(Account).filter_by(email=email).first()
        if existing:
            errors.append("Un compte existe déjà avec cette adresse email.")

        if errors:
            # Réafficher le formulaire avec erreurs
            return render_template("GAME_UI/auth/register.html", errors=errors, email=email)

        # Créer le Player (profil en jeu)
        # Pour l'instant on utilise l'email tronqué comme "name"
        player_name = email[:50] or "SansNom"
        player = Player(name=player_name)
        session.add(player)
        session.flush()  # pour avoir player.id

        # Créer l'Account
        account = Account(
            email=email,
            password_hash=generate_password_hash(password),
            player_id=player.id,
        )
        session.add(account)

        _ensure_starting_land_card(session, player)

        session.commit()

        # Préparer la réponse + cookie player_id
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
    """Connexion par email + mot de passe. Charge l'Account et son Player."""
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
            return render_template("GAME_UI/auth/login.html", errors=errors, email=email)

        # Récupérer le player associé
        player = account.player
        if not player:
            # cas théorique : account sans player
            errors.append("Aucun profil joueur associé à ce compte.")
            return render_template("GAME_UI/auth/login.html", errors=errors, email=email)

        # OK → cookie + redirection vers la forêt
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
    """Simple logout: clear player_id cookie and redirect to home."""
    resp = make_response(redirect(url_for("frontend.home")))
    resp.set_cookie(
        "player_id",
        "",
        httponly=True,
        samesite="Lax",
        max_age=0,           # expire immédiatement
    )
    return resp

@frontend_bp.get("/inventory")
def inventory_page():
    """Page Inventaire (ressources + cartes), nécessite d'être connecté."""
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))

        return render_template("GAME_UI/inventory.html")
    finally:
        session.close()