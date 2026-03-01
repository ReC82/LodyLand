# app/i18n/__init__.py
"""
Centralized i18n system for LodyLand - FIXED VERSION

Features:
- Load translations from YAML files
- Support multiple languages (fr, en, es, ...)
- Currency labels and formatting  
- Template helpers for Jinja2
- JS API for frontend
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
import yaml

# Global state - Use class to avoid reference issues
class _I18nState:
    def __init__(self):
        self.translations: Dict[str, Dict[str, Any]] = {}
        self.currencies: Dict[str, Any] = {}
        self.items_data: Dict[str, Any] = {}  # Cache for items.yml
        self.cards_data: Dict[str, Any] = {}  # Cache for cards.yml
        self.default_lang: str = "en"
        self.available_langs: list = ["fr", "en"]

_STATE = _I18nState()

# Paths
I18N_DIR = Path(__file__).resolve().parent
TRANSLATIONS_DIR = I18N_DIR / "translations"
CURRENCIES_FILE = I18N_DIR.parent / "data" / "currencies.yml"
ITEMS_FILE = I18N_DIR.parent / "data" / "items.yml"
CARDS_FILE = I18N_DIR.parent / "data" / "cards.yml"


# =============================================================================
# Initialization
# =============================================================================

def load_translations() -> None:
    """Load all translation files from i18n/translations/*.yml"""
    if not TRANSLATIONS_DIR.exists():
        print(f"[i18n] WARNING: translations directory not found: {TRANSLATIONS_DIR}")
        return
    
    for lang_file in TRANSLATIONS_DIR.glob("*.yml"):
        lang = lang_file.stem  # fr, en, es...
        
        try:
            with lang_file.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            
            _STATE.translations[lang] = data
            print(f"[i18n] Loaded {len(data)} keys for language: {lang}")
        
        except Exception as e:
            print(f"[i18n] ERROR loading {lang_file}: {e}")


def load_currencies() -> None:
    """Load currency definitions from data/currencies.yml"""
    if not CURRENCIES_FILE.exists():
        print(f"[i18n] WARNING: currencies file not found: {CURRENCIES_FILE}")
        return
    
    try:
        with CURRENCIES_FILE.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        currencies_data = data.get("currencies", {})
        
        # Clear and update to preserve reference
        _STATE.currencies.clear()
        _STATE.currencies.update(currencies_data)
        
        print(f"[i18n] Loaded {len(_STATE.currencies)} currency types: {list(_STATE.currencies.keys())}")
    
    except Exception as e:
        print(f"[i18n] ERROR loading currencies: {e}")
        import traceback
        traceback.print_exc()


def load_items_data() -> None:
    """Load items.yml into memory"""
    if not ITEMS_FILE.exists():
        print(f"[i18n] WARNING: items file not found: {ITEMS_FILE}")
        return
    
    try:
        with ITEMS_FILE.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        items_map = data.get("items", {})
        
        # Clear and update to preserve reference
        _STATE.items_data.clear()
        _STATE.items_data.update(items_map)
        
        print(f"[i18n] Loaded {len(_STATE.items_data)} items from {ITEMS_FILE}")
    
    except Exception as e:
        print(f"[i18n] ERROR loading items: {e}")
        import traceback
        traceback.print_exc()


def load_cards_data() -> None:
    """Load cards.yml into memory"""
    if not CARDS_FILE.exists():
        print(f"[i18n] WARNING: cards file not found: {CARDS_FILE}")
        return
    
    try:
        with CARDS_FILE.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        # Convert list to dict by key for fast access
        cards_list = data.get("cards", [])
        cards_dict = {card["key"]: card for card in cards_list if "key" in card}
        
        # Clear and update to preserve reference
        _STATE.cards_data.clear()
        _STATE.cards_data.update(cards_dict)
        
        print(f"[i18n] Loaded {len(_STATE.cards_data)} cards from {CARDS_FILE}")
    
    except Exception as e:
        print(f"[i18n] ERROR loading cards: {e}")
        import traceback
        traceback.print_exc()


def init_i18n() -> None:
    """Initialize the i18n system. Call this at app startup."""
    load_translations()
    load_currencies()
    load_items_data()
    load_cards_data()


# =============================================================================
# Translation functions
# =============================================================================

def t(key: str, lang: str = None, **kwargs) -> str:
    """
    Translate a key to the target language.
    """
    if lang is None:
        lang = _STATE.default_lang
    
    if lang not in _STATE.translations:
        lang = _STATE.default_lang
    
    # Navigate nested dict via dot notation
    parts = key.split(".")
    value = _STATE.translations.get(lang, {})
    
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            break
    
    # Not found -> return key as fallback
    if value is None or not isinstance(value, str):
        return key
    
    # Interpolate variables
    if kwargs:
        try:
            value = value.format(**kwargs)
        except KeyError as e:
            print(f"[i18n] WARNING: missing variable {e} in key '{key}'")
    
    return value


def t_plural(key: str, count: int, lang: str = None, **kwargs) -> str:
    """Translate with plural support."""
    if lang is None:
        lang = _STATE.default_lang
    
    plural_key = f"{key}.one" if count == 1 else f"{key}.other"
    kwargs["count"] = count
    return t(plural_key, lang=lang, **kwargs)


# =============================================================================
# Currency helpers
# =============================================================================

def get_currency_label(
    currency_type: str,
    count: int = 1,
    lang: str = None,
    short: bool = False
) -> str:
    """Get localized currency label."""
    if lang is None:
        lang = _STATE.default_lang
    
    currency_def = _STATE.currencies.get(currency_type, {})
    labels = currency_def.get("labels", {}).get(lang, {})
    
    if not labels:
        labels = currency_def.get("labels", {}).get("en", {})
    
    if short:
        return labels.get("short", currency_type.upper()[0])
    
    if count == 1:
        return labels.get("singular", currency_type.capitalize())
    else:
        return labels.get("plural", currency_type.capitalize() + "s")


def format_currency(
    amount: int,
    currency_type: str,
    lang: str = None,
    with_label: bool = True,
    short: bool = False
) -> str:
    """Format a currency amount with its label."""
    if not with_label:
        return str(amount)
    
    label = get_currency_label(currency_type, amount, lang, short)
    
    if short:
        return f"{amount}{label}"
    else:
        return f"{amount} {label}"


def get_currency_icon(currency_type: str) -> str:
    """Get the icon path for a currency."""
    currency_def = _STATE.currencies.get(currency_type, {})
    return currency_def.get("icon", "/static/assets/img/ui/default.png")


def get_currency_key(currency_type: str) -> str:
    """Get the technical key for a currency (shards, essence)."""
    currency_def = _STATE.currencies.get(currency_type, {})
    return currency_def.get("key", currency_type)


# =============================================================================
# Jinja2 template helpers
# =============================================================================

def register_i18n_helpers(app) -> None:
    """Register i18n functions as Jinja2 globals."""
    from flask import g, request, has_request_context
    
    # Wrapper pour t() qui détecte la langue à chaque appel
    def t_auto(key: str, **kwargs) -> str:
        """Translate with automatic language detection"""
        if not has_request_context():
            return t(key, lang=_STATE.default_lang, **kwargs)
        
        player = getattr(g, 'player', None)
        lang = get_user_language(request, player=player)
        
        # DEBUG
        if key == "profile.title":  # Log seulement pour un cas spécifique
            print(f"[t_auto] key={key}, player={player}, lang={lang}")
        
        return t(key, lang=lang, **kwargs)
    
    # Wrappers pour les autres fonctions
    def currency_label_auto(currency_type: str, count: int = 1, short: bool = False):
        if not has_request_context():
            lang = _STATE.default_lang
        else:
            player = getattr(g, 'player', None)
            lang = get_user_language(request, player=player)
        return get_currency_label(currency_type, count, lang, short)
    
    def format_currency_auto(amount: int, currency_type: str, with_label: bool = True, short: bool = False):
        if not has_request_context():
            lang = _STATE.default_lang
        else:
            player = getattr(g, 'player', None)
            lang = get_user_language(request, player=player)
        return format_currency(amount, currency_type, lang, with_label, short)
    
    # Enregistrer les wrappers
    app.jinja_env.globals["t"] = t_auto
    app.jinja_env.globals["t_plural"] = t_plural
    app.jinja_env.globals["currency_label"] = currency_label_auto
    app.jinja_env.globals["currency_icon"] = get_currency_icon
    app.jinja_env.globals["format_currency"] = format_currency_auto


# =============================================================================
# API helpers (for frontend JS)
# =============================================================================

def get_translations_for_js(lang: str) -> Dict[str, Any]:
    """Get all translations for a language as a flat dict for JS."""
    if lang not in _STATE.translations:
        lang = _STATE.default_lang
    
    return _STATE.translations.get(lang, {})

def get_user_language(request, player=None) -> str:
    print(f"[i18n] === get_user_language called ===")
    print(f"[i18n]   player object: {player}")
    print(f"[i18n]   player.id: {player.id if player else 'N/A'}")
    print(f"[i18n]   player.name: {player.name if player else 'N/A'}")
    
    # 1. Player preference in DB (highest priority)
    if player is not None:
        player_lang = getattr(player, "lang", None)
        print(f"[i18n]   player.lang from getattr: {player_lang}")
        print(f"[i18n]   type(player_lang): {type(player_lang)}")
        print(f"[i18n]   _STATE.available_langs: {_STATE.available_langs}")
        print(f"[i18n]   player_lang in available_langs: {player_lang in _STATE.available_langs if player_lang else 'N/A'}")
        
        if player_lang and player_lang in _STATE.available_langs:
            print(f"[i18n]   ✓✓✓ USING PLAYER DB LANG: {player_lang}")
            return player_lang
        else:
            print(f"[i18n]   ✗ Player lang invalid or empty")
    
    # 2. Query param
    lang = request.args.get("lang")
    if lang in _STATE.available_langs:
        print(f"[i18n]   ✓ Using query param: {lang}")
        return lang
    
    # 3. Cookie
    lang = request.cookies.get("lang")
    print(f"[i18n]   Cookie lang: {lang}")
    if lang in _STATE.available_langs:
        print(f"[i18n]   ✓ Using cookie: {lang}")
        return lang
    
    # 4. Accept-Language
    lang = request.accept_languages.best_match(_STATE.available_langs)
    if lang:
        print(f"[i18n]   ✓ Using Accept-Language: {lang}")
        return lang
    
    # 5. Default
    print(f"[i18n]   ✓ Using default: {_STATE.default_lang}")
    return _STATE.default_lang


# =============================================================================
# Game data translation helpers (items, cards)
# =============================================================================

def translate_data_dict(data: dict, lang: str = None) -> dict:
    """
    Recursively translate all string values in a dict if they look like i18n keys.
    
    Example:
        data = {"label": "items.branch.label", "icon": "/static/..."}
        → {"label": "Branch", "icon": "/static/..."}
    
    A string is considered an i18n key if:
    - It contains at least one dot
    - It doesn't start with '/' (to avoid translating paths)
    - It doesn't start with 'http' (to avoid translating URLs)
    """
    if lang is None:
        lang = _STATE.default_lang
    
    result = {}
    
    for key, value in data.items():
        if isinstance(value, str):
            # Check if it looks like an i18n key
            is_i18n_key = (
                '.' in value 
                and not value.startswith('/') 
                and not value.startswith('http')
            )
            
            if is_i18n_key:
                # Try to translate
                translated = t(value, lang=lang)
                result[key] = translated
            else:
                # Keep as-is (path, URL, regular string)
                result[key] = value
        
        elif isinstance(value, dict):
            # Recursively translate nested dicts
            result[key] = translate_data_dict(value, lang)
        
        elif isinstance(value, list):
            # Translate items in lists
            result[key] = [
                translate_data_dict(item, lang) if isinstance(item, dict) else item
                for item in value
            ]
        
        else:
            # Keep as-is (numbers, bools, None, etc.)
            result[key] = value
    
    return result


def get_item(item_key: str, lang: str = None) -> dict | None:
    """
    Get an item from items.yml and translate it.
    
    Usage:
        item = get_item("branch", "en")
        # → {"key": "branch", "label": "Branch", "description": "A branch...", ...}
    
    Args:
        item_key: The item's key (e.g., "branch", "wood")
        lang: Target language (defaults to default_lang)
    
    Returns:
        Translated item dict, or None if not found
    """
    if item_key not in _STATE.items_data:
        return None
    
    # Copy the item data (don't modify the cached version)
    item_data = _STATE.items_data[item_key].copy()
    
    # Translate all i18n keys
    return translate_data_dict(item_data, lang)


def get_all_items(lang: str = None) -> dict:
    """
    Get all items translated.
    
    Returns:
        dict with item_key -> translated_item_data
    """
    result = {}
    for item_key in _STATE.items_data.keys():
        result[item_key] = get_item(item_key, lang)
    return result


def get_card(card_key: str, lang: str = None) -> dict | None:
    """
    Get a card from cards.yml and translate it.
    
    Args:
        card_key: The card's key (e.g., "land_forest", "recipe_rope")
        lang: Target language (defaults to default_lang)
    
    Returns:
        Translated card dict, or None if not found
    """
    if card_key not in _STATE.cards_data:
        return None
    
    # Copy the card data (don't modify the cached version)
    card_data = _STATE.cards_data[card_key].copy()
    
    # Translate all i18n keys
    return translate_data_dict(card_data, lang)


def get_all_cards(lang: str = None) -> dict:
    """
    Get all cards translated.
    
    Returns:
        dict with card_key -> translated_card_data
    """
    result = {}
    for card_key in _STATE.cards_data.keys():
        result[card_key] = get_card(card_key, lang)
    return result


# Legacy exports for backward compatibility
_TRANSLATIONS = _STATE.translations
_CURRENCIES = _STATE.currencies
_DEFAULT_LANG = _STATE.default_lang
_AVAILABLE_LANGS = _STATE.available_langs
