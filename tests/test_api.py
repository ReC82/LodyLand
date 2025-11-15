# =============================================================================
# File: tests/test_api.py
# Purpose: Minimal API smoke tests (health, create player).
# =============================================================================
import json
import os
import tempfile
import pytest
from uuid import uuid4
from app.routes import create_app
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
    rv = client.post("/api/tiles/unlock", json={"playerId": player["id"], "resource": "branch"})
    assert rv.status_code == 200
    tile_id = rv.get_json()["id"]

    # Collect once => ok
    rv = client.post("/api/collect", json={"tileId": tile_id})
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["ok"] is True
    assert data["player"]["xp"] >= XP_PER_COLLECT
    assert "next" in data and isinstance(data["next"], str) and len(data["next"]) > 0
    
def test_sell_flow():
    app = create_app()
    client = app.test_client()

    # Create player
    rv = client.post("/api/player", json={"name": "Trader"})
    assert rv.status_code == 200
    p = rv.get_json()
    pid = p["id"]

    # Unlock branch tile
    rv = client.post("/api/tiles/unlock", json={"playerId": pid, "resource": "branch"})
    assert rv.status_code == 200
    tile_id = rv.get_json()["id"]

    # Collect twice (so we can sell 2)
    rv = client.post("/api/collect", json={"tileId": tile_id}); assert rv.status_code == 200
    # Force cooldown skip for the test: set cooldown_until to None by re-listing and just collecting again after manual patch?
    # Simpler for MVP: unlock a second branch tile and collect once again:
    rv = client.post("/api/tiles/unlock", json={"playerId": pid, "resource": "branch"}); assert rv.status_code == 200
    tile2 = rv.get_json()["id"]
    rv = client.post("/api/collect", json={"tileId": tile2}); assert rv.status_code == 200

    # Sell 2 branch
    rv = client.post("/api/sell", json={"resource": "branch", "qty": 2, "playerId": pid})
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["ok"] is True
    assert data["sold"]["resource"] == "branch"
    assert data["sold"]["qty"] == 2
    # Price must be >=1 coin per branch
    assert data["sold"]["gain"] >= 2
    # Inventory decreased
    assert data["stock"]["qty"] >= 0
    # Coins increased
    assert data["player"]["coins"] >= data["sold"]["gain"]
    
def test_daily_chest_once_per_day():
    app = create_app()
    client = app.test_client()

    name = f"POL-{uuid4().hex[:6]}"
    # Create player
    rv = client.post("/api/player", json={"name": name})
    assert rv.status_code == 200
    p = rv.get_json()
    pid = p["id"]

    # Set cookie for the session to simulate UI usage
    # client.set_cookie("localhost", "player_id", str(pid))
    client.post("/api/login", json={"id": pid})

    # First claim -> OK
    rv = client.post("/api/daily")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["ok"] is True
    assert data["reward"] >= 1
    coins_after = data["player"]["coins"]

    # Second claim same day -> 409
    rv = client.post("/api/daily")
    assert rv.status_code == 409
    data2 = rv.get_json()
    assert data2["error"] == "already_claimed"
    assert "next_at" in data2

    # Force yesterday to allow another claim
    from app.db import SessionLocal
    from app.models import Player
    from datetime import datetime, timezone, timedelta

    with SessionLocal() as s:
        me = s.get(Player, pid)
        assert me is not None
        me.last_daily = (datetime.now(timezone.utc).date() - timedelta(days=1))
        s.commit()

    # Claim again -> OK
    rv = client.post("/api/daily")
    assert rv.status_code == 200
    data3 = rv.get_json()
    assert data3["ok"] is True
    assert data3["player"]["coins"] >= coins_after + data3["reward"]

def test_unlock_requires_min_level():
    app = create_app()
    client = app.test_client()

    # Crée player niveau 0
    rv = client.post("/api/player", json={"name": "Lowbie"})
    assert rv.status_code == 200
    p = rv.get_json()
    pid = p["id"]

    # Liste resources pour trouver une ressource qui exige un level >= 2 (ex: stone)
    rv = client.get("/api/resources")
    assert rv.status_code == 200
    res = rv.get_json()
    demanding = None
    for r in res:
        if r["unlock_min_level"] >= 2:  # on cible une ressource non déblocable au lvl 0
            demanding = r
            break
    assert demanding is not None, "Besoin d'une ressource avec unlock_min_level >= 2 dans le seed"

    # Essaye de l'unlock au level 0 -> 403
    rv = client.post("/api/tiles/unlock", json={"playerId": pid, "resource": demanding["key"]})
    assert rv.status_code == 403
    data = rv.get_json()
    assert data["error"] == "level_too_low"
    assert data["required"] == demanding["unlock_min_level"]

    