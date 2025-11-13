# app/unlock_rules.py
from __future__ import annotations

from typing import Any, Dict, Tuple

from .models import Player


RuleSpec = Any  # dict | list | None
RuleResult = Tuple[bool, Dict[str, Any]]


def _eval_simple_rule(player: Player, rule: Dict[str, Any]) -> RuleResult:
    """Évalue une règle 'feuille' du type {"type": "...", "value": ...}."""
    rtype = rule.get("type")
    value = rule.get("value")

    # --- niveau minimal -------------------------------------------------
    if rtype == "level_at_least":
        needed = int(value)
        current = int(player.level or 0)
        ok = current >= needed
        if ok:
            return True, {}
        return False, {
            "reason": "level_too_low",
            "required": needed,
            "current_level": current,
        }

    # --- coins minimal ---------------------------------------------------
    if rtype == "coins_at_least":
        needed = int(value)
        current = int(player.coins or 0)
        ok = current >= needed
        if ok:
            return True, {}
        return False, {
            "reason": "not_enough_coins",
            "required": needed,
            "current_coins": current,
        }

    # 🔮 plus tard : diams_at_least, resource_at_least, has_card, etc.

    # Règle inconnue -> on considère que ça passe (on loguera plus tard si besoin)
    return True, {}


def _eval_block(player: Player, spec: RuleSpec) -> RuleResult:
    """
    Évalue récursivement une structure de règles.

    Formes supportées :
    - None / {}      -> OK
    - {"all": [ ... ]} -> tous doivent être vrais (ET)
    - {"any": [ ... ]} -> au moins un doit être vrai (OU)
    - {"type": "..."}  -> règle simple
    - [ ... ]          -> liste implicite en AND (équiv. {"all": [...]})
    """
    if not spec:
        return True, {}

    # dict
    if isinstance(spec, dict):
        # Bloc "all"
        if "all" in spec:
            for sub in spec["all"]:
                ok, info = _eval_block(player, sub)
                if not ok:
                    return False, info
            return True, {}

        # Bloc "any"
        if "any" in spec:
            last_info: Dict[str, Any] = {}
            for sub in spec["any"]:
                ok, info = _eval_block(player, sub)
                if ok:
                    return True, {}
                last_info = info
            # aucun n’est passé
            return False, last_info or {"reason": "no_variant_matches"}

        # Sinon, on considère que c’est une règle simple
        return _eval_simple_rule(player, spec)

    # liste => AND implicite
    if isinstance(spec, list):
        for sub in spec:
            ok, info = _eval_block(player, sub)
            if not ok:
                return False, info
        return True, {}

    # Autres types inattendus -> OK par défaut
    return True, {}


def check_unlock_rules(player: Player, rules: RuleSpec) -> RuleResult:
    """
    Point d’entrée utilisé par l’API.

    - si rules est None / vide -> OK (seules les contraintes "simples"
      type unlock_min_level s’appliquent).
    - sinon -> on évalue la structure de règles (all/any/règles simples).
    """
    if not rules:
        return True, {}

    return _eval_block(player, rules)
