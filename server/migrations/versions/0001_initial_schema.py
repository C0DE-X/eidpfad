"""Initial authoritative campaign schema."""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("display_name", sa.String(40), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("meta_progress", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_profiles_display_name", "profiles", ["display_name"], unique=True)
    op.create_index("ix_profiles_token_hash", "profiles", ["token_hash"], unique=True)
    op.create_table(
        "profile_recovery",
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("recovery_hash", sa.String(64), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_profile_recovery_recovery_hash", "profile_recovery", ["recovery_hash"], unique=True)
    op.create_table(
        "campaigns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invite_code", sa.String(8), nullable=False),
        sa.Column("owner_profile_id", sa.String(36), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("campaign_length", sa.String(20), nullable=False),
        sa.Column("world_tier", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("checkpoint_state", sa.JSON(), nullable=False),
        sa.Column("live_state", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_campaigns_invite_code", "campaigns", ["invite_code"], unique=True)
    op.create_index("ix_campaigns_owner_profile_id", "campaigns", ["owner_profile_id"])
    op.create_table(
        "campaign_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("profiles.id"), nullable=False),
        sa.Column("weapon", sa.String(24), nullable=False),
        sa.Column("magic", sa.String(24), nullable=False),
        sa.Column("character_level", sa.Integer(), nullable=False),
        sa.UniqueConstraint("campaign_id", "profile_id"),
    )
    op.create_index("ix_campaign_members_campaign_id", "campaign_members", ["campaign_id"])
    op.create_index("ix_campaign_members_profile_id", "campaign_members", ["profile_id"])


def downgrade() -> None:
    op.drop_table("campaign_members")
    op.drop_table("campaigns")
    op.drop_table("profile_recovery")
    op.drop_table("profiles")
