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
from .lands import get_land_def

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
            parts: list[str] = []
            if cd.price_coins:
                parts.append(f"{cd.price_coins} 🪙")
            if cd.price_diams:
                parts.append(f"{cd.price_diams} 💎")
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
            # pas connecté → retour home (ou login)
            return redirect(url_for("frontend.home"))

        # Nombre de slots depuis lands.yml
        slots = get_land_slots("forest", default=6)

        return render_template("GAME_UI/lands/forest.html", slots=slots)
    finally:
        session.close()

@frontend_bp.get("/land/beach")
def land_beach():
    session = SessionLocal()
    try:
        player = get_current_player(session)
        if not player:
            return redirect(url_for("frontend.home"))

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
            # plus tard on pourra afficher un message dans /lands
            return redirect(url_for("frontend.lands_select"))

        slots = get_land_slots("beach", default=6)

        return render_template("GAME_UI/lands/beach.html", slots=slots)
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
        return render_template("GAME_UI/lands/village.html")
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