# app/routes/api_players.py

from datetime import datetime, timezone, timedelta, date

from flask import Blueprint, jsonify, request
from app.db import SessionLocal
from app.models import Player
from app.progression import next_threshold
from app.economy import DAILY_REWARD_COINS
from app.auth import get_current_player 

bp = Blueprint("daily", __name__) 
    # -----------------------------------------------------------------
    # Daily chest
    # -----------------------------------------------------------------
@bp.post("/daily")
def claim_daily():  
    """Claim daily chest (once per UTC day) + gestion du streak."""
    from datetime import datetime, timezone, timedelta, date  # au cas où

    with SessionLocal() as s:
        me = get_current_player(s)
        if not me:
            return jsonify({"error": "not_authenticated"}), 401

        today_utc: date = datetime.now(timezone.utc).date()

        # Déjà pris aujourd'hui ?
        if me.last_daily == today_utc:
            next_reset = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
            return jsonify({
                "error": "already_claimed",
                "next_at": next_reset.isoformat()
            }), 409

        # --- Calcul du nouveau streak -------------------------------------
        # Cas 1 : jamais pris / très vieux -> on repart à 1
        new_streak = 1
        if me.last_daily:
            # Si pris hier, on continue la série
            if me.last_daily == (today_utc - timedelta(days=1)):
                new_streak = (me.daily_streak or 0) + 1
            else:
                new_streak = 1

        me.last_daily = today_utc
        me.daily_streak = new_streak

        # Best streak
        current_best = me.best_streak or 0
        if new_streak > current_best:
            me.best_streak = new_streak
        else:
            me.best_streak = current_best

        # Créditer les coins
        me.coins = (me.coins or 0) + DAILY_REWARD_COINS

        s.commit()
        s.refresh(me)

        next_reset = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)

        return jsonify({
            "ok": True,
            "reward": DAILY_REWARD_COINS,
            "player": {
                "id": me.id,
                "name": me.name,
                "coins": me.coins,
                "diams": me.diams,
                "xp": me.xp,
                "level": me.level,
                "next_xp": next_threshold(me.level),
            },
            "streak": {
                "current": me.daily_streak,
                "best": me.best_streak,
            },
            "next_at": next_reset.isoformat(),
        }), 200

@bp.get("/daily/status")
def daily_status():
    """Retourne le statut du coffre quotidien (sans rien modifier)."""
    with SessionLocal() as s:
        me = get_current_player(s)
        if not me:
            # Pour le front, un 401 clair est ok : pas loggé = pas de coffre.
            return jsonify({"error": "not_authenticated"}), 401

        today_utc: date = datetime.now(timezone.utc).date()

        # Par défaut : streak 0 si null
        current_streak = me.daily_streak or 0
        best_streak = me.best_streak or 0

        # Calcul du prochain reset (minuit UTC du lendemain)
        next_reset_dt = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        next_reset_iso = next_reset_dt.isoformat()

        # Eligible si : jamais pris OU dernier daily < aujourd'hui
        if not me.last_daily or me.last_daily < today_utc:
            eligible = True
        else:
            # me.last_daily == today_utc -> déjà pris aujourd'hui
            eligible = False

        return jsonify({
            "eligible": eligible,
            "next_reset": next_reset_iso,
            "streak": {
                "current": current_streak,
                "best": best_streak,
            },
        }), 200