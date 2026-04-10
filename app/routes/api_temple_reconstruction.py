# app/routes/api_temple_reconstruction.py
"""
Temple Reconstruction API
  GET  /temple/reconstruction/state   → état du joueur (briques posées, dispo, stock carte)
  POST /temple/reconstruction/place   → poser une brique (body: {"brick_key": "..."})
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import yaml
from flask import Blueprint, jsonify, request

from app.auth import get_current_player
from app.db import SessionLocal
from app.i18n import get_item, get_user_language
from app.models import PlayerCard, ResourceStock, TempleReconstructionBrick
from app.services.cards import give_player_card

bp = Blueprint("temple_reconstruction", __name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "temple_reconstruction.yml"
_BLESSING_CARD_KEY = "blessing_of_the_temple"
_GLOBAL_STOCK = 100  # nombre max de cartes bénédiction distribuables


def _load_config() -> dict:
    with _CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# Build a flat index {brick_key: {layer, cost, ...}} at module load time
def _build_brick_index(cfg: dict) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for layer in cfg["temple_reconstruction"]["layers"]:
        layer_num = layer["layer"]
        required_layer = layer.get("required_layer")
        for brick in layer["bricks"]:
            index[brick["key"]] = {
                "layer": layer_num,
                "required_layer": required_layer,
                "cost": brick["cost"],
                "name_fr": brick.get("name_fr", brick["key"]),
                "description_fr": brick.get("description_fr", ""),
            }
    return index


_CONFIG: dict = _load_config()
_BRICK_INDEX: dict[str, dict] = _build_brick_index(_CONFIG)
_RESOURCE_SOURCES: dict[str, list] = _CONFIG["temple_reconstruction"].get("resource_sources", {})

# Keys grouped by layer
_LAYER_BRICKS: dict[int, list[str]] = {}
for _bk, _bd in _BRICK_INDEX.items():
    _LAYER_BRICKS.setdefault(_bd["layer"], []).append(_bk)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _placed_keys(session, player_id: int) -> set[str]:
    rows = (
        session.query(TempleReconstructionBrick)
        .filter_by(player_id=player_id)
        .all()
    )
    return {r.brick_key for r in rows}


def _player_stocks(session, player_id: int) -> dict[str, float]:
    """Return all resource stocks for the player as {resource_key: qty}."""
    rows = session.query(ResourceStock).filter_by(player_id=player_id).all()
    return {r.resource: float(r.qty or 0) for r in rows}


def _layer_complete(layer_num: int, placed: set[str]) -> bool:
    return all(bk in placed for bk in _LAYER_BRICKS.get(layer_num, []))


def _blessings_distributed(session) -> int:
    return (
        session.query(PlayerCard)
        .filter_by(card_key=_BLESSING_CARD_KEY)
        .count()
    )


def _deduct_resources(session, player_id: int, cost: dict) -> str | None:
    """
    Deduct `cost` from the player's ResourceStock.
    Returns None on success, or an error key describing the missing resource.
    """
    # First pass: check all
    for res_key, amount in cost.items():
        rs = (
            session.query(ResourceStock)
            .filter_by(player_id=player_id, resource=res_key)
            .first()
        )
        owned = float(rs.qty) if rs else 0.0
        if owned < amount:
            return res_key  # missing this resource

    # Second pass: deduct
    for res_key, amount in cost.items():
        rs = (
            session.query(ResourceStock)
            .filter_by(player_id=player_id, resource=res_key)
            .first()
        )
        rs.qty = round(float(rs.qty) - amount, 2)

    return None


# ---------------------------------------------------------------------------
# GET /temple/reconstruction/state
# ---------------------------------------------------------------------------

@bp.get("/reconstruction/state")
def state():
    with SessionLocal() as s:
        p = get_current_player(s)
        if not p:
            return jsonify({"error": "player_required"}), 401

        placed = _placed_keys(s, p.id)
        stocks = _player_stocks(s, p.id)
        stock_remaining = max(0, _GLOBAL_STOCK - _blessings_distributed(s))
        already_blessed = (
            s.query(PlayerCard)
            .filter_by(player_id=p.id, card_key=_BLESSING_CARD_KEY)
            .first()
        ) is not None

        lang = get_user_language(request, player=p)

        # Build per-layer status
        layers_status = []
        for layer_cfg in _CONFIG["temple_reconstruction"]["layers"]:
            layer_num = layer_cfg["layer"]
            req = layer_cfg.get("required_layer")
            unlocked = (req is None) or _layer_complete(req, placed)
            bricks = []
            for brick in layer_cfg["bricks"]:
                # Enrich cost with player stock + translated label
                cost_detail = {}
                can_afford = True
                for res_key, needed in brick["cost"].items():
                    owned = stocks.get(res_key, 0.0)
                    item_data = get_item(res_key, lang) or {}
                    raw_label = item_data.get("label", res_key)
                    # If translate_data_dict returned the i18n key as-is, use res_key as fallback
                    label = raw_label if (raw_label and not raw_label.startswith("items.")) else res_key
                    cost_detail[res_key] = {
                        "needed": needed,
                        "owned": owned,
                        "label": label,
                        "icon": item_data.get("icon", ""),
                        "ok": owned >= needed,
                        "sources": _RESOURCE_SOURCES.get(res_key, []),
                    }
                    if owned < needed:
                        can_afford = False

                bricks.append({
                    "key": brick["key"],
                    "name_fr": brick.get("name_fr", brick["key"]),
                    "description_fr": brick.get("description_fr", ""),
                    "cost": brick["cost"],
                    "cost_detail": cost_detail,
                    "can_afford": can_afford,
                    "placed": brick["key"] in placed,
                    "available": unlocked and brick["key"] not in placed,
                })
            layers_status.append({
                "layer": layer_num,
                "name_fr": layer_cfg.get("name_fr", ""),
                "description_fr": layer_cfg.get("description_fr", ""),
                "unlocked": unlocked,
                "complete": _layer_complete(layer_num, placed),
                "bricks": bricks,
            })

        total_bricks = len(_BRICK_INDEX)
        placed_count = len(placed)
        fully_complete = placed_count >= total_bricks

        return jsonify({
            "placed_count": placed_count,
            "total_bricks": total_bricks,
            "fully_complete": fully_complete,
            "already_blessed": already_blessed,
            "stock_remaining": stock_remaining,
            "layers": layers_status,
        })


# ---------------------------------------------------------------------------
# POST /temple/reconstruction/place
# ---------------------------------------------------------------------------

@bp.post("/reconstruction/place")
def place_brick():
    data = request.get_json(silent=True) or {}
    brick_key = (data.get("brick_key") or "").strip()
    if not brick_key:
        return jsonify({"error": "brick_key_required"}), 400

    if brick_key not in _BRICK_INDEX:
        return jsonify({"error": "brick_unknown"}), 400

    brick_def = _BRICK_INDEX[brick_key]

    with SessionLocal() as s:
        p = get_current_player(s)
        if not p:
            return jsonify({"error": "player_required"}), 401

        placed = _placed_keys(s, p.id)

        # Already placed?
        if brick_key in placed:
            return jsonify({"error": "brick_already_placed"}), 409

        # Required layer complete?
        req = brick_def["required_layer"]
        if req is not None and not _layer_complete(req, placed):
            return jsonify({"error": "layer_locked", "required_layer": req}), 403

        # Check & deduct resources
        missing = _deduct_resources(s, p.id, brick_def["cost"])
        if missing:
            return jsonify({"error": "insufficient_resources", "resource": missing}), 402

        # Place the brick
        s.add(TempleReconstructionBrick(
            player_id=p.id,
            brick_key=brick_key,
            placed_at=dt.datetime.utcnow(),
        ))

        placed.add(brick_key)
        placed_count = len(placed)
        total_bricks = len(_BRICK_INDEX)
        fully_complete = placed_count >= total_bricks

        # Completion reward
        reward = None
        if fully_complete:
            already_blessed = (
                s.query(PlayerCard)
                .filter_by(player_id=p.id, card_key=_BLESSING_CARD_KEY)
                .first()
            ) is not None

            if not already_blessed:
                stock_used = _blessings_distributed(s)  # before this grant
                if stock_used < _GLOBAL_STOCK:
                    give_player_card(s, p.id, _BLESSING_CARD_KEY, qty=1)
                    reward = {"type": "card", "key": _BLESSING_CARD_KEY}
                else:
                    # Stock épuisé — récompense de consolation
                    p.shards = (p.shards or 0) + 2000
                    p.essence = (p.essence or 0) + 20
                    reward = {"type": "consolation", "coins": 2000, "diams": 20}

        s.commit()

        return jsonify({
            "ok": True,
            "brick_key": brick_key,
            "placed_count": placed_count,
            "total_bricks": total_bricks,
            "fully_complete": fully_complete,
            "reward": reward,
        })
