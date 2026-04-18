# app/services/story_engine.py
"""
Story engine: find which story events should be shown to a player.

Events are now stored in the DB (StoryEventDef) and managed via the admin panel.
The YAML file (levels.yml) is no longer the source of truth for story events —
it is only used once on first boot to seed the DB.

This module does NOT handle persistence (which events were already shown).
The caller must provide a set of already_seen_ids.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set

# Type alias for clarity
StoryEvent = Dict[str, Any]


def _row_to_event(ev) -> StoryEvent:
    """Convert a StoryEventDef ORM row to a plain dict."""
    return {
        "id": ev.id,
        "level": ev.level,
        "trigger": ev.trigger,
        "land_key": ev.land_key,
        "show_once": ev.show_once,
        "modal_variant": ev.modal_variant,
        "pages": ev.pages or [],
        "quest_start": ev.quest_start,
    }


def _iter_all_story_events(session=None) -> Iterable[StoryEvent]:
    """Yield all enabled story events from the DB."""
    from app.models import StoryEventDef

    def _query(s):
        rows = (
            s.query(StoryEventDef)
            .filter_by(enabled=True)
            .order_by(StoryEventDef.level, StoryEventDef.sort_order, StoryEventDef.id)
            .all()
        )
        for row in rows:
            yield _row_to_event(row)

    if session is not None:
        yield from _query(session)
    else:
        from app.db import SessionLocal
        with SessionLocal() as s:
            # materialize to avoid session-closed issues
            yield from list(_query(s))


def find_story_events_for_trigger(
    *,
    trigger: str,
    player_level: int,
    already_seen_ids: Optional[Set[str]] = None,
    land_key: Optional[str] = None,
    just_reached_level: Optional[int] = None,
    is_first_login: bool = False,
    session=None,
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
    land_key:
        Required for land-related triggers.
    just_reached_level:
        Level just reached, for on_level_reached events.
    is_first_login:
        Whether this is the player's first login.
    session:
        Optional DB session to reuse.
    """
    if already_seen_ids is None:
        already_seen_ids = set()

    result: List[StoryEvent] = []

    for ev in _iter_all_story_events(session):
        ev_trigger = ev.get("trigger")

        if ev_trigger != trigger:
            continue

        ev_id = ev.get("id")
        if not ev_id or ev_id in already_seen_ids:
            continue

        ev_level = int(ev.get("level", 0))

        if trigger == "on_first_login":
            if not is_first_login:
                continue

        elif trigger == "on_level_reached":
            if just_reached_level is None:
                continue
            if ev_level != just_reached_level:
                continue

        elif trigger in ("on_land_unlocked", "on_enter_land"):
            ev_land_key = ev.get("land_key")
            if not land_key or not ev_land_key:
                continue
            if ev_land_key != land_key:
                continue

        if ev_level > player_level:
            continue

        result.append(ev)

    result.sort(key=lambda e: (int(e.get("level", 0)), str(e.get("id", ""))))
    return result
