# app/quests/loader.py

from pathlib import Path
from typing import Dict, Any

import yaml

# Type alias for readability
QuestTemplate = Dict[str, Any]


# Base paths -------------------------------------------------------------


# ! Adjust if your project structure is different
PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
QUESTS_YAML_PATH = DATA_DIR / "quests.yml"


def _build_default_templates() -> Dict[str, QuestTemplate]:
    """
    Build a minimal set of quest templates used as fallback
    when quests.yml is missing or invalid.
    """
    # You can keep this in sync with your YAML file, but simplified.
    return {
        "qt_gather_wood_small": {
            "key": "qt_gather_wood_small",
            "quest_type": "daily",
            "category": "farming",
            "enabled": True,
            "title": {
                "fr": "Récolter du bois",
                "en": "Gather some wood",
            },
            "description": {
                "fr": "Va couper un peu de bois dans la forêt.",
                "en": "Go cut some wood in the forest.",
            },
            "sources": ["auto_daily"],
            "objective_templates": [
                {
                    "kind": "collect_resource",
                    "resource_keys": ["res_wood_branch"],
                    "quantity_min": 5,
                    "quantity_max": 10,
                    "ignore_boosts": True,
                }
            ],
            "reward_templates": {
                "coins_min": 5,
                "coins_max": 15,
                "diams_min": 0,
                "diams_max": 1,
            },
        }
    }


# Global registry
QUEST_TEMPLATES: Dict[str, QuestTemplate] = {}


def load_quest_templates() -> Dict[str, QuestTemplate]:
    """
    Load quest templates from quests.yml into the global QUEST_TEMPLATES dict.

    - Reads config/quests.yml
    - Validates minimal required fields
    - Fallbacks to hard-coded default templates if needed
    """
    global QUEST_TEMPLATES

    if not QUESTS_YAML_PATH.exists():
        print("quests.yml introuvable, utilisation des quêtes par défaut.")
        print(f"Chemin recherché: {QUESTS_YAML_PATH}")
        QUEST_TEMPLATES = _build_default_templates()
        return QUEST_TEMPLATES

    try:
        raw = yaml.safe_load(QUESTS_YAML_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        print(f"Erreur lors du chargement de quests.yml: {exc}")
        QUEST_TEMPLATES = _build_default_templates()
        return QUEST_TEMPLATES

    raw_templates = raw.get("quest_templates") or {}
    if not isinstance(raw_templates, dict):
        print(
            "quests.yml ne contient pas de section 'quest_templates', "
            "utilisation des quêtes par défaut."
        )
        QUEST_TEMPLATES = _build_default_templates()
        return QUEST_TEMPLATES

    allowed_types = {"daily", "weekly", "bonus", "event"}
    valid: Dict[str, QuestTemplate] = {}

    for yaml_key, tpl in raw_templates.items():
        if not isinstance(tpl, dict):
            print(f"Quête '{yaml_key}' ignorée (template non dict).")
            continue

        # Normalise key
        template_key = (tpl.get("key") or str(yaml_key)).strip()
        quest_type = (tpl.get("quest_type") or "").strip()
        title = tpl.get("title") or {}
        description = tpl.get("description") or {}
        objectives = tpl.get("objective_templates") or []
        rewards = tpl.get("reward_templates") or {}

        errors = []

        if quest_type not in allowed_types:
            errors.append("quest_type invalide ou manquant")

        if not isinstance(title, dict) or "fr" not in title or "en" not in title:
            errors.append("title.fr / title.en manquants")

        if not isinstance(objectives, list) or not objectives:
            errors.append("objective_templates vide ou invalide")

        if errors:
            print(f"Quête '{yaml_key}' ignorée: {', '.join(errors)}")
            continue

        # Force normalized fields back into template
        tpl["key"] = template_key
        tpl["quest_type"] = quest_type
        tpl["title"] = title
        tpl["description"] = description
        tpl["objective_templates"] = objectives
        tpl["reward_templates"] = rewards

        valid[template_key] = tpl

    if not valid:
        print("quests.yml ne contient aucune quête valide, utilisation des defaults.")
        valid = _build_default_templates()

    QUEST_TEMPLATES = valid
    print(f"QUEST_TEMPLATES loaded keys: {list(QUEST_TEMPLATES.keys())}")
    return QUEST_TEMPLATES


# Load on import so the registry is ready when the app starts
load_quest_templates()
