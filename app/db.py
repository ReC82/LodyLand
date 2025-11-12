# =============================================================================
# File: app/db.py
# Purpose: Minimal SQLite engine + SQLAlchemy session factory.
# =============================================================================
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get DATABASE_URL from env or fallback
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///game.db")

engine = create_engine(DATABASE_URL, echo=False, future=True)

class Base(DeclarativeBase):
    """Declarative base for ORM models."""
    pass

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def init_db():
    """Create all tables if they don't exist."""
    # Import models so metadata sees them before create_all
    from . import models  # noqa: F401
    Base.metadata.create_all(engine)
