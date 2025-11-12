# =============================================================================
# File: tests/test_api.py
# Purpose: Minimal API smoke tests (health, create player).
# =============================================================================
import json
import os
import tempfile
import pytest
from app import create_app
from app.db import Base, engine
from app.progression import XP_PER_COLLECT

@pytest.fixture(autouse=True)
def _setup_tmp_db(monkeypatch):
    """Use a temporary SQLite file per test run."""
    fd, path = tempfile.mkstemp(prefix="test_db_", suffix=".sqlite")
    os.close(fd)
    os.environ["DATABASE_URL"] = f"sqlite:///{path}"
    # Re-create tables on this temp engine
    Base.metadata.create_all(bind=engine)
    yield
    try:
        os.remove(path)
    except FileNotFoundError:
        pass

def test_health():
    app = create_app()
    client = app.test_client()
    rv = client.get("/api/health")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["status"] == "ok"

def test_create_player_and_unlock_collect():
    app = create_app()
    client = app.test_client()

    # Create player
    rv = client.post("/api/player", json={"name": "Lloyd"})
    assert rv.status_code == 200
    player = rv.get_json()
    assert player["name"] == "Lloyd"

    # Unlock tile
    rv = client.post("/api/tiles/unlock", json={"playerId": player["id"], "resource": "wood"})
    assert rv.status_code == 200
    tile_id = rv.get_json()["id"]

    # Collect once => ok
    rv = client.post("/api/collect", json={"tileId": tile_id})
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["ok"] is True
    assert data["player"]["xp"] >= XP_PER_COLLECT
    assert "next" in data and isinstance(data["next"], str) and len(data["next"]) > 0