# =============================================================================
# File: app/models.py
# Purpose: Minimal ORM models for MVP (Player, Tile, ResourceStock)
# Notes:
# - SQLAlchemy 2.0 style (Mapped[...] + mapped_column)
# - Types explicites sur chaque colonne
# - Dates/DateTime en UTC (Stockage naïf en SQLite, interprétation UTC côté app)
# =============================================================================
from __future__ import annotations

import datetime as dt  # use dt.date / dt.datetime for annotations
from sqlalchemy import (
    Integer, String, Date, DateTime, Boolean,
    ForeignKey, Text, UniqueConstraint, Float
)
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # economy
    coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    diams: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # progression
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # daily chest (date UTC, sans heure)
    last_daily: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    daily_streak: Mapped[int] = mapped_column(Integer, default=0)   # streak courant
    best_streak: Mapped[int] = mapped_column(Integer, default=0)    # meilleur streak


class Tile(Base):
    __tablename__ = "tiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True, nullable=False)
    resource: Mapped[str] = mapped_column(String(30), nullable=False)  # "wood", "stone", "water"
    locked: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # SQLite stocke naïf; on traite comme UTC dans l'app
    cooldown_until: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    # player: Mapped["Player"] = relationship(back_populates="tiles")


class ResourceStock(Base):
    __tablename__ = "resource_stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    resource: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    qty: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    __table_args__ = (
        UniqueConstraint("player_id", "resource", name="uix_player_resource"),
    )
    
class ResourceDef(Base):
    __tablename__ = "resource_defs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True, index=True)   # ex: "wood"
    label: Mapped[str] = mapped_column(String)                          # ex: "Bois"
    icon: Mapped[str | None] = mapped_column(String, nullable=True)          # ex: "wood.png"
    unlock_min_level: Mapped[int] = mapped_column(Integer, default=0)   # ex: 2
    base_cooldown: Mapped[float] = mapped_column(Float, default=10.0)
    base_sell_price: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    unlock_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unlock_description: Mapped[str | None] = mapped_column(Text, nullable=True)
   
class CardDef(Base):
    __tablename__ = "card_defs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True, index=True)
    label: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String, nullable=True)

    type: Mapped[str] = mapped_column(String)  # "resource_unlock", "building_unlock", etc.

    target_resource: Mapped[str | None] = mapped_column(String, nullable=True)
    target_building: Mapped[str | None] = mapped_column(String, nullable=True)
    #target_land: Mapped[str | None] = mapped_column(String, nullable=True)

    price_coins: Mapped[int] = mapped_column(Integer, default=0)
    price_diams: Mapped[int] = mapped_column(Integer, default=0)

    max_owned: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1 pour unique, None = illimité

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    unlock_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PlayerCard(Base):
    __tablename__ = "player_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    card_key: Mapped[str] = mapped_column(String, index=True)
    qty: Mapped[int] = mapped_column(Integer, default=1)

    player = relationship("Player", backref="cards")    