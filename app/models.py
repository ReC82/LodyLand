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
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    
    # New currency columns (after DB migration)
    shards: Mapped[int] = mapped_column(Integer, default=0)
    essence: Mapped[int] = mapped_column(Integer, default=0)
    
    # Backward compatibility properties (temporary)
    @property
    def coins(self) -> int:
        """Legacy property: maps to shards"""
        return self.shards
    
    @coins.setter
    def coins(self, value: int):
        """Legacy setter: maps to shards"""
        self.shards = value
    
    @property
    def diams(self) -> int:
        """Legacy property: maps to essence"""
        return self.essence
    
    @diams.setter
    def diams(self, value: int):
        """Legacy setter: maps to essence"""
        self.essence = value

    # progression
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # daily chest
    last_daily: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    daily_streak: Mapped[int] = mapped_column(Integer, default=0)
    best_streak: Mapped[int] = mapped_column(Integer, default=0)
    
    lang: Mapped[str] = mapped_column(String(5), default="fr", nullable=False)

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
            # ✅ Anti multi-comptes
    email_verified = Column(Boolean, default=False, nullable=False)
    email_token = Column(String(64), nullable=True)  # token de vérification

    # ✅ Futur NFT / wallet Base (MetaMask)
    wallet_address = Column(String(42), nullable=True, unique=True)  # adresse EVM 0x...
    wallet_linked_at = Column(DateTime, nullable=True)

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
    icon: Mapped[str | None] = mapped_column(String, nullable=True)  
    kind: Mapped[str] = mapped_column(String, default="resource")# ex: "wood.png"
    #unlock_min_level: Mapped[int] = mapped_column(Integer, default=0)   # ex: 2
    #base_cooldown: Mapped[float] = mapped_column(Float, default=10.0)
    base_sell_price: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    #unlock_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
    
class PlayerCraftJob(Base):
    """
    One delayed craft in progress for a player.

    - quantity_total : combien d'items au total à produire (ex: 5 colliers)
    - quantity_done  : combien déjà livrés dans l'inventaire
    - started_at / ends_at : fenêtre de temps globale du job
    - status : active / done / cancelled (on utilise active/done pour l’instant)
    """

    __tablename__ = "player_craft_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id"),
        index=True,
        nullable=False,
    )

    item_key: Mapped[str] = mapped_column(String(100), nullable=False)
    craft_location: Mapped[str] = mapped_column(String(100), nullable=False)

    quantity_total: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        default=dt.datetime.utcnow,
        nullable=False,
    )
    ends_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)

    status: Mapped[str] = mapped_column(
        String(20),
        default="active",      # active / done / cancelled
        nullable=False,
    )

    # backref pratique si besoin: player.craft_jobs
    player = relationship("Player", backref="craft_jobs")     
    
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

# app/models.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Float,
    UniqueConstraint,
)
# ... tes autres imports existants (Base, etc.)

# ---------------------------------------------------------------------------
# LandSlotState: per-player, per-land, per-slot cooldown + last tool used
# ---------------------------------------------------------------------------

class LandSlotState(Base):
    __tablename__ = "land_slot_states"

    id = Column(Integer, primary_key=True)

    # Player owning this slot state
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)

    # Short land key used in YAML and API: "forest", "beach", "lake", ...
    land_key = Column(String(50), nullable=False)

    # Slot index inside the land (0..N-1)
    slot_index = Column(Integer, nullable=False)

    # When this slot will be ready again (cooldown end)
    cooldown_until = Column(DateTime, nullable=True)

    # Last tool used on this slot: "hands", "axe", "shovel", ...
    last_tool_key = Column(String(50), nullable=True)

    __table_args__ = (
        # Ensure only one row per (player, land, slot_index)
        UniqueConstraint(
            "player_id",
            "land_key",
            "slot_index",
            name="uq_land_slot_state_player_land_slot",
        ),
    )

class PlayerStoryFlag(Base):
    """Store which story events have been seen by a player."""

    __tablename__ = "player_story_flags"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), index=True, nullable=False)
    story_id = Column(String(100), index=True, nullable=False)
    seen_at = Column(DateTime, nullable=False, default=dt.datetime.utcnow)

    # Optional: relation back to Player
    player = relationship("Player", backref="story_flags")
    
# ---------------------------------------------------------------------------
# Temple (special land) - daily run state
# ---------------------------------------------------------------------------

class TempleRun(Base):
    """
    Stores daily Temple state for a player.

    - One row per player per day (UTC date)
    - Traps are stored server-side only (client never receives them)
    - progress_row: how many rows cleared from bottom (0..8)
    """

    __tablename__ = "temple_runs"

    __table_args__ = (
        UniqueConstraint("player_id", "day", name="uq_temple_run_player_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    player_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    day: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)

    lives: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    # 0..8 (rows cleared from bottom)
    progress_row: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # { "1": [2], "2": [1,9], ... } keys as strings for JSON stability
    traps: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    
    broken_tiles: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)


# ---------------------------------------------------------------------------
# Temple Reconstruction — persistent bricks placed by each player
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Buildings — construction + état opérationnel par joueur
# ---------------------------------------------------------------------------

class PlayerBuilding(Base):
    """
    Un building en cours de construction ou opérationnel pour un joueur.

    Statuts :
      pending_resources   → le joueur doit déposer les matériaux
      pending_construction → tous les matériaux réunis, prêt à lancer
      under_construction  → construction en cours (ends_at = fin)
      operational         → building actif
    """

    __tablename__ = "player_buildings"

    __table_args__ = (
        UniqueConstraint(
            "player_id", "building_key",
            name="uq_player_building",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), index=True, nullable=False)
    building_key: Mapped[str] = mapped_column(String(100), nullable=False)

    # Statut du cycle de vie
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending_resources"
    )

    # Ressources déjà déposées (dict : resource_key → qty_deposited)
    # Irrécupérables une fois déposées.
    banked_materials: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Timestamps construction
    construction_started_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    construction_ends_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, default=dt.datetime.utcnow
    )

    player = relationship("Player", backref="buildings")


class TempleReconstructionBrick(Base):
    """
    One row per brick placed by a player.
    36 rows max per player (pyramid 8+7+...+1).
    """

    __tablename__ = "temple_reconstruction_bricks"

    __table_args__ = (
        UniqueConstraint(
            "player_id", "brick_key",
            name="uq_temple_brick_player_brick",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    brick_key: Mapped[str] = mapped_column(String(60), nullable=False)
    placed_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, default=dt.datetime.utcnow
    )