# =============================================================================
# File: app/services/cards.py
# Purpose: Helper functions to manage player cards (centralized logic).
# =============================================================================
from __future__ import annotations

from sqlalchemy.orm import Session
from app.models import PlayerCard


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
