# =============================================================================
# File: app/routes/api_tickets.py
# Purpose: Support ticket API (create, list, search)
# =============================================================================
from __future__ import annotations

import datetime as dt

from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from app.db import SessionLocal
from app.auth import get_current_player
from app.models import SupportTicket, Player, TICKET_CATEGORIES, TICKET_STATUSES

bp = Blueprint("tickets", __name__)


def _ticket_summary(t: SupportTicket, player_name: str | None = None) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "category": t.category,
        "status": t.status,
        "player_level": t.player_level,
        "created_at": t.created_at.isoformat(),
        "player_name": player_name or "—",
        "mine": False,  # overridden by caller
    }


def _ticket_detail(t: SupportTicket, player_name: str | None = None, is_mine: bool = False) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "category": t.category,
        "description": t.description,
        "steps": t.steps,
        "status": t.status,
        "player_level": t.player_level,
        "page_url": t.page_url,
        "browser_info": t.browser_info,
        "admin_note": t.admin_note,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
        "player_name": player_name or "—",
        "mine": is_mine,
    }


# ---------------------------------------------------------------------------
# GET /tickets  — search / list
# ---------------------------------------------------------------------------
@bp.get("/tickets")
def list_tickets():
    with SessionLocal() as s:
        me = get_current_player(s)
        my_id = me.id if me else None

        q        = (request.args.get("q") or "").strip()
        category = (request.args.get("category") or "").strip()
        mine     = request.args.get("mine") == "1"
        page     = max(1, int(request.args.get("page") or 1))
        per_page = 20

        query = s.query(SupportTicket)

        if mine and my_id:
            query = query.filter(SupportTicket.player_id == my_id)

        if category and category in TICKET_CATEGORIES:
            query = query.filter(SupportTicket.category == category)

        if q:
            like = f"%{q}%"
            query = query.filter(
                or_(
                    SupportTicket.title.ilike(like),
                    SupportTicket.description.ilike(like),
                )
            )

        total = query.count()
        tickets = (
            query.order_by(SupportTicket.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        # Bulk-load player names
        player_ids = list({t.player_id for t in tickets})
        names = {
            p.id: p.name
            for p in s.query(Player).filter(Player.id.in_(player_ids)).all()
        }

        items = []
        for t in tickets:
            d = _ticket_summary(t, names.get(t.player_id))
            d["mine"] = (t.player_id == my_id)
            items.append(d)

        return jsonify({
            "tickets": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page),
        })


# ---------------------------------------------------------------------------
# GET /tickets/<id>  — detail
# ---------------------------------------------------------------------------
@bp.get("/tickets/<int:ticket_id>")
def get_ticket(ticket_id: int):
    with SessionLocal() as s:
        me = get_current_player(s)
        t = s.get(SupportTicket, ticket_id)
        if not t:
            return jsonify({"error": "not_found"}), 404

        is_mine = bool(me and me.id == t.player_id)
        player_name = t.player.name if t.player else "—"
        return jsonify(_ticket_detail(t, player_name, is_mine))


# ---------------------------------------------------------------------------
# POST /tickets  — create
# ---------------------------------------------------------------------------
@bp.post("/tickets")
def create_ticket():
    with SessionLocal() as s:
        me = get_current_player(s)
        if not me:
            return jsonify({"error": "not_authenticated"}), 401

        data = request.get_json(silent=True) or {}

        title       = (data.get("title") or "").strip()
        category    = (data.get("category") or "bug").strip()
        description = (data.get("description") or "").strip()
        steps       = (data.get("steps") or "").strip() or None
        page_url    = (data.get("page_url") or "").strip()[:500] or None
        browser_info = (data.get("browser_info") or "").strip()[:500] or None

        if not title:
            return jsonify({"error": "title_required"}), 400
        if len(title) > 200:
            return jsonify({"error": "title_too_long"}), 400
        if not description:
            return jsonify({"error": "description_required"}), 400
        if category not in TICKET_CATEGORIES:
            category = "other"

        ticket = SupportTicket(
            player_id    = me.id,
            title        = title,
            category     = category,
            description  = description,
            steps        = steps,
            player_level = me.level,
            page_url     = page_url,
            browser_info = browser_info,
            status       = "open",
            created_at   = dt.datetime.utcnow(),
            updated_at   = dt.datetime.utcnow(),
        )
        s.add(ticket)
        s.commit()
        s.refresh(ticket)

        return jsonify({"ok": True, "id": ticket.id}), 201
