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
    PlayerItem,        # NEW
)
from app.progression import next_threshold
from app.craft_defs import CRAFT_DEFS

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
        "coins": p.coins,
        "diams": p.diams,
        "level": p.level,
        "xp": p.xp,
        "next_xp": getattr(p, "next_xp", None),  # ou via progression
    }
    
def _compute_craft_table_level(session, player: Player) -> int:
    """
    Compute the craft table level for a player based on owned cards.

    Version simple:
    - level 1 par défaut (table de craft de base)
    - +1 pour chaque upgrade (on pourra affiner plus tard)
    """
    level = 1  # on donne la table de craft de base à tout le monde

    def has_card(card_key: str) -> bool:
        return (
            session.query(PlayerCard)
            .filter_by(player_id=player.id, card_key=card_key)
            .count()
            > 0
        )

    # Base craft (si un jour tu veux démarrer à 0 et exiger craft_base, tu ajusteras)
    if has_card("craft_base"):
        level = max(level, 1)

    # Upgrades
    if has_card("craft_upgrade_1"):
        level = max(level, 2)

    if has_card("craft_upgrade_2"):
        level = max(level, 3)

    return level
    
    
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
                "coins": p.coins,
                "diams": p.diams,
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
            "coins": p.coins,
            "diams": p.diams,
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
                "coins": p.coins,
                "diams": p.diams,
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
                    "coins": p.coins,
                    "diams": p.diams,
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
                    "coins": p.coins,
                    "diams": p.diams,
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
                "coins": p.coins,
                "diams": p.diams,
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

        # ------------------------------
        # Tiles
        # ------------------------------
        tiles = (
            s.query(Tile)
            .filter_by(player_id=me.id)
            .order_by(Tile.id.asc())
            .all()
        )
        tiles_payload = []
        for t in tiles:
            tiles_payload.append({
                "id": t.id,
                "playerId": t.player_id,
                "resource": t.resource,
                "locked": t.locked,
                "cooldown_until": (
                    t.cooldown_until.isoformat() if t.cooldown_until else None
                ),
            })

        # ------------------------------
        # Resource inventory
        # ------------------------------
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

        # ------------------------------
        # Resource defs
        # ------------------------------
        resources_rows = (
            s.query(ResourceDef)
            .filter_by(enabled=True)
            .order_by(ResourceDef.unlock_min_level.asc())
            .all()
        )
        resources_payload = [
            {
                "key": r.key,
                "label": r.label,
                "icon": r.icon,
                "unlock_min_level": r.unlock_min_level,
                "base_cooldown": r.base_cooldown,
                "base_sell_price": r.base_sell_price,
                "enabled": r.enabled,
            }
            for r in resources_rows
        ]

        # ------------------------------
        # Cards (NEW)
        # ------------------------------
        # 1) all enabled card defs
        card_defs = (
            s.query(CardDef)
            .filter_by(enabled=True)
            .order_by(CardDef.key.asc())
            .all()
        )

        # 2) owned qty indexed by card_key
        owned_rows = (
            s.query(PlayerCard)
            .filter_by(player_id=me.id)
            .all()
        )
        owned_map = {pc.card_key: pc.qty for pc in owned_rows}

        cards_payload = []
        for cd in card_defs:
            cards_payload.append({
                "key": cd.key,
                "label": cd.label,
                "description": cd.description,
                "icon": cd.icon,

                "categorie": cd.categorie,
                "rarity": cd.rarity,
                "type": cd.type,

                "gameplay": cd.gameplay or {},
                "prices": cd.prices or [],
                "shop": cd.shop or {},
                "buy_rules": cd.buy_rules or {},

                "enabled": cd.enabled,
                "owned_qty": owned_map.get(cd.key, 0),
            })

        # ------------------------------
        # Items craftés (PlayerItem)
        # ------------------------------
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

            cfg = CRAFT_DEFS.get(it.item_key, {})  # peut être vide si supprimé du YAML

            items_payload.append({
                "item_key": it.item_key,
                "qty": it.quantity,
                "label_fr": cfg.get("label_fr"),
                "label_en": cfg.get("label_en"),
                "icon": cfg.get("icon"),
                "type": cfg.get("type"),
                "category": cfg.get("category"),
            })

        # ------------------------------
        # Info Craft (niveau de table)
        # ------------------------------
        craft_table_level = _compute_craft_table_level(s, me)
        craft_payload = {
            "craft_table_level": craft_table_level,
        }

        # ------------------------------
        # Return final state
        # ------------------------------
        return jsonify({
            "player": {
                "id": me.id,
                "name": me.name,
                "level": me.level,
                "xp": me.xp,
                "coins": me.coins,
                "diams": me.diams,
                "next_xp": next_threshold(me.level),
            },
            "tiles": tiles_payload,
            "inventory": inventory_payload,
            "resources": resources_payload,

            # NEW
            "cards": cards_payload,
            
            "items": items_payload,
            "craft": craft_payload,
        }), 200

        
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