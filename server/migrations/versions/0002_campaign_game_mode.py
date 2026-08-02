"""Persist the immutable singleplayer or multiplayer campaign mode."""

from alembic import op
import sqlalchemy as sa

revision = "0002_campaign_game_mode"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column("game_mode", sa.String(length=20), nullable=False, server_default="multiplayer"),
    )


def downgrade() -> None:
    op.drop_column("campaigns", "game_mode")
