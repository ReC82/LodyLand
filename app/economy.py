# app/economy.py
# Purpose: Simple economy helpers (static prices for MVP).

PRICES = {
    "wood": 1,
    "stone": 2,
    "water": 1,
}

def get_price(resource: str) -> int:
    """Return unit price for a resource, or 0 if unknown."""
    return PRICES.get(resource.lower().strip(), 0)

def list_prices():
    """Return a serializable view of all prices."""
    return [{"resource": r, "price": p} for r, p in PRICES.items()]
