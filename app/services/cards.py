# =============================================================================
# File: app/services/cards.py
# Purpose: Helper functions to manage player cards (centralized logic).
# =============================================================================
from __future__ import annotations

from sqlalchemy.orm import Session
from app.models import PlayerCard, CardDef
from typing import Any

def set_player_card_qty(
    session: Session,
    player_id: int,
    card_key: str,
    qty: int,
) -> PlayerCard | None:
    """
    Set the quantity of a specific card for a given player.

    - If qty <= 0 and card exists -> delete it.
    - If card doesn't exist and qty > 0 -> create it.
    - If card exists and qty > 0 -> update qty.

    Returns:
        The PlayerCard instance (or None if deleted / nothing to keep).
    """
    pc = (
        session.query(PlayerCard)
        .filter_by(player_id=player_id, card_key=card_key)
        .first()
    )

    if qty <= 0:
        # delete existing card if any
        if pc is not None:
            session.delete(pc)
        return None

    if pc is None:
        pc = PlayerCard(player_id=player_id, card_key=card_key, qty=qty)
        session.add(pc)
    else:
        pc.qty = qty

    return pc


def give_player_card(
    session: Session,
    player_id: int,
    card_key: str,
    qty: int = 1,
) -> PlayerCard:
    """
    Increment the quantity of a specific card for a given player.

    If the card does not exist yet, it is created with qty.
    """
    pc = (
        session.query(PlayerCard)
        .filter_by(player_id=player_id, card_key=card_key)
        .first()
    )

    if pc is None:
        pc = PlayerCard(player_id=player_id, card_key=card_key, qty=qty)
        session.add(pc)
    else:
        pc.qty += qty

    return pc

def serialize_card_def(cd: CardDef, owned_qty: int = 0, context: str = "inventory") -> dict[str, Any]:
    """
    Adapter between the new CardDef model (card_*) and the legacy API shape.

    Returns a dict with the fields expected by the frontend today:
      - key, label, description, icon
      - categorie, rarity, type
      - gameplay, prices, shop, buy_rules
      - owned_qty
    """
    shop_cfg = cd.shop or {}

    # prices are stored inside shop in new schema
    prices = shop_cfg.get("prices") or []

    # buy_rules can live in shop or as unlock_rules
    buy_rules = shop_cfg.get("buy_rules") or cd.unlock_rules or {}

    # Rebuild a "legacy-like" shop block
    legacy_shop = {
        "show_in_main_shop": shop_cfg.get("show_in_main_shop", False),
        "show_in_village_shop": shop_cfg.get("show_in_village_shop", False),
        "buy_rules": buy_rules,
        "tradable": cd.tradable,
        "giftable": cd.giftable,
        "quantity": cd.card_quantity,
        "purchase_limit": cd.card_purchase_limit_quantity,
        "max_owned": cd.card_max_owned,
    }

    return {
        # Identité
        "key": cd.key,

        # Affichage (compat avec ancien front)
        "label": cd.card_label,
        "description": cd.card_description,
        "icon": cd.card_image,

        # Métadonnées
        "categorie": cd.card_category,
        "rarity": cd.card_rarity,
        "type": cd.card_type,

        # Gameplay & shop
        "gameplay": cd.card_gameplay or {},
        "prices": prices,
        "shop": legacy_shop,
        "buy_rules": buy_rules,

        # Flags
        "enabled": cd.enabled,
        "owned_qty": owned_qty,
    }