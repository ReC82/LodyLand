# =============================================================================
# File: app/models.py
# Purpose: Minimal ORM models for MVP (Player, Tile).
# =============================================================================
from datetime import datetime
from sqlalchemy import Integer, String, ForeignKey, Boolean, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Player(Base):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    level: Mapped[int] = mapped_column(Integer, default=0)
    coins: Mapped[int] = mapped_column(Integer, default=0)
    diams: Mapped[int] = mapped_column(Integer, default=0)
    xp: Mapped[int] = mapped_column(Integer, default=0) 

class Tile(Base):
    __tablename__ = "tiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)  # inline index
    resource: Mapped[str] = mapped_column(String)  # e.g., "wood", "stone"
    locked: Mapped[bool] = mapped_column(Boolean, default=True)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

