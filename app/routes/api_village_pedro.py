# =============================================================================
# app/routes/api_village_pedro.py
# API Pedro — dépôt de matériaux + lancement de construction
# =============================================================================

from __future__ import annotations

import os
import yaml
import datetime as dt

from flask import Blueprint, jsonify, request

from app.db import SessionLocal
from app.auth import get_current_player
from app.models import PlayerBuilding, ResourceStock

bp = Blueprint("village_pedro", __name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_buildings_cache: dict | None = None

def _load_buildings() -> dict:
    global _buildings_cache
    if _buildings_cache is None:
        path = os.path.join(os.path.dirname(__file__), "..", "data", "buildings.yml")
        with open(path, encoding="utf-8") as f:
            _buildings_cache = yaml.safe_load(f).get("buildings", {})
    return _buildings_cache


def _get_or_create_building(session, player_id: int, building_key: str) -> PlayerBuilding:
    row = (
        session.query(PlayerBuilding)
        .filter_by(player_id=player_id, building_key=building_key)
        .first()
    )
    if not row:
        row = PlayerBuilding(
            player_id=player_id,
            building_key=building_key,
            status="pending_resources",
            banked_materials={},
        )
        session.add(row)
        session.flush()
    return row


def _all_materials_met(banked: dict, required: dict) -> bool:
    for mat, qty in required.items():
        if int(banked.get(mat, 0)) < int(qty):
            return False
    return True


def _deduct_resource(session, player_id: int, resource: str, qty: int) -> bool:
    """Retire `qty` d'une ressource du stock joueur. Renvoie False si stock insuffisant."""
    stock = (
        session.query(ResourceStock)
        .filter_by(player_id=player_id, resource=resource)
        .first()
    )
    if not stock or stock.qty < qty:
        return False
    stock.qty -= qty
    return True


# ---------------------------------------------------------------------------
# POST /api/village/pedro/deposit
# Body: { building_key, resource, qty }
# ---------------------------------------------------------------------------

@bp.post("/village/pedro/deposit")
def api_pedro_deposit():
    data = request.get_json(silent=True) or {}
    building_key = data.get("building_key")
    resource     = data.get("resource")
    qty          = int(data.get("qty", 0))

    if not building_key or not resource or qty <= 0:
        return jsonify({"ok": False, "error": "invalid_params"}), 400

    buildings = _load_buildings()
    bdef = buildings.get(building_key)
    if not bdef:
        return jsonify({"ok": False, "error": "unknown_building"}), 404

    required = bdef.get("construction", {}).get("materials", {})
    if resource not in required:
        return jsonify({"ok": False, "error": "resource_not_needed"}), 400

    with SessionLocal() as session:
        player = get_current_player(session)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        pb = _get_or_create_building(session, player.id, building_key)

        if pb.status not in ("pending_resources",):
            return jsonify({"ok": False, "error": "wrong_status"}), 400

        # Calculer combien on peut encore déposer
        already   = int((pb.banked_materials or {}).get(resource, 0))
        needed    = int(required[resource])
        remaining = needed - already
        if remaining <= 0:
            return jsonify({"ok": False, "error": "already_full"}), 400

        deposit = min(qty, remaining)

        # Débiter le stock joueur (irrécupérable)
        if not _deduct_resource(session, player.id, resource, deposit):
            return jsonify({"ok": False, "error": "not_enough_resources"}), 400

        # Créditer le banked_materials
        banked = dict(pb.banked_materials or {})
        banked[resource] = already + deposit
        pb.banked_materials = banked

        # Vérifier si tous les matériaux sont réunis
        if _all_materials_met(banked, required):
            pb.status = "pending_construction"

        session.commit()
        session.refresh(pb)

        return jsonify({
            "ok": True,
            "building_key": building_key,
            "resource": resource,
            "deposited": deposit,
            "banked_materials": pb.banked_materials,
            "status": pb.status,
        })


# ---------------------------------------------------------------------------
# POST /api/village/pedro/start
# Body: { building_key }
# ---------------------------------------------------------------------------

@bp.post("/village/pedro/start")
def api_pedro_start():
    data = request.get_json(silent=True) or {}
    building_key = data.get("building_key")
    if not building_key:
        return jsonify({"ok": False, "error": "missing_building_key"}), 400

    buildings = _load_buildings()
    bdef = buildings.get(building_key)
    if not bdef:
        return jsonify({"ok": False, "error": "unknown_building"}), 404

    duration = int(bdef.get("construction", {}).get("duration_seconds", 0))

    with SessionLocal() as session:
        player = get_current_player(session)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        pb = (
            session.query(PlayerBuilding)
            .filter_by(player_id=player.id, building_key=building_key)
            .first()
        )
        if not pb or pb.status != "pending_construction":
            return jsonify({"ok": False, "error": "wrong_status"}), 400

        now = dt.datetime.utcnow()
        pb.status                  = "under_construction"
        pb.construction_started_at = now
        pb.construction_ends_at    = now + dt.timedelta(seconds=duration)

        session.commit()

        return jsonify({
            "ok": True,
            "building_key": building_key,
            "status": pb.status,
            "construction_ends_at": pb.construction_ends_at.isoformat() + "Z",
            "duration_seconds": duration,
        })


# ---------------------------------------------------------------------------
# POST /api/village/pedro/check_complete
# Vérifie si la construction est terminée et passe le bâtiment en operational
# Body: { building_key }
# ---------------------------------------------------------------------------

@bp.post("/village/pedro/check_complete")
def api_pedro_check_complete():
    data = request.get_json(silent=True) or {}
    building_key = data.get("building_key")
    if not building_key:
        return jsonify({"ok": False, "error": "missing_building_key"}), 400

    with SessionLocal() as session:
        player = get_current_player(session)
        if not player:
            return jsonify({"ok": False, "error": "not_authenticated"}), 401

        pb = (
            session.query(PlayerBuilding)
            .filter_by(player_id=player.id, building_key=building_key)
            .first()
        )
        if not pb:
            return jsonify({"ok": False, "error": "not_found"}), 404

        if pb.status == "under_construction":
            now = dt.datetime.utcnow()
            if pb.construction_ends_at and now >= pb.construction_ends_at:
                pb.status = "operational"
                session.commit()

        return jsonify({
            "ok": True,
            "building_key": building_key,
            "status": pb.status,
            "construction_ends_at": (
                pb.construction_ends_at.isoformat() + "Z"
                if pb.construction_ends_at else None
            ),
        })
