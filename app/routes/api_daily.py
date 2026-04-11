# app/routes/api_daily.py

import random
from datetime import datetime, timezone, timedelta, date

from flask import Blueprint, jsonify
from app.db import SessionLocal
from app.models import Player, PlayerCard, ResourceStock
from app.progression import next_threshold, apply_xp_and_level_up
from app.auth import get_current_player

bp = Blueprint("daily", __name__)

# ---------------------------------------------------------------------------
# Land → resource pool
# Each entry: (resource_key, rarity)
# Rarity weights: common=60, uncommon=25, rare=12, epic=3
# ---------------------------------------------------------------------------
LAND_RESOURCES: dict[str, list[tuple[str, str]]] = {
    "forest": [
        ("branch",           "common"),
        ("dirt",             "common"),
        ("palm_leaf",        "common"),
        ("small_stone",      "common"),
        ("vine",             "uncommon"),
        ("bark",             "uncommon"),
        ("worm",             "uncommon"),
        ("palm_wood_log",    "uncommon"),
        ("apple",            "uncommon"),
        ("flint",            "uncommon"),
        ("resin",            "rare"),
        ("ancient_bark",     "rare"),
        ("clay",             "rare"),
        ("ancient_relic_part", "epic"),
    ],
    "beach": [
        ("sand",             "common"),
        ("seashell",         "uncommon"),
        ("starfish",         "uncommon"),
        ("pearl",            "rare"),
        ("nautilus_shell",   "rare"),
    ],
    "cave": [
        ("stone",            "common"),
        ("stone_dust",       "common"),
        ("stone_chunk",      "common"),
        ("coal",             "common"),
        ("gold_dust",        "uncommon"),
        ("aluminium_foil_fragment", "uncommon"),
        ("iron_ore",         "uncommon"),
        ("gold_ore",         "rare"),
        ("gold_leaf",        "rare"),
        ("cobalt_ore",       "rare"),
        ("moon_crystal_shard", "epic"),
    ],
    "desert": [
        ("sand_fine",        "common"),
        ("cactus_fiber",     "common"),
        ("time_sand",        "rare"),
    ],
}

# Card key → land key
CARD_TO_LAND: dict[str, str] = {
    "land_forest":       "forest",
    "land_beach":        "beach",
    "land_cave":         "cave",
    "land_desert":       "desert",
    "land_farm":         "farm",
    "land_lake":         "lake",
    "land_volcano":      "volcano",
    "land_mountain":     "mountain",
    "land_haunted_woods": "haunted_woods",
    "land_frozen":       "frozen",
}

# Starting lands (always unlocked, no card needed)
STARTING_LANDS = {"forest"}

# Rarity weights for random pick
RARITY_WEIGHT = {"common": 60, "uncommon": 25, "rare": 12, "epic": 3}

# Quantities per rarity × level tier (0=beginner, 1=mid, 2=advanced)
RARITY_QTY: dict[str, dict[int, tuple[int, int]]] = {
    "common":   {0: (2, 5),  1: (3, 8),  2: (5, 12)},
    "uncommon": {0: (1, 2),  1: (2, 4),  2: (3, 6)},
    "rare":     {0: (1, 1),  1: (1, 2),  2: (1, 3)},
    "epic":     {0: (1, 1),  1: (1, 1),  2: (1, 2)},
}

# Shard + XP base ranges by level tier
SHARD_RANGE  = {0: (20, 50),  1: (40, 90),  2: (70, 150)}
XP_RANGE     = {0: (10, 25),  1: (20, 50),  2: (40, 100)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_tier(level: int) -> int:
    if level < 3:
        return 0
    if level < 7:
        return 1
    return 2


def _unlocked_lands(player_id: int, session) -> list[str]:
    lands = list(STARTING_LANDS)
    rows = session.query(PlayerCard).filter_by(player_id=player_id).all()
    for pc in rows:
        land = CARD_TO_LAND.get(pc.card_key)
        if land and land not in lands:
            lands.append(land)
    return lands


def _weighted_choice(pool: list[tuple[str, str]]) -> tuple[str, str]:
    """Pick one (key, rarity) from pool, weighted by rarity."""
    weights = [RARITY_WEIGHT.get(r, 10) for _, r in pool]
    total = sum(weights)
    r = random.random() * total
    acc = 0
    for item, rarity in pool:
        acc += RARITY_WEIGHT.get(rarity, 10)
        if r <= acc:
            return item, rarity
    return pool[-1]


def _roll_rewards(player, session, new_streak: int) -> list[dict]:
    """Generate reward list for this chest claim."""
    tier = _get_tier(player.level or 0)
    day_in_cycle = ((new_streak - 1) % 7) + 1          # 1-7
    weeks_done   = (new_streak - 1) // 7
    week_mult    = min(1.0 + weeks_done * 0.15, 2.0)   # +15% per week, cap 2×
    is_week_end  = (day_in_cycle == 7)

    lands        = _unlocked_lands(player.id, session)
    resource_pool: list[tuple[str, str]] = []
    for land in lands:
        resource_pool.extend(LAND_RESOURCES.get(land, []))

    rewards: list[dict] = []

    # --- Slot 1: always shards -------------------------------------------------
    lo, hi = SHARD_RANGE[tier]
    amt = random.randint(lo, hi)
    if is_week_end:
        amt = int(amt * week_mult)
    rewards.append({
        "type":   "shards",
        "amount": amt,
        "icon":   "/static/assets/img/ui/shards.png",
        "label":  "Éclats",
    })

    # --- Slot 2: resource (if pool available) OR xp ----------------------------
    if resource_pool:
        key, rarity = _weighted_choice(resource_pool)
        lo2, hi2 = RARITY_QTY[rarity][tier]
        qty = random.randint(lo2, hi2)
        if is_week_end:
            qty = max(1, int(qty * week_mult))
        rewards.append({
            "type":   "resource",
            "key":    key,
            "amount": qty,
            "icon":   f"/static/assets/img/items/resources/{key}.png",
            "label":  key,
        })
    else:
        lo2, hi2 = XP_RANGE[tier]
        xp_amt = random.randint(lo2, hi2)
        if is_week_end:
            xp_amt = int(xp_amt * week_mult)
        rewards.append({
            "type":   "xp",
            "amount": xp_amt,
            "icon":   "/static/assets/img/ui/xp_icon.png",
            "label":  "XP",
        })

    # --- Slot 3: XP, second resource, or essence (rare) -----------------------
    roll = random.random()
    if roll < 0.50 and resource_pool:
        # Second resource
        key2, rarity2 = _weighted_choice(resource_pool)
        lo3, hi3 = RARITY_QTY[rarity2][tier]
        qty2 = random.randint(lo3, hi3)
        if is_week_end:
            qty2 = max(1, int(qty2 * week_mult))
        rewards.append({
            "type":   "resource",
            "key":    key2,
            "amount": qty2,
            "icon":   f"/static/assets/img/items/resources/{key2}.png",
            "label":  key2,
        })
    elif roll < 0.92:
        # XP
        lo3, hi3 = XP_RANGE[tier]
        xp_amt3 = random.randint(lo3, hi3)
        if is_week_end:
            xp_amt3 = int(xp_amt3 * week_mult)
        rewards.append({
            "type":   "xp",
            "amount": xp_amt3,
            "icon":   "/static/assets/img/ui/xp_icon.png",
            "label":  "XP",
        })
    else:
        # Essence (rare, ~8%)
        essence_amt = random.randint(1, max(1, tier + 1))
        if is_week_end:
            essence_amt = max(1, int(essence_amt * week_mult))
        rewards.append({
            "type":   "essence",
            "amount": essence_amt,
            "icon":   "/static/assets/img/ui/essence.png",
            "label":  "Essences",
        })

    # --- Day 7 bonus: extra resource or essence --------------------------------
    if is_week_end:
        if resource_pool:
            key_b, rarity_b = _weighted_choice(resource_pool)
            lo_b, hi_b = RARITY_QTY[rarity_b][tier]
            qty_b = max(1, int(random.randint(lo_b, hi_b) * week_mult))
            rewards.append({
                "type":   "resource",
                "key":    key_b,
                "amount": qty_b,
                "icon":   f"/static/assets/img/items/resources/{key_b}.png",
                "label":  key_b,
            })
        else:
            rewards.append({
                "type":   "essence",
                "amount": max(1, tier + 1),
                "icon":   "/static/assets/img/ui/essence.png",
                "label":  "Essences",
            })

    return rewards


def _apply_rewards(player, rewards: list[dict], session) -> None:
    """Persist each reward to the player record / stocks."""
    for r in rewards:
        rtype = r["type"]
        amount = r.get("amount", 0)
        if amount <= 0:
            continue

        if rtype == "shards":
            player.shards = (player.shards or 0) + amount

        elif rtype == "essence":
            player.essence = (player.essence or 0) + amount

        elif rtype == "xp":
            try:
                apply_xp_and_level_up(session, player, float(amount))
            except Exception:
                player.xp = (player.xp or 0.0) + float(amount)

        elif rtype == "resource":
            key = r.get("key", "")
            if not key:
                continue
            stock = (
                session.query(ResourceStock)
                .filter_by(player_id=player.id, resource=key)
                .one_or_none()
            )
            if stock:
                stock.qty = (stock.qty or 0.0) + float(amount)
            else:
                session.add(ResourceStock(
                    player_id=player.id,
                    resource=key,
                    qty=float(amount),
                ))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@bp.post("/daily")
def claim_daily():
    """Claim daily chest (once per UTC day) + streak management."""
    with SessionLocal() as s:
        me = get_current_player(s)
        if not me:
            return jsonify({"error": "not_authenticated"}), 401

        today_utc: date = datetime.now(timezone.utc).date()

        # Already claimed today?
        if me.last_daily == today_utc:
            next_reset = (
                datetime.now(timezone.utc)
                .replace(hour=0, minute=0, second=0, microsecond=0)
                + timedelta(days=1)
            )
            current_streak  = me.daily_streak or 0
            day_in_cycle    = ((current_streak - 1) % 7) + 1 if current_streak > 0 else 1
            return jsonify({
                "error":         "already_claimed",
                "already_claimed": True,
                "next_at":       next_reset.isoformat(),
                "day_in_cycle":  day_in_cycle,
                "streak": {
                    "current": current_streak,
                    "best":    me.best_streak or 0,
                },
            }), 409

        # --- Streak calculation -------------------------------------------------
        new_streak = 1
        if me.last_daily:
            if me.last_daily == (today_utc - timedelta(days=1)):
                new_streak = (me.daily_streak or 0) + 1

        me.last_daily    = today_utc
        me.daily_streak  = new_streak
        me.best_streak   = max(me.best_streak or 0, new_streak)

        # --- Generate + apply rewards ------------------------------------------
        rewards = _roll_rewards(me, s, new_streak)
        _apply_rewards(me, rewards, s)

        s.commit()
        s.refresh(me)

        next_reset = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=1)
        )

        day_in_cycle = ((new_streak - 1) % 7) + 1
        weeks_done   = (new_streak - 1) // 7
        week_mult    = round(min(1.0 + weeks_done * 0.15, 2.0), 2)

        return jsonify({
            "ok": True,
            "rewards": rewards,
            "day_in_cycle": day_in_cycle,
            "week_multiplier": week_mult,
            "player": {
                "id":      me.id,
                "name":    me.name,
                "shards":  me.shards,
                "essence": me.essence,
                "xp":      me.xp,
                "level":   me.level,
                "next_xp": next_threshold(me.level),
            },
            "streak": {
                "current": me.daily_streak,
                "best":    me.best_streak,
            },
            "next_at": next_reset.isoformat(),
        }), 200


@bp.get("/daily/status")
def daily_status():
    """Return daily chest status without modifying anything."""
    with SessionLocal() as s:
        me = get_current_player(s)
        if not me:
            return jsonify({"error": "not_authenticated"}), 401

        today_utc: date = datetime.now(timezone.utc).date()

        current_streak = me.daily_streak or 0
        best_streak    = me.best_streak or 0
        day_in_cycle   = ((current_streak - 1) % 7) + 1 if current_streak > 0 else 1

        next_reset_dt  = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            + timedelta(days=1)
        )

        eligible = not me.last_daily or me.last_daily < today_utc

        return jsonify({
            "eligible":    eligible,
            "next_reset":  next_reset_dt.isoformat(),
            "day_in_cycle": day_in_cycle,
            "streak": {
                "current": current_streak,
                "best":    best_streak,
            },
        }), 200
