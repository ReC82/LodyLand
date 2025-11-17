# app/frontend.py
from flask import Blueprint, render_template, redirect, url_for

frontend_bp = Blueprint("frontend", __name__)

@frontend_bp.get("/")
def home():
    """Page principale du jeu (UI joueur)."""
    return render_template("GAME_UI/index.html")

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