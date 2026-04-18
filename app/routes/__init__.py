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
from .api_craft import bp as craft_bp
from .api_lands import bp as lands_bp
from .village import bp as village_bp
from .api_quests import bp as quests_bp
from .api_village_trades import bp as village_trades_bp
from .api_village_cardshop import bp as village_cardshop_bp
from .api_village_pedro import bp as village_pedro_bp
from .api_temple import bp as temple_bp
from .api_temple_reconstruction import bp as temple_reconstruction_bp
from .api_notebook import bp as notebook_bp
from .api_minigame import bp as minigame_bp

from .api_i18n import bp as i18n_bp

def register_routes(app: Flask) -> None:
    """Enregistre tous les blueprints API sur l'app Flask."""
    app.register_blueprint(players_bp,   url_prefix="/api")
    app.register_blueprint(resources_bp, url_prefix="/api")
    app.register_blueprint(inventory_bp, url_prefix="/api")
    app.register_blueprint(daily_bp,     url_prefix="/api")
    app.register_blueprint(misc_bp,      url_prefix="/api")
    app.register_blueprint(cards_bp,     url_prefix="/api")
    app.register_blueprint(shop_bp,      url_prefix="/api")
    app.register_blueprint(craft_bp,     url_prefix="/api")
    app.register_blueprint(lands_bp,     url_prefix="/api")
    app.register_blueprint(quests_bp,    url_prefix="/api")
    
    app.register_blueprint(village_bp,     url_prefix="/village")
    app.register_blueprint(village_trades_bp, url_prefix="/api")
    app.register_blueprint(village_cardshop_bp, url_prefix="/api")
    app.register_blueprint(village_pedro_bp,   url_prefix="/api")

    app.register_blueprint(i18n_bp, url_prefix="/api")
    
    app.register_blueprint(temple_bp, url_prefix="/temple")
    app.register_blueprint(temple_reconstruction_bp, url_prefix="/temple")
    app.register_blueprint(notebook_bp, url_prefix="/api")
    app.register_blueprint(minigame_bp, url_prefix="/api")
    
