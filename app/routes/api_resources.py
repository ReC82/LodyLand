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
from app.quests.service import on_resource_collected

bp = Blueprint("resources", __name__)


# ============================================================================
# Local helpers (avoid circular imports)
# ============================================================================

def _get_res_def(session, key: str) -> ResourceDef | None:
    """Return an enabled ResourceDef by its key, or None if missing."""
    if not key:
        return None
    return (
        session.query(ResourceDef)
        .filter_by(key=key, enabled=True)
        .first()
    )


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

    # Base loot
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

    # Extra loot
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


# ============================================================================
# Card helpers (centralized logic for boosts / unlocks)
# IMPORTANT: we avoid using CardDef.type in SQL filters (was causing AttributeError),
#            and instead filter in Python on the loaded CardDef instances.
# ============================================================================

def _count_cards(
    session,
    player_id: int,
    card_type: str,
    target_resource: str | None = None,
) -> int:
    """
    Return total quantity of cards of a given type (optionally tied to a resource).

    Filters:
      - cd.type == card_type
      - if target_resource is set, cd.target_resource == target_resource
    """
    rows = (
        session.query(PlayerCard, CardDef)
        .join(CardDef, CardDef.key == PlayerCard.card_key)
        .filter(PlayerCard.player_id == player_id)
        .all()
    )

    total = 0
    for pc, cd in rows:
        if getattr(cd, "type", None) != card_type:
            continue
        if target_resource is not None:
            if getattr(cd, "target_resource", None) != target_resource:
                continue
        total += pc.qty

    return total


def _has_unlock_resource_card(session, player_id: int, resource_key: str) -> bool:
    """
    Return True if player owns at least one unlock_resource card for this resource.

    Filters:
      - cd.type == "unlock_resource"
      - cd.target_resource == resource_key
    """
    rows = (
        session.query(PlayerCard, CardDef)
        .join(CardDef, CardDef.key == PlayerCard.card_key)
        .filter(PlayerCard.player_id == player_id)
        .all()
    )

    for pc, cd in rows:
        if getattr(cd, "type", None) != "unlock_resource":
            continue
        if getattr(cd, "target_resource", None) != resource_key:
            continue
        if pc.qty > 0:
            return True

    return False


def _get_xp_boost_cards(session, player_id: int):
    """
    Return list of XP boost configs:

    [
      {"qty":1, "type":"addition", "amount":0.10},
      ...
    ]

    Expected structure in CardDef.gameplay:
      gameplay:
        xp:
          type: "addition" | "multiplier"
          amount: 0.10
    """
    rows = (
        session.query(PlayerCard, CardDef)
        .join(CardDef, CardDef.key == PlayerCard.card_key)
        .filter(PlayerCard.player_id == player_id)
        .all()
    )

    boosts = []
    for pc, cd in rows:
        if getattr(cd, "type", None) != "xp_boost":
            continue

        gp = cd.gameplay or {}
        xp_cfg = gp.get("xp")
        if not xp_cfg:
            continue

        boosts.append(
            {
                "qty": pc.qty,
                "type": xp_cfg.get("type", "addition"),
                "amount": float(xp_cfg.get("amount", 0.0)),
            }
        )

    return boosts


def _get_cooldown_boost_cards(session, player_id: int, resource_key: str):
    """
    Returns cooldown boosts for this resource OR global ones.

    Expected structure in CardDef.gameplay:
      gameplay:
        target_resource: "branch" | null
        cooldown:
          type: "reduction" | "multiplier"
          amount: 0.10
    """
    rows = (
        session.query(PlayerCard, CardDef)
        .join(CardDef, CardDef.key == PlayerCard.card_key)
        .filter(PlayerCard.player_id == player_id)
        .all()
    )

    boosts = []
    for pc, cd in rows:
        if getattr(cd, "type", None) != "reduce_cooldown":
            continue

        gp = cd.gameplay or {}

        # Resource-specific? None = global
        target = gp.get("target_resource")
        if target not in (None, resource_key):
            continue

        cd_cfg = gp.get("cooldown")
        if not cd_cfg:
            continue

        boosts.append(
            {
                "qty": pc.qty,
                "type": cd_cfg.get("type", "reduction"),
                "amount": float(cd_cfg.get("amount", 0.0)),
            }
        )

    return boosts


def _get_land_loot_boost_cards(
    session,
    player_id: int,
    land_key: str,
    tool_key: str,
):
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
        .filter(PlayerCard.player_id == player_id)
        .all()
    )

    boosts = []
    for pc, cd in rows:
        if getattr(cd, "type", None) != "land_loot_boost":
            continue

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

        boosts.append(
            {
                "qty": pc.qty,
                "type": loot_cfg.get("type", "addition"),
                "amount": float(loot_cfg.get("amount", 0.0)),
            }
        )

    return boosts


def _get_resource_boost_cards(
    session,
    player_id: int,
    resource_key: str,
):
    """
    Return a list of boost configs taken from CardDef.gameplay.boost.

    Only selects cards:
      - cd.type == "resource_boost"
      - gameplay.target_resource == resource_key

    Expected structure in CardDef.gameplay:
      gameplay:
        target_resource: "branch"
        boost:
          type: "addition" | "multiplier"
          amount: 0.10
    """
    rows = (
        session.query(PlayerCard, CardDef)
        .join(CardDef, CardDef.key == PlayerCard.card_key)
        .filter(PlayerCard.player_id == player_id)
        .all()
    )

    boosts = []
    for pc, cd in rows:
        if getattr(cd, "type", None) != "resource_boost":
            continue

        gp = cd.gameplay or {}
        if gp.get("target_resource") != resource_key:
            continue

        boost_cfg = gp.get("boost")
        if not boost_cfg:
            continue

        boosts.append(
            {
                "qty": pc.qty,
                "type": boost_cfg.get("type", "addition"),
                "amount": float(boost_cfg.get("amount", 0.0)),
            }
        )

    return boosts


def _compute_collect_amount(
    session,
    player_id: int,
    resource_key: str,
) -> float:
    """
    Compute how many units of a resource are collected per click.

    Uses boost cards from YAML:

      - "addition":   base * (1 + amount * qty)
      - "multiplier": base * (amount ** qty)
    """
    base = 1.0
    value = base

    boosts = _get_resource_boost_cards(session, player_id, resource_key)

    for b in boosts:
        qty = b["qty"]
        amount = b["amount"]     # ex: 0.10
        btype = b["type"]        # "addition" or "multiplier"

        if qty <= 0:
            continue

        if btype == "addition":
            # Example: +0.1 per card → qty=2 → base * (1 + 0.1*2)
            value = value * (1 + amount * qty)
        elif btype == "multiplier":
            # Example: x1.5 per card → qty=2 → base * (1.5^2)
            value = value * (amount ** qty)

    return round(value, 4)


def _compute_xp_gain(
    session,
    player_id: int,
    base_xp: int,
) -> float:
    """
    Compute XP gain per collect using YAML boost configs.
    """
    xp = float(base_xp)

    boosts = _get_xp_boost_cards(session, player_id)

    for b in boosts:
        qty = b["qty"]
        amount = b["amount"]
        btype = b["type"]

        if qty <= 0:
            continue

        if btype == "addition":
            # +10% XP per card
            xp = xp * (1 + amount * qty)
        elif btype == "multiplier":
            # x1.5 XP per card
            xp = xp * (amount ** qty)

    return round(xp, 4)


def _compute_cooldown(
    session,
    player_id: int,
    resource_key: str,
    base_cooldown: float,
) -> float:
    """
    Compute final cooldown using YAML-based cooldown boost cards.
    """
    cooldown = float(base_cooldown)

    boosts = _get_cooldown_boost_cards(session, player_id, resource_key)

    for b in boosts:
        qty = b["qty"]
        amount = b["amount"]    # 0.10 means 10%
        btype = b["type"]

        if qty <= 0:
            continue

        if btype == "reduction":
            # Reduction per card: base * (1 - amount*qty), clamped to at least 10% of original
            cooldown = cooldown * max(0.1, (1 - amount * qty))
        elif btype == "multiplier":
            # Multiplicative cooldown: base * (amount ** qty)
            cooldown = cooldown * (amount ** qty)

    return round(cooldown, 4)


def _compute_land_loot_multiplier(
    session,
    player_id: int,
    land_key: str,
    tool_key: str,
) -> float:
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


# ============================================================================
# Resources listing (for UI + tests)
# ============================================================================

@bp.get("/resources")
def list_resources():
    """Return all enabled resource definitions (for UI + tests)."""
    with SessionLocal() as s:
        rows = (
            s.query(ResourceDef)
            .filter_by(enabled=True)
            .order_by(ResourceDef.unlock_min_level.asc())
            .all()
        )
        return jsonify(
            [
                {
                    "key": r.key,
                    "label": r.label,
                    "unlock_min_level": r.unlock_min_level,
                    "base_cooldown": r.base_cooldown,
                    "base_sell_price": r.base_sell_price,
                    "enabled": r.enabled,
                }
                for r in rows
            ]
        )


# ============================================================================
# Collect endpoint (land mode + legacy tile mode)
# ============================================================================

@bp.post("/collect")
def collect():
    """
    Collect resources in two possible modes:

    1) Land mode (preferred, new):
       Body: {"land": "forest", "slot": 0}
       - Uses lands.yml definition + tools / loot system

    2) Legacy tile mode:
       Body: {"tileId": 123}
       - Uses Tile / cooldown_until as before
    """
    data = request.get_json(silent=True) or {}

    # ----------------------------------------------------------------------
    # 1) New mode: collect on a land (beach, forest, lake, ...)
    # ----------------------------------------------------------------------
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
            # Current player from cookie
            p = get_current_player(s)
            if not p:
                return jsonify({"error": "player_required"}), 401

            # Check land is unlocked via card
            if not _player_has_land(s, p.id, land_key):
                return jsonify({"error": "land_locked"}), 403

            # Land definition from lands.yml
            land_def = get_land_def(land_key)
            if not land_def:
                return jsonify({"error": "land_unknown"}), 400

            slots = int(land_def.get("slots", 0) or 0)
            if slots <= 0:
                return jsonify({"error": "land_has_no_slots"}), 400
            if slot < 0 or slot >= slots:
                return jsonify({"error": "slot_out_of_range", "max": slots}), 400

            # For now: always use "hands" as tool
            tools_cfg = land_def.get("tools") or {}
            tool_key = "hands"
            tool_cfg = tools_cfg.get(tool_key)
            if not tool_cfg:
                return jsonify({"error": "tool_not_allowed", "tool": tool_key}), 400

            # Base loot roll (without boosts)
            raw_loot = _roll_land_loot(tool_cfg)  # {resource: base_qty}

            # Global land loot multiplier (cards with type "land_loot_boost")
            land_loot_mult = _compute_land_loot_multiplier(
                s,
                p.id,
                land_key,
                tool_key,
            )

            # Current time (for XP & cooldown displayed to client)
            now = datetime.now(timezone.utc)

            # XP gain for this collect (base XP_PER_COLLECT + XP cards)
            gained_xp = _compute_xp_gain(s, p.id, XP_PER_COLLECT)
            level_up, new_level, level_rewards = apply_xp_and_level_up(
                s,
                p,
                gained_xp,
            )

            # Apply resource_boost cards, update inventory, and quest progress
            loot_payload = []
            for res_key, base_amount in raw_loot.items():
                # Per unit amount (cards "resource_boost" for that resource)
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

                # Quest progression for collect_resource (land mode)
                # base_amount is pre-boost amount used for quest logic.
                on_resource_collected(
                    session=s,
                    player=p,
                    resource_key=res_key,
                    base_amount=int(base_amount),
                )

            # "Virtual" cooldown for client (not stored per slot yet)
            # We use the first base_loot resource as reference for cooldown.
            base_res = None
            base_loot_list = tool_cfg.get("base_loot") or []
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

            return (
                jsonify(
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
                ),
                200,
            )

    # ----------------------------------------------------------------------
    # 2) Legacy mode: collect on a Tile
    # ----------------------------------------------------------------------
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

        # Base cooldown from resource definition
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
            level_up, new_level, level_rewards = apply_xp_and_level_up(
                s,
                p,
                gained_xp,
            )

        # Resource gain for this tile
        if t.resource:
            rs = (
                s.query(ResourceStock)
                .filter_by(player_id=t.player_id, resource=t.resource)
                .first()
            )
            if not rs:
                rs = ResourceStock(
                    player_id=t.player_id,
                    resource=t.resource,
                    qty=0.0,
                )
                s.add(rs)

            # Apply resource_boost cards
            amount = _compute_collect_amount(s, t.player_id, t.resource)
            new_qty = (rs.qty or 0.0) + amount
            rs.qty = round(new_qty, 2)

            # Quest progression for collect_resource (tile mode)
            if p:
                # One tile collect = base_amount 1 for quest purposes.
                on_resource_collected(
                    session=s,
                    player=p,
                    resource_key=t.resource,
                    base_amount=1,
                )

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


# ============================================================================
# Tiles unlock + listing
# ============================================================================

@bp.post("/tiles/unlock")
def unlock_tile():
    """
    Unlock a tile for the current player or explicit playerId.

    Body:
      {
        "resource": "wood",
        "playerId": 1  # optional, fallback to cookie if missing
      }
    """
    data = request.get_json(silent=True) or {}

    resource = (data.get("resource") or "").strip().lower()
    if not resource:
        return jsonify({"error": "resource_required"}), 400

    # playerId can be absent → fallback to cookie
    player_id = data.get("playerId")

    with SessionLocal() as s:
        # 1) Resolve player
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
                return jsonify(
                    {
                        "error": "level_too_low",
                        "required": rd.unlock_min_level,
                    }
                ), 403

            # Advanced unlock rules (coins, other conditions...)
            ok, details = check_unlock_rules(p, rd.unlock_rules)
            if not ok:
                payload = {
                    "error": details.get("reason", "unlock_conditions_not_met")
                }
                payload.update(details)
                return jsonify(payload), 403
        # else: player has a card, we bypass normal conditions

        # 4) Create tile
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


@bp.get("/player/<int:player_id>/tiles")
def list_tiles(player_id: int):
    """
    Return all tiles for a player + resource metadata.

    Includes:
      - id, playerId, resource, locked, cooldown_until
      - icon, description, unlock_text (from ResourceDef)
    """
    with SessionLocal() as s:
        # Fast check: player must exist
        if not s.get(Player, player_id):
            return jsonify({"error": "player_not_found"}), 404

        # Join Tile + ResourceDef
        rows = (
            s.query(Tile, ResourceDef)
            .outerjoin(ResourceDef, Tile.resource == ResourceDef.key)
            .filter(Tile.player_id == player_id)
            .all()
        )

        data = []
        for t, rd in rows:
            data.append(
                {
                    "id": t.id,
                    "playerId": t.player_id,
                    "resource": t.resource,
                    "locked": t.locked,
                    "cooldown_until": (
                        t.cooldown_until.isoformat() if t.cooldown_until else None
                    ),
                    # Extra fields for front /play:
                    "icon": rd.icon if rd else None,
                    "description": rd.description if rd else None,
                    # Human-readable unlock text for UI (comes from ResourceDef)
                    "unlock_text": (
                        rd.unlock_description
                        if (rd and rd.unlock_description)
                        else None
                    ),
                }
            )

        return jsonify(data)
