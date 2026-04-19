# app/services/skill_engine.py
"""
Skill engine — passive skill progression system.

Categories:
  - resource : progresses on resource collection (subject_key = resource key)
  - land     : progresses on land tile actions  (subject_key = land key)
  - craft    : progresses on crafts             (subject_key = item_key or None for global)

Bonus types:
  double_drop          : % chance of getting 2x loot
  cooldown_reduction   : seconds removed from slot cooldown
  craft_time_reduction : % reduction of craft duration
  instant_craft_chance : % chance of instant craft
  xp_bonus             : % extra XP per action
  shard_chance         : % chance to receive shards on harvest

Safety caps (prevent runaway values):
  double_drop          : max 50 %
  cooldown_reduction   : max 30 s
  craft_time_reduction : max 50 %
  instant_craft_chance : max 30 %
  xp_bonus             : max 100 %
  shard_chance         : max 30 %
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# ── Safety caps ───────────────────────────────────────────────────────────────
BONUS_CAPS: Dict[str, float] = {
    "double_drop":          50.0,
    "cooldown_reduction":   30.0,
    "craft_time_reduction": 50.0,
    "instant_craft_chance": 30.0,
    "xp_bonus":            100.0,
    "shard_chance":         30.0,
}

MAX_SKILL_LEVEL = 5


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_or_create_player_skill(session, player_id: int, skill_key: str):
    from app.models import PlayerSkill
    ps = (
        session.query(PlayerSkill)
        .filter_by(player_id=player_id, skill_key=skill_key)
        .first()
    )
    if ps is None:
        ps = PlayerSkill(player_id=player_id, skill_key=skill_key, progress=0, level=0)
        session.add(ps)
        session.flush()
    return ps


def _compute_level_from_progress(levels_cfg: List[dict], progress: int) -> int:
    """Return the highest level whose req <= progress, max MAX_SKILL_LEVEL."""
    current = 0
    for entry in sorted(levels_cfg, key=lambda e: e.get("level", 0)):
        lvl = int(entry.get("level", 0))
        req = int(entry.get("req", 0))
        if lvl > MAX_SKILL_LEVEL:
            continue
        if progress >= req:
            current = lvl
    return current


def _bonuses_at_level(levels_cfg: List[dict], level: int) -> List[dict]:
    """Return bonus list for a given level (cumulative up to that level)."""
    if level <= 0:
        return []
    # Collect all bonuses from level 1 up to `level`
    # We merge by type, taking the value from the exact level entry
    bonus_map: Dict[str, float] = {}
    for entry in sorted(levels_cfg, key=lambda e: e.get("level", 0)):
        if entry.get("level", 0) > level:
            break
        for b in entry.get("bonuses", []):
            btype = b.get("type")
            bval = float(b.get("value", 0))
            bonus_map[btype] = bval  # latest level's value wins (overrides previous)
    return [{"type": t, "value": v} for t, v in bonus_map.items()]


# ── Public API ────────────────────────────────────────────────────────────────

def record_skill_progress(
    player_id: int,
    category: str,
    subject_key: Optional[str],
    amount: int = 1,
    session=None,
) -> List[Dict[str, Any]]:
    """
    Record progress on a skill and check for level-ups.

    Returns list of level-up events: [{"skill_key": ..., "new_level": ...}]
    Set session=None to use a fresh one (auto-closed).
    """
    if amount <= 0:
        return []

    def _do(s):
        from app.models import SkillDef, PlayerSkill

        # Find all matching SkillDefs (may be 0 or 1, but built for extensibility)
        q = s.query(SkillDef).filter_by(category=category, enabled=True)
        if subject_key:
            q = q.filter_by(subject_key=subject_key)
        else:
            q = q.filter(SkillDef.subject_key.is_(None))
        skills = q.all()

        level_ups = []
        for skill in skills:
            ps = _get_or_create_player_skill(s, player_id, skill.key)
            old_level = ps.level
            ps.progress = int(ps.progress or 0) + amount
            new_level = _compute_level_from_progress(skill.levels or [], ps.progress)
            if new_level != old_level:
                ps.level = new_level
                level_ups.append({"skill_key": skill.key, "new_level": new_level,
                                  "name_fr": skill.name_fr, "name_en": skill.name_en})
        # No commit here — caller owns the transaction
        return level_ups

    if session is not None:
        return _do(session)

    from app.db import SessionLocal
    with SessionLocal() as s:
        result = _do(s)
        s.commit()
        return result


def get_player_bonus(
    player_id: int,
    bonus_type: str,
    category: Optional[str] = None,
    subject_key: Optional[str] = None,
    session=None,
) -> float:
    """
    Get total (capped) bonus value for a player for a given bonus_type.

    Example: get_player_bonus(pid, "double_drop", "resource", "branch")
    Returns float (e.g. 6.0 for 6%).
    """
    def _do(s):
        from app.models import SkillDef, PlayerSkill

        q = s.query(PlayerSkill, SkillDef).join(
            SkillDef, PlayerSkill.skill_key == SkillDef.key
        ).filter(
            PlayerSkill.player_id == player_id,
            SkillDef.enabled == True,
            PlayerSkill.level > 0,
        )
        if category:
            q = q.filter(SkillDef.category == category)
        if subject_key:
            q = q.filter(SkillDef.subject_key == subject_key)

        total = 0.0
        for ps, skill in q.all():
            bonuses = _bonuses_at_level(skill.levels or [], ps.level)
            for b in bonuses:
                if b["type"] == bonus_type:
                    total += float(b["value"])

        cap = BONUS_CAPS.get(bonus_type, 9999.0)
        return min(total, cap)

    if session is not None:
        return _do(session)

    from app.db import SessionLocal
    with SessionLocal() as s:
        return _do(s)


def get_all_player_skills(player_id: int, session=None) -> List[Dict[str, Any]]:
    """
    Return all skill data for profile display.
    Skills with no PlayerSkill entry (level 0, progress 0) are included.
    """
    def _do(s):
        from app.models import SkillDef, PlayerSkill

        all_defs = s.query(SkillDef).filter_by(enabled=True).order_by(
            SkillDef.category, SkillDef.key
        ).all()

        ps_map = {
            ps.skill_key: ps
            for ps in s.query(PlayerSkill).filter_by(player_id=player_id).all()
        }

        result = []
        for skill in all_defs:
            ps = ps_map.get(skill.key)
            progress = int(ps.progress) if ps else 0
            level = int(ps.level) if ps else 0

            # Next level req
            next_req = None
            for entry in sorted(skill.levels or [], key=lambda e: e.get("level", 0)):
                if entry.get("level", 0) > level:
                    next_req = int(entry.get("req", 0))
                    break

            active_bonuses = _bonuses_at_level(skill.levels or [], level)

            result.append({
                "key": skill.key,
                "name_fr": skill.name_fr,
                "name_en": skill.name_en,
                "category": skill.category,
                "subject_key": skill.subject_key,
                "level": level,
                "max_level": MAX_SKILL_LEVEL,
                "progress": progress,
                "next_req": next_req,
                "bonuses": active_bonuses,
                "all_levels": skill.levels or [],
            })
        return result

    if session is not None:
        return _do(session)

    from app.db import SessionLocal
    with SessionLocal() as s:
        return _do(s)
