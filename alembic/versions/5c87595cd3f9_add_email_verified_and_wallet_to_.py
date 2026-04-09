"""add email_verified and wallet to accounts

Revision ID: 5c87595cd3f9
Revises: 7acddb502ba4
Create Date: 2026-04-07 15:04:37.545161

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c87595cd3f9'
down_revision: Union[str, Sequence[str], None] = '7acddb502ba4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column(
        'email_verified', 
        sa.Boolean(), 
        nullable=False, 
        server_default='0'
    ))
    op.add_column('accounts', sa.Column('email_token', sa.String(64), nullable=True))
    op.add_column('accounts', sa.Column('wallet_address', sa.String(42), nullable=True))
    op.add_column('accounts', sa.Column('wallet_linked_at', sa.DateTime(), nullable=True))
    # ← ligne create_unique_constraint supprimée


def downgrade() -> None:
    op.drop_column('accounts', 'wallet_linked_at')
    op.drop_column('accounts', 'wallet_address')
    op.drop_column('accounts', 'email_token')
    op.drop_column('accounts', 'email_verified')
