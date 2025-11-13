# tests/test_unlock_rules.py
from app.unlock_rules import check_unlock_rules
from app.models import Player


def make_player(level=0, coins=0):
    # On n’a pas besoin de session, juste un objet Player en mémoire
    return Player(name="Test", level=level, coins=coins)


def test_no_rules_always_ok():
    p = make_player(level=0, coins=0)
    ok, info = check_unlock_rules(p, None)
    assert ok is True
    assert info == {}


def test_all_rules_ok():
    p = make_player(level=2, coins=100)
    rules = {
        "all": [
            {"type": "level_at_least", "value": 1},
            {"type": "coins_at_least", "value": 10},
        ]
    }
    ok, info = check_unlock_rules(p, rules)
    assert ok is True
    assert info == {}


def test_all_rules_fail_on_level():
    p = make_player(level=0, coins=100)
    rules = {
        "all": [
            {"type": "level_at_least", "value": 1},
            {"type": "coins_at_least", "value": 10},
        ]
    }
    ok, info = check_unlock_rules(p, rules)
    assert ok is False
    assert info.get("reason") == "level_too_low"


def test_any_rules_ok():
    p = make_player(level=0, coins=50)
    rules = {
        "any": [
            {"type": "level_at_least", "value": 10},
            {"type": "coins_at_least", "value": 10},
        ]
    }
    ok, info = check_unlock_rules(p, rules)
    assert ok is True
    assert info == {}


def test_any_rules_fail():
    p = make_player(level=0, coins=0)
    rules = {
        "any": [
            {"type": "level_at_least", "value": 1},
            {"type": "coins_at_least", "value": 5},
        ]
    }
    ok, info = check_unlock_rules(p, rules)
    assert ok is False
    # on accepte n’importe quelle "reason" tant que ça échoue