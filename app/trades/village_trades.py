# app/trades/village_trades.py
from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import CardDef, Player, PlayerCard, ResourceStock, ResourceDef
from app.services.cards import give_player_card


# Quels tags de card_tags sont considérés comme des "land tags"
LAND_TAGS = {
    "forest",
    "beach",
    "lake",
    "mountain",
    "cave",
    "village",
    "temple",
    "desert",
}


def _as_list(value) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _get_land_tag_from_card(cd: CardDef) -> Optional[str]:
    """
    Devine le land à partir des card_tags.
    Ex: ["branch", "treasure", "forest"] -> "forest"
    """
    tags = set(_as_list(getattr(cd, "card_tags", [])))
    for t in LAND_TAGS:
        if t in tags:
            return t
    return None


def _is_treasure_trade_card(cd: CardDef) -> bool:
    """
    Filtre de base : "est-ce que cette carte est une carte treasure
    utilisable dans le trade du village ?"
    """
    if not cd.enabled:
        return False

    tags = set(_as_list(getattr(cd, "card_tags", [])))
    if "treasure" not in tags:
        return False

    shop_cfg = cd.shop or {}
    prices = shop_cfg.get("prices") or []
    if not prices:
        return False

    price0 = prices[0] or {}
    res_costs = price0.get("resources") or {}
    if not res_costs:
        return False

    # Optionnel : on peut décider de ne gérer que les trades à 1 ressource
    if len(res_costs) != 1:
        return False

    return True


def _extract_price_from_card(cd: CardDef) -> Tuple[str, int]:
    """
    Extrait (resource_key, amount) à partir de shop.prices[0].resources.

    On suppose qu'il y a exactement 1 ressource (déjà vérifié par _is_treasure_trade_card).
    """
    shop_cfg = cd.shop or {}
    prices = shop_cfg.get("prices") or []
    price0 = prices[0] or {}
    res_costs = price0.get("resources") or {}

    # On prend la première (et normalement unique) entrée
    (res_key, amount) = next(iter(res_costs.items()))
    return str(res_key), int(amount or 0)


def list_trades_for_player(
    session: Session,
    player: Player,
    land_slug: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retourne la liste des trades disponibles pour le joueur.

    land_slug:
      - None ou "all" -> toutes les cartes treasure
      - "forest" -> uniquement les cartes treasure taggées forest, etc.
    """

    # ------------------------------------------------------------------ #
    # 1) Récupérer toutes les CardDef et filtrer sur les "treasure"
    # ------------------------------------------------------------------ #
    all_cards: List[CardDef] = (
        session.query(CardDef)
        .filter(CardDef.enabled == True)  # noqa: E712
        .all()
    )

    treasure_cards = [cd for cd in all_cards if _is_treasure_trade_card(cd)]

    if not treasure_cards:
        return {"trades": [], "available_lands": []}

    # Normaliser le filtre land
    land_filter = (land_slug or "").strip().lower()
    if land_filter in ("", "all"):
        land_filter = None

    # ------------------------------------------------------------------ #
    # 2) Pré-charger les infos du joueur et des ressources
    # ------------------------------------------------------------------ #

    # a) cartes possédées par le joueur
    player_cards_rows: List[PlayerCard] = (
        session.query(PlayerCard)
        .filter(PlayerCard.player_id == player.id)
        .all()
    )
    player_cards_map = {row.card_key: row for row in player_cards_rows}

    # b) stocks de ressources du joueur (cache lazy)
    resource_stock_cache: Dict[str, ResourceStock] = {}

    # c) définitions des ressources pour les labels / icônes
    resource_defs: Dict[str, ResourceDef] = {
        rd.key: rd
        for rd in session.query(ResourceDef)
        .filter(ResourceDef.enabled == True)  # noqa: E712
        .all()
    }

    # ------------------------------------------------------------------ #
    # 3) Construire les trades + liste des lands disponibles
    # ------------------------------------------------------------------ #
    trades: List[dict] = []
    land_counts: Dict[str, int] = {}

    for cd in treasure_cards:
        land_tag = _get_land_tag_from_card(cd) or "other"
        land_counts[land_tag] = land_counts.get(land_tag, 0) + 1

        # Filtre éventuel
        if land_filter and land_tag != land_filter:
            continue

        # Prix
        resource_key, amount = _extract_price_from_card(cd)

        # Stock de la ressource chez le joueur (via cache)
        if resource_key not in resource_stock_cache:
            rs = (
                session.query(ResourceStock)
                .filter_by(player_id=player.id, resource=resource_key)
                .one_or_none()
            )
            resource_stock_cache[resource_key] = rs or ResourceStock(
                player_id=player.id,
                resource=resource_key,
                qty=0.0,
            )
        stock_row = resource_stock_cache[resource_key]
        player_resource_qty = float(stock_row.qty or 0.0)

        # Stock global de la carte (card_quantity)
        stock_global = getattr(cd, "card_quantity", None)
        if stock_global is None:
            stock_global = -1  # -1 = illimité
        else:
            stock_global = int(stock_global)

        # Quantité possédée par le joueur
        owned_row = player_cards_map.get(cd.key)
        owned_qty = int(owned_row.qty or 0) if owned_row else 0

        # Limites éventuelles
        max_owned = getattr(cd, "card_max_owned", None)
        if max_owned is not None:
            max_owned = int(max_owned)

        limit_per_player = getattr(cd, "card_purchase_limit_quantity", None)
        if limit_per_player is not None:
            limit_per_player = int(limit_per_player)

        # Conditions d'achat
        can_buy_reasons: List[str] = []

        # 1) Stock global (si limité)
        if stock_global == 0:
            can_buy_reasons.append("Stock épuisé pour cette carte.")

        # 2) Max possédé
        if max_owned is not None and owned_qty >= max_owned:
            can_buy_reasons.append(
                "Tu possèdes déjà le nombre maximum de cette carte."
            )

        # 3) Limite d'achats par joueur (si tu veux l'utiliser)
        if limit_per_player is not None and owned_qty >= limit_per_player:
            can_buy_reasons.append(
                f"Tu as déjà atteint la limite d'échanges pour cette carte "
                f"({owned_qty}/{limit_per_player})."
            )

        # 4) Ressource requise
        if player_resource_qty < amount:
            can_buy_reasons.append(
                "Tu n'as pas assez de ressource rare pour cet échange."
            )

        can_buy = len(can_buy_reasons) == 0
        cant_buy_reason = can_buy_reasons[0] if can_buy_reasons else ""

        rd = resource_defs.get(resource_key)
        res_label = (
            getattr(rd, "label", None)
            or getattr(rd, "label_fr", None)
            or getattr(rd, "label_en", None)
            or resource_key
        )
        res_icon = getattr(rd, "icon", None)

        trades.append(
            {
                "card_key": cd.key,
                "label": getattr(cd, "card_label", cd.key),
                "description": getattr(cd, "card_description", ""),
                "image": getattr(cd, "card_image", None),
                "rarity": getattr(cd, "card_rarity", "common"),
                "land_tag": land_tag,
                "resource_cost": {
                    "resource_key": resource_key,
                    "amount": amount,
                    "label": res_label,
                    "icon": res_icon,
                    "player_qty": float(player_resource_qty),
                },
                "stock_global": stock_global,
                "owned_qty": owned_qty,
                "can_buy": can_buy,
                "cant_buy_reason": cant_buy_reason,
            }
        )

    # ------------------------------------------------------------------ #
    # 4) Construire la liste des lands dispo pour les filtres
    # ------------------------------------------------------------------ #
    def _land_label(slug: str) -> str:
        mapping = {
            "forest": "Forêt",
            "beach": "Plage",
            "lake": "Lac",
            "mountain": "Montagne",
            "cave": "Grotte",
            "village": "Village",
            "temple": "Temple",
            "desert": "Désert",
            "other": "Autres",
        }
        return mapping.get(slug, slug.title())

    available_lands: List[dict] = []
    total_count = sum(land_counts.values())
    available_lands.append(
        {"slug": "all", "label": "Tous les lands", "count": int(total_count)}
    )

    for slug, count in sorted(land_counts.items(), key=lambda kv: kv[0]):
        available_lands.append(
            {
                "slug": slug,
                "label": _land_label(slug),
                "count": int(count),
            }
        )

    # Tri des trades par land puis label
    trades.sort(key=lambda t: (t.get("land_tag") or "", t.get("label") or ""))

    return {
        "trades": trades,
        "available_lands": available_lands,
    }


def execute_trade_for_player(
    session: Session,
    player: Player,
    card_key: str,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Exécute un trade pour une carte treasure (card_key).

    Retourne:
      (True, payload)  si OK
      (False, {"error": "...", "details": "...", ...}) si erreur
    """
    card_key = (card_key or "").strip()
    if not card_key:
        return False, {"error": "invalid_card_key"}

    cd: Optional[CardDef] = (
        session.query(CardDef)
        .filter(CardDef.key == card_key)
        .filter(CardDef.enabled == True)  # noqa: E712
        .one_or_none()
    )
    if not cd or not _is_treasure_trade_card(cd):
        return False, {"error": "unknown_trade_card"}

    # Prix
    resource_key, amount = _extract_price_from_card(cd)
    if amount <= 0:
        return False, {"error": "invalid_price", "details": "amount <= 0"}

    # Stock global (card_quantity)
    stock_global = getattr(cd, "card_quantity", None)
    if stock_global is not None:
        stock_global = int(stock_global)
        if stock_global <= 0:
            return False, {"error": "out_of_stock"}

    # Stock de la ressource du joueur
    stock_row: Optional[ResourceStock] = (
        session.query(ResourceStock)
        .filter_by(player_id=player.id, resource=resource_key)
        .one_or_none()
    )
    player_qty = float(stock_row.qty or 0.0) if stock_row else 0.0
    if player_qty < amount:
        return False, {"error": "not_enough_resource", "resource_key": resource_key}

    # Quantité possédée
    owned_row: Optional[PlayerCard] = (
        session.query(PlayerCard)
        .filter_by(player_id=player.id, card_key=card_key)
        .one_or_none()
    )
    owned_qty = int(owned_row.qty or 0) if owned_row else 0

    max_owned = getattr(cd, "card_max_owned", None)
    if max_owned is not None and owned_qty >= int(max_owned):
        return False, {"error": "max_owned_reached"}

    limit_per_player = getattr(cd, "card_purchase_limit_quantity", None)
    if limit_per_player is not None and owned_qty >= int(limit_per_player):
        return False, {"error": "purchase_limit_reached"}

    # --- Tout est OK -> appliquer le trade ---

    # 1) Débiter la ressource rare
    if not stock_row:
        stock_row = ResourceStock(player_id=player.id, resource=resource_key, qty=0.0)
        session.add(stock_row)
    stock_row.qty = float(stock_row.qty or 0.0) - float(amount)

    # 2) Donner la carte (1 exemplaire par trade)
    give_player_card(session, player.id, card_key, qty=1)

    # 3) Décrémenter le stock global (card_quantity) si limité
    if stock_global is not None:
        cd.card_quantity = stock_global - 1

    # 4) Recharger infos pour le retour
    session.flush()
    session.refresh(player)
    session.refresh(cd)

    updated_owned_row: Optional[PlayerCard] = (
        session.query(PlayerCard)
        .filter_by(player_id=player.id, card_key=card_key)
        .one_or_none()
    )
    new_owned_qty = int(updated_owned_row.qty or 0) if updated_owned_row else 0

    new_stock_global = getattr(cd, "card_quantity", None)
    if new_stock_global is None:
        new_stock_global = -1

    return True, {
        "card_key": card_key,
        "player": {
            "id": player.id,
            "level": player.level,
            "coins": player.coins,
            "diams": player.diams,
        },
        "resource": {
            "resource_key": resource_key,
            "new_qty": float(stock_row.qty or 0.0),
        },
        "owned_qty": new_owned_qty,
        "stock_global": int(new_stock_global),

    }
