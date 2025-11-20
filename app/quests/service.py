# app/quests/service.py
# Core quest service: templates loading, instance creation, progression hooks.

from __future__ import annotations

import datetime as dt
import random
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Player, PlayerQuest, PlayerQuestObjective
from app.quests.loader import QUEST_TEMPLATES


# Base max quests per player (can be modified later with cards)
BASE_MAX_QUESTS = 10


def get_player_max_quests(player: Player) -> int:
    """
    Compute the max number of active quests a player can have.
    For now, this is a fixed base value (10).
    Later, you can add card effects / perks here.
    """
    return BASE_MAX_QUESTS


def count_active_quests(session: Session, player: Player) -> int:
    """
    Return the number of active quests for this player.
    """
    return (
        session.query(PlayerQuest)
        .filter(
            PlayerQuest.player_id == player.id,
            PlayerQuest.status == "active",
        )
        .count()
    )


def can_player_receive_quest(session: Session, player: Player) -> bool:
    """
    Check if the player still has a free slot in his quest stack.
    """
    max_quests = get_player_max_quests(player)
    active_count = count_active_quests(session, player)
    return active_count < max_quests


# -------------------------------------------------------------------------
# Template selection helpers
# -------------------------------------------------------------------------


def pick_random_daily_template_for_source(source: str) -> Optional[Dict[str, Any]]:
    """
    Pick a random quest template of type 'daily' that can be given
    by the provided source (e.g. 'auto_daily', 'villager_generic').

    Returns the raw template dict from QUEST_TEMPLATES or None if none match.
    """
    candidates = []
    for tpl in QUEST_TEMPLATES.values():
        if tpl.get("quest_type") != "daily":
            continue
        sources = tpl.get("sources") or []
        if source in sources:
            candidates.append(tpl)

    if not candidates:
        return None

    return random.choice(candidates)


# -------------------------------------------------------------------------
# Quest instance creation
# -------------------------------------------------------------------------


def _random_quantity(obj_tpl: Dict[str, Any]) -> int:
    """
    Compute a random quantity between quantity_min and quantity_max.
    If quantity_max is missing, use quantity_min.
    """
    qmin = int(obj_tpl.get("quantity_min", 1))
    qmax = int(obj_tpl.get("quantity_max", qmin))
    if qmax < qmin:
        qmax = qmin
    return random.randint(qmin, qmax)


def _pick_from_list_or_single(values: Any) -> Optional[str]:
    """
    Helper to pick a single key from either a list or a string.
    Returns None if values is falsy.
    """
    if not values:
        return None
    if isinstance(values, list):
        return random.choice(values)
    if isinstance(values, str):
        return values
    return None


def _compute_expires_at(quest_type: str, now: dt.datetime) -> Optional[dt.datetime]:
    """
    Compute a simple expires_at based on quest_type.
    For now:
    - daily  -> now + 1 day
    - weekly -> now + 7 days
    - others -> None
    """
    if quest_type == "daily":
        return now + dt.timedelta(days=1)
    if quest_type == "weekly":
        return now + dt.timedelta(days=7)
    return None


def _generate_rewards_from_template(rewards_tpl: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate concrete rewards from the reward_templates section.

    V1: only coins and diams.
    Later we can extend to items, resources, cards, etc.
    """
    coins_min = int(rewards_tpl.get("coins_min", 0))
    coins_max = int(rewards_tpl.get("coins_max", coins_min))
    if coins_max < coins_min:
        coins_max = coins_min

    diams_min = int(rewards_tpl.get("diams_min", 0))
    diams_max = int(rewards_tpl.get("diams_max", diams_min))
    if diams_max < diams_min:
        diams_max = diams_min

    coins = random.randint(coins_min, coins_max)
    diams = random.randint(diams_min, diams_max)

    rewards: Dict[str, Any] = {
        "coins": coins,
        "diams": diams,
    }

    # TODO: extend with resources / cards if needed later
    return rewards


def create_quest_instance_from_template(
    session: Session,
    player: Player,
    template_key: str,
    source: str,
    now: Optional[dt.datetime] = None,
) -> PlayerQuest:
    """
    Create a PlayerQuest + PlayerQuestObjective entries for a given player
    from a quest template (quests.yml).
    """
    if now is None:
        now = dt.datetime.utcnow()

    tpl = QUEST_TEMPLATES.get(template_key)
    if not tpl:
        raise ValueError(f"Quest template '{template_key}' not found in QUEST_TEMPLATES.")

    quest_type = tpl.get("quest_type", "daily")
    title = tpl.get("title") or {}
    description = tpl.get("description") or {}
    objectives_tpl = tpl.get("objective_templates") or []
    rewards_tpl = tpl.get("reward_templates") or {}

    title_fr = title.get("fr") or template_key
    title_en = title.get("en") or template_key
    desc_fr = description.get("fr") or ""
    desc_en = description.get("en") or ""

    # Generate concrete rewards
    rewards_concrete = _generate_rewards_from_template(rewards_tpl)

    # Create main quest instance
    quest = PlayerQuest(
        player_id=player.id,
        template_key=template_key,
        quest_type=quest_type,
        source=source,
        title_fr=title_fr,
        title_en=title_en,
        description_fr=desc_fr,
        description_en=desc_en,
        status="active",
        started_at=now,
        expires_at=_compute_expires_at(quest_type, now),
        rewards_json=rewards_concrete,
    )

    session.add(quest)
    session.flush()  # ensure quest.id is available

    # Create objectives
    objectives: list[PlayerQuestObjective] = []
    for idx, obj_tpl in enumerate(objectives_tpl):
        kind = (obj_tpl.get("kind") or "").strip()
        if not kind:
            continue

        resource_key = _pick_from_list_or_single(obj_tpl.get("resource_keys"))
        item_key = _pick_from_list_or_single(obj_tpl.get("item_keys"))

        target_value = _random_quantity(obj_tpl)

        obj = PlayerQuestObjective(
            player_quest_id=quest.id,
            index_in_quest=idx,
            kind=kind,
            resource_key=resource_key,
            item_key=item_key,
            target_value=target_value,
            current_value=0,
            ignore_boosts=bool(obj_tpl.get("ignore_boosts", False)),
            consecutive_required=bool(obj_tpl.get("consecutive_required", False)),
            extra_json=None,
        )
        session.add(obj)
        objectives.append(obj)

    quest.objectives = objectives

    return quest


# -------------------------------------------------------------------------
# Daily quest assignment
# -------------------------------------------------------------------------


def _start_of_utc_day(now: dt.datetime) -> dt.datetime:
    """
    Return the datetime corresponding to the start of the UTC day for 'now'.
    Used to check if a daily quest was already given today.
    """
    return dt.datetime(year=now.year, month=now.month, day=now.day)


def assign_daily_quest_if_needed(
    session: Session,
    player: Player,
    now: Optional[dt.datetime] = None,
) -> Optional[PlayerQuest]:
    """
    Ensure the player has at most one auto_daily quest per day.
    """
    if now is None:
        now = dt.datetime.utcnow()

    if not can_player_receive_quest(session, player):
        return None

    day_start = _start_of_utc_day(now)

    existing = (
        session.query(PlayerQuest)
        .filter(
            PlayerQuest.player_id == player.id,
            PlayerQuest.source == "auto_daily",
            PlayerQuest.started_at >= day_start,
            PlayerQuest.status == "active",
        )
        .first()
    )

    if existing:
        return None

    tpl = pick_random_daily_template_for_source("auto_daily")
    if not tpl:
        return None

    template_key = tpl.get("key")
    if not template_key:
        return None

    quest = create_quest_instance_from_template(
        session=session,
        player=player,
        template_key=template_key,
        source="auto_daily",
        now=now,
    )

    return quest


# -------------------------------------------------------------------------
# Quest completion & reward application
# -------------------------------------------------------------------------


def _apply_quest_rewards(player: Player, quest: PlayerQuest) -> None:
    """
    Apply quest rewards to the player object (coins, diams, etc.).
    Commit is handled by the caller.
    """
    rewards = quest.rewards_json or {}
    coins = int(rewards.get("coins", 0))
    diams = int(rewards.get("diams", 0))

    if coins:
        player.coins += coins
    if diams:
        player.diams += diams

    # TODO: extend with resources, items, cards later


def try_complete_quest(
    session: Session,
    player: Player,
    quest: PlayerQuest,
    now: Optional[dt.datetime] = None,
) -> bool:
    """
    Check if all objectives of the quest are completed.
    If yes:
      - mark quest as completed
      - apply rewards to the player
    Returns True if completion happened, False otherwise.
    """
    if quest.status != "active":
        return False

    if now is None:
        now = dt.datetime.utcnow()

    if any(obj.current_value < obj.target_value for obj in quest.objectives):
        return False

    quest.status = "completed"
    quest.completed_at = now

    _apply_quest_rewards(player, quest)

    print(
        f"[quests] Player {player.id} completed quest {quest.id} "
        f"({quest.template_key}), rewards={quest.rewards_json}"
    )

    return True


# -------------------------------------------------------------------------
# Progression hooks
# -------------------------------------------------------------------------


def on_resource_collected(
    session: Session,
    player: Player,
    resource_key: str,
    base_amount: int,
    now: Optional[dt.datetime] = None,
) -> None:
    """
    Called whenever the player collects resources.

    - resource_key: internal resource key (ex: "res_wood_branch")
    - base_amount: amount BEFORE boosts (for quest progression)
    """
    if now is None:
        now = dt.datetime.utcnow()

    if base_amount <= 0:
        return

    active_quests = (
        session.query(PlayerQuest)
        .filter(
            PlayerQuest.player_id == player.id,
            PlayerQuest.status == "active",
        )
        .all()
    )

    for quest in active_quests:
        updated = False

        for obj in quest.objectives:
            if obj.kind != "collect_resource":
                continue
            if obj.resource_key != resource_key:
                continue

            increment = base_amount
            new_value = obj.current_value + increment
            if new_value > obj.target_value:
                new_value = obj.target_value

            if new_value != obj.current_value:
                obj.current_value = new_value
                updated = True

        if updated:
            try_complete_quest(session, player, quest, now=now)


def on_item_crafted(
    session: Session,
    player: Player,
    item_key: str,
    quantity: int,
    now: Optional[dt.datetime] = None,
) -> None:
    """
    Called whenever the player crafts one or more items.

    - item_key: internal item key (ex: "item_rope")
    - quantity: number of items crafted in this action
    """
    if now is None:
        now = dt.datetime.utcnow()

    if quantity <= 0:
        return

    active_quests = (
        session.query(PlayerQuest)
        .filter(
            PlayerQuest.player_id == player.id,
            PlayerQuest.status == "active",
        )
        .all()
    )

    for quest in active_quests:
        updated = False

        for obj in quest.objectives:
            if obj.kind != "craft_item":
                continue
            if obj.item_key != item_key:
                continue

            new_value = obj.current_value + quantity
            if new_value > obj.target_value:
                new_value = obj.target_value

            if new_value != obj.current_value:
                obj.current_value = new_value
                updated = True

        if updated:
            try_complete_quest(session, player, quest, now=now)


# -------------------------------------------------------------------------
# Debug helper (optional)
# -------------------------------------------------------------------------


def debug_create_daily_quest_for_player(player_id: int, template_key: str) -> None:
    """
    Simple debug helper:
    - Opens a DB session
    - Loads the player
    - Creates a quest instance from the given template_key
    - Commits and prints some info
    """
    with SessionLocal() as session:
        player = session.query(Player).get(player_id)
        if not player:
            print(f"[quests_debug] Player {player_id} not found.")
            return

        if not can_player_receive_quest(session, player):
            print(f"[quests_debug] Player {player_id} has no free quest slot.")
            return

        quest = create_quest_instance_from_template(
            session=session,
            player=player,
            template_key=template_key,
            source="debug_manual",
        )

        session.commit()
        print(
            f"[quests_debug] Created quest {quest.id} for player {player_id} "
            f"from template '{template_key}' with {len(quest.objectives)} objectives."
        )
