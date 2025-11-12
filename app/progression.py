# =============================================================================
# File: app/progression.py
# Purpose: Minimal level/XP progression helpers for the MVP.
# =============================================================================

# XP thresholds per level (index = level)
# Example: thresholds[1] = 10 means "to be level 1, you need >= 10 XP".
LEVELS = [10, 30, 60, 100, 150] 

XP_PER_COLLECT = 1

def level_for_xp(xp: int) -> int:
    lvl = 0
    for thr in LEVELS:
        if xp >= thr:
            lvl += 1
        else:
            break
    return lvl

def next_threshold(level: int):
    # retourne le seuil CUMULATIF du prochain niveau
    if level >= len(LEVELS):
        return None  # max level
    return LEVELS[level]
