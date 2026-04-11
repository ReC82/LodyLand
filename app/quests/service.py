# app/quests/service.py
# Service de quêtes : génération procédurale, progression, récompenses.

from __future__ import annotations

import datetime as dt
import random
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Player, PlayerQuest, PlayerQuestObjective
from app.quests.loader import QUEST_TEMPLATES  # conservé pour les quêtes storyline


# ---------------------------------------------------------------------------
# CONFIGURATION GLOBALE
# ---------------------------------------------------------------------------

# Niveau minimum pour accéder aux quêtes
QUEST_MIN_LEVEL = 3

# Plafond de quêtes par tier par jour (évite des montants absurdes aux hauts niveaux)
MAX_DAILY_PER_TIER = 10

# Plafond de quêtes hebdomadaires par tier (indépendant du niveau)
MAX_WEEKLY_PER_TIER = 3


# ---------------------------------------------------------------------------
# HELPERS GÉNÉRAUX
# ---------------------------------------------------------------------------

def _start_of_utc_week(now: dt.datetime) -> dt.datetime:
    """Lundi 00:00 UTC de la semaine courante."""
    weekday = now.isoweekday()  # 1 = Lundi
    monday = now - dt.timedelta(days=weekday - 1)
    return dt.datetime(monday.year, monday.month, monday.day)


def can_player_receive_quest(session: Session, player: Player) -> bool:
    """Vérifie que le joueur n'a pas trop de quêtes actives."""
    active_count = (
        session.query(PlayerQuest)
        .filter(PlayerQuest.player_id == player.id)
        .filter(PlayerQuest.status.in_(["active", "ready"]))
        .count()
    )
    return active_count < 100  # limite large, on ne bloque presque jamais


def _get_unlocked_lands(session: Session, player: Player) -> set:
    """Retourne l'ensemble des card_keys de lands débloqués (qty > 0)."""
    from app.models import PlayerCard
    cards = (
        session.query(PlayerCard)
        .filter(
            PlayerCard.player_id == player.id,
            PlayerCard.card_key.like("land_%"),
            PlayerCard.qty > 0,
        )
        .all()
    )
    return {c.card_key for c in cards}


def _difficulty_of(quest: PlayerQuest) -> str:
    """Retourne la difficulté d'une quête (générée ou template legacy)."""
    # Quêtes générées : difficulté stockée dans rewards_json
    rj = quest.rewards_json or {}
    if "difficulty" in rj:
        return rj["difficulty"]
    # Legacy : cherche dans les templates YAML
    tpl = QUEST_TEMPLATES.get(quest.template_key, {})
    return tpl.get("difficulty") or "easy"


# ---------------------------------------------------------------------------
# ATTRIBUTION — QUÊTES QUOTIDIENNES
# ---------------------------------------------------------------------------

def assign_daily_quest_if_needed(session: Session, player: Player, now=None):
    """
    Garantit que le joueur a exactement N quêtes par tier (easy/medium/hard)
    pour la journée en cours, où N = min(level, MAX_DAILY_PER_TIER).

    - Purge automatiquement l'excédent (garde les quêtes avec le plus de progression)
    - Génère les quêtes manquantes
    """
    if (player.level or 0) < QUEST_MIN_LEVEL:
        return

    if now is None:
        now = dt.datetime.utcnow()

    from app.quests.generator import generate_quest
    from sqlalchemy import or_

    today = now.date()
    day_start = dt.datetime(today.year, today.month, today.day)

    n_per_tier     = min(int(player.level or 0), MAX_DAILY_PER_TIER)
    unlocked_lands = _get_unlocked_lands(session, player)

    # Toutes les quêtes daily encore actives (non expirées)
    existing = (
        session.query(PlayerQuest)
        .filter(
            PlayerQuest.player_id == player.id,
            PlayerQuest.quest_type == "daily",
            PlayerQuest.status.in_(["active", "ready"]),
            or_(PlayerQuest.expires_at.is_(None), PlayerQuest.expires_at > now),
        )
        .all()
    )

    # Quêtes daily complétées aujourd'hui : comptées pour ne pas générer de remplaçants
    completed_today: Dict[str, int] = {}
    for q in (
        session.query(PlayerQuest)
        .filter(
            PlayerQuest.player_id == player.id,
            PlayerQuest.quest_type == "daily",
            PlayerQuest.status == "completed",
            PlayerQuest.started_at >= day_start,
        )
        .all()
    ):
        diff = _difficulty_of(q)
        completed_today[diff] = completed_today.get(diff, 0) + 1

    by_difficulty: Dict[str, list] = {"easy": [], "medium": [], "hard": []}
    for q in existing:
        diff = _difficulty_of(q)
        by_difficulty.setdefault(diff, []).append(q)

    # Purge l'excédent : on garde les quêtes avec le plus de progression
    for difficulty in ("easy", "medium", "hard"):
        quests = by_difficulty.get(difficulty, [])
        if len(quests) > n_per_tier:
            # Trie par progression décroissante pour garder les plus avancées
            by_prog = sorted(
                quests,
                key=lambda q: sum(o.current_value for o in q.objectives),
                reverse=True,
            )
            to_keep   = set(id(q) for q in by_prog[:n_per_tier])
            to_expire = [q for q in quests if id(q) not in to_keep]
            for q in to_expire:
                q.status = "expired"
                if q.completed_at is None:
                    q.completed_at = now
            by_difficulty[difficulty] = by_prog[:n_per_tier]

    # Génère les quêtes manquantes (actives + complétées aujourd'hui = quota du jour)
    for difficulty in ("easy", "medium", "hard"):
        current = len(by_difficulty.get(difficulty, [])) + completed_today.get(difficulty, 0)
        while current < n_per_tier:
            if not can_player_receive_quest(session, player):
                return
            quest = generate_quest(
                session=session,
                player=player,
                difficulty=difficulty,
                quest_type="daily",
                unlocked_land_keys=unlocked_lands,
                now=day_start,
            )
            if quest is None:
                break
            current += 1


# ---------------------------------------------------------------------------
# ATTRIBUTION — QUÊTES HEBDOMADAIRES
# ---------------------------------------------------------------------------

def assign_weekly_quest_if_needed(session: Session, player: Player, now=None):
    """
    Garantit exactement 1 quête par tier (easy/medium/hard) pour la semaine en cours.
    Purge l'excédent éventuel (ancien système).
    """
    if (player.level or 0) < QUEST_MIN_LEVEL:
        return

    if now is None:
        now = dt.datetime.utcnow()

    from app.quests.generator import generate_quest
    from sqlalchemy import or_

    week_start     = _start_of_utc_week(now)
    unlocked_lands = _get_unlocked_lands(session, player)

    # Toutes les quêtes weekly encore actives (non expirées)
    existing = (
        session.query(PlayerQuest)
        .filter(
            PlayerQuest.player_id == player.id,
            PlayerQuest.quest_type == "weekly",
            PlayerQuest.status.in_(["active", "ready"]),
            or_(PlayerQuest.expires_at.is_(None), PlayerQuest.expires_at > now),
        )
        .all()
    )

    by_difficulty: Dict[str, list] = {"easy": [], "medium": [], "hard": []}
    for q in existing:
        diff = _difficulty_of(q)
        by_difficulty.setdefault(diff, []).append(q)

    # Purge l'excédent (max 1 par tier pour les weekly)
    for difficulty in ("easy", "medium", "hard"):
        quests = by_difficulty.get(difficulty, [])
        if len(quests) > MAX_WEEKLY_PER_TIER:
            by_prog = sorted(
                quests,
                key=lambda q: sum(o.current_value for o in q.objectives),
                reverse=True,
            )
            to_keep = set(id(q) for q in by_prog[:MAX_WEEKLY_PER_TIER])
            for q in quests:
                if id(q) not in to_keep:
                    q.status = "expired"
                    if q.completed_at is None:
                        q.completed_at = now
            by_difficulty[difficulty] = by_prog[:MAX_WEEKLY_PER_TIER]

    # Génère les quêtes manquantes (1 par tier)
    for difficulty in ("easy", "medium", "hard"):
        if by_difficulty.get(difficulty):
            continue  # déjà 1 quête pour ce tier
        if not can_player_receive_quest(session, player):
            return
        generate_quest(
            session=session,
            player=player,
            difficulty=difficulty,
            quest_type="weekly",
            unlocked_land_keys=unlocked_lands,
            now=week_start,
        )


# ---------------------------------------------------------------------------
# ATTRIBUTION — QUÊTE CONTINUE
# ---------------------------------------------------------------------------

def assign_continuous_quest_if_needed(
    session: Session,
    player: Player,
    exclude_quest_id: int | None = None,
    now=None,
):
    """
    Garantit que le joueur a toujours exactement 1 quête continue active.
    Purge les doublons éventuels (ancien système).
    """
    if (player.level or 0) < QUEST_MIN_LEVEL:
        return None

    if now is None:
        now = dt.datetime.utcnow()

    from app.quests.generator import generate_quest

    # Récupère toutes les quêtes continues actives
    all_active = (
        session.query(PlayerQuest)
        .filter(
            PlayerQuest.player_id == player.id,
            PlayerQuest.quest_type == "continuous",
            PlayerQuest.status.in_(["active", "ready"]),
        )
        .order_by(PlayerQuest.started_at.desc())
        .all()
    )

    # Purge les doublons : on garde la plus récente, on expire les autres
    if len(all_active) > 1:
        for q in all_active[1:]:
            q.status = "expired"
            if q.completed_at is None:
                q.completed_at = now
        all_active = all_active[:1]

    # La quête active (hors celle qu'on vient de terminer)
    existing = next(
        (q for q in all_active if q.id != exclude_quest_id),
        None,
    )
    if existing:
        return existing

    unlocked_lands = _get_unlocked_lands(session, player)
    difficulty = random.choices(
        ["easy", "medium", "hard"],
        weights=[3, 2, 1],
        k=1,
    )[0]

    return generate_quest(
        session=session,
        player=player,
        difficulty=difficulty,
        quest_type="continuous",
        unlocked_land_keys=unlocked_lands,
        now=now,
    )


# ---------------------------------------------------------------------------
# STORYLINE — basée sur les templates YAML (inchangée)
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

    if not candidate or not can_player_receive_quest(session, player):
        return None

    return _create_from_template(session, player, candidate["key"], "system_storyline", now)


# ---------------------------------------------------------------------------
# CRÉATION DE QUÊTE DEPUIS UN TEMPLATE (uniquement pour storyline/legacy)
# ---------------------------------------------------------------------------

def _create_from_template(
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
        raise ValueError(f"Template '{template_key}' introuvable.")

    qtype = tpl.get("quest_type", "daily")
    title = tpl.get("title", {})
    desc  = tpl.get("description", {})
    objectives_tpl = tpl.get("objective_templates", [])
    rewards_tpl    = tpl.get("reward_templates", {})

    # Calcul expiration (legacy)
    if qtype == "daily":
        tomorrow = now.date() + dt.timedelta(days=1)
        expires  = dt.datetime(tomorrow.year, tomorrow.month, tomorrow.day)
    elif qtype == "weekly":
        days_to_monday = (8 - now.isoweekday()) % 7 or 7
        next_monday = now.date() + dt.timedelta(days=days_to_monday)
        expires = dt.datetime(next_monday.year, next_monday.month, next_monday.day)
    else:
        expires = None

    shards_min = int(rewards_tpl.get("shards_min", rewards_tpl.get("coins_min", 0)))
    shards_max = int(rewards_tpl.get("shards_max", rewards_tpl.get("coins_max", shards_min)))
    ess_min    = int(rewards_tpl.get("essence_min", rewards_tpl.get("diams_min", 0)))
    ess_max    = int(rewards_tpl.get("essence_max", rewards_tpl.get("diams_max", ess_min)))
    xp_min     = int(rewards_tpl.get("xp_min", 0))
    xp_max     = int(rewards_tpl.get("xp_max", xp_min))

    rewards_json = {
        "shards":     random.randint(shards_min, max(shards_min, shards_max)),
        "essence":    random.randint(ess_min,    max(ess_min,    ess_max)),
        "xp":         random.randint(xp_min,     max(xp_min,     xp_max)),
        "difficulty": tpl.get("difficulty") or "easy",
    }

    quest = PlayerQuest(
        player_id      = player.id,
        template_key   = template_key,
        quest_type     = qtype,
        source         = source,
        title_fr       = title.get("fr", template_key),
        title_en       = title.get("en", template_key),
        description_fr = desc.get("fr", ""),
        description_en = desc.get("en", ""),
        status         = "active",
        started_at     = now,
        expires_at     = expires,
        rewards_json   = rewards_json,
    )
    session.add(quest)
    session.flush()

    for idx, obj_tpl in enumerate(objectives_tpl):
        kind = obj_tpl.get("kind")
        if not kind:
            continue

        resource_key = _pick_any(obj_tpl.get("resource_keys"))
        item_key     = _pick_any(obj_tpl.get("item_keys"))

        if kind == "unlock_land" and not item_key:
            item_key = _pick_any(obj_tpl.get("land_keys"))

        qmin = int(obj_tpl.get("quantity_min", 1))
        qmax = int(obj_tpl.get("quantity_max", qmin))
        target = random.randint(qmin, max(qmin, qmax))

        session.add(PlayerQuestObjective(
            player_quest_id      = quest.id,
            index_in_quest       = idx,
            kind                 = kind,
            resource_key         = resource_key,
            item_key             = item_key,
            target_value         = target,
            current_value        = 0,
            ignore_boosts        = bool(obj_tpl.get("ignore_boosts", False)),
            consecutive_required = bool(obj_tpl.get("consecutive_required", False)),
        ))

    return quest


def _pick_any(values: Any) -> Optional[str]:
    if not values:
        return None
    if isinstance(values, list):
        return random.choice(values)
    if isinstance(values, str):
        return values
    return None


# ---------------------------------------------------------------------------
# HOOKS DE PROGRESSION
# ---------------------------------------------------------------------------

def try_complete_quest(
    session: Session,
    player: Player,
    quest: PlayerQuest,
    now: Optional[dt.datetime] = None,
) -> bool:
    """
    Vérifie si tous les objectifs sont atteints.
    Si oui, passe la quête en statut 'ready' (récompenses non encore appliquées).
    Retourne True si la quête vient de passer à 'ready'.
    """
    if quest.status != "active":
        return False
    if now is None:
        now = dt.datetime.utcnow()
    if any(obj.current_value < obj.target_value for obj in quest.objectives):
        return False

    quest.status       = "ready"
    quest.completed_at = now
    return True


def on_resource_collected(
    session: Session,
    player: Player,
    resource_key: str,
    base_amount: int,
    now=None,
) -> List[PlayerQuest]:
    """
    Hook appelé après chaque récolte de ressource.
    Met à jour la progression des quêtes actives.
    Retourne la liste des quêtes qui viennent de passer en 'ready'.
    """
    if now is None:
        now = dt.datetime.utcnow()
    if base_amount <= 0:
        return []

    quests = (
        session.query(PlayerQuest)
        .filter(PlayerQuest.player_id == player.id)
        .filter(PlayerQuest.status == "active")
        .all()
    )

    newly_ready: List[PlayerQuest] = []
    for q in quests:
        updated = False
        for obj in q.objectives:
            if obj.kind == "collect_resource" and obj.resource_key == resource_key:
                nv = min(obj.current_value + base_amount, obj.target_value)
                if nv != obj.current_value:
                    obj.current_value = nv
                    updated = True
        if updated and try_complete_quest(session, player, q, now=now):
            newly_ready.append(q)

    return newly_ready


def on_item_crafted(
    session: Session,
    player: Player,
    item_key: str,
    quantity: int,
    now: Optional[dt.datetime] = None,
) -> List[PlayerQuest]:
    """
    Hook appelé après chaque craft.
    Retourne la liste des quêtes qui viennent de passer en 'ready'.
    """
    if now is None:
        now = dt.datetime.utcnow()
    if quantity <= 0:
        return []

    active_quests = (
        session.query(PlayerQuest)
        .filter(PlayerQuest.player_id == player.id, PlayerQuest.status == "active")
        .all()
    )

    newly_ready: List[PlayerQuest] = []
    for quest in active_quests:
        updated = False
        for obj in quest.objectives:
            if obj.kind != "craft_item":
                continue
            if obj.item_key not in (item_key, f"item_{item_key}"):
                continue
            nv = min(obj.current_value + quantity, obj.target_value)
            if nv != obj.current_value:
                obj.current_value = nv
                updated = True
        if updated and try_complete_quest(session, player, quest, now=now):
            newly_ready.append(quest)

    return newly_ready


def on_land_unlocked(
    session: Session,
    player: Player,
    land_key: str,
    now: Optional[dt.datetime] = None,
) -> None:
    if now is None:
        now = dt.datetime.utcnow()
    land_key = (land_key or "").strip()
    if not land_key:
        return

    for quest in (
        session.query(PlayerQuest)
        .filter(PlayerQuest.player_id == player.id, PlayerQuest.status == "active")
        .all()
    ):
        updated = False
        for obj in quest.objectives:
            if obj.kind == "unlock_land" and obj.item_key == land_key:
                nv = min(obj.current_value + 1, obj.target_value)
                if nv != obj.current_value:
                    obj.current_value = nv
                    updated = True
        if updated:
            try_complete_quest(session, player, quest, now=now)


def on_card_granted(
    session: Session,
    player: Player,
    card_key: str,
    now: Optional[dt.datetime] = None,
) -> None:
    if now is None:
        now = dt.datetime.utcnow()
    card_key = (card_key or "").strip()
    if not card_key:
        return

    if card_key.startswith("land_"):
        on_land_unlocked(session, player, land_key=card_key, now=now)

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
        if quest:
            quest.status       = "completed"
            quest.completed_at = now
            _apply_quest_rewards(player, quest)


# ---------------------------------------------------------------------------
# APPLICATION DES RÉCOMPENSES
# ---------------------------------------------------------------------------

def _apply_quest_rewards(player: Player, quest: PlayerQuest) -> None:
    rewards = quest.rewards_json or {}
    shards  = int(rewards.get("shards",  rewards.get("coins",  0)) or 0)
    essence = int(rewards.get("essence", rewards.get("diams",  0)) or 0)
    xp      = int(rewards.get("xp", 0) or 0)

    if shards:
        player.shards  = (player.shards  or 0) + shards
    if essence:
        player.essence = (player.essence or 0) + essence
    if xp:
        player.xp      = (player.xp      or 0) + xp


# ---------------------------------------------------------------------------
# EXPIRATION AUTOMATIQUE
# ---------------------------------------------------------------------------

def auto_mark_expired_quests(
    session: Session,
    player: Player,
    now: Optional[dt.datetime] = None,
) -> int:
    """Passe en 'expired' toutes les quêtes dont expires_at est dépassé."""
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

    for q in to_expire:
        q.status = "expired"
        if q.completed_at is None:
            q.completed_at = now

    return len(to_expire)


# ---------------------------------------------------------------------------
# SÉRIALISEUR
# ---------------------------------------------------------------------------

def serialize_quest(quest: PlayerQuest) -> dict:
    def _to_iso(v):
        return v.isoformat() if v is not None else None

    rewards = dict(quest.rewards_json or {})
    # Extrait la difficulté depuis rewards_json (quêtes générées) ou template legacy
    difficulty = rewards.pop("difficulty", None)
    if not difficulty:
        tpl = QUEST_TEMPLATES.get(quest.template_key, {})
        difficulty = tpl.get("difficulty") or "easy"

    return {
        "id":             quest.id,
        "template_key":   quest.template_key,
        "quest_type":     quest.quest_type,
        "difficulty":     difficulty,
        "source":         quest.source,
        "title_fr":       quest.title_fr,
        "title_en":       quest.title_en,
        "description_fr": quest.description_fr,
        "description_en": quest.description_en,
        "status":         quest.status,
        "rewards":        rewards,
        "started_at":     _to_iso(quest.started_at),
        "expires_at":     _to_iso(quest.expires_at),
        "completed_at":   _to_iso(quest.completed_at),
        "objectives": [
            {
                "index":               o.index_in_quest,
                "kind":                o.kind,
                "resource_key":        o.resource_key,
                "item_key":            o.item_key,
                "current":             o.current_value,
                "target":              o.target_value,
                "ignore_boosts":       o.ignore_boosts,
                "consecutive_required": o.consecutive_required,
            }
            for o in quest.objectives
        ],
    }
