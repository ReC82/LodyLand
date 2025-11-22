# app/village_shop.py
from __future__ import annotations

from pathlib import Path
from functools import lru_cache
import datetime as dt
import yaml

DATA_DIR = Path(__file__).resolve().parent / "data"
VILLAGE_SHOP_FILE = DATA_DIR / "village_shop.yml"


@lru_cache(maxsize=1)
def _load_village_shop_raw() -> dict:
    """Load the raw YAML config for the village shop (cached)."""
    if not VILLAGE_SHOP_FILE.exists():
        return {"offers": []}

    with VILLAGE_SHOP_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if "offers" not in data or data["offers"] is None:
        data["offers"] = []

    return data


def get_all_village_offers() -> list[dict]:
    """Return all village offers as defined in the YAML file (no filtering)."""
    data = _load_village_shop_raw()
    offers = data.get("offers", []) or []
    return list(offers)


def get_active_village_offers(today: dt.date | None = None) -> list[dict]:
    """
    Return the list of offers that are active for the given date.

    Rules:
    - offer.enabled must be True (or missing -> treated as True)
    - start_date <= today <= end_date (inclusive)
    """
    if today is None:
        today = dt.date.today()

    active: list[dict] = []
    for offer in get_all_village_offers():
        if not offer.get("enabled", True):
            continue

        start_str = offer.get("start_date")
        end_str = offer.get("end_date")
        if not start_str or not end_str:
            continue

        try:
            start = dt.date.fromisoformat(start_str)
            end = dt.date.fromisoformat(end_str)
        except ValueError:
            continue

        if start <= today <= end:
            active.append(offer)

    return active


def get_village_excluded_card_keys(now: dt.datetime | None = None) -> set[str]:
    """
    Return all card keys that are currently sold in the village shop.

    These keys must be hidden from the main shop.
    Only offers with item_type == "card" are considered.
    """
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)

    active_offers = get_active_village_offers(today=now.date())
    excluded: set[str] = set()

    for offer in active_offers:
        if offer.get("item_type") != "card":
            continue

        card_key = offer.get("item_key")
        if card_key:
            excluded.add(card_key)

    return excluded
