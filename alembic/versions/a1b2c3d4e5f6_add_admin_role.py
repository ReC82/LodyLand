"""Add admin_role field to players table.

Revision ID: a1b2c3d4e5f6
Revises: e3f25dc3b5e9
Create Date: 2026-04-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'e3f25dc3b5e9'
branch_labels = None
depends_on = None


def upgrade():
    # Add admin_role column to players table
    op.add_column('players', sa.Column('admin_role', sa.String(30), nullable=True))


def downgrade():
    # Remove admin_role column from players table
    op.drop_column('players', 'admin_role')
