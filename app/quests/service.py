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


# ---------------------------------------------------------------------------
# GLOBAL CONFIG
# ---------------------------------------------------------------------------

# Max total quests in stack (daily + weekly + storyline + bonus)
BASE_MAX_QUESTS = 40

# How many days of daily quests can backlog
DAILY_BACKLOG_DAYS = 7


def get_player_max_quests(player: Player) -> int:
    """Global max amount of active quests a player can have."""
    return BASE_MAX_QUESTS


def get_player_daily_slots(player: Player) -> int:
    """
    Daily quests per day:
      - Base = 3
      - +1 per 5 levels
    """
    lvl = int(player.level or 0)
    return 3 + (lvl // 5)


def can_player_receive_quest(session: Session, player: Player) -> bool:
    """Check global quest stack capacity."""
    active_count = (
        session.query(PlayerQuest)
        .filter(PlayerQuest.player_id == player.id)
        .filter(PlayerQuest.status == "active")
        .count()
    )
    return active_count < get_player_max_quests(player)


def _start_of_utc_day(now: dt.datetime) -> dt.datetime:
    """00:00:00 UTC of given datetime."""
    return dt.datetime(now.year, now.month, now.day)


def _start_of_utc_week(now: dt.datetime) -> dt.datetime:
    """
    Monday 00:00 UTC of the current week.
    ISO weekday: Monday=1.
    """
    weekday = now.isoweekday()  # 1 = Monday
    monday = now - dt.timedelta(days=weekday - 1)
    return dt.datetime(monday.year, monday.month, monday.day)


def _date_only(dt_value: dt.datetime) -> dt.date:
    return dt.date(dt_value.year, dt_value.month, dt_value.day)


def _random_quantity(obj_tpl: Dict[str, Any]) -> int:
    qmin = int(obj_tpl.get("quantity_min", 1))
    qmax = int(obj_tpl.get("quantity_max", qmin))
    if qmax < qmin:
        qmax = qmin
    return random.randint(qmin, qmax)


def _pick_from_list_or_single(values: Any) -> Optional[str]:
    if not values:
        return None
    if isinstance(values, list):
        return random.choice(values)
    if isinstance(values, str):
        return values
    return None


def _compute_expires_at(
    quest_type: str,
    now: Optional[dt.datetime] = None,
) -> Optional[dt.datetime]:
    if now is None:
        now = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)

    qtype = (quest_type or "").lower()

    if qtype == "daily":
        return now + dt.timedelta(days=1)
    if qtype == "weekly":
        return now + dt.timedelta(days=7)

    # NEW : autres quêtes non-storyline => expiration « lambda » (ex: 30 jours)
    if qtype in ("bonus", "event", "other"):
        return now + dt.timedelta(days=30)

    # Storyline et types inconnus : pas d'expiration
    return None


def _generate_rewards_from_template(rewards_tpl: Dict[str, Any]) -> Dict[str, Any]:
    coins_min = int(rewards_tpl.get("coins_min", 0))
    coins_max = int(rewards_tpl.get("coins_max", coins_min))
    if coins_max < coins_min:
        coins_max = coins_min

    diams_min = int(rewards_tpl.get("diams_min", 0))
    diams_max = int(rewards_tpl.get("diams_max", diams_min))
    if diams_max < diams_min:
        diams_max = diams_min

    return {
        "coins": random.randint(coins_min, coins_max),
        "diams": random.randint(diams_min, diams_max),
    }


# ---------------------------------------------------------------------------
# QUEST INSTANCE CREATION
# ---------------------------------------------------------------------------

def create_quest_instance_from_template(
    session: Session,
    player: Player,
    template_key: str,
    source: str,
    now: Optional[dt.datetime] = None,
) -> PlayerQuest:

    if now is None:
        now = dt.datetime.utcnow()

    tpl = QUEST_TEMPLATES.get(template_key)
    if not tpl:
        raise ValueError(f"Quest template '{template_key}' not found.")

    qtype = tpl.get("quest_type", "daily")
    title = tpl.get("title", {})
    desc = tpl.get("description", {})
    objectives_tpl = tpl.get("objective_templates", [])
    rewards_tpl = tpl.get("reward_templates", {})

    quest = PlayerQuest(
        player_id=player.id,
        template_key=template_key,
        quest_type=qtype,
        source=source,
        title_fr=title.get("fr", template_key),
        title_en=title.get("en", template_key),
        description_fr=desc.get("fr", ""),
        description_en=desc.get("en", ""),
        status="active",
        started_at=now,
        expires_at=_compute_expires_at(qtype, now),
        rewards_json=_generate_rewards_from_template(rewards_tpl),
    )

    session.add(quest)
    session.flush()  # get quest.id

    # OBJECTIVES
    for idx, obj_tpl in enumerate(objectives_tpl):
        kind = obj_tpl.get("kind")
        if not kind:
            continue

        # Valeurs "classiques"
        resource_key = _pick_from_list_or_single(obj_tpl.get("resource_keys"))
        item_key = _pick_from_list_or_single(obj_tpl.get("item_keys"))

        # 🔹 Cas particulier : unlock_land
        # On utilise land_keys pour remplir item_key (ex: "land_cave")
        if kind == "unlock_land" and not item_key:
            land_key = _pick_from_list_or_single(obj_tpl.get("land_keys"))
            if land_key:
                item_key = land_key

        obj = PlayerQuestObjective(
            player_quest_id=quest.id,
            index_in_quest=idx,
            kind=kind,
            resource_key=resource_key,
            item_key=item_key,
            target_value=_random_quantity(obj_tpl),
            current_value=0,
            ignore_boosts=bool(obj_tpl.get("ignore_boosts", False)),
            consecutive_required=bool(obj_tpl.get("consecutive_required", False)),
        )
        session.add(obj)

    return quest


# ---------------------------------------------------------------------------
# DAILY QUESTS (BACKLOG)
# ---------------------------------------------------------------------------

def assign_daily_quest_if_needed(session: Session, player: Player, now=None):
    if now is None:
        now = dt.datetime.utcnow()

    today = _date_only(now)
    first_day = today - dt.timedelta(days=DAILY_BACKLOG_DAYS - 1)

    last_created = None
    current = first_day

    while current <= today:
        day_start = dt.datetime(current.year, current.month, current.day)
        day_end = day_start + dt.timedelta(days=1)

        day_quests = (
            session.query(PlayerQuest)
            .filter(PlayerQuest.player_id == player.id)
            .filter(PlayerQuest.source == "auto_daily")
            .filter(PlayerQuest.started_at >= day_start)
            .filter(PlayerQuest.started_at < day_end)
            .all()
        )

        existing_count = len(day_quests)
        allowed = get_player_daily_slots(player)

        used_keys = set(q.template_key for q in day_quests)

        while existing_count < allowed:
            if not can_player_receive_quest(session, player):
                return last_created

            tpl = pick_random_daily_template_for_source(
                source="auto_daily",
                exclude_keys=used_keys,
            )
            if not tpl:
                break

            quest = create_quest_instance_from_template(
                session=session,
                player=player,
                template_key=tpl["key"],
                source="auto_daily",
                now=day_start,
            )

            used_keys.add(tpl["key"])
            existing_count += 1
            last_created = quest

        current += dt.timedelta(days=1)

    return last_created


def pick_random_daily_template_for_source(source, exclude_keys=None):
    if exclude_keys is None:
        exclude_keys = set()
    candidates = []

    for tpl in QUEST_TEMPLATES.values():
        if tpl.get("quest_type") != "daily":
            continue
        if tpl.get("key") in exclude_keys:
            continue
        if source in (tpl.get("sources") or []):
            candidates.append(tpl)

    return random.choice(candidates) if candidates else None


# ---------------------------------------------------------------------------
# WEEKLY — SIMPLE VERSION (ONE WEEKLY PER WEEK)
# ---------------------------------------------------------------------------

def assign_weekly_quest_if_needed(session: Session, player: Player, now=None):
    """Simple version: ensure 1 auto_weekly per week."""
    if now is None:
        now = dt.datetime.utcnow()

    week_start = _start_of_utc_week(now)

    # Already has a weekly this week?
    existing = (
        session.query(PlayerQuest)
        .filter(PlayerQuest.player_id == player.id)
        .filter(PlayerQuest.source == "auto_weekly")
        .filter(PlayerQuest.started_at >= week_start)
        .first()
    )
    if existing:
        return None

    if not can_player_receive_quest(session, player):
        return None

    tpl = pick_random_weekly_template_for_source(
        source="auto_weekly",
        player=player,
        now=now,
    )
    if not tpl:
        return None

    return create_quest_instance_from_template(
        session=session,
        player=player,
        template_key=tpl["key"],
        source="auto_weekly",
        now=now,
    )


def pick_random_weekly_template_for_source(source, player=None, now=None):
    if now is None:
        now = dt.datetime.utcnow()

    def _parse_date(val):
        if not val:
            return None
        try:
            return dt.datetime.fromisoformat(val)
        except Exception:
            return None

    candidates = []
    for tpl in QUEST_TEMPLATES.values():
        if tpl.get("quest_type") != "weekly":
            continue
        if source not in (tpl.get("sources") or []):
            continue

        if not tpl.get("enabled", True):
            continue

        min_level = tpl.get("min_player_level")
        if min_level and player and player.level < min_level:
            continue

        start = _parse_date(tpl.get("available_from"))
        end = _parse_date(tpl.get("available_until"))

        if start and now < start:
            continue
        if end and now >= end:
            continue

        candidates.append(tpl)

    return random.choice(candidates) if candidates else None


# ---------------------------------------------------------------------------
# STORYLINE
# ---------------------------------------------------------------------------

def assign_next_storyline_quest_if_needed(session: Session, player: Player, now=None):
    if now is None:
        now = dt.datetime.utcnow()

    active = (
        session.query(PlayerQuest)
        .filter(PlayerQuest.player_id == player.id)
        .filter(PlayerQuest.quest_type == "storyline")
        .filter(PlayerQuest.status.in_(["active", "ready"]))
        .first()
    )
    if active:
        return None

    completed_keys = {
        q.template_key
        for q in session.query(PlayerQuest)
        .filter(PlayerQuest.player_id == player.id)
        .filter(PlayerQuest.quest_type == "storyline")
        .filter(PlayerQuest.status == "completed")
        .all()
    }

    storyline_tpls = [
        tpl for tpl in QUEST_TEMPLATES.values()
        if tpl.get("quest_type") == "storyline" and tpl.get("enabled", True)
    ]

    if not storyline_tpls:
        return None

    def _key(tpl):
        return (
            tpl.get("storyline_id") or "",
            tpl.get("storyline_step") or 0,
            tpl.get("key") or "",
        )

    storyline_tpls.sort(key=_key)
    candidate = None

    for tpl in storyline_tpls:
        key = tpl.get("key")
        if not key or key in completed_keys:
            continue

        required = tpl.get("requires_quests_completed") or []
        if any(r not in completed_keys for r in required):
            continue

        min_level = tpl.get("min_player_level")
        if min_level and player.level < min_level:
            continue

        candidate = tpl
        break

    if not candidate:
        return None

    if not can_player_receive_quest(session, player):
        return None

    return create_quest_instance_from_template(
        session=session,
        player=player,
        template_key=candidate["key"],
        source="system_storyline",
        now=now,
    )


# ---------------------------------------------------------------------------
# PROGRESSION HOOKS
# ---------------------------------------------------------------------------

def try_complete_quest(
    session: Session,
    player: Player,
    quest: PlayerQuest,
    now: Optional[dt.datetime] = None,
) -> bool:
    """
    V2 — On NE termine PLUS réellement la quête ici.

    Rôle maintenant :
      - Vérifier si tous les objectifs sont atteints
      - Si oui, passer la quête en statut "ready"
      - NE PAS appliquer les récompenses
      - NE PAS consommer de ressources

    La vraie "validation" (récompenses + retrait de ressources)
    sera faite plus tard via un endpoint /api/quests/claim.
    """
    if quest.status != "active":
        return False

    if now is None:
        now = dt.datetime.utcnow()

    # Si un objectif n'est pas encore atteint -> on ne fait rien
    if any(obj.current_value < obj.target_value for obj in quest.objectives):
        return False

    # On passe simplement la quête en "ready"
    quest.status = "ready"
    quest.completed_at = now  # moment où les objectifs sont remplis

    print(
        f"[quests] Player {player.id} finished objectives for quest {quest.id} "
        f"({quest.template_key}), status set to 'ready'."
    )

    # IMPORTANT : pas de _apply_quest_rewards ici !
    return True


def on_resource_collected(session, player, resource_key, base_amount, now=None):
    if now is None:
        now = dt.datetime.utcnow()
    if base_amount <= 0:
        return

    quests = (
        session.query(PlayerQuest)
        .filter(PlayerQuest.player_id == player.id)
        .filter(PlayerQuest.status == "active")
        .all()
    )

    for q in quests:
        updated = False
        for obj in q.objectives:
            if obj.kind == "collect_resource" and obj.resource_key == resource_key:
                nv = min(obj.current_value + base_amount, obj.target_value)
                if nv != obj.current_value:
                    obj.current_value = nv
                    updated = True

        if updated:
            try_complete_quest(session, player, q, now=now)


def on_item_crafted(
    session: Session,
    player: Player,
    item_key: str,
    quantity: int,
    now: Optional[dt.datetime] = None,
) -> None:
    """
    Called whenever the player crafts one or more items.

    - item_key: internal item key (ex: "rope")
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

            # ✅ Accepter soit "rope" soit "item_rope"
            if obj.item_key not in (item_key, f"item_{item_key}"):
                continue

            new_value = obj.current_value + quantity
            if new_value > obj.target_value:
                new_value = obj.target_value

            if new_value != obj.current_value:
                obj.current_value = new_value
                updated = True

        if updated:
            try_complete_quest(session, player, quest, now=now)


def on_land_unlocked(
    session: Session,
    player: Player,
    land_key: str,
    now: Optional[dt.datetime] = None,
) -> None:
    """
    Hook générique appelé quand un land est débloqué (via carte land_*).

    Il met à jour les objectifs de type "unlock_land" dont item_key == land_key.
    """
    if now is None:
        now = dt.datetime.utcnow()

    land_key = (land_key or "").strip()
    if not land_key:
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
            if obj.kind != "unlock_land":
                continue
            if obj.item_key != land_key:
                continue

            new_value = obj.current_value + 1
            if new_value > obj.target_value:
                new_value = obj.target_value

            if new_value != obj.current_value:
                obj.current_value = new_value
                updated = True

        if updated:
            try_complete_quest(session, player, quest, now=now)


def on_card_granted(
    session: Session,
    player: Player,
    card_key: str,
    now: Optional[dt.datetime] = None,
) -> None:
    """
    Hook appelé quand une carte est donnée au joueur (level-up, shop, etc.).

    - générique : pour toute carte land_*, on met à jour les objectifs "unlock_land"
    - spécifique : quand le joueur reçoit la carte 'land_cave', on termine
      la quête storyline 'qt_story_cave_01_prepare' s'il l'a en cours.
    """
    if now is None:
        now = dt.datetime.utcnow()

    card_key = (card_key or "").strip()
    if not card_key:
        return

    # Cas générique : toute carte land_* débloque un land
    if card_key.startswith("land_"):
        # land_key = card_key (même convention)
        on_land_unlocked(session, player, land_key=card_key, now=now)

    # Cas spécifique : préparer la grotte (quête cave 01)
    if card_key == "land_cave":
        quest = (
            session.query(PlayerQuest)
            .filter(
                PlayerQuest.player_id == player.id,
                PlayerQuest.template_key == "qt_story_cave_01_prepare",
                PlayerQuest.status.in_(["active", "ready"]),
            )
            .order_by(PlayerQuest.id.desc())
            .first()
        )
        if not quest:
            return

        # On la complète directement
        quest.status = "completed"
        quest.completed_at = now

        _apply_quest_rewards(player, quest)

        print(
            f"[quests] Player {player.id} auto-completed cave storyline quest "
            f"{quest.id} ({quest.template_key}) on land_cave unlock."
        )


# ---------------------------------------------------------------------------
# REWARDS APPLICATION (réutilisé par /api/quests/claim)
# ---------------------------------------------------------------------------

def _apply_quest_rewards(player: Player, quest: PlayerQuest) -> None:
    """
    Applique les récompenses de la quête au joueur (coins, diams, etc.).
    Le commit est géré par l'appelant.
    """
    rewards = quest.rewards_json or {}

    coins = int(rewards.get("coins", 0) or 0)
    diams = int(rewards.get("diams", 0) or 0)

    if coins:
        player.coins += coins
    if diams:
        player.diams += diams

    # Plus tard : resources, items, cards, etc.


# ---------------------------------------------------------------------------
# AUTO-MARK EXPIRED QUESTS
# ---------------------------------------------------------------------------

def auto_mark_expired_quests(
    session: Session,
    player: Player,
    now: Optional[dt.datetime] = None,
) -> int:
    """
    Passe automatiquement en 'expired' toutes les quêtes actives ou prêtes
    dont expires_at est dépassé.

    Retourne le nombre de quêtes modifiées.
    """
    if now is None:
        now = dt.datetime.utcnow()

    to_expire = (
        session.query(PlayerQuest)
        .filter(PlayerQuest.player_id == player.id)
        .filter(PlayerQuest.status.in_(["active", "ready"]))
        .filter(PlayerQuest.expires_at.isnot(None))
        .filter(PlayerQuest.expires_at < now)
        .all()
    )

    changed = 0
    for q in to_expire:
        q.status = "expired"
        if q.completed_at is None:
            q.completed_at = now
        changed += 1

    if changed:
        print(f"[quests] auto_mark_expired_quests: player={player.id}, changed={changed}")

    return changed


# ---------------------------------------------------------------------------
# SERIALIZER
# ---------------------------------------------------------------------------

def serialize_quest(quest: PlayerQuest) -> dict:

    def _to_iso(dt_value):
        return dt_value.isoformat() if dt_value is not None else None

    return {
        "id": quest.id,
        "template_key": quest.template_key,
        "quest_type": quest.quest_type,
        "source": quest.source,
        "title_fr": quest.title_fr,
        "title_en": quest.title_en,
        "description_fr": quest.description_fr,
        "description_en": quest.description_en,
        "status": quest.status,
        "rewards": quest.rewards_json or {},
        "started_at": _to_iso(quest.started_at),
        "expires_at": _to_iso(quest.expires_at),
        "completed_at": _to_iso(quest.completed_at),
        "objectives": [
            {
                "index": o.index_in_quest,
                "kind": o.kind,
                "resource_key": o.resource_key,
                "item_key": o.item_key,
                "current": o.current_value,
                "target": o.target_value,
                "ignore_boosts": o.ignore_boosts,
                "consecutive_required": o.consecutive_required,
            }
            for o in quest.objectives
        ],
    }
