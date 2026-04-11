"""
app/quests/generator.py
Générateur procédural de quêtes — aucun template YAML requis.
Les quêtes sont générées à la volée en fonction des lands débloqués par le joueur
et des ressources disponibles dans ces lands.
"""
from __future__ import annotations

import datetime as dt
import os
import random
from typing import Any, Dict, List, Optional, Set

import yaml
from sqlalchemy.orm import Session

from app.models import Player, PlayerQuest, PlayerQuestObjective

# ---------------------------------------------------------------------------
# Paramètres de difficulté
# ---------------------------------------------------------------------------

DIFFICULTIES = ("easy", "medium", "hard")

# Plages de quantités par difficulté et type de quête
_QTY: Dict[str, Dict[str, tuple]] = {
    "daily": {
        "easy":   (8,   20),
        "medium": (20,  50),
        "hard":   (50,  120),
    },
    "weekly": {
        "easy":   (50,  100),
        "medium": (100, 200),
        "hard":   (200, 400),
    },
    "continuous": {
        "easy":   (15,  30),
        "medium": (30,  70),
        "hard":   (70,  150),
    },
}

# Plages de récompenses par difficulté et type de quête
_REWARDS: Dict[str, Dict[str, Dict[str, tuple]]] = {
    "daily": {
        "easy":   {"shards": (5,   20),  "essence": (0, 0),  "xp": (8,   18)},
        "medium": {"shards": (20,  50),  "essence": (0, 2),  "xp": (20,  40)},
        "hard":   {"shards": (50,  120), "essence": (1, 5),  "xp": (50,  90)},
    },
    "weekly": {
        "easy":   {"shards": (25,  70),  "essence": (0, 2),  "xp": (35,  70)},
        "medium": {"shards": (70,  180), "essence": (1, 5),  "xp": (70,  140)},
        "hard":   {"shards": (180, 400), "essence": (3, 12), "xp": (140, 280)},
    },
    "continuous": {
        "easy":   {"shards": (8,   25),  "essence": (0, 1),  "xp": (12,  25)},
        "medium": {"shards": (25,  65),  "essence": (0, 3),  "xp": (28,  55)},
        "hard":   {"shards": (65,  140), "essence": (1, 6),  "xp": (60,  110)},
    },
}

# Nombre d'objectifs par difficulté (min, max)
_OBJ_COUNTS: Dict[str, tuple] = {
    "easy":   (1, 1),
    "medium": (1, 2),
    "hard":   (1, 3),
}

# Titres en français par difficulté
_TITLES_FR: Dict[str, List[str]] = {
    "easy": [
        "Petite récolte",
        "Cueillette rapide",
        "Collecte légère",
        "Mission simple",
        "Coup de main",
        "Petite collecte",
    ],
    "medium": [
        "Collecte du jour",
        "Ravitaillement",
        "Mission intermédiaire",
        "Approvisionnement",
        "Récolte variée",
        "Mission du village",
    ],
    "hard": [
        "Grande expédition",
        "Effort soutenu",
        "Collecte massive",
        "Corvée du village",
        "Approvisionnement intensif",
        "Mission critique",
    ],
}

# ---------------------------------------------------------------------------
# Chargement des données lands (mis en cache au niveau du module)
# ---------------------------------------------------------------------------
_LANDS_DATA: Optional[Dict] = None


def _get_lands() -> Dict:
    global _LANDS_DATA
    if _LANDS_DATA is None:
        path = os.path.join(os.path.dirname(__file__), "..", "data", "lands.yml")
        with open(path, "r", encoding="utf-8") as f:
            _LANDS_DATA = yaml.safe_load(f) or {}
    return _LANDS_DATA


def _land_card_key(land_name: str, land_data: Dict) -> str:
    """Retourne la card_key (ex: 'land_forest') d'un land."""
    k = str(land_data.get("key") or "")
    if k.startswith("land_"):
        return k
    ck = str(land_data.get("card_key") or "")
    if ck:
        return ck
    return f"land_{land_name}"


# ---------------------------------------------------------------------------
# Catalogue de ressources
# ---------------------------------------------------------------------------

def build_resource_catalog(unlocked_land_keys: Set[str]) -> Dict[str, List[str]]:
    """
    Construit le catalogue de ressources récoltables depuis les lands débloqués.

    Retourne:
        {
            "hand_base":  [res, ...],  # loot garanti avec les mains (hands.base_loot)
            "hand_extra": [res, ...],  # loot bonus avec les mains (hands.extra_loot)
            "tool_base":  [res, ...],  # loot garanti avec des outils (tool_*.base_loot)
            "tool_extra": [res, ...],  # loot bonus avec des outils (tool_*.extra_loot)
        }
    """
    lands = _get_lands()
    catalog: Dict[str, List[str]] = {
        "hand_base": [], "hand_extra": [],
        "tool_base": [], "tool_extra": [],
    }

    for land_name, land_data in lands.items():
        if not isinstance(land_data, dict):
            continue
        card_key = _land_card_key(land_name, land_data)
        if card_key not in unlocked_land_keys:
            continue

        for tool_name, tool_data in (land_data.get("tools") or {}).items():
            if tool_name == "any" or not isinstance(tool_data, dict):
                continue

            is_hand   = (tool_name == "hands")
            base_cat  = "hand_base"  if is_hand else "tool_base"
            extra_cat = "hand_extra" if is_hand else "tool_extra"

            for loot in (tool_data.get("base_loot") or []):
                r = loot.get("resource")
                if r and r not in catalog[base_cat]:
                    catalog[base_cat].append(r)

            for loot in (tool_data.get("extra_loot") or []):
                r = loot.get("resource")
                if r and r not in catalog[extra_cat]:
                    catalog[extra_cat].append(r)

    return catalog


# ---------------------------------------------------------------------------
# Génération des objectifs
# ---------------------------------------------------------------------------

def _pick_objectives(
    difficulty: str,
    quest_type: str,
    catalog: Dict[str, List[str]],
) -> List[Dict[str, Any]]:
    """
    Génère 1 à N objectifs de type collect_resource selon la difficulté.

    Facile   : 1 ressource récoltable à la main uniquement
    Moyen    : 1-2 ressources (mains ou outils)
    Difficile: 1-3 ressources (préférence outils, grandes quantités)
    """

    def _dedup(lst: List[str]) -> List[str]:
        seen: Set[str] = set()
        return [x for x in lst if not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]

    if difficulty == "easy":
        pool = catalog["hand_base"][:]
        if not pool:
            pool = catalog["hand_extra"][:]
        n = 1

    elif difficulty == "medium":
        pool = _dedup(
            catalog["hand_base"] + catalog["hand_extra"] + catalog["tool_base"]
        )
        n_min, n_max = _OBJ_COUNTS["medium"]
        n = random.randint(n_min, n_max)

    else:  # hard
        # Priorité aux ressources d'outils, mais on accepte aussi les mains
        pool = _dedup(
            catalog["tool_base"] + catalog["tool_extra"] +
            catalog["hand_base"] + catalog["hand_extra"]
        )
        n_min, n_max = _OBJ_COUNTS["hard"]
        n = random.randint(n_min, n_max)

    if not pool:
        return []

    n = min(n, len(pool))
    chosen = random.sample(pool, n)

    qty_range = _QTY.get(quest_type, _QTY["daily"]).get(difficulty, (8, 20))

    return [
        {
            "kind": "collect_resource",
            "resource_key": res,
            "quantity": random.randint(*qty_range),
        }
        for res in chosen
    ]


# ---------------------------------------------------------------------------
# Génération des récompenses
# ---------------------------------------------------------------------------

def _gen_rewards(difficulty: str, quest_type: str) -> Dict[str, Any]:
    """Génère les récompenses aléatoires pour une quête."""
    ranges = _REWARDS.get(quest_type, _REWARDS["daily"]).get(
        difficulty, _REWARDS["daily"]["easy"]
    )

    shards  = random.randint(*ranges["shards"])
    xp      = random.randint(*ranges["xp"])

    ess_min, ess_max = ranges["essence"]
    # Essence : donnée seulement parfois (30 % facile/moyen, 60 % difficile)
    ess_chance = 0.6 if difficulty == "hard" else 0.3
    essence = (
        random.randint(ess_min, ess_max)
        if (ess_max > 0 and random.random() < ess_chance)
        else 0
    )

    return {
        "shards":     shards,
        "essence":    essence,
        "xp":         xp,
        "difficulty": difficulty,   # méta-champ pour serialize_quest
    }


# ---------------------------------------------------------------------------
# Génération du titre et de la description
# ---------------------------------------------------------------------------

def _gen_title_fr(difficulty: str, objectives: List[Dict]) -> str:
    base = random.choice(_TITLES_FR.get(difficulty, _TITLES_FR["easy"]))
    if len(objectives) == 1:
        res = objectives[0].get("resource_key", "")
        if res:
            return f"{base} — {res.replace('_', ' ')}"
    return base


def _gen_desc_fr(difficulty: str, objectives: List[Dict]) -> str:
    if not objectives:
        return ""
    parts = [
        f"{obj.get('quantity', 1)}× {obj.get('resource_key', '?').replace('_', ' ')}"
        for obj in objectives
    ]
    joined = ", ".join(parts)
    if difficulty == "easy":
        return f"Récoltez à mains nues : {joined}."
    elif difficulty == "medium":
        return f"Récoltez pour le village : {joined}."
    else:
        return f"Approvisionnement intensif requis : {joined}."


# ---------------------------------------------------------------------------
# Calcul de la date d'expiration
# ---------------------------------------------------------------------------

def _expires_at(quest_type: str, now: dt.datetime) -> Optional[dt.datetime]:
    """
    daily      : expire à minuit UTC de la nuit prochaine
    weekly     : expire le dimanche à minuit (= lundi 00:00 UTC)
    continuous : pas d'expiration
    """
    if quest_type == "daily":
        tomorrow = now.date() + dt.timedelta(days=1)
        return dt.datetime(tomorrow.year, tomorrow.month, tomorrow.day)

    elif quest_type == "weekly":
        # Nombre de jours jusqu'au prochain lundi (fin du dimanche)
        days_to_monday = (8 - now.isoweekday()) % 7 or 7
        next_monday = now.date() + dt.timedelta(days=days_to_monday)
        return dt.datetime(next_monday.year, next_monday.month, next_monday.day)

    return None


# ---------------------------------------------------------------------------
# Fonction principale de génération
# ---------------------------------------------------------------------------

def generate_quest(
    session: Session,
    player: Player,
    difficulty: str,
    quest_type: str,
    unlocked_land_keys: Set[str],
    now: Optional[dt.datetime] = None,
) -> Optional[PlayerQuest]:
    """
    Génère et persiste une quête procédurale.
    Retourne l'instance PlayerQuest (flush sans commit), ou None si impossible.

    Args:
        session:             Session SQLAlchemy active
        player:              Joueur destinataire
        difficulty:          "easy" | "medium" | "hard"
        quest_type:          "daily" | "weekly" | "continuous"
        unlocked_land_keys:  Ensemble des card_keys de lands débloqués
        now:                 Timestamp de création (défaut : utcnow)
    """
    if now is None:
        now = dt.datetime.utcnow()

    catalog    = build_resource_catalog(unlocked_land_keys)
    objectives = _pick_objectives(difficulty, quest_type, catalog)

    if not objectives:
        return None

    rewards  = _gen_rewards(difficulty, quest_type)
    title_fr = _gen_title_fr(difficulty, objectives)
    desc_fr  = _gen_desc_fr(difficulty, objectives)

    quest = PlayerQuest(
        player_id     = player.id,
        template_key  = f"gen_{difficulty}_{quest_type}",
        quest_type    = quest_type,
        source        = f"auto_{quest_type}",
        title_fr      = title_fr,
        title_en      = title_fr,      # TODO: version anglaise si besoin
        description_fr= desc_fr,
        description_en= desc_fr,
        status        = "active",
        started_at    = now,
        expires_at    = _expires_at(quest_type, now),
        rewards_json  = rewards,
    )
    session.add(quest)
    session.flush()  # obtenir quest.id

    for idx, obj in enumerate(objectives):
        session.add(PlayerQuestObjective(
            player_quest_id    = quest.id,
            index_in_quest     = idx,
            kind               = obj["kind"],
            resource_key       = obj.get("resource_key"),
            item_key           = obj.get("item_key"),
            target_value       = obj["quantity"],
            current_value      = 0,
            ignore_boosts      = False,
            consecutive_required = False,
        ))

    return quest
