# app/auth.py
from flask import request
from .models import Player

def get_current_player(session):
    """Récupère le joueur courant via le cookie 'player_id'."""
    pid = request.cookies.get("player_id")
    if not pid:
        return None
    try:
        pid = int(pid)
    except ValueError:
        return None
    return session.get(Player, pid)
