"""add resource descriptions

Revision ID: 82e0f42dfdee
Revises: b65b72ff0400
Create Date: 2025-11-13 21:04:03.485042

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82e0f42dfdee'
down_revision: Union[str, Sequence[str], None] = 'b65b72ff0400'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "resource_defs",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "resource_defs",
        sa.Column("unlock_description", sa.Text(), nullable=True),
    )

def downgrade():
    op.drop_column("resource_defs", "unlock_description")
    op.drop_column("resource_defs", "description")
