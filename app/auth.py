# app/auth.py
from flask import request, session
from .models import Player

def get_current_player(db_session):
    """Récupère le joueur courant via la session Flask signée."""
    pid = session.get("player_id")  # ← session Flask, pas le cookie brut
    if not pid:
        # Fallback cookie brut (compatibilité temporaire)
        pid = request.cookies.get("player_id")
    if not pid:
        return None
    try:
        pid = int(pid)
    except (ValueError, TypeError):
        return None
    return db_session.get(Player, pid)
