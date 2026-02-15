# app/routes/api_players.py
from __future__ import annotations

from flask import Blueprint, jsonify, request, make_response

from app.db import SessionLocal
from app.models import (
    Player,
    Tile,
    ResourceStock,
    ResourceDef,
    PlayerCard,
    CardDef,
    PlayerItem,
    PlayerQuest,
    PlayerCraftJob,
    PlayerStoryFlag,
)
from app.progression import next_threshold, LEVELS, MAX_LEVEL, xp_required_for

from app.craft_defs import CRAFT_DEFS, ITEM_DEFS
import app.craft_defs as craft_defs
import datetime as dt

from app.quests.service import (
    assign_daily_quest_if_needed,
    assign_weekly_quest_if_needed,
    assign_next_storyline_quest_if_needed,
    auto_mark_expired_quests,
    serialize_quest,
)

from app.services.cards import serialize_card_def
#from app.routes.api_craft import _compute_craft_table_level, _update_craft_jobs_for_player
from app.services.crafts import compute_craft_table_level, update_craft_jobs_for_player


bp = Blueprint("players", __name__)


def _round_qty(q, digits: int = 2) -> float:
    if q is None:
        q = 0.0
    return round(float(q), digits)


def _player_to_dict(p: Player) -> dict:
    # Petit helper pour uniformiser les réponses
    return {
        "id": p.id,
        "name": p.name,
        "shards": p.shards,
        "essence": p.essence,
        "level": p.level,
        "xp": p.xp,
        "next_xp": getattr(p, "next_xp", None),  # ou via progression
    }

def _ensure_starting_land_card(session, player: Player) -> None:
    """Ensure the player owns the starting land card (forest)."""
    # Check if the player already has the card
    existing = (
        session.query(PlayerCard)
        .filter_by(player_id=player.id, card_key="land_forest")
        .first()
    )
    if existing:
        return  # already has the card

    # If not, create it with qty=1
    pc = PlayerCard(player_id=player.id, card_key="land_forest", qty=1)
    session.add(pc)
    # No commit here: let the caller decide when to commit


@bp.post("/player")
def create_player():
    s = SessionLocal()
    name = (request.get_json() or {}).get("name")
    if not name:
        s.close()
        return jsonify({"error": "name_required"}), 400

    existing = s.query(Player).filter_by(name=name).first()
    if existing:
        p = existing
        resp = jsonify(
            {
                "id": p.id,
                "name": p.name,
                "level": p.level,
                "shards": p.shards,
                "essence": p.essence,
                "xp": p.xp,
                "next_xp": next_threshold(p.level),
            }
        )
        s.close()
        return resp, 200

    p = Player(name=name)
    s.add(p)
    s.commit()
    resp = jsonify(
        {
            "id": p.id,
            "name": p.name,
            "level": p.level,
            "shards": p.shards,
            "essence": p.essence,
            "xp": p.xp,
            "next_xp": next_threshold(p.level),
        }
    )
    s.close()
    return resp, 200


@bp.get("/player/<int:player_id>")
def get_player(player_id: int):
    """Return a player by id."""
    with SessionLocal() as s:
        p = s.get(Player, player_id)
        if not p:
            return jsonify({"error": "not_found"}), 404
        return jsonify(
            {
                "id": p.id,
                "name": p.name,
                "level": p.level,
                "shards": p.shards,
                "essence": p.essence,
                "xp": p.xp,
                "next_xp": next_threshold(p.level),
            }
        )


# -----------------------------------------------------------------
# Auth: register / login / logout / me
# -----------------------------------------------------------------
@bp.post("/register")
def register():
    """Create a player (if not exists) and set a 'player_id' cookie."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name_required"}), 400

    with SessionLocal() as s:
        p = s.query(Player).filter_by(name=name).first()
        if not p:
            p = Player(name=name)
            s.add(p)
            s.commit()
            s.refresh(p)

        _ensure_starting_land_card(s, p)
        s.commit()

        resp = make_response(
            jsonify(
                {
                    "id": p.id,
                    "name": p.name,
                    "level": p.level,
                    "shards": p.shards,
                    "essence": p.essence,
                    "xp": p.xp,
                    "next_xp": next_threshold(p.level),
                }
            )
        )
        resp.set_cookie(
            "player_id",
            str(p.id),
            httponly=True,
            samesite="Lax",
            max_age=60 * 60 * 24 * 365,
        )
        return resp, 200


@bp.post("/login")
def login():
    """Login by id or name and set the 'player_id' cookie."""
    data = request.get_json(silent=True) or {}
    pid = data.get("id")
    name = (data.get("name") or "").strip()

    with SessionLocal() as s:
        p = None
        if pid:
            try:
                p = s.get(Player, int(pid))
            except Exception:
                p = None
        if not p and name:
            p = s.query(Player).filter_by(name=name).first()
        if not p:
            return jsonify({"error": "player_not_found"}), 404

        resp = make_response(
            jsonify(
                {
                    "id": p.id,
                    "name": p.name,
                    "level": p.level,
                    "shards": p.shards,
                    "essence": p.essence,
                    "xp": p.xp,
                    "next_xp": next_threshold(p.level),
                }
            )
        )
        resp.set_cookie(
            "player_id",
            str(p.id),
            httponly=True,
            samesite="Lax",
            max_age=60 * 60 * 24 * 365,
        )
        return resp, 200


@bp.post("/logout")
def logout():
    resp = make_response(jsonify({"ok": True}))
    resp.set_cookie("player_id", "", max_age=0)
    return resp, 200


@bp.get("/me")
def whoami():
    with SessionLocal() as s:
        p = _get_current_player(s)
        if not p:
            return jsonify({"error": "not_authenticated"}), 401
        return jsonify(
            {
                "id": p.id,
                "name": p.name,
                "level": p.level,
                "shards": p.shards,
                "essence": p.essence,
                "xp": p.xp,
                "next_xp": next_threshold(p.level),
            }
        )


@bp.get("/state")
def get_state():
    """Return full player state, including cards (new format)."""
    with SessionLocal() as s:
        me = _get_current_player(s)
        if not me:
            return jsonify({"error": "not_authenticated"}), 401

        # --- NEW: ensure daily / weekly / storyline quests are assigned ---
        now = dt.datetime.utcnow()
        assign_daily_quest_if_needed(s, me, now=now)
        assign_weekly_quest_if_needed(s, me, now=now)
        assign_next_storyline_quest_if_needed(s, me, now=now)
        auto_mark_expired_quests(s, me)
        s.commit()

        # --- IMPORTANT: resolve craft jobs BEFORE building inventory/items ---
        update_craft_jobs_for_player(s, me)
        s.commit()  # Persist credited PlayerItem changes before reading inventory/items

        # --- NEW: Load active quests ---------------------------------------
        quests = (
            s.query(PlayerQuest)
            .filter(PlayerQuest.player_id == me.id)
            .filter(
                PlayerQuest.status.in_(
                    ["active", "ready", "completed", "expired"]
                )
            )
            .order_by(PlayerQuest.started_at.desc())
            .all()
        )
        quests_payload = [serialize_quest(q) for q in quests]

        # -------------------------------------------------------------------
        # Tiles
        # -------------------------------------------------------------------
        tiles = (
            s.query(Tile)
            .filter_by(player_id=me.id)
            .order_by(Tile.id.asc())
            .all()
        )
        tiles_payload = []
        for t in tiles:
            tiles_payload.append(
                {
                    "id": t.id,
                    "playerId": t.player_id,
                    "resource": t.resource,
                    "locked": t.locked,
                    "cooldown_until": (
                        t.cooldown_until.isoformat()
                        if t.cooldown_until
                        else None
                    ),
                }
            )

        # -------------------------------------------------------------------
        # Resource inventory
        # -------------------------------------------------------------------
        stocks = (
            s.query(ResourceStock)
            .filter_by(player_id=me.id)
            .order_by(ResourceStock.resource.asc())
            .all()
        )
        inventory_payload = [
            {"resource": rs.resource, "qty": _round_qty(rs.qty)}
            for rs in stocks
        ]

        # -------------------------------------------------------------------
        # Resource defs  ✅ ADAPTÉ AU NOUVEAU MODELE
        # -------------------------------------------------------------------
        resources_rows = (
            s.query(ResourceDef)
            .filter_by(enabled=True)
            .order_by(ResourceDef.key.asc())
            .all()
        )
        resources_payload = [
            {
                "key": r.key,
                "label": r.label,
                "icon": r.icon,
                "kind": r.kind,
                "base_sell_price": r.base_sell_price,
                "enabled": r.enabled,
                "description": r.description,
                "unlock_description": r.unlock_description,
            }
            for r in resources_rows
        ]

        # -------------------------------------------------------------------
        # Cards (NEW) – via service
        # -------------------------------------------------------------------
        card_defs = (
            s.query(CardDef)
            .filter_by(enabled=True)
            .order_by(CardDef.key.asc())
            .all()
        )

        owned_rows = (
            s.query(PlayerCard)
            .filter_by(player_id=me.id)
            .all()
        )
        owned_map = {pc.card_key: pc.qty for pc in owned_rows}

        # Ici, le contexte est plutôt "inventory" pour le /state global
        cards_payload = []
        for cd in card_defs:
            owned_qty = owned_map.get(cd.key, 0)
            cards_payload.append(
                serialize_card_def(
                    cd,
                    owned_qty=owned_qty,
                    context="inventory",
                )
            )

        # -------------------------------------------------------------------
        # Items craftés (PlayerItem)
        # -------------------------------------------------------------------
        item_rows = (
            s.query(PlayerItem)
            .filter_by(player_id=me.id)
            .order_by(PlayerItem.item_key.asc())
            .all()
        )

        items_payload = []
        for it in item_rows:
            if it.quantity <= 0:
                continue  # on n'envoie pas les stacks vides

            meta = craft_defs.ITEM_DEFS.get(it.item_key, {}) or {}
            craft_cfg = craft_defs.CRAFT_DEFS.get(it.item_key, {}) or {}

            cfg = {**meta, **craft_cfg}

            print("[DEBUG ITEM META] key =", it.item_key, "meta =", meta)
            print("[DEBUG ITEM CFG ] key =", it.item_key, "cfg  =", cfg)

            items_payload.append(
                {
                    "item_key": it.item_key,
                    "qty": it.quantity,
                    "label_fr": cfg.get("label_fr"),
                    "label_en": cfg.get("label_en"),
                    "icon": cfg.get("icon"),
                    "type": cfg.get("type"),
                    "category": cfg.get("category"),
                }
            )

        # -------------------------------------------------------------------
        # Craft : niveau de table + jobs en cours
        # -------------------------------------------------------------------

        # 1) Mettre à jour les jobs en cours (donne les items terminés)
        #_update_craft_jobs_for_player(s, me)

        # 2) Niveau de table
        craft_table_level = compute_craft_table_level(s, me)

        # 3) Charger les jobs actifs
        now = dt.datetime.utcnow()
        job_rows = (
            s.query(PlayerCraftJob)
            .filter(PlayerCraftJob.player_id == me.id)
            .filter(PlayerCraftJob.status == "active")
            .order_by(PlayerCraftJob.started_at.asc())
            .all()
        )

        jobs_payload = []
        for job in job_rows:
            total = int(job.quantity_total or 0)
            done = int(job.quantity_done or 0)
            remaining_units = max(0, total - done)

            started_at = job.started_at
            ends_at = job.ends_at

            total_secs = max(
                0, int((ends_at - started_at).total_seconds())
            )
            elapsed = max(0, int((now - started_at).total_seconds()))
            remaining_total_secs = max(0, total_secs - elapsed)

            # Durée par item (approx) si on a un total non nul
            if total > 0 and total_secs > 0:
                seconds_per_unit = total_secs / total
            else:
                seconds_per_unit = 0

            # Temps jusqu'au prochain item (approx)
            if remaining_units > 0 and seconds_per_unit > 0:
                # Combien d'items *devraient* être finis à cet instant ?
                units_should_be_done = min(
                    total, int(elapsed // seconds_per_unit)
                )
                next_threshold_time = (
                    units_should_be_done + 1
                ) * seconds_per_unit
                seconds_until_next_unit = max(
                    0, int(next_threshold_time - elapsed)
                )
                if seconds_until_next_unit > remaining_total_secs:
                    seconds_until_next_unit = remaining_total_secs
            else:
                seconds_until_next_unit = 0

            # Label / meta depuis craft_defs si dispo
            cfg = craft_defs.CRAFT_DEFS.get(job.item_key, {}) or {}
            label = cfg.get("label") or job.item_key

            job_payload = {
                "id": job.id,
                "station_key": job.craft_location,
                "item_key": job.item_key,
                "label": label,
                "quantity_total": total,
                "quantity_done": done,
                "remaining_units": remaining_units,
                "started_at": started_at.isoformat(),
                "ends_at": ends_at.isoformat(),
                "seconds_total": total_secs,
                "seconds_elapsed": elapsed,
                "seconds_remaining_total": remaining_total_secs,
                "seconds_per_unit": int(seconds_per_unit)
                if seconds_per_unit
                else 0,
                "seconds_until_next_unit": seconds_until_next_unit,
                "status": job.status,
            }
            jobs_payload.append(job_payload)

        # Pour l'instant, on considère qu'il n'y a qu'une seule table de craft "générique"
        # -> on expose un "active_job" pratique pour l'UI sur craft_table
        active_job = None
        for jp in jobs_payload:
            if jp["station_key"].startswith("craft_table"):
                active_job = jp
                break

        craft_payload = {
            "craft_table_level": craft_table_level,
            "jobs": jobs_payload,
            "active_job": active_job,
        }

        # -------------------------------------------------------------------
        # Story flags (which story events have been seen)
        # -------------------------------------------------------------------
        story_flags_rows = (
            s.query(PlayerStoryFlag).filter_by(player_id=me.id).all()
        )
        seen_story_ids = [row.story_id for row in story_flags_rows]

        # -------------------------------------------------------------------
        # Return final state
        # -------------------------------------------------------------------
        print("DEBUG ITEM:", items_payload)
        return (
            jsonify(
                {
                    "player": {
                        "id": me.id,
                        "name": me.name,
                        "level": me.level,
                        "xp": me.xp,
                        "shards": me.shards,
                        "essence": me.essence,
                        "next_xp": next_threshold(me.level),
                    },
                    "tiles": tiles_payload,
                    "inventory": inventory_payload,
                    "resources": resources_payload,
                    "cards": cards_payload,
                    "items": items_payload,
                    "craft": craft_payload,
                    "quests": quests_payload,
                    "story_flags": seen_story_ids,
                }
            ),
            200,
        )


@bp.post("/story/seen")
def mark_story_seen():
    """Mark a given story event as seen for the current player."""
    with SessionLocal() as s:
        me = _get_current_player(s)
        if not me:
            return jsonify({"error": "not_authenticated"}), 401

        data = request.get_json(silent=True) or {}
        story_id = (data.get("story_id") or "").strip()

        if not story_id:
            return jsonify({"error": "story_id_required"}), 400

        # Check if already stored
        existing = (
            s.query(PlayerStoryFlag)
            .filter_by(player_id=me.id, story_id=story_id)
            .one_or_none()
        )
        if existing:
            return jsonify({"ok": True, "already_seen": True}), 200

        flag = PlayerStoryFlag(
            player_id=me.id,
            story_id=story_id,
            seen_at=dt.datetime.utcnow(),
        )
        s.add(flag)
        s.commit()

        return jsonify({"ok": True, "already_seen": False}), 200


# -----------------------------------------------------------------
# Helper: cookie-based auth
# -----------------------------------------------------------------
def _get_current_player(session):
    pid = request.cookies.get("player_id")
    if not pid:
        return None
    try:
        pid = int(pid)
    except ValueError:
        return None
    return session.get(Player, pid)


from app.progression import LEVELS, xp_required_for
from app.models import ResourceDef, CardDef


@bp.get("/levels")
def get_levels_definitions():
    """
    Return the list of level definitions for the UI:
      - xp_min / xp_max (pour afficher la barre)
      - normalized rewards (shards/essence/resources/cards)
      - story_events (brut depuis levels.yml)
      - system_unlocks (brut depuis levels.yml)
    """
    with SessionLocal() as s:
        # Cache des définitions pour enrichir les rewards
        resource_defs = {
            r.key: r
            for r in s.query(ResourceDef).filter_by(enabled=True).all()
        }
        card_defs = {
            c.key: c
            for c in s.query(CardDef).filter_by(enabled=True).all()
        }

        level_numbers = sorted(LEVELS.keys()) if LEVELS else []
        payload = []

        for idx, lvl in enumerate(level_numbers):
            thr = xp_required_for(lvl)

            # xp_min = seuil de ce niveau
            xp_min = thr

            # xp_max = seuil du niveau suivant, ou None si dernier niveau
            if idx + 1 < len(level_numbers):
                next_lvl = level_numbers[idx + 1]
                xp_max = xp_required_for(next_lvl)
            else:
                xp_max = None

            cfg = LEVELS[lvl]
            rewards_cfg = cfg.get("rewards", []) or []

            # NEW: raw story + system unlocks (directement depuis LEVELS)
            story_events_cfg = cfg.get("story_events", []) or []
            system_unlocks_cfg = cfg.get("system_unlocks", []) or []

            normalized_rewards = []
            for r in rewards_cfg:
                r_type = r.get("type")

                if r_type == "shards":
                    amount = int(r.get("amount", 0))
                    normalized_rewards.append(
                        {
                            "type": "shards",
                            "amount": amount,
                            "label": "shards",
                            "icon": "/static/GAME_UI/img/ui/shards.png",
                        }
                    )

                elif r_type == "essence":
                    amount = int(r.get("amount", 0))
                    normalized_rewards.append(
                        {
                            "type": "essence",
                            "amount": amount,
                            "label": "essence",
                            "icon": "/static/GAME_UI/img/ui/essence.png",
                        }
                    )

                elif r_type == "resource":
                    resource_key = r.get("resource_key") or ""
                    amount = float(r.get("amount", 0))
                    rd = resource_defs.get(resource_key)
                    normalized_rewards.append(
                        {
                            "type": "resource",
                            "key": resource_key,
                            "amount": amount,
                            "label": rd.label if rd else resource_key,
                            "icon": rd.icon if rd else None,
                        }
                    )

                elif r_type == "card":
                    card_key = r.get("card_key") or ""
                    amount = int(r.get("amount", 1))
                    cd = card_defs.get(card_key)
                    label = getattr(cd, "card_label", None) if cd else None
                    icon = getattr(cd, "card_image", None) if cd else None
                    normalized_rewards.append(
                        {
                            "type": "card",
                            "key": card_key,
                            "amount": amount,
                            "label": label or card_key,
                            "icon": icon,
                        }
                    )

            payload.append(
                {
                    "level": lvl,
                    "xp_required": thr,
                    "xp_min": xp_min,
                    "xp_max": xp_max,
                    "rewards": normalized_rewards,
                    # story + unlocks bruts (le front décidera quoi en faire)
                    "story_events": story_events_cfg,
                    "system_unlocks": system_unlocks_cfg,
                }
            )

    return jsonify(payload)
