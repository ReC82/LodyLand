"""craft: add craft_queue_extra_slots to players

Revision ID: e3f25dc3b5e9
Revises: ea6fde935c80
Create Date: 2026-04-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3f25dc3b5e9'
down_revision: Union[str, Sequence[str], None] = '5c87595cd3f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'players',
        sa.Column('craft_queue_extra_slots', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('players', 'craft_queue_extra_slots')
