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
    ForeignKey, Text, UniqueConstraint, Float, Column, func
)
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime

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

    # daily chest
    last_daily: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    daily_streak: Mapped[int] = mapped_column(Integer, default=0)
    best_streak: Mapped[int] = mapped_column(Integer, default=0)

    account: Mapped["Account"] = relationship(
        "Account",
        back_populates="player",
        uselist=False
    )
    
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # One account -> one player profile (you can adapt)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    player = relationship("Player", back_populates="account")

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

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    card_type: Mapped[str] = mapped_column(String, nullable=False)
    card_category: Mapped[str | None] = mapped_column(String, nullable=True)
    card_tags: Mapped[list | None] = mapped_column(JSON, nullable=True)

    card_label: Mapped[str] = mapped_column(String, nullable=False)
    card_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    card_image: Mapped[str | None] = mapped_column(String, nullable=True)
    card_rarity: Mapped[str | None] = mapped_column(String, nullable=True)

    card_gameplay: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    shop: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    tradable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    giftable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    card_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    card_purchase_limit_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    card_max_owned: Mapped[int | None] = mapped_column(Integer, nullable=True)

    unlock_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PlayerCard(Base):
    __tablename__ = "player_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    card_key: Mapped[str] = mapped_column(String, index=True)
    qty: Mapped[int] = mapped_column(Integer, default=1)

    player = relationship("Player", backref="cards")    
    
class PlayerItem(Base):
    __tablename__ = "player_items"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    item_key = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )    
    
class PlayerLandSlots(Base):
    __tablename__ = "player_land_slots"

    id = mapped_column(Integer, primary_key=True)
    player_id = mapped_column(Integer, ForeignKey("players.id"), index=True, nullable=False)
    land_key = mapped_column(String, nullable=False)  # "forest", "beach"...
    extra_slots = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("player_id", "land_key", name="uix_player_land_slots"),
    )
    
# =============================================================================
# Quest System Models (PlayerQuest, PlayerQuestObjective)
# =============================================================================

class PlayerQuest(Base):
    __tablename__ = "player_quests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True, nullable=False)

    # Quest template key from quests.yml
    template_key: Mapped[str] = mapped_column(String(100), nullable=False)

    # daily | weekly | bonus | event
    quest_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Source of assignment (auto_daily, villager_x, event_x)
    source: Mapped[str] = mapped_column(String(50), nullable=False)

    # Localized quest title & description (snapshot)
    title_fr: Mapped[str] = mapped_column(String(255), nullable=False)
    title_en: Mapped[str] = mapped_column(String(255), nullable=False)
    description_fr: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)

    # active, completed, failed, expired
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    expires_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    # Rewards snapshot (coins, diams, cards, items...)
    rewards_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Objectives associated with this quest
    objectives = relationship(
        "PlayerQuestObjective",
        back_populates="quest",
        cascade="all, delete-orphan"
    )


class PlayerQuestObjective(Base):
    __tablename__ = "player_quest_objectives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    player_quest_id: Mapped[int] = mapped_column(
        ForeignKey("player_quests.id"), index=True, nullable=False
    )

    # Order of the objective inside quest
    index_in_quest: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # collect_resource / craft_item / open_daily_chest / complete_quests...
    kind: Mapped[str] = mapped_column(String(50), nullable=False)

    # Optional fields depending on the kind
    resource_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    item_key: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Progression
    target_value: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Ignore boosts when counting resource collection
    ignore_boosts: Mapped[bool] = mapped_column(Boolean, default=False)

    # For streak-based quests (daily chest in a row)
    consecutive_required: Mapped[bool] = mapped_column(Boolean, default=False)

    # Additional parameters (JSON)
    extra_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Back link to the parent quest
    quest = relationship("PlayerQuest", back_populates="objectives")
