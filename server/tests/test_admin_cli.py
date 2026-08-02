import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.admin_cli import delete_profile, export_backup, restore_profile
from app.database import Base
from app.models import Campaign, CampaignMember, Profile, ProfileRecovery


class AdminCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        with self.sessions() as db:
            db.add_all([
                Profile(id="owner", display_name="Owner", token_hash="a" * 64),
                Profile(id="partner", display_name="Partner", token_hash="b" * 64),
            ])
            db.add(ProfileRecovery(profile_id="owner", recovery_hash="c" * 64))
            db.add(Campaign(
                id="campaign", invite_code="ABC123", owner_profile_id="owner",
                seed=7, campaign_length="expedition", game_mode="multiplayer",
            ))
            db.add_all([
                CampaignMember(
                    id="owner-member", campaign_id="campaign", profile_id="owner",
                    weapon="longsword", magic="rune",
                ),
                CampaignMember(
                    id="partner-member", campaign_id="campaign", profile_id="partner",
                    weapon="bow", magic="ember",
                ),
            ])
            db.commit()

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_backup_is_private_and_owner_restore_recovers_entire_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "eidpfad.json"
            with patch("app.admin_cli.SessionLocal", self.sessions):
                export_backup(backup)
                self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
                delete_profile("owner", confirm="owner")
                restore_profile(backup, "owner")

            with self.sessions() as db:
                self.assertIsNotNone(db.get(Profile, "owner"))
                self.assertIsNotNone(db.get(ProfileRecovery, "owner"))
                campaign = db.get(Campaign, "campaign")
                self.assertIsNotNone(campaign)
                self.assertEqual(campaign.owner_profile_id, "owner")
                member_count = db.scalar(
                    select(func.count()).select_from(CampaignMember).where(
                        CampaignMember.campaign_id == "campaign"
                    )
                )
                self.assertEqual(member_count, 2)

    def test_restore_refuses_owned_campaign_when_partner_profile_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "eidpfad.json"
            with patch("app.admin_cli.SessionLocal", self.sessions):
                export_backup(backup)
                delete_profile("owner", confirm="owner")
                with self.sessions() as db:
                    db.delete(db.get(Profile, "partner"))
                    db.commit()
                with self.assertRaisesRegex(SystemExit, "member profiles are missing"):
                    restore_profile(backup, "owner")

            with self.sessions() as db:
                self.assertIsNone(db.get(Profile, "owner"))
                self.assertIsNone(db.get(Campaign, "campaign"))

    def test_restore_rejects_malformed_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            backup = Path(directory) / "broken.json"
            backup.write_text(json.dumps({"format_version": 1, "profiles": []}), encoding="utf-8")
            with patch("app.admin_cli.SessionLocal", self.sessions):
                with self.assertRaisesRegex(SystemExit, "incomplete or malformed"):
                    restore_profile(backup, "owner")
