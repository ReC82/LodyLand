"""add temple_reconstruction_bricks table

Revision ID: a1b2c3d4e5f6
Revises: 5c87595cd3f9
Create Date: 2026-04-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '5c87595cd3f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'temple_reconstruction_bricks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('brick_key', sa.String(60), nullable=False),
        sa.Column('placed_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('player_id', 'brick_key', name='uq_temple_brick_player_brick'),
    )
    op.create_index('ix_temple_reconstruction_bricks_player_id',
                    'temple_reconstruction_bricks', ['player_id'])


def downgrade() -> None:
    op.drop_index('ix_temple_reconstruction_bricks_player_id',
                  table_name='temple_reconstruction_bricks')
    op.drop_table('temple_reconstruction_bricks')
