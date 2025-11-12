from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d21e821f3d0e"
down_revision = "33b69ee51ca5"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite: add NOT NULL column requires a server_default
    with op.batch_alter_table("players") as batch:
        batch.add_column(sa.Column("xp", sa.Integer(), nullable=False, server_default="0"))
    # drop the default so future inserts use the app default (not DB-level)
    with op.batch_alter_table("players") as batch:
        batch.alter_column("xp", server_default=None)


def downgrade():
    with op.batch_alter_table("players") as batch:
        batch.drop_column("xp")
