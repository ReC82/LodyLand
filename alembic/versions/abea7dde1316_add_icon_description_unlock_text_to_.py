"""Add icon, description, unlock_text to resource_defs

Revision ID: abea7dde1316
Revises: 82e0f42dfdee
Create Date: 2025-11-13 22:33:36.638211

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'abea7dde1316'
down_revision: Union[str, Sequence[str], None] = '82e0f42dfdee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("resource_defs", sa.Column("icon", sa.String(), nullable=True))
    pass


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("resource_defs", "icon")
    pass
