# app/i18n/__init__.py
"""
Centralized i18n system for LodyLand.

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

# Global caches
_TRANSLATIONS: Dict[str, Dict[str, Any]] = {}
_CURRENCIES: Dict[str, Any] = {}
_DEFAULT_LANG = "en"
_AVAILABLE_LANGS = ["fr", "en"]

# Paths
I18N_DIR = Path(__file__).resolve().parent
TRANSLATIONS_DIR = I18N_DIR / "translations"
CURRENCIES_FILE = I18N_DIR.parent / "data" / "currencies.yml"


# =============================================================================
# Initialization
# =============================================================================

def load_translations() -> None:
    """Load all translation files from i18n/translations/*.yml"""
    global _TRANSLATIONS
    
    if not TRANSLATIONS_DIR.exists():
        print(f"[i18n] WARNING: translations directory not found: {TRANSLATIONS_DIR}")
        return
    
    for lang_file in TRANSLATIONS_DIR.glob("*.yml"):
        lang = lang_file.stem  # fr, en, es...
        
        try:
            with lang_file.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            
            _TRANSLATIONS[lang] = data
            print(f"[i18n] Loaded {len(data)} keys for language: {lang}")
        
        except Exception as e:
            print(f"[i18n] ERROR loading {lang_file}: {e}")


def load_currencies() -> None:
    """Load currency definitions from data/currencies.yml"""
    global _CURRENCIES
    
    if not CURRENCIES_FILE.exists():
        print(f"[i18n] WARNING: currencies file not found: {CURRENCIES_FILE}")
        return
    
    try:
        with CURRENCIES_FILE.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        _CURRENCIES = data.get("currencies", {})
        print(f"[i18n] Loaded {len(_CURRENCIES)} currency types")
    
    except Exception as e:
        print(f"[i18n] ERROR loading currencies: {e}")


def init_i18n() -> None:
    """Initialize the i18n system. Call this at app startup."""
    load_translations()
    load_currencies()


# =============================================================================
# Translation functions
# =============================================================================

def t(key: str, lang: str = None, **kwargs) -> str:
    """
    Translate a key to the target language.
    
    Args:
        key: Translation key (e.g. "ui.welcome", "errors.not_found")
        lang: Target language (fr, en, ...). If None, uses default.
        **kwargs: Variables to interpolate in the translation
    
    Returns:
        Translated string, or the key itself if not found
    
    Examples:
        t("ui.welcome")
        t("ui.greeting", name="Alice")
        t("errors.not_enough", resource="wood", lang="fr")
    """
    if lang is None:
        lang = _DEFAULT_LANG
    
    if lang not in _TRANSLATIONS:
        lang = _DEFAULT_LANG
    
    # Navigate nested dict via dot notation
    parts = key.split(".")
    value = _TRANSLATIONS.get(lang, {})
    
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
    """
    Translate with plural support.
    
    Expects translations like:
        items:
          branch:
            one: "{count} branch"
            other: "{count} branches"
    
    Args:
        key: Base translation key
        count: Number for plural decision
        lang: Target language
        **kwargs: Additional variables
    """
    if lang is None:
        lang = _DEFAULT_LANG
    
    # Get the plural form
    plural_key = f"{key}.one" if count == 1 else f"{key}.other"
    
    kwargs["count"] = count
    return t(plural_key, lang=lang, **kwargs)


# =============================================================================
# Currency helpers
# =============================================================================

def get_currency_label(
    currency_type: str,  # "primary" or "premium"
    count: int = 1,
    lang: str = None,
    short: bool = False
) -> str:
    """
    Get localized currency label.
    
    Args:
        currency_type: "primary" (shards) or "premium" (essence)
        count: Amount (for singular/plural)
        lang: Target language
        short: Use short form (É, E) instead of full label
    
    Returns:
        Localized currency name
    
    Examples:
        get_currency_label("primary", 1, "fr")     -> "Éclat"
        get_currency_label("primary", 10, "fr")    -> "Éclats"
        get_currency_label("premium", 5, "en")     -> "Essences"
        get_currency_label("primary", 1, "fr", short=True)  -> "É"
    """
    if lang is None:
        lang = _DEFAULT_LANG
    
    currency_def = _CURRENCIES.get(currency_type, {})
    labels = currency_def.get("labels", {}).get(lang, {})
    
    if not labels:
        # Fallback to English
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
    """
    Format a currency amount with its label.
    
    Args:
        amount: Quantity
        currency_type: "primary" or "premium"
        lang: Target language
        with_label: Include the currency name
        short: Use short label
    
    Returns:
        Formatted string
    
    Examples:
        format_currency(100, "primary", "fr")           -> "100 Éclats"
        format_currency(1, "premium", "en")             -> "1 Essence"
        format_currency(50, "primary", "fr", short=True) -> "50É"
        format_currency(200, "primary", with_label=False) -> "200"
    """
    if not with_label:
        return str(amount)
    
    label = get_currency_label(currency_type, amount, lang, short)
    
    if short:
        return f"{amount}{label}"
    else:
        return f"{amount} {label}"


def get_currency_icon(currency_type: str) -> str:
    """
    Get the icon path for a currency.
    
    Args:
        currency_type: "primary" or "premium"
    
    Returns:
        Icon file path
    """
    currency_def = _CURRENCIES.get(currency_type, {})
    return currency_def.get("icon", "/static/assets/img/ui/default.png")


def get_currency_key(currency_type: str) -> str:
    """
    Get the technical key for a currency (shards, essence).
    
    This is used for database columns, API responses, etc.
    """
    currency_def = _CURRENCIES.get(currency_type, {})
    return currency_def.get("key", currency_type)


# =============================================================================
# Jinja2 template helpers
# =============================================================================

def register_i18n_helpers(app) -> None:
    """
    Register i18n functions as Jinja2 globals.
    
    Call this after creating your Flask app:
        from app.i18n import register_i18n_helpers
        register_i18n_helpers(app)
    
    Then in templates:
        {{ t("ui.welcome") }}
        {{ currency_label("primary", 10) }}
    """
    app.jinja_env.globals["t"] = t
    app.jinja_env.globals["t_plural"] = t_plural
    app.jinja_env.globals["currency_label"] = get_currency_label
    app.jinja_env.globals["currency_icon"] = get_currency_icon
    app.jinja_env.globals["format_currency"] = format_currency


# =============================================================================
# API helpers (for frontend JS)
# =============================================================================

def get_translations_for_js(lang: str) -> Dict[str, Any]:
    """
    Get all translations for a language as a flat dict for JS.
    
    This is used by /api/i18n endpoint to send translations to the frontend.
    """
    if lang not in _TRANSLATIONS:
        lang = _DEFAULT_LANG
    
    return _TRANSLATIONS.get(lang, {})


def get_user_language(request) -> str:
    """
    Detect user's preferred language from request.
    
    Priority:
    1. Query param ?lang=fr
    2. Cookie (lang)
    3. Accept-Language header
    4. Default (en)
    """
    # 1. Query param
    lang = request.args.get("lang")
    if lang in _AVAILABLE_LANGS:
        return lang
    
    # 2. Cookie
    lang = request.cookies.get("lang")
    if lang in _AVAILABLE_LANGS:
        return lang
    
    # 3. Accept-Language header
    lang = request.accept_languages.best_match(_AVAILABLE_LANGS)
    if lang:
        return lang
    
    # 4. Default
    return _DEFAULT_LANG
