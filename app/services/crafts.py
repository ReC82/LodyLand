# =============================================================================
# File: app/services/crafts.py
# Purpose: Centralized logic for craftable items & recipes.
#
# This module:
#   - reads definitions from craft_defs.CRAFT_DEFS (YAML source of truth)
#   - applies player context (owned cards, table level, etc.)
#   - returns API-friendly dicts for the frontend.
# =============================================================================
from __future__ import annotations

from typing import Any, Dict, List

import datetime as dt

from sqlalchemy.orm import Session

from app import craft_defs
from app.models import Player


def serialize_craft_def(
    item_key: str,
    cfg: Dict[str, Any],
    *,
    player: Player,
    is_unlocked: bool,
    craft_table_level: int,
    location: str = "craft_table",
) -> Dict[str, Any]:
    """
    Transform a raw craft item config (from YAML) into an API-friendly dict.

    This is similar in spirit to serialize_card_def for cards.
    """
    recipe = cfg.get("recipe") or {}
    unlock_cond = cfg.get("unlock_condition") or {}

    label = cfg.get("label") or cfg.get("key") or item_key
    description = cfg.get("description") or ""

    return {
        # identity
        "item_key": item_key,
        "key": item_key,
        "label": label,
        "description": description,
        "icon": cfg.get("icon"),

        # metadata
        "kind": cfg.get("kind"),
        "type": cfg.get("type") or cfg.get("kind"),
        "category": cfg.get("category"),
        "rarity": cfg.get("rarity"),
        "craftable": cfg.get("craftable", True),

        # recipe info
        "recipe": {
            "craft_location": recipe.get("craft_location") or location,
            "width": recipe.get("width"),
            "height": recipe.get("height"),
            "pattern": recipe.get("pattern") or [],
            "legend": recipe.get("legend") or {},
            "output_quantity": recipe.get("output_quantity") or 1,
            "craft_time_seconds": recipe.get("craft_time_seconds") or 0,
            "required_table_level": recipe.get("required_table_level") or 1,
        },

        # unlock info
        "unlock_condition": unlock_cond,
        "is_unlocked": is_unlocked,

        # context
        "craft_table_level": craft_table_level,
        "enabled": cfg.get("enabled", True),
    }


def _player_has_card(session: Session, player_id: int, card_key: str | None) -> bool:
    """Check if player owns at least 1 copy of a card."""
    if not card_key:
        return False

    from app.models import PlayerCard  # local import to avoid circular deps

    count = (
        session.query(PlayerCard)
        .filter_by(player_id=player_id, card_key=card_key)
        .count()
    )
    return count > 0


def is_craft_unlocked_for_player(
    session: Session,
    player: Player,
    cfg: Dict[str, Any],
    *,
    craft_table_level: int,
) -> bool:
    """
    Evaluate whether a given craft is usable by the player right now.

    - checks required_table_level vs craft_table_level
    - checks unlock_condition (card, level, etc.)
    """
    recipe = cfg.get("recipe") or {}
    required_table_level = int(recipe.get("required_table_level") or 1)
    if craft_table_level < required_table_level:
        return False

    unlock = cfg.get("unlock_condition") or {}
    utype = unlock.get("type")

    if utype == "card":
        card_key = unlock.get("key")
        if not _player_has_card(session, player.id, card_key):
            return False

    if utype == "level":
        min_level = int(unlock.get("min_level") or 1)
        if player.level < min_level:
            return False

    # Later you can add more conditions (lands, quests, etc.)
    return True


def list_crafts_for_location(
    session: Session,
    player: Player,
    *,
    location: str,
    craft_table_level: int,
) -> List[Dict[str, Any]]:
    """
    Main entrypoint for the /craft/recipes endpoint.

    Filters CRAFT_DEFS by location and returns serialized crafts for the player.
    """
    results: List[Dict[str, Any]] = []

    for item_key, cfg in craft_defs.CRAFT_DEFS.items():
        recipe = cfg.get("recipe") or {}
        craft_location = (
            recipe.get("craft_location") or cfg.get("station_key") or "craft_table"
        )

        if craft_location != location:
            continue

        is_unlocked = is_craft_unlocked_for_player(
            session=session,
            player=player,
            cfg=cfg,
            craft_table_level=craft_table_level,
        )

        results.append(
            serialize_craft_def(
                item_key=item_key,
                cfg=cfg,
                player=player,
                is_unlocked=is_unlocked,
                craft_table_level=craft_table_level,
                location=location,
            )
        )

    # Simple sort by label for now
    results.sort(key=lambda c: c.get("label") or "")
    return results

# =============================================================================
# Craft state helpers (table level + job updates)
# =============================================================================

def compute_craft_table_level(session: Session, player: Player) -> int:
    """
    Compute the craft table level for a player based on owned cards.

    Cards expected:
      - access_craft_table_basic
      - access_craft_table_medium
      - access_craft_table_advanced

    Levels:
      0 = no table
      1 = basic
      2 = medium
      3 = advanced
    """
    from app.models import PlayerCard  # local import to avoid circular deps

    def has_card(card_key: str) -> bool:
        return (
            session.query(PlayerCard)
            .filter_by(player_id=player.id, card_key=card_key)
            .count()
            > 0
        )

    level = 0
    has_basic = has_card("access_craft_table_basic")
    has_medium = has_card("access_craft_table_medium")
    has_advanced = has_card("access_craft_table_advanced")

    if has_basic or has_medium or has_advanced:
        level = max(level, 1)
    if has_medium or has_advanced:
        level = max(level, 2)
    if has_advanced:
        level = max(level, 3)

    return level


def get_craft_queue_max_slots(player: Player) -> int:
    """
    Return the total number of craft queue slots available to a player.
    Base is 2 (1 active + 1 queued). Each extra slot purchased adds 1 more.
    """
    extra = int(getattr(player, "craft_queue_extra_slots", 0) or 0)
    return 2 + extra


def get_craft_next_slot_cost(player: Player) -> int:
    """
    Cost in essence to unlock the next queue slot.
    Formula: 2^(extra_slots + 1)  →  2, 4, 8, 16 ...
    """
    extra = int(getattr(player, "craft_queue_extra_slots", 0) or 0)
    return 2 ** (extra + 1)


def update_craft_jobs_for_player(session: Session, player: Player) -> list:
    """
    Update all active and queued craft jobs for this player:
      - compute how many units should be completed based on time (active jobs)
      - credit missing items into PlayerItem
      - mark active job as done when finished
      - promote the next queued job to active

    Returns a list of item_keys that were just completed (for notifications).
    Notes:
      - This function does NOT commit; caller decides transaction boundaries.
    """
    from app.models import PlayerCraftJob, PlayerItem  # local import to avoid circular deps
    from app.quests.service import on_item_crafted

    now = dt.datetime.utcnow()
    just_completed: list = []

    # Process active jobs first
    active_jobs = (
        session.query(PlayerCraftJob)
        .filter(PlayerCraftJob.player_id == player.id)
        .filter(PlayerCraftJob.status == "active")
        .order_by(PlayerCraftJob.started_at.asc())
        .all()
    )

    for job in active_jobs:
        total = int(job.quantity_total or 0)
        done = int(job.quantity_done or 0)

        if total <= 0:
            job.status = "done"
            just_completed.append(job.item_key)
            continue

        total_duration = (job.ends_at - job.started_at).total_seconds()
        if total_duration <= 0:
            completed_units = total
        else:
            elapsed = (now - job.started_at).total_seconds()
            if elapsed <= 0:
                completed_units = 0
            else:
                per_unit = total_duration / total
                completed_units = int(elapsed // per_unit)
                if completed_units > total:
                    completed_units = total

        if completed_units > done:
            delta = completed_units - done

            pi = (
                session.query(PlayerItem)
                .filter_by(player_id=player.id, item_key=job.item_key)
                .one_or_none()
            )
            if pi is None:
                pi = PlayerItem(
                    player_id=player.id,
                    item_key=job.item_key,
                    quantity=delta,
                )
                session.add(pi)
            else:
                pi.quantity = int(pi.quantity or 0) + delta

            # Quest hook (reward for newly crafted units)
            on_item_crafted(
                session=session,
                player=player,
                item_key=job.item_key,
                quantity=delta,
            )

            job.quantity_done = completed_units

        if completed_units >= total or now >= job.ends_at:
            job.status = "done"
            just_completed.append(job.item_key)

    # After processing active jobs, check if we can promote a queued job
    still_has_active = (
        session.query(PlayerCraftJob)
        .filter(PlayerCraftJob.player_id == player.id)
        .filter(PlayerCraftJob.status == "active")
        .count()
    ) > 0

    if not still_has_active:
        # Find the oldest queued job and promote it
        next_queued = (
            session.query(PlayerCraftJob)
            .filter(PlayerCraftJob.player_id == player.id)
            .filter(PlayerCraftJob.status == "queued")
            .order_by(PlayerCraftJob.id.asc())
            .first()
        )
        if next_queued:
            # Get craft duration from CRAFT_DEFS
            cfg = craft_defs.CRAFT_DEFS.get(next_queued.item_key, {}) or {}
            recipe = cfg.get("recipe") or {}
            craft_time_seconds = int(recipe.get("craft_time_seconds") or 0)
            total_duration_secs = craft_time_seconds * int(next_queued.quantity_total or 1)

            next_queued.status = "active"
            next_queued.started_at = now
            next_queued.ends_at = now + dt.timedelta(seconds=total_duration_secs)

    return just_completed
