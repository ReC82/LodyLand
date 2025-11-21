from __future__ import annotations

from pathlib import Path
from functools import lru_cache
import datetime as dt
import yaml

# Base directory for data files (same style as lands.yml)
DATA_DIR = Path(__file__).resolve().parent / "data"
VILLAGE_SHOP_FILE = DATA_DIR / "village_shop.yml"


@lru_cache(maxsize=1)
def _load_village_shop_raw() -> dict:
    """
    Load the raw YAML config for the village shop.
    Result is cached to avoid re-reading the file on every request.
    """
    if not VILLAGE_SHOP_FILE.exists():
        # Fail-safe: if file missing, return empty structure
        return {"offers": []}

    with VILLAGE_SHOP_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # Ensure offers is always a list
    if "offers" not in data or data["offers"] is None:
        data["offers"] = []

    return data


def get_all_village_offers() -> list[dict]:
    """
    Return all village offers as defined in the YAML file.
    No date / enabled filtering is applied here.
    """
    data = _load_village_shop_raw()
    offers = data.get("offers", []) or []
    # Return a shallow copy to avoid accidental in-place modifications
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
            # If dates are missing, we skip the offer for safety
            continue

        try:
            start = dt.date.fromisoformat(start_str)
            end = dt.date.fromisoformat(end_str)
        except ValueError:
            # Invalid date format -> skip
            continue

        if start <= today <= end:
            active.append(offer)

    return active


def get_village_excluded_card_keys(today: dt.date | None = None) -> set[str]:
    """
    Return the set of card_key that are currently sold in the village shop.

    This can be used to exclude these keys from the 'normal' shop so that
    unique items only appear in one place at a time.
    """
    excluded: set[str] = set()
    for offer in get_active_village_offers(today):
        card_key = offer.get("card_key")
        if card_key:
            excluded.add(card_key)
    return excluded
