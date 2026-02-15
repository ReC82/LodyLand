# app/routes/api_i18n.py
"""
API endpoints for i18n support.

Provides translations and currency info to the frontend.
"""

from flask import Blueprint, jsonify, request, make_response

from app.i18n import (
    get_translations_for_js,
    get_user_language,
    _CURRENCIES,
    _AVAILABLE_LANGS,
)

bp = Blueprint("i18n", __name__)


# =============================================================================
# GET /api/i18n/translations
# =============================================================================

@bp.get("/i18n/translations")
def get_translations():
    """
    Return all translations for the user's language.
    
    Query params:
        ?lang=fr  (optional, auto-detected if omitted)
    
    Response:
        {
          "lang": "fr",
          "translations": { ... },
          "currencies": { ... }
        }
    """
    lang = get_user_language(request)
    
    translations = get_translations_for_js(lang)
    
    # Also send currency info (labels, icons, etc.)
    currencies = {}
    for curr_type, curr_def in _CURRENCIES.items():
        currencies[curr_type] = {
            "key": curr_def.get("key"),
            "icon": curr_def.get("icon"),
            "labels": curr_def.get("labels", {}).get(lang, {}),
            "color": curr_def.get("color"),
        }
    
    return jsonify({
        "lang": lang,
        "available_langs": _AVAILABLE_LANGS,
        "translations": translations,
        "currencies": currencies,
    })


# =============================================================================
# POST /api/i18n/set-language
# =============================================================================

@bp.post("/i18n/set-language")
def set_language():
    """
    Set user's preferred language (stored in DB + cookie).
    
    Body:
        { "lang": "fr" }
    
    Response:
        { "ok": true, "lang": "fr" }
    """
    from app.auth import get_current_player
    from app.db import SessionLocal
    
    data = request.get_json(silent=True) or {}
    lang = data.get("lang", "en")
    
    if lang not in _AVAILABLE_LANGS:
        return jsonify({"ok": False, "error": "invalid_language"}), 400
    
    # Save to DB if user is logged in
    with SessionLocal() as session:
        player = get_current_player(session)
        
        if player:
            player.lang = lang
            session.commit()
            print(f"[i18n] Saved language preference for {player.name}: {lang}")
    
    # Also set cookie as fallback
    resp = make_response(jsonify({"ok": True, "lang": lang}))
    resp.set_cookie("lang", lang, max_age=365*24*60*60)  # 1 year
    
    return resp


# =============================================================================
# GET /api/i18n/currency-info
# =============================================================================

@bp.get("/i18n/currency-info")
def get_currency_info():
    """
    Get detailed currency information.
    
    Useful for UI that needs to display currency labels, icons, etc.
    
    Response:
        {
          "primary": {
            "key": "shards",
            "icon": "/static/...",
            "labels": { "fr": {...}, "en": {...} },
            ...
          },
          "premium": {...}
        }
    """
    return jsonify(_CURRENCIES)
