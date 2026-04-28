# app/routes/api_notebook.py
from __future__ import annotations

import math
from pathlib import Path

import yaml
from flask import Blueprint, jsonify, request

from app.db import SessionLocal
from app.models import Player, PlayerCard, PlayerLandSlots
from app.auth import get_current_player

# Intended game progression order for lands in the notebook
_LAND_SORT_ORDER: dict[str, int] = {
    "forest": 1,
    "beach": 2,
    "cave": 3,
    "desert": 4,
    "lake": 5,
    "frozen": 6,
    "haunted_forest": 7,
    "jurassic": 8,
    "ruins": 9,
}

bp = Blueprint("notebook", __name__)

def _load_lands_defs() -> dict:
    path = Path("app/data/lands.yml")
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_items_defs() -> dict:
    """
    items.yml can be either:
      - { items: {key: {...}, ... } }
      - { key: {...}, ... }
    """
    path = Path("app/data/items.yml")
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if isinstance(raw, dict) and isinstance(raw.get("items"), dict):
        return raw["items"]
    return raw if isinstance(raw, dict) else {}


def _item_meta(items_defs: dict, key: str) -> dict:
    """
    Return a compact meta block for a resource/tool/item:
    { key, label, icon, kind }
    """
    d = (items_defs or {}).get(key) if isinstance(items_defs, dict) else None
    if not isinstance(d, dict):
        return {"key": key, "label": key, "icon": None, "kind": None}

    return {
        "key": key,
        "label": d.get("label") or key,
        "icon": d.get("icon"),  # usually '/static/...'
        "kind": d.get("kind"),
    }


# -------------------------
# Helpers: slots + loot merge
# -------------------------
def _compute_next_slot_cost(base_cost: float, multiplier: float, extra_owned: int) -> int:
    """
    next_cost = ceil(base_cost * multiplier ** extra_owned)
    """
    try:
        base = float(base_cost or 0)
        mult = float(multiplier or 1.0)
        n = int(extra_owned or 0)
    except Exception:
        return 0

    if base <= 0:
        return 0
    if mult <= 0:
        mult = 1.0

    return int(math.ceil(base * (mult**n)))


def _get_extra_slots_owned(session, player_id: int, land_key: str) -> int:
    """
    Optional: if you have a table to store extra slots, read it.
    If the table does not exist (or any error), return 0 safely.
    """
    try:
        sql = """
        SELECT extra_slots
        FROM player_land_slots
        WHERE player_id = :pid AND land_key = :lkey
        LIMIT 1
        """
        row = session.execute(sql, {"pid": player_id, "lkey": land_key}).fetchone()
        if not row:
            return 0
        return int(row[0] or 0)
    except Exception:
        return 0


def _merge_loot(tool_cfg: dict, any_extra: list) -> list:
    """
    Merge:
      - tool.base_loot
      - tool.extra_loot
      - tools.any.extra_loot
    into one flat list.
    """
    out = []

    base_loot = tool_cfg.get("base_loot") or []
    extra_loot = tool_cfg.get("extra_loot") or []

    for src in (base_loot, extra_loot, any_extra):
        if not isinstance(src, list):
            continue
        for it in src:
            if not isinstance(it, dict):
                continue
            res = it.get("resource")
            if not res:
                continue

            chance = float(it.get("chance") or 0)
            mn = int(it.get("min") or 1)
            mx = int(it.get("max") or mn)

            out.append(
                {
                    "resource": res,
                    "chance": chance,
                    "chance_pct": int(round(chance * 100)),
                    "min": mn,
                    "max": mx,
                }
            )

    return out


def _compute_xp_per_collect(land_xp: float, tool_multiplier: float) -> float:
    try:
        lx = float(land_xp or 0)
        tm = float(tool_multiplier or 1.0)
    except Exception:
        return 0.0
    if tm <= 0:
        tm = 1.0
    return lx * tm


# -------------------------
# Route
# -------------------------
@bp.get("/notebook")
def get_notebook():
    with SessionLocal() as s:
        me = get_current_player(s)
        if not me:
            return jsonify({"error": "not_authenticated"}), 401

        lands_defs = _load_lands_defs()
        items_defs = _load_items_defs()

        owned_cards = s.query(PlayerCard).filter(PlayerCard.player_id == me.id).all()
        owned = {c.card_key for c in owned_cards if (c.qty or 0) > 0}

        lands_payload = []

        for land_key, cfg in (lands_defs or {}).items():
            if not isinstance(cfg, dict):
                continue

            starting = bool(cfg.get("starting_land"))
            unlocked = starting or (f"land_{land_key}" in owned) or (land_key in owned)

            land_label = (
                cfg.get("label")
                or cfg.get("label_fr")
                or cfg.get("label_en")
                or land_key.replace("_", " ").capitalize()
            )
            land_xp = cfg.get("xp_per_collect") or 0

            payload = {
                "key": land_key,
                "label": land_label,
                "short_description": cfg.get("short_description"),
                "full_description": cfg.get("full_description"),
                "logo": cfg.get("logo"),
                "slot_icon": cfg.get("slot_icon"),
                "starting_land": starting,
                "unlocked": unlocked,
                "xp_per_collect": land_xp,
            }

            if unlocked:
                # Slots
                base_slots = int(cfg.get("slots") or 0)
                base_cost = cfg.get("additional_slot_base_cost_diams") or 0
                mult = cfg.get("additional_slot_cost_multiplier") or 1.0

                pls = (
                    s.query(PlayerLandSlots)
                    .filter_by(player_id=me.id, land_key=land_key)
                    .first()
                )
                extra_owned = pls.extra_slots if pls else 0
                next_cost = _compute_next_slot_cost(base_cost, mult, extra_owned)

                payload["slots"] = {
                    "base": base_slots,
                    "extra_owned": extra_owned,
                    "total": base_slots + extra_owned,
                    "next_cost_diams": next_cost,
                }

                tools = cfg.get("tools") or {}
                if not isinstance(tools, dict):
                    tools = {}

                any_cfg = tools.get("any") or {}
                any_extra = any_cfg.get("extra_loot") or []
                if not isinstance(any_extra, list):
                    any_extra = []

                tool_details = []
                loot_keys = set()

                for tool_key, tcfg in tools.items():
                    if tool_key == "any":
                        continue
                    if not isinstance(tcfg, dict):
                        continue

                    merged_loot = _merge_loot(tcfg, any_extra)

                    enriched_loot = []
                    for row in merged_loot:
                        rk = row.get("resource")
                        if rk:
                            loot_keys.add(rk)

                        meta = _item_meta(items_defs, rk) if rk else {"key": rk, "label": rk, "icon": None, "kind": None}

                        # ✅ Key point: expose icon/label/kind directly on the loot row
                        enriched_loot.append(
                            {
                                **row,
                                "key": rk,
                                "label": meta.get("label"),
                                "icon": meta.get("icon"),
                                "kind": meta.get("kind"),

                                # ✅ backward/forward compatibility (optional but useful)
                                "resource_obj": {
                                    "key": rk,
                                    "label": meta.get("label"),
                                    "icon": meta.get("icon"),
                                    "kind": meta.get("kind"),
                                },
                            }
                        )

                    tool_meta = _item_meta(items_defs, tool_key)
                    tool_label = tcfg.get("label") or tool_meta.get("label") or tool_key

                    xp_mult = tcfg.get("xp_multiplier")
                    xp_mult = float(xp_mult) if xp_mult is not None else 1.0
                    xp_gain = _compute_xp_per_collect(land_xp, xp_mult)

                    tool_details.append(
                        {
                            "tool_key": tool_key,
                            "label": tool_label,
                            "emoji": tcfg.get("emoji") or "",
                            "icon": tool_meta.get("icon"),
                            "cooldown_seconds": tcfg.get("cooldown_seconds"),
                            "xp_multiplier": xp_mult,
                            "xp_gain": xp_gain,
                            "loot": enriched_loot,

                            # optional
                            "tool_obj": {
                                "key": tool_key,
                                "label": tool_label,
                                "icon": tool_meta.get("icon"),
                                "kind": tool_meta.get("kind"),
                            },
                        }
                    )

                tool_details.sort(
                    key=lambda t: (
                        t.get("tool_key") != "hands",
                        (t.get("label") or "").lower(),
                    )
                )

                payload["loot_keys"] = sorted(loot_keys)
                payload["tools"] = tool_details

            lands_payload.append(payload)

        lands_payload.sort(key=lambda x: (
            not x["unlocked"],
            _LAND_SORT_ORDER.get(x["key"], 999),
            (x.get("label") or "").lower(),
        ))

        return jsonify({"player": {"id": me.id, "level": me.level}, "lands": lands_payload}), 200
