# =============================================================================
# File: app/routes/__init__.py
# Purpose: Regrouper et enregistrer tous les blueprints API.
# =============================================================================
from __future__ import annotations

from flask import Flask

from .api_players import bp as players_bp
from .api_resources import bp as resources_bp
from .api_inventory import bp as inventory_bp
from .api_daily import bp as daily_bp
from .api_misc import bp as misc_bp
from .api_cards import bp as cards_bp
from .api_shop import bp as shop_bp

def register_routes(app: Flask) -> None:
    """Enregistre tous les blueprints API sur l'app Flask."""
    app.register_blueprint(players_bp,   url_prefix="/api")
    app.register_blueprint(resources_bp, url_prefix="/api")
    app.register_blueprint(inventory_bp, url_prefix="/api")
    app.register_blueprint(daily_bp,     url_prefix="/api")
    app.register_blueprint(misc_bp,      url_prefix="/api")
    app.register_blueprint(cards_bp,     url_prefix="/api")
    app.register_blueprint(shop_bp,      url_prefix="/api")
