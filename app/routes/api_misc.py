# app/routes/api_players.py
from flask import Blueprint, jsonify, request
from app.db import SessionLocal
from app.models import Player


bp = Blueprint("misc", __name__) 



# -----------------------------------------------------------------
# Dev UI
# -----------------------------------------------------------------
@bp.get("/ui")
def dev_ui():
    return bp.send_static_file("ui/index.html")

@bp.get("/health")
def health():
    """Simple health endpoint used by tests."""
    return jsonify({"status": "ok"})