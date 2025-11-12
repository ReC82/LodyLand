# =============================================================================
# File: alembic/env.py
# Purpose: Alembic configuration hooking to app models + .env DATABASE_URL.
# =============================================================================
import os
from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from alembic import context

# Load .env for DATABASE_URL
from dotenv import load_dotenv
load_dotenv()

# Alembic Config object, provides access to values within .ini file.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Import app metadata ------------------------------------------------------
# We import Base.metadata to let Alembic auto-generate migrations.
from app.db import Base  # noqa: E402
from app import models   # noqa: F401  # ensure models are imported/register

target_metadata = Base.metadata

# --- Database URL from env ----------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///game.db")
if DATABASE_URL:
    # Override sqlalchemy.url at runtime (prefer env over alembic.ini)
    config.set_main_option("sqlalchemy.url", DATABASE_URL)

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
