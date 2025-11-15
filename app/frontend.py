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
