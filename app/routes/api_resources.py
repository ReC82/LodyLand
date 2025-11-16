# app/routes/api_resources.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from app.db import SessionLocal
from app.models import ResourceDef, Tile, Player, ResourceStock, CardDef, PlayerCard
from app.progression import XP_PER_COLLECT, level_for_xp, next_threshold
from app.unlock_rules import check_unlock_rules
from app.auth import get_current_player

bp = Blueprint("resources", __name__)

# -----------------------------------------------------------------
# Helpers locaux (évitent les import circulaires)
# -----------------------------------------------------------------
def _get_res_def(session, key: str) -> ResourceDef | None:
  if not key:
      return None
  return session.query(ResourceDef).filter_by(key=key, enabled=True).first()

# -----------------------------------------------------------------
# Card helpers
# -----------------------------------------------------------------
def _count_cards(session, player_id: int, card_type: str, target_resource: str | None = None) -> int:
    """Return total quantity of cards of a given type (optionally tied to a resource)."""
    q = (
        session.query(PlayerCard, CardDef)
        .join(CardDef, CardDef.key == PlayerCard.card_key)
        .filter(
            PlayerCard.player_id == player_id,
            CardDef.type == card_type,
        )
    )
    if target_resource is not None:
        q = q.filter(CardDef.target_resource == target_resource)

    rows = q.all()
    return sum(pc.qty for pc, cd in rows)


def _has_unlock_resource_card(session, player_id: int, resource_key: str) -> bool:
    """Return True if player owns at least one unlock_resource card for this resource."""
    q = (
        session.query(PlayerCard, CardDef)
        .join(CardDef, CardDef.key == PlayerCard.card_key)
        .filter(
            PlayerCard.player_id == player_id,
            CardDef.type == "unlock_resource",
            CardDef.target_resource == resource_key,
        )
    )
    rows = q.all()
    return any(pc.qty > 0 for pc, cd in rows)


def _compute_collect_amount(session, player_id: int, resource_key: str) -> float:
    """
    Compute how many units of a resource are collected per click.

    Rules:
      - base_amount = 1.0
      - each 'resource_boost' card for this resource gives +10%
    """
    base_amount = 1.0
    n_boost = _count_cards(session, player_id, "resource_boost", resource_key)
    multiplier = 1.0 + 0.1 * n_boost
    return base_amount * multiplier


def _compute_xp_gain(session, player_id: int, base_xp: int) -> float:
    """
    Compute XP gain per collect.

    Rules:
      - base_xp from progression.XP_PER_COLLECT
      - each 'boost_xp' card gives +10% XP globally
    """
    n = _count_cards(session, player_id, "boost_xp", None)
    multiplier = 1.0 + 0.1 * n
    return base_xp * multiplier


def _compute_cooldown(session, player_id: int, resource_key: str, base_cooldown: float) -> float:
    """
    Compute cooldown duration in seconds.

    Rules:
      - base_cooldown from ResourceDef.base_cooldown
      - 'reduce_cooldown' cards:
          * if target_resource = resource_key -> resource-specific
          * if target_resource is NULL -> global
        Each card gives -10% cooldown, min 10% of base.
    """
    n_res = _count_cards(session, player_id, "reduce_cooldown", resource_key)
    n_global = _count_cards(session, player_id, "reduce_cooldown", None)
    total = n_res + n_global
    if total <= 0:
        return float(base_cooldown)

    # At least 10% of base cooldown
    factor = max(0.1, 1.0 - 0.1 * total)
    return float(base_cooldown) * factor

# -----------------------------------------------------------------
# Resources listing (for UI + tests)
# -----------------------------------------------------------------

@bp.get("/resources")
def list_resources():
    """Liste les définitions de ressources (pour UI + tests)."""
    with SessionLocal() as s:
        rows = (
            s.query(ResourceDef)
            .filter_by(enabled=True)
            .order_by(ResourceDef.unlock_min_level.asc())
            .all()
        )
        return jsonify([
            {
                "key": r.key,
                "label": r.label,
                "unlock_min_level": r.unlock_min_level,
                "base_cooldown": r.base_cooldown,
                "base_sell_price": r.base_sell_price,
                "enabled": r.enabled,
            }
            for r in rows
        ])
        
@bp.post("/collect")
def collect():
    data = request.get_json(silent=True) or {}
    tile_id = data.get("tileId")
    if not tile_id:
        return jsonify({"error": "tileId_required"}), 400

    with SessionLocal() as s:
        t = s.get(Tile, tile_id)
        if not t:
            return jsonify({"error": "tile_missing"}), 400
        if t.locked:
            return jsonify({"error": "locked"}), 400

        now = datetime.now(timezone.utc)
        cd = t.cooldown_until
        if cd is not None and cd.tzinfo is None:
            cd = cd.replace(tzinfo=timezone.utc)

        if cd and cd > now:
            return (
                jsonify(
                    {"error": "on_cooldown", "until": cd.isoformat()}
                ),
                409,
            )

        rd = _get_res_def(s, t.resource)
        base_cd = rd.base_cooldown if rd else 10

        # Apply cooldown reduction cards (resource-specific + global)
        effective_cd = _compute_cooldown(s, t.player_id, t.resource, base_cd)
        next_cd = now + timedelta(seconds=effective_cd)
        t.cooldown_until = next_cd

        level_up = False
        p = s.get(Player, t.player_id)
        if p:
            # Apply XP boost cards
            gained_xp = _compute_xp_gain(s, p.id, XP_PER_COLLECT)
            p.xp = (p.xp or 0) + gained_xp

            old_level = p.level or 0
            new_level = level_for_xp(p.xp)
            if new_level > old_level:
                p.level = new_level
                level_up = True

        if t.resource:
            rs = (
                s.query(ResourceStock)
                .filter_by(
                    player_id=t.player_id, resource=t.resource
                )
                .first()
            )
            if not rs:
                rs = ResourceStock(
                    player_id=t.player_id,
                    resource=t.resource,
                    qty=0.0,  # we use float now
                )
                s.add(rs)

            # Apply resource_boost cards
            amount = _compute_collect_amount(s, t.player_id, t.resource)
            rs.qty = (rs.qty or 0.0) + amount

        s.commit()
        return jsonify(
            {
                "ok": True,
                "next": next_cd.isoformat(),
                "player": {
                    "id": p.id,
                    "name": p.name,
                    "xp": p.xp,
                    "level": p.level,
                    "next_xp": next_threshold(p.level),
                },
                "level_up": level_up,
            }
        )        
        
@bp.post("/tiles/unlock")
def unlock_tile():
    """
    Unlock a tile for the current player or explicit playerId.

    Body: {"resource":"wood", "playerId": 1 (optionnel)}
    """
    data = request.get_json(silent=True) or {}

    resource = (data.get("resource") or "").strip().lower()
    if not resource:
        return jsonify({"error": "resource_required"}), 400

    # playerId peut être absent → fallback cookie
    player_id = data.get("playerId")

    with SessionLocal() as s:
        # 1) Résoudre le player
        if player_id is not None:
            p = s.get(Player, int(player_id))
            if not p:
                return jsonify({"error": "player_not_found"}), 404
        else:
            me = get_current_player(s)
            if not me:
                return jsonify({"error": "player_required"}), 400
            p = me

        # 2) ResourceDef
        rd = _get_res_def(s, resource)
        if not rd:
            return jsonify({"error": "resource_unknown_or_disabled"}), 400

        # 3) Check unlock conditions unless player owns an unlock_resource card
        has_unlock_card = _has_unlock_resource_card(s, p.id, resource)

        if not has_unlock_card:
            # Minimal level check
            if p.level < rd.unlock_min_level:
                return jsonify({
                    "error": "level_too_low",
                    "required": rd.unlock_min_level,
                }), 403

            # Advanced unlock rules (coins, other conditions...)
            ok, details = check_unlock_rules(p, rd.unlock_rules)
            if not ok:
                payload = {"error": details.get("reason", "unlock_conditions_not_met")}
                payload.update(details)
                return jsonify(payload), 403
        # else: player has a card, we bypass normal conditions


        # 5) Si tout est OK -> créer la tuile
        t = Tile(
            player_id=p.id,
            resource=resource,
            locked=False,
            cooldown_until=None,
        )
        s.add(t)
        s.commit()
        s.refresh(t)

        return jsonify({"id": t.id}), 200        
    
    # -----------------------------------------------------------------
    # Tiles
    # -----------------------------------------------------------------
@bp.get("/player/<int:player_id>/tiles")
def list_tiles(player_id: int):
    """Return all tiles for a player + metadata de ressource."""
    with SessionLocal() as s:
        # Fast check player exists
        if not s.get(Player, player_id):
            return jsonify({"error": "player_not_found"}), 404

        # jointure Tile + ResourceDef
        rows = (
            s.query(Tile, ResourceDef)
            .outerjoin(ResourceDef, Tile.resource == ResourceDef.key)
            .filter(Tile.player_id == player_id)
            .all()
        )

        data = []
        for t, rd in rows:
            data.append({
                "id": t.id,
                "playerId": t.player_id,
                "resource": t.resource,
                "locked": t.locked,
                "cooldown_until": t.cooldown_until.isoformat() if t.cooldown_until else None,

                # nouveaux champs pour le front /play :
                "icon": rd.icon if rd else None,
                "description": rd.description if rd else None,
                # on expose un champ unlock_text que ton front consomme
                "unlock_text": (
                    rd.unlock_description
                    if (rd and rd.unlock_description)
                    else None
                ),
            })

        return jsonify(data)    