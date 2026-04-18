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

# Session factory (no autocommit, no autoflush)
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


class Base(DeclarativeBase):
    """Declarative base for ORM models."""
    pass


def init_db():
    """Create all tables if they don't exist."""
    # Import models so metadata sees them before create_all
    from . import models  # noqa: F401
    Base.metadata.create_all(engine)

    # Incremental migrations: add new columns if missing
    from sqlalchemy import text, inspect
    with engine.connect() as conn:
        inspector = inspect(engine)
        player_cols = [c["name"] for c in inspector.get_columns("players")]
        if "theme" not in player_cols:
            conn.execute(text("ALTER TABLE players ADD COLUMN theme TEXT NOT NULL DEFAULT 'light'"))
            conn.commit()
        else:
            # Migrate existing players who still have the old default
            conn.execute(text("UPDATE players SET theme = 'light' WHERE theme = 'default'"))
            conn.commit()

        # Mini-game tables (created by create_all above, but ensure columns exist)
        tables = inspector.get_table_names()
        if "minigame_defs" in tables:
            mg_cols = [c["name"] for c in inspector.get_columns("minigame_defs")]
            if "free_attempts_per_day" not in mg_cols:
                conn.execute(text(
                    "ALTER TABLE minigame_defs ADD COLUMN free_attempts_per_day INTEGER NOT NULL DEFAULT 1"
                ))
                conn.commit()
