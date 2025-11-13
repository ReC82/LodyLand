"""Add icon, description, unlock_text to resource_defs

Revision ID: 7acddb502ba4
Revises: abea7dde1316
Create Date: 2025-11-13 22:34:44.483755

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7acddb502ba4'
down_revision: Union[str, Sequence[str], None] = 'abea7dde1316'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
