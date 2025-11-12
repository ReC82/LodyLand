# =============================================================================
# File: app/progression.py
# Purpose: Minimal level/XP progression helpers for the MVP.
# =============================================================================

# XP thresholds per level (index = level)
# Example: thresholds[1] = 10 means "to be level 1, you need >= 10 XP".
LEVEL_THRESHOLDS = [0, 10, 30, 60, 100]

def level_for_xp(xp: int) -> int:
    """Return the level reached for a given xp according to LEVEL_THRESHOLDS."""
    if xp is None:
        xp = 0
    lvl = 0
    for i, need in enumerate(LEVEL_THRESHOLDS):
        if xp >= need:
            lvl = i
        else:
            break
    return lvl

def next_threshold(level: int) -> int | None:
    """Return the XP required to reach the next level (or None if max)."""
    nxt = level + 1
    return LEVEL_THRESHOLDS[nxt] if nxt < len(LEVEL_THRESHOLDS) else None
