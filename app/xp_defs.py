# app/xp_defs.py
# Central place for level / XP definitions

LEVEL_DEFS = [
    {
        "level": 0,
        "xp_min": 0,
        "xp_max": 100,
        "rewards": []
    },
    {
        "level": 1,
        "xp_min": 100,
        "xp_max": 300,
        "rewards": [
            {"type": "resource", "key": "branch", "label": "Branches", "amount": 10},
            {"type": "coins", "label": "coins", "amount": 50},
        ],
    },
    {
        "level": 2,
        "xp_min": 300,
        "xp_max": 700,
        "rewards": [
            {"type": "card", "key": "card_land_village", "label": "Carte Village", "amount": 1},
        ],
    },
    # ➜ complète / adapte selon ton XP système
]
