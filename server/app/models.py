from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    display_name: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    meta_progress: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ProfileRecovery(Base):
    """A separately rotatable, single-use recovery credential.

    Keeping this in its own table lets existing installations add recovery for
    profiles without changing the security properties of the bearer-token
    column. Existing profiles can enroll a recovery credential while they
    still have a valid device token.
    """

    __tablename__ = "profile_recovery"

    profile_id: Mapped[str] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    recovery_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    invite_code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    owner_profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), index=True)
    seed: Mapped[int] = mapped_column(BigInteger)
    campaign_length: Mapped[str] = mapped_column(String(20), default="fieldzug")
    world_tier: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="waiting")
    checkpoint_state: Mapped[dict] = mapped_column(JSON, default=dict)
    live_state: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CampaignMember(Base):
    __tablename__ = "campaign_members"
    __table_args__ = (UniqueConstraint("campaign_id", "profile_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profiles.id"), index=True)
    weapon: Mapped[str] = mapped_column(String(24))
    magic: Mapped[str] = mapped_column(String(24))
    character_level: Mapped[int] = mapped_column(Integer, default=1)
