# app/routes/api_resources.py
from __future__ import annotations

import random

from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from app.db import SessionLocal
from app.models import ResourceDef, Tile, Player, ResourceStock, CardDef, PlayerCard
from app.progression import XP_PER_COLLECT, next_threshold, apply_xp_and_level_up
from app.unlock_rules import check_unlock_rules
from app.auth import get_current_player
from app.lands import get_land_def

bp = Blueprint("resources", __name__)

# -----------------------------------------------------------------
# Helpers locaux (évitent les import circulaires)
# -----------------------------------------------------------------
def _get_res_def(session, key: str) -> ResourceDef | None:
  if not key:
      return None
  return session.query(ResourceDef).filter_by(key=key, enabled=True).first()

def _player_has_land(session, player_id: int, land_key: str) -> bool:
    """
    Return True if the player owns the card that unlocks this land.

    Convention:
      land 'forest' -> card_key 'land_forest'
      land 'beach'  -> card_key 'land_beach'
    """
    card_key = f"land_{land_key}"
    row = (
        session.query(PlayerCard)
        .filter_by(player_id=player_id, card_key=card_key)
        .first()
    )
    return bool(row and row.qty > 0)

def _roll_land_loot(tool_cfg: dict) -> dict[str, float]:
    """
    Given a tool config from lands.yml, roll base_loot + extra_loot.

    Returns:
        dict {resource_key: total_amount}
    """
    loot: dict[str, float] = {}

    def add_res(key: str, amount: float) -> None:
        loot[key] = loot.get(key, 0.0) + float(amount)

    for entry in tool_cfg.get("base_loot", []) or []:
        res = entry.get("resource")
        if not res:
            continue
        chance = float(entry.get("chance", 1.0))
        if random.random() <= chance:
            mn = int(entry.get("min", 1))
            mx = int(entry.get("max", mn))
            amount = random.randint(mn, mx)
            add_res(res, amount)

    for entry in tool_cfg.get("extra_loot", []) or []:
        res = entry.get("resource")
        if not res:
            continue
        chance = float(entry.get("chance", 0.0))
        if random.random() <= chance:
            mn = int(entry.get("min", 1))
            mx = int(entry.get("max", mn))
            amount = random.randint(mn, mx)
            add_res(res, amount)

    return loot


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

def _get_xp_boost_cards(session, player_id: int):
    """
    Return list of XP boost configs:
    [
      {"qty":1, "type":"addition", "amount":0.10},
      ...
    ]
    """
    rows = (
        session.query(PlayerCard, CardDef)
        .join(CardDef, CardDef.key == PlayerCard.card_key)
        .filter(
            PlayerCard.player_id == player_id,
            CardDef.type == "xp_boost"
        )
        .all()
    )

    boosts = []
    for pc, cd in rows:
        gp = cd.gameplay or {}
        xp_cfg = gp.get("xp")
        if not xp_cfg:
            continue

        boosts.append({
            "qty": pc.qty,
            "type": xp_cfg.get("type", "addition"),
            "amount": float(xp_cfg.get("amount", 0.0)),
        })

    return boosts

def _get_cooldown_boost_cards(session, player_id: int, resource_key: str):
    """
    Returns cooldown boosts for this resource OR global ones.
    """
    rows = (
        session.query(PlayerCard, CardDef)
        .join(CardDef, CardDef.key == PlayerCard.card_key)
        .filter(PlayerCard.player_id == player_id)
        .filter(CardDef.type == "reduce_cooldown")
        .all()
    )

    boosts = []
    for pc, cd in rows:
        gp = cd.gameplay or {}

        # Resource-specific?
        target = gp.get("target_resource")
        if target not in (None, resource_key):
            continue

        cd_cfg = gp.get("cooldown")
        if not cd_cfg:
            continue

        boosts.append({
            "qty": pc.qty,
            "type": cd_cfg.get("type", "reduction"),
            "amount": float(cd_cfg.get("amount", 0.0)),
        })

    return boosts



def _compute_collect_amount(session, player_id: int, resource_key: str) -> float:
    """
    Compute how many units of a resource are collected per click.

    Uses YAML values:
      - addition: base * (1 + amount * qty)
      - multiplier: base * (amount ** qty)
    """

    base = 1.0

    boosts = _get_resource_boost_cards(session, player_id, resource_key)

    value = base

    for b in boosts:
        qty = b["qty"]
        amount = b["amount"]     # ex: 0.10
        btype = b["type"]        # "addition" or "multiplier"

        if btype == "addition":
            # Example: +0.1 per card → qty=2 → base * (1 + 0.1*2)
            value = value * (1 + amount * qty)

        elif btype == "multiplier":
            # Example: x1.5 per card → qty=2 → base * (1.5^2)
            value = value * (amount ** qty)

    return round(value, 4)


def _compute_xp_gain(session, player_id: int, base_xp: int) -> float:
    """
    Compute XP gain per collect using YAML boost configs.
    """
    xp = base_xp

    boosts = _get_xp_boost_cards(session, player_id)

    for b in boosts:
        qty = b["qty"]
        amount = b["amount"]
        btype = b["type"]

        if btype == "addition":
            # +10% xp per card
            xp = xp * (1 + amount * qty)

        elif btype == "multiplier":
            # x1.5 xp per card
            xp = xp * (amount ** qty)

    return round(xp, 4)

def _compute_cooldown(session, player_id: int, resource_key: str, base_cooldown: float) -> float:
    """
    Compute cooldown using YAML-based boost configs.
    """
    cooldown = base_cooldown

    boosts = _get_cooldown_boost_cards(session, player_id, resource_key)

    for b in boosts:
        qty = b["qty"]
        amount = b["amount"]    # 0.10 means 10%
        btype = b["type"]

        if btype == "reduction":
            # Reduction per card: base * (1 - amount*qty)
            cooldown = cooldown * max(0.1, (1 - amount * qty))

        elif btype == "multiplier":
            # Multiplicative: base * (amount ** qty)
            cooldown = cooldown * (amount ** qty)

    return round(cooldown, 4)

def _compute_land_loot_multiplier(session, player_id: int, land_key: str, tool_key: str) -> float:
    """
    Compute a global loot multiplier for land collection.

    Base = 1.0

    For each boost:
      - type == "addition":     value *= (1 + amount * qty)
      - type == "multiplier":   value *= (amount ** qty)
    """
    value = 1.0

    boosts = _get_land_loot_boost_cards(session, player_id, land_key, tool_key)

    for b in boosts:
        qty = b["qty"]
        amount = b["amount"]
        btype = b["type"]

        if qty <= 0 or amount == 0:
            continue

        if btype == "addition":
            value *= (1 + amount * qty)
        elif btype == "multiplier":
            value *= (amount ** qty)

    return round(value, 4)


def _get_land_loot_boost_cards(session, player_id: int, land_key: str, tool_key: str):
    """
    Return list of land loot boosts for this player, filtered by land/tool.

    Expected YAML structure on CardDef.gameplay:

      gameplay:
        target_land: "forest" | null
        target_tool: "hands" | null
        loot:
          type: "addition" | "multiplier"
          amount: 0.20
    """
    rows = (
        session.query(PlayerCard, CardDef)
        .join(CardDef, CardDef.key == PlayerCard.card_key)
        .filter(
            PlayerCard.player_id == player_id,
            CardDef.type == "land_loot_boost",
        )
        .all()
    )

    boosts = []
    for pc, cd in rows:
        gp = cd.gameplay or {}

        # Optional filters: land + tool
        target_land = gp.get("target_land")
        if target_land is not None and target_land != land_key:
            continue

        target_tool = gp.get("target_tool")
        if target_tool is not None and target_tool != tool_key:
            continue

        loot_cfg = gp.get("loot")
        if not loot_cfg:
            continue

        boosts.append({
            "qty": pc.qty,
            "type": loot_cfg.get("type", "addition"),
            "amount": float(loot_cfg.get("amount", 0.0)),
        })

    return boosts


def _get_resource_boost_cards(session, player_id: int, resource_key: str):
    """
    Return a list of (boost_type, amount) taken from CardDef.gameplay.boost.
    
    Only selects cards:
      - type = "resource_boost"
      - target_resource = resource_key
    """
    rows = (
        session.query(PlayerCard, CardDef)
        .join(CardDef, CardDef.key == PlayerCard.card_key)
        .filter(
            PlayerCard.player_id == player_id,
            CardDef.type == "resource_boost",
        )
        .filter(CardDef.gameplay != None)
        .all()
    )

    boosts = []
    for pc, cd in rows:
        # we expect cd.gameplay = {"target_resource": "...", "boost": {...}}
        gp = cd.gameplay or {}
        if gp.get("target_resource") != resource_key:
            continue

        boost_cfg = gp.get("boost")
        if not boost_cfg:
            continue

        boosts.append({
            "qty": pc.qty,
            "type": boost_cfg.get("type", "addition"),
            "amount": float(boost_cfg.get("amount", 0.0)),
        })

    return boosts


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

    # --------- 1) Nouveau mode: collect sur un land (beach, forest, ...) ----------
    land_key = (data.get("land") or "").strip()
    if land_key:
        slot = data.get("slot")
        if slot is None:
            return jsonify({"error": "slot_required"}), 400

        try:
            slot = int(slot)
        except ValueError:
            return jsonify({"error": "slot_invalid"}), 400

        with SessionLocal() as s:
            # Joueur via cookie
            p = get_current_player(s)
            if not p:
                return jsonify({"error": "player_required"}), 401

            # Vérifier la carte de land
            if not _player_has_land(s, p.id, land_key):
                return jsonify({"error": "land_locked"}), 403

            # Définition du land
            land_def = get_land_def(land_key)
            if not land_def:
                return jsonify({"error": "land_unknown"}), 400

            slots = int(land_def.get("slots", 0) or 0)
            if slots <= 0:
                return jsonify({"error": "land_has_no_slots"}), 400
            if slot < 0 or slot >= slots:
                return jsonify({"error": "slot_out_of_range", "max": slots}), 400

            # Pour l'instant: on utilise toujours les mains
            tools_cfg = land_def.get("tools") or {}
            tool_key = "hands"
            tool_cfg = tools_cfg.get(tool_key)
            if not tool_cfg:
                return jsonify({"error": "tool_not_allowed", "tool": tool_key}), 400

            # Calcul du loot brut (sans boosts)
            raw_loot = _roll_land_loot(tool_cfg)  # {resource: base_qty}
            
            # Global land loot multiplier (cards "land_loot_boost")
            land_loot_mult = _compute_land_loot_multiplier(s, p.id, land_key, tool_key)

            # Temps actuel (pour XP et cooldown client-side)
            now = datetime.now(timezone.utc)

            # XP (one collect action = base XP_PER_COLLECT, with boost cards)
            gained_xp = _compute_xp_gain(s, p.id, XP_PER_COLLECT)
            level_up, new_level, level_rewards = apply_xp_and_level_up(s, p, gained_xp)

            # Appliquer les boosts de ressource + maj inventaire
            loot_payload = []
            for res_key, base_amount in raw_loot.items():
                # quantité boostée par les cartes "resource_boost"
                per_unit = _compute_collect_amount(s, p.id, res_key)
                amount = base_amount * per_unit * land_loot_mult

                rs = (
                    s.query(ResourceStock)
                    .filter_by(player_id=p.id, resource=res_key)
                    .first()
                )
                if not rs:
                    rs = ResourceStock(
                        player_id=p.id,
                        resource=res_key,
                        qty=0.0,
                    )
                    s.add(rs)

                new_qty = (rs.qty or 0.0) + amount
                rs.qty = round(new_qty, 2)

                loot_payload.append(
                    {
                        "resource": res_key,
                        "base_amount": base_amount,
                        "final_amount": round(amount, 2),
                    }
                )

            # Cooldown "virtuel" pour le client (pour l'instant pas stocké par slot)
            # On prend la première resource de base_loot comme référence
            base_res = None
            base_loot_list = (tool_cfg.get("base_loot") or [])
            if base_loot_list:
                base_res = base_loot_list[0].get("resource")
            base_cd = 10
            if base_res:
                rd = _get_res_def(s, base_res)
                if rd and rd.base_cooldown is not None:
                    base_cd = rd.base_cooldown

            effective_cd = _compute_cooldown(s, p.id, base_res or "", base_cd)
            next_cd = now + timedelta(seconds=effective_cd)

            s.commit()
            s.refresh(p)

            return jsonify(
                {
                    "ok": True,
                    "mode": "land",
                    "land": land_key,
                    "slot": slot,
                    "loot": loot_payload,
                    "next": next_cd.isoformat(),
                    "player": {
                        "id": p.id,
                        "name": p.name,
                        "xp": p.xp,
                        "level": p.level,
                        "next_xp": next_threshold(p.level),
                        "coins": p.coins,
                        "diams": p.diams,
                    },
                    "level_up": level_up,
                    "level_rewards": level_rewards,
                }
            ), 200

    # --------- 2) Mode existant: collect sur une Tile ----------
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
        level_rewards = []
        p = s.get(Player, t.player_id)
        if p:
            gained_xp = _compute_xp_gain(s, p.id, XP_PER_COLLECT)
            level_up, new_level, level_rewards = apply_xp_and_level_up(s, p, gained_xp)



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
            new_qty = (rs.qty or 0.0) + amount
            rs.qty = round(new_qty, 2)

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
                    "coins": p.coins,
                    "diams": p.diams,
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