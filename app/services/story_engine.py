# app/services/story_engine.py
"""
Story engine: find which story events should be shown to a player
based on:
- their level
- which land they just unlocked or entered
- first login, etc.

This does NOT handle persistence (which events were already shown).
The caller must provide a set of already_seen_ids.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set

from .levels_loader import get_all_levels


# Type alias for clarity
StoryEvent = Dict[str, Any]


def _iter_all_story_events() -> Iterable[StoryEvent]:
    """Yield all story events from all levels."""
    for lvl in get_all_levels():
        level_number = int(lvl.get("level", 0))
        events = lvl.get("story_events") or []
        if not isinstance(events, list):
            continue

        for ev in events:
            if not isinstance(ev, dict):
                continue

            # Attach level info for convenience
            ev = dict(ev)  # shallow copy
            ev.setdefault("level", level_number)
            yield ev


def find_story_events_for_trigger(
    *,
    trigger: str,
    player_level: int,
    already_seen_ids: Optional[Set[str]] = None,
    land_key: Optional[str] = None,
    just_reached_level: Optional[int] = None,
    is_first_login: bool = False,
) -> List[StoryEvent]:
    """
    Return all story events matching the given trigger and context.

    Parameters
    ----------
    trigger:
        One of "on_first_login", "on_level_reached",
        "on_land_unlocked", "on_enter_land", ...
    player_level:
        Current player level (after any update).
    already_seen_ids:
        Set of story event ids already shown to this player.
        (Use empty set if you don't track them yet.)
    land_key:
        Required for land-related triggers (on_land_unlocked, on_enter_land).
    just_reached_level:
        Level just reached, for on_level_reached events.
    is_first_login:
        Whether this is the player's first login, for on_first_login events.
    """
    if already_seen_ids is None:
        already_seen_ids = set()

    result: List[StoryEvent] = []

    for ev in _iter_all_story_events():
        ev_trigger = ev.get("trigger")

        if ev_trigger != trigger:
            continue

        # Basic id filtering
        ev_id = ev.get("id")
        if not ev_id or ev_id in already_seen_ids:
            # no id or already seen -> skip
            continue

        ev_level = int(ev.get("level", 0))

        # --- Trigger-specific filtering ------------------------------------

        if trigger == "on_first_login":
            # Only if this call is actually for a first login
            if not is_first_login:
                continue
            # optional: you could also restrict "max level" here, but not needed

        elif trigger == "on_level_reached":
            # We need a level to compare
            if just_reached_level is None:
                continue
            # Only story events tied to that specific level
            if ev_level != just_reached_level:
                continue

        elif trigger in ("on_land_unlocked", "on_enter_land"):
            # We expect a land_key in both the event and the call context
            ev_land_key = ev.get("land_key")
            if not land_key or not ev_land_key:
                continue
            if ev_land_key != land_key:
                continue

        # You can add more trigger types here if needed

        # Optional: restrict by player_level if it makes sense
        # (e.g., don't show events for levels above player_level)
        if ev_level > player_level:
            continue

        result.append(ev)

    # You can define an order, for now we sort by level then id
    result.sort(key=lambda e: (int(e.get("level", 0)), str(e.get("id", ""))))
    return result
