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
from .models import Player, Account
from .routes.api_players import _ensure_starting_land_card

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

@frontend_bp.get("/land/beach")
def land_beach():
    """Display the Beach land page (x slots)."""
    # Later we can pass dynamic data here (player, cards, etc.)
    return render_template("GAME_UI/lands/beach.html")

@frontend_bp.get("/land/forest")
def land_forest():
    """Display the Beach land page (x slots)."""
    # Later we can pass dynamic data here (player, cards, etc.)
    return render_template("GAME_UI/lands/forest.html")

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
